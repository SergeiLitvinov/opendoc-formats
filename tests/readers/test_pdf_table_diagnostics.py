"""Table strategy failures carry source evidence, not inferred warning semantics."""

from threading import Event

import pymupdf
import pytest
from opendoc_model import ArtifactLimitError, PreservationState, document_to_json, get_integration

from opendoc_formats import ImportOptions, read_document
from opendoc_formats.errors import ResourceLimitError
from opendoc_formats.readers.pdf_geometry import extract_pdf_geometry
from opendoc_formats.readers.pdf_ocr_types import OcrPageResult
from opendoc_formats.readers.pdf_semantic import analyze_pdf_geometry
from tests.readers.test_pdf_model_ocr_diagnostics import own_pdf


def test_table_strategy_failures_keep_pages_provenance_and_json(tmp_path, monkeypatch):
    source = own_pdf(tmp_path)
    before = source.read_bytes()

    def failed(*args, **kwargs):
        raise RuntimeError('Own table-analysis failure')

    with monkeypatch.context() as context:
        context.setattr(pymupdf.Page, 'find_tables', failed)
        geometry = extract_pdf_geometry(source)
        result = read_document(source)
    assert result.success and not result.lossless and not result.assessment_complete
    records = [item for item in get_integration(result.document).preservation if item.issue.code == 'pdf.table-analysis-failed']
    assert len(records) == len(geometry.diagnostics) == 4
    assert analyze_pdf_geometry(geometry).diagnostics.preservation == tuple(geometry.diagnostics)
    for index, record in enumerate(records):
        page = index//2+1
        assert record.issue.location == f'{source}#page={page}/tables'
        assert record.issue.reason == 'pdf-table-strategy-failed' and record.state is PreservationState.OPAQUE
        assert record.provenance.page == page and record.provenance.source_path == str(source)
        assert record.issue.measurement['strategy'] == ('lines_strict', 'text')[index % 2]
        assert record.issue.measurement['legacy_warning_path'] == f'metadata.warnings[{index}]'
    assert sum(item.code == 'pdf.table-analysis-failed' for item in result.issues) == 4
    assert not any(item.code == 'pdf.warning' for item in result.issues)
    transport = tmp_path/'model.json'
    transport.write_text(document_to_json(result.document), encoding='utf-8')
    restored = read_document(transport)
    assert get_integration(restored.document).preservation == get_integration(result.document).preservation
    assert restored.issues == result.issues
    assert source.read_bytes() == before and read_document(source).success


def test_geometry_and_ocr_warning_links_do_not_shift_each_other(tmp_path, monkeypatch):
    source = own_pdf(tmp_path)

    class Engine:
        is_available = True

        def recognize_pdf_geometry(self, *args, **kwargs):
            return [OcrPageResult(warnings=['Own OCR warning'])]

    def failed(*args, **kwargs):
        raise RuntimeError('Own native analysis failure')

    monkeypatch.setattr(pymupdf.Page, 'find_tables', failed)
    result = read_document(source, options=ImportOptions(pdf_mode='structure', ocr_engine_factory=lambda **kwargs: Engine()))
    assert result.success
    assert sum(item.code == 'pdf.table-analysis-failed' for item in result.issues) == 4
    ocr = [item for item in result.issues if item.code == 'pdf.ocr-provider-warning']
    assert len(ocr) == 1 and ocr[0].measurement['legacy_warning_path'] == 'metadata.warnings[4]'
    assert not any(item.code == 'pdf.warning' for item in result.issues)


@pytest.mark.parametrize('native', [False, True])
def test_table_analysis_limit_is_not_best_effort_warning(tmp_path, monkeypatch, native):
    source = own_pdf(tmp_path)
    original = source.read_bytes()
    error = (ResourceLimitError('Own table work limit') if native else
             ArtifactLimitError('Own table work limit', path='pages[0].tables', quota='table work', maximum=2))
    calls = []

    def limited(*args, **kwargs):
        calls.append(True)
        raise error

    with monkeypatch.context() as context:
        context.setattr(pymupdf.Page, 'find_tables', limited)
        with pytest.raises(type(error)) as captured:
            extract_pdf_geometry(source)
        assert captured.value is error and calls == [True]
        calls.clear()
        if native:
            with pytest.raises(ResourceLimitError):
                read_document(source)
        else:
            result = read_document(source)
            assert result.document is None and result.issues[0].code == 'import.document-limit'
            assert 'pages[0].tables' in result.issues[0].location
        assert calls == [True]
    assert source.read_bytes() == original and read_document(source).success


def test_cancel_after_backend_table_analysis_precedes_native_traversal(tmp_path, monkeypatch):
    source = own_pdf(tmp_path)
    original = source.read_bytes()
    stop, calls = Event(), []

    class Finder:
        @property
        def tables(self):
            pytest.fail('Native tables were traversed after cancellation')

    def finished(*args, **kwargs):
        calls.append(True)
        stop.set()
        return Finder()

    with monkeypatch.context() as context:
        context.setattr(pymupdf.Page, 'find_tables', finished)
        result = read_document(source, options=ImportOptions(cancelled=stop.is_set))
    assert calls == [True] and result.document is None and result.issues[0].code == 'import.cancelled'
    assert source.read_bytes() == original and read_document(source).success
