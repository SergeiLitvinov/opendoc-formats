"""Own PDF originals prove cancellation inside the private Word projection."""

import importlib
from threading import Event

import pymupdf
import pytest
from opendoc_model import Resource, ResourceKind, document_to_json

from opendoc_formats import ExportOptions, ImportOptions, read_document, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.support.cancellation import checkpoint
from opendoc_formats.writers.docx_writer import write_docx_model
from opendoc_formats.writers.pdf_docx_model import prepare_pdf_docx
from opendoc_formats.writers.pdf_to_docx import PdfModelConverter
from tests.writers.test_pdf_docx_complex import merged_table
from tests.writers.test_pdf_docx_graphics import curved_clip, grouped_form, image_form
from tests.writers.test_pdf_model_docx import columns


@pytest.fixture
def pdf_source(request, tmp_path):
    own = tmp_path / 'single.pdf'
    profile = request.param
    if profile == 'text':
        columns(own)
    elif profile == 'table':
        merged_table(own)
    elif profile == 'image':
        image_form(own, repeated=True)
    elif profile == 'clip':
        curved_clip(own, vector=True)
    elif profile == 'commands':
        with pymupdf.open() as native:
            page = native.new_page(width=400, height=300)
            shape = page.new_shape()
            shape.draw_line((40, 40), (220, 80))
            shape.draw_line((220, 80), (180, 190))
            shape.finish(color=(.2, .3, .7), width=.75)
            shape.commit()
            native.save(own)
    else:
        grouped_form(own, opacity=.5 if profile == 'opacity' else 1, isolated=profile == 'opacity')
    path = tmp_path / 'own.pdf'
    with pymupdf.open(own) as native:
        native.fullcopy_page(0)
        native.save(path)
    return path


@pytest.mark.parametrize('pdf_source', ['text', 'table', 'image', 'clip', 'group', 'opacity', 'commands'], indirect=True)
def test_inactive_callback_preserves_complete_private_view(pdf_source):
    model = read_document(pdf_source).document
    original, source = document_to_json(model), pdf_source.read_bytes()
    expected = prepare_pdf_docx(model)
    polls = []

    def inactive():
        polls.append(True)
        return False

    actual = prepare_pdf_docx(model, cancelled=inactive)
    assert len(polls) > 20
    assert document_to_json(actual) == document_to_json(expected)
    assert document_to_json(model) == original and pdf_source.read_bytes() == source


@pytest.mark.parametrize(('pdf_source', 'module', 'name'), [
    ('text', 'pdf_docx_model', '_prepare_line_geometry'),
    ('text', 'pdf_docx_model', '_prepare_baselines'),
    ('table', 'pdf_docx_model', '_prepare_table'),
    ('table', 'pdf_docx_borders', '_covered'),
    ('image', 'pdf_docx_images', 'prepare_image_transform'),
    ('clip', 'pdf_docx_graphics', '_word_clip_commands'),
    ('clip', 'pdf_docx_graphics', 'word_svg_bytes'),
    ('group', 'pdf_native_groups', 'preview_svg'),
    ('opacity', 'pdf_group_compositor', '_over'),
], indirect=['pdf_source'])
@pytest.mark.parametrize('route', ['prepare', 'writer', 'registry'])
def test_stop_between_projected_objects_preserves_input_and_target(pdf_source, module, name, route, tmp_path, monkeypatch):
    model = read_document(pdf_source).document
    if module == 'pdf_native_groups':
        from opendoc_model import get_vector_scene, set_scene_clip

        from opendoc_formats.readers.pdf_scopes import attach_pdf_scopes

        attach_pdf_scopes(model, limits=None, include_neutral=True)
        # Exercise the accepted edited native profile; source Form clips are not silently discarded.
        for section in model.sections:
            scene = get_vector_scene(model, section.properties['pdf_scene_id'])
            for clip in scene.clips:
                set_scene_clip(model, scene.id, clip.id, None)
    original, source = document_to_json(model), pdf_source.read_bytes()
    target = tmp_path / 'kept.docx'
    target.write_bytes(b'own previous destination')
    owner = importlib.import_module('opendoc_formats.writers.' + module)
    native = getattr(owner, name)
    stop, completed = Event(), []

    def first(*args, **kwargs):
        assert not completed, 'Projection processed another object after cancellation'
        result = native(*args, **kwargs)
        completed.append(True)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(owner, name, first)
        if route == 'registry':
            report = write_document(model, target, options=ExportOptions(cancelled=stop.is_set))
            assert not report.success and any(issue.feature == 'export.cancelled' for issue in report.issues)
        else:
            with pytest.raises(OperationCancelledError):
                if route == 'prepare':
                    prepare_pdf_docx(model, cancelled=stop.is_set)
                else:
                    write_docx_model(model, target, cancelled=stop.is_set)
    assert completed == [True]
    assert document_to_json(model) == original and pdf_source.read_bytes() == source
    assert target.read_bytes() == b'own previous destination' and not list(tmp_path.glob('.*.partial'))
    checkpoint()
    assert prepare_pdf_docx(model).source_format == 'pdf'


@pytest.mark.parametrize('pdf_source', ['text'], indirect=True)
def test_font_cancellation_is_not_swallowed_as_font_preflight_failure(pdf_source, monkeypatch):
    from opendoc_formats.fonts import resource_fonts

    model = read_document(pdf_source).document
    model.resources['own-font'] = Resource('own-font', ResourceKind.FONT, 'font/ttf', data=b'own inert font program')
    original = document_to_json(model)

    def cancelled(data):
        raise OperationCancelledError('Own provider cancellation')

    monkeypatch.setattr(resource_fonts, 'font_program_names', cancelled)
    with pytest.raises(OperationCancelledError, match='Own provider'):
        prepare_pdf_docx(model)
    assert document_to_json(model) == original


@pytest.mark.parametrize('pdf_source', ['text'], indirect=True)
def test_converter_inherits_import_signal_when_export_options_are_omitted(pdf_source, tmp_path, monkeypatch):
    from opendoc_formats.writers import pdf_docx_model

    target = tmp_path / 'kept.docx'
    target.write_bytes(b'previous')
    stop = Event()
    native = pdf_docx_model._prepare_line_geometry

    def finish(paragraph):
        native(paragraph)
        stop.set()

    monkeypatch.setattr(pdf_docx_model, '_prepare_line_geometry', finish)
    report = PdfModelConverter(import_options=ImportOptions(cancelled=stop.is_set)).convert(pdf_source, target)
    assert not report.success and any(issue.feature == 'export.cancelled' for issue in report.issues)
    assert target.read_bytes() == b'previous'


@pytest.mark.parametrize('pdf_source', ['text'], indirect=True)
def test_direct_prepare_validates_callback_and_early_signal(pdf_source):
    model = read_document(pdf_source).document
    with pytest.raises(ValueError, match='callable'):
        prepare_pdf_docx(model, cancelled=True)
    with pytest.raises(OperationCancelledError):
        prepare_pdf_docx(model, cancelled=lambda: True)
    checkpoint()


@pytest.mark.parametrize('pdf_source', ['text'], indirect=True)
@pytest.mark.parametrize('public', [False, True])
def test_late_cancel_after_prepared_model_validation_discards_view(pdf_source, tmp_path, monkeypatch, public):
    from opendoc_model import DocumentModel

    model = read_document(pdf_source).document
    original = document_to_json(model)
    target = tmp_path / 'late.docx'
    target.write_bytes(b'previous')
    stop = Event()
    validate = DocumentModel.validate

    def finish(document, *args, **kwargs):
        result = validate(document, *args, **kwargs)
        if document.metadata.get('pdf_docx_layout'):
            stop.set()
        return result

    monkeypatch.setattr(DocumentModel, 'validate', finish)
    if public:
        report = write_document(model, target, options=ExportOptions(cancelled=stop.is_set))
        assert not report.success and any(issue.feature == 'export.cancelled' for issue in report.issues)
    else:
        with pytest.raises(OperationCancelledError):
            prepare_pdf_docx(model, cancelled=stop.is_set)
    assert stop.is_set() and target.read_bytes() == b'previous' and document_to_json(model) == original


@pytest.mark.parametrize('pdf_source', ['commands'], indirect=True)
def test_vector_command_cancel_keeps_error_type_and_closes_native_document(pdf_source, monkeypatch):
    model = read_document(pdf_source).document
    original = document_to_json(model)
    stop, drawn, documents = Event(), [], []
    draw = pymupdf.Shape.draw_line
    open_document = pymupdf.open

    def first(shape, *args, **kwargs):
        assert not drawn
        result = draw(shape, *args, **kwargs)
        drawn.append(True)
        stop.set()
        return result

    def track(*args, **kwargs):
        document = open_document(*args, **kwargs)
        documents.append(document)
        return document

    with monkeypatch.context() as context:
        context.setattr(pymupdf.Shape, 'draw_line', first)
        context.setattr(pymupdf, 'open', track)
        with pytest.raises(OperationCancelledError):
            prepare_pdf_docx(model, cancelled=stop.is_set)
    assert drawn == [True] and documents and all(document.is_closed for document in documents)
    assert document_to_json(model) == original
    assert prepare_pdf_docx(model).source_format == 'pdf'
