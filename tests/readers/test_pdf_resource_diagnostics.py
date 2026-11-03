"""Known missing pixels, unassessed drawings and unresolved cell layout stay distinct."""

from dataclasses import replace

import pymupdf
import pytest
from opendoc_model import (
    ArtifactLimitError,
    PreservationState,
    TableCell,
    document_to_json,
    get_integration,
    walk_model,
)

from opendoc_formats import ImportOptions, read_document, write_document
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from opendoc_formats.readers import pdf_geometry, pdf_images


def own_pdf(tmp_path):
    path = tmp_path/'own.pdf'
    with pymupdf.open() as pdf:
        pixels = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
        pixels.clear_with(80)
        for _ in range(2):
            page = pdf.new_page(width=400, height=500)
            xref = page.insert_image(pymupdf.Rect(20, 20, 40, 40), pixmap=pixels)
            page.insert_image(pymupdf.Rect(50, 20, 70, 40), xref=xref)
            page.draw_rect(pymupdf.Rect(80, 60, 200, 120), color=(0, 0, 0), width=1)
        pdf.save(path)
    return path


def roundtrip(result, tmp_path):
    path = tmp_path/'model.json'
    path.write_text(document_to_json(result.document), encoding='utf-8')
    restored = read_document(path)
    assert restored.issues == result.issues
    assert get_integration(restored.document).preservation == get_integration(result.document).preservation


@pytest.mark.parametrize('mode', ['fast', 'structure'])
def test_missing_repeated_image_bytes_are_located_lost_occurrences(tmp_path, monkeypatch, mode):
    source = own_pdf(tmp_path)
    original = source.read_bytes()
    native = pymupdf.Page.get_text

    def missing(page, *args, **kwargs):
        result = native(page, *args, **kwargs)
        if args and args[0] == 'dict' and kwargs.get('flags') == pymupdf.TEXT_PRESERVE_IMAGES:
            for block in result.get('blocks', []):
                if block.get('type') == 1:
                    block['image'] = b''
        return result

    with monkeypatch.context() as context:
        context.setattr(pymupdf.Page, 'get_text', missing)
        records = []
        images, warnings = pdf_images.extract_pdf_images(source, diagnostics=records)
        assert not images and len(warnings) == len(records) == 4
        result = read_document(source, options=ImportOptions(pdf_mode=mode))
    assert result.success and not result.lossless
    records = [r for r in get_integration(result.document).preservation if r.issue.code == 'pdf.image-bytes-missing']
    assert len(records) == 4
    for index, record in enumerate(records):
        assert record.state is PreservationState.LOST and record.provenance.page == index//2+1
        assert record.issue.reason == 'pdf-image-bytes-missing'
        assert record.issue.location.startswith(f'{source}#page={index//2+1}/images[')
        offset = 1 if mode == 'structure' else 0
        assert record.issue.measurement['legacy_warning_path'] == f'metadata.warnings[{offset+index}]'
    assert records[0].issue.measurement['xref'] == records[1].issue.measurement['xref']
    assert records[0].issue.location != records[1].issue.location
    assert not any(i.code == 'pdf.warning' for i in result.issues)
    roundtrip(result, tmp_path)
    destination = tmp_path/'previous.docx'
    destination.write_bytes(b'previous complete output')
    report = write_document(result.document, destination)
    assert not report.success and any(issue.feature == 'pdf-docx.source-unknown' for issue in report.issues)
    assert destination.read_bytes() == b'previous complete output'
    assert source.read_bytes() == original and read_document(source).success


def test_failed_vector_extraction_is_unassessed_not_a_claim_of_missing_vectors(tmp_path, monkeypatch):
    source = own_pdf(tmp_path)
    original = source.read_bytes()
    native = pdf_images.extract_pdf_vector_drawings

    def failed(*args, **kwargs):
        raise RuntimeError('Own vector backend failure')

    def during_vectors(*args, **kwargs):
        with monkeypatch.context() as context:
            context.setattr(pymupdf.Page, 'get_drawings', failed)
            return native(*args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(pdf_images, 'extract_pdf_vector_drawings', during_vectors)
        result = read_document(source)
    records = [r for r in get_integration(result.document).preservation if r.issue.code == 'pdf.vector-extraction-failed']
    assert result.success and len(records) == 2 and not result.lossless
    for page, record in enumerate(records, 1):
        assert record.state is PreservationState.OPAQUE and record.issue.reason == 'pdf-vector-backend-failed'
        assert record.issue.location == f'{source}#page={page}/drawings' and record.provenance.page == page
    assert not any(i.code == 'pdf.warning' for i in result.issues)
    roundtrip(result, tmp_path)
    assert source.read_bytes() == original and read_document(source).success


@pytest.mark.parametrize('kind', ['model-limit', 'native-limit', 'cancel'])
def test_vector_limits_and_cancellation_are_not_warnings(tmp_path, monkeypatch, kind):
    source = own_pdf(tmp_path)
    original = source.read_bytes()
    error = (ArtifactLimitError('Own vector limit', path='pages[0].drawings', quota='vector work', maximum=2)
             if kind == 'model-limit' else ResourceLimitError('Own vector work limit') if kind == 'native-limit'
             else OperationCancelledError('Own vector cancellation'))
    native = pdf_images.extract_pdf_vector_drawings
    calls = []

    def failed(*args, **kwargs):
        calls.append(True)
        raise error

    def during_vectors(*args, **kwargs):
        with monkeypatch.context() as context:
            context.setattr(pymupdf.Page, 'get_drawings', failed)
            return native(*args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(pymupdf.Page, 'get_drawings', failed)
        with pytest.raises(type(error)) as captured:
            native(source)
        assert captured.value is error and calls == [True]
    calls.clear()
    with monkeypatch.context() as context:
        context.setattr(pdf_images, 'extract_pdf_vector_drawings', during_vectors)
        if kind == 'native-limit':
            with pytest.raises(ResourceLimitError):
                read_document(source)
        else:
            result = read_document(source)
            assert result.document is None
            assert result.issues[0].code == ('import.document-limit' if kind == 'model-limit' else 'import.cancelled')
        assert calls == [True]
    assert source.read_bytes() == original and read_document(source).success


def test_unresolved_cell_layout_keeps_text_and_canonical_location(tmp_path, monkeypatch):
    source = own_pdf(tmp_path)
    original = source.read_bytes()
    native = pdf_geometry.extract_pdf_geometry

    def unresolved(*args, **kwargs):
        geometry = native(*args, **kwargs)
        cells = tuple(pdf_geometry.PdfTableCellGeometry(row, column, f'Cell {row}:{column}')
                      for row in range(2) for column in range(2))
        table = pdf_geometry.PdfTableGeometry((('Cell 0:0', 'Cell 0:1'), ('Cell 1:0', 'Cell 1:1')),
                                              cells, (70, 150, 270, 230), 0)
        geometry.pages[0] = replace(geometry.pages[0], tables=(table,))
        return geometry

    with monkeypatch.context() as context:
        context.setattr(pdf_geometry, 'extract_pdf_geometry', unresolved)
        result = read_document(source)
    assert result.success and not result.lossless
    cells = [ref for ref in walk_model(result.document) if isinstance(ref.node, TableCell)]
    records = [r for r in get_integration(result.document).preservation if r.issue.code == 'pdf.cell-layout-unresolved']
    assert len(cells) == len(records) == 4
    assert [r.issue.location for r in records] == [ref.path for ref in cells]
    for record, ref in zip(records, cells):
        assert record.state is PreservationState.OPAQUE and record.provenance.page == 1
        assert record.issue.reason == 'pdf-cell-layout-unmeasured'
        assert ref.node.blocks[0].plain_text.startswith('Cell ')
    assert not any(i.code == 'pdf.warning' for i in result.issues)
    roundtrip(result, tmp_path)
    assert source.read_bytes() == original and read_document(source).success


def test_cell_reconstruction_stops_before_next_unresolved_cell(tmp_path, monkeypatch):
    from opendoc_formats.readers import pdf_table_model

    source = own_pdf(tmp_path)
    original = source.read_bytes()
    page = pdf_geometry.PdfPageGeometry(1, 400, 500)
    from threading import Event

    stop, calls = Event(), []
    native = pdf_table_model.append_pdf_warning

    def first(*args, **kwargs):
        assert not calls, 'Another cell was reconstructed after cancellation'
        native(*args, **kwargs)
        calls.append(True)
        stop.set()

    monkeypatch.setattr(pdf_table_model, 'append_pdf_warning', first)
    with pytest.raises(OperationCancelledError):
        pdf_table_model.pdf_table_rows(page, {'rows': [['Own cell one', 'Own cell two']]},
                                       lambda *args: pytest.fail('Unexpected run builder'), [], cancelled=stop.is_set)
    assert calls == [True] and source.read_bytes() == original


def test_warning_binding_cancellation_does_not_change_source_records(tmp_path):
    from copy import deepcopy

    from opendoc_model import DiagnosticIssue, IssueSeverity, Provenance

    from opendoc_formats.readers.pdf_diagnostics import append_pdf_warning, bind_warning_records

    source = own_pdf(tmp_path)
    original = source.read_bytes()
    warnings, records, polls = [], [], []
    for index in range(3):
        append_pdf_warning(warnings, records, DiagnosticIssue(
            'own.pdf-warning', IssueSeverity.LOSS, f'Own warning {index}', f'{source}#page=1', reason='own-unassessed',
        ), Provenance('pdf', str(source), page=1))
    before = deepcopy(records)

    def cancelled():
        polls.append(True)
        return len(polls) == 2

    with pytest.raises(OperationCancelledError):
        bind_warning_records(records, 4, cancelled=cancelled)
    assert polls == [True, True] and records == before and source.read_bytes() == original
