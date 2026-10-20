"""A cancelled PDF import publishes no partial Model and releases native documents."""

from importlib import import_module
from threading import Event

import pytest
from opendoc_model import DocumentModel, document_to_json

from opendoc_formats import AdapterRegistry, AdapterSpec, ImportOptions, read_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.pdf_model import read_pdf_model
from opendoc_formats.readers.pdf_ocr_merge import read_pdf_scenario


def own_pdf(tmp_path):
    pdf = pytest.importorskip('pymupdf')
    path = tmp_path / 'own.pdf'
    with pdf.open() as document:
        for number in range(3):
            document.new_page().insert_text((72, 72), f'Own page {number}')
        document.save(path)
    return path


def test_native_text_cancellation_stops_before_table_analysis_and_next_page(tmp_path, monkeypatch):
    import pymupdf

    path = own_pdf(tmp_path)
    original = path.read_bytes()
    stop, visited = Event(), []
    native_text = pymupdf.Page.get_text

    def extract(page, *args, **kwargs):
        visited.append(page.number)
        result = native_text(page, *args, **kwargs)
        stop.set()
        return result

    def forbidden(*args, **kwargs):
        raise AssertionError('Cancelled geometry continued to table extraction')

    with monkeypatch.context() as context:
        context.setattr(pymupdf.Page, 'get_text', extract)
        context.setattr('opendoc_formats.readers.pdf_geometry._find_tables', forbidden)
        result = read_document(path, options=ImportOptions(cancelled=stop.is_set))
    assert not result.success and result.document is None and result.issues[0].code == 'import.cancelled'
    assert visited == [0] and path.read_bytes() == original
    # Reopen and retry after cancellation, without stale backend objects or partial state.
    assert read_document(path).success


@pytest.mark.parametrize('module,name', [
    ('pdf_geometry', 'extract_pdf_geometry'), ('pdf_images', 'extract_pdf_images'),
    ('pdf_images', 'extract_pdf_vector_drawings'), ('pdf_images', 'enrich_geometry_with_images'),
    ('pdf_fonts', 'extract_pdf_fonts'), ('pdf_paint', 'attach_text_paint'),
    ('pdf_interactive', 'attach_pdf_interactions'), ('pdf_scopes', 'attach_pdf_scopes'),
])
def test_signal_reaches_each_native_import_stage(tmp_path, monkeypatch, module, name):
    path = own_pdf(tmp_path)
    original = path.read_bytes()
    stop, entered = Event(), []
    backend = import_module('opendoc_formats.readers.'+module)
    function = getattr(backend, name)

    def cancel(*args, **kwargs):
        entered.append(True)
        assert kwargs.get('cancelled') is not None
        stop.set()
        return function(*args, **kwargs)

    monkeypatch.setattr(backend, name, cancel)
    result = read_document(path, options=ImportOptions(cancelled=stop.is_set))
    assert entered == [True] and not result.success and result.document is None
    assert result.issues[0].code == 'import.cancelled' and path.read_bytes() == original


@pytest.mark.parametrize('provider_raises', [False, True])
def test_ocr_cancellation_is_not_downgraded_to_a_warning(tmp_path, monkeypatch, provider_raises):
    path = own_pdf(tmp_path)
    stop = Event()

    class Engine:
        is_available = True

        def recognize_pdf_geometry(self, *args, **kwargs):
            if provider_raises:
                raise OperationCancelledError('Own OCR cancelled')
            stop.set()
            return []

    def forbidden(*args, **kwargs):
        raise AssertionError('Cancelled OCR continued to image extraction')

    monkeypatch.setattr('opendoc_formats.readers.pdf_images.extract_pdf_images', forbidden)
    result = read_document(path, options=ImportOptions(
        pdf_mode='structure', ocr_engine_factory=lambda **kwargs: Engine(), cancelled=stop.is_set,
    ))
    assert not result.success and result.document is None and result.issues[0].code == 'import.cancelled'
    stop.clear()
    with pytest.raises(OperationCancelledError):
        read_pdf_scenario(str(path), mode='structure', ocr_engine=Engine(), cancelled=stop.is_set)


def test_direct_reader_cancel_and_invalid_callback_are_explicit(tmp_path):
    path = own_pdf(tmp_path)
    with pytest.raises(OperationCancelledError):
        read_pdf_model(path=path, cancelled=lambda: True)
    with pytest.raises(ValueError, match='callable'):
        read_pdf_model(path=path, cancelled=True)


def test_cancel_between_table_strategies_does_not_start_the_second_backend_call(tmp_path, monkeypatch):
    import pymupdf

    path = own_pdf(tmp_path)
    stop, strategies = Event(), []
    find_tables = pymupdf.Page.find_tables

    def find(page, *args, **kwargs):
        strategies.append(kwargs.get('strategy'))
        result = find_tables(page, *args, **kwargs)
        stop.set()
        return result

    monkeypatch.setattr(pymupdf.Page, 'find_tables', find)
    result = read_document(path, options=ImportOptions(cancelled=stop.is_set))
    assert not result.success and result.issues[0].code == 'import.cancelled'
    assert strategies == ['lines_strict']


def test_cancel_during_disposable_interaction_removal_preserves_source_annotations(tmp_path, monkeypatch):
    import pymupdf

    path = own_pdf(tmp_path)
    with pymupdf.open(path) as document:
        document[0].add_text_annot((30, 30), 'Own first note')
        document[0].add_text_annot((60, 60), 'Own second note')
        document.saveIncr()
    original = path.read_bytes()
    stop, deleted = Event(), []
    delete = pymupdf.Page.delete_annot

    def remove(page, annotation):
        deleted.append(annotation.xref)
        result = delete(page, annotation)
        stop.set()
        return result

    monkeypatch.setattr(pymupdf.Page, 'delete_annot', remove)
    result = read_document(path, options=ImportOptions(cancelled=stop.is_set))
    assert not result.success and result.document is None and result.issues[0].code == 'import.cancelled'
    assert len(deleted) == 1 and path.read_bytes() == original
    with pymupdf.open(path) as document:
        assert len(list(document[0].annots())) == 2


def test_registry_discards_late_cancellation_during_model_validation(tmp_path, monkeypatch):
    path = tmp_path / 'own.native'
    path.write_text('Own', encoding='utf-8')
    model, stop = DocumentModel(), Event()

    def validate(*, limits=None):
        stop.set()
        return []

    monkeypatch.setattr(model, 'validate', validate)
    registry = AdapterRegistry()
    registry.register(AdapterSpec('own', ('.native',), lambda path, options: model))
    result = registry.read(path, options=ImportOptions(cancelled=stop.is_set))
    assert not result.success and result.document is None and result.issues[0].code == 'import.cancelled'


def test_inactive_callback_keeps_the_complete_model_identical(tmp_path):
    import pymupdf

    path = own_pdf(tmp_path)
    with pymupdf.open(path) as document:
        page = document[0]
        page.draw_rect((30, 110, 100, 150), color=(0, 0, 1), fill=(1, 0, 0))
        page.add_text_annot((150, 150), 'Own note')
        pixel = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 2, 2), False)
        pixel.clear_with(128)
        page.insert_image((30, 200, 80, 250), stream=pixel.tobytes('png'))
        document.saveIncr()
    original, checks = path.read_bytes(), []

    def keep_running():
        checks.append(True)
        return False

    ordinary = read_document(path)
    monitored = read_document(path, options=ImportOptions(cancelled=keep_running))
    assert ordinary.success and monitored.success and len(checks) > 30
    assert document_to_json(monitored.document) == document_to_json(ordinary.document)
    assert path.read_bytes() == original


def test_direct_reader_cancels_at_final_history_stage_without_returning_model(tmp_path, monkeypatch):
    path, stop = own_pdf(tmp_path), Event()
    history = import_module('opendoc_formats.support.pdf_mapping_history')
    original = history.attach_history_map

    def finish(*args, **kwargs):
        original(*args, **kwargs)
        stop.set()

    monkeypatch.setattr(history, 'attach_history_map', finish)
    with pytest.raises(OperationCancelledError, match='completion'):
        read_pdf_model(path=path, cancelled=stop.is_set)


def test_native_cancellation_exception_is_not_best_effort_table_warning(tmp_path, monkeypatch):
    import pymupdf

    path = own_pdf(tmp_path)

    def cancelled(*args, **kwargs):
        raise OperationCancelledError('Own native table cancelled')

    monkeypatch.setattr(pymupdf.Page, 'find_tables', cancelled)
    result = read_document(path)
    assert not result.success and result.document is None and result.issues[0].code == 'import.cancelled'
