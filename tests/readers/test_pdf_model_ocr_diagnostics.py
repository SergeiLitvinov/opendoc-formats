"""OCR provider warnings survive rich PDF import and the public JSON transport."""

import pytest
from opendoc_model import PreservationState, document_to_json, get_integration

from opendoc_formats import ImportOptions, read_document
from opendoc_formats.readers.pdf_ocr_merge import read_pdf_scenario
from opendoc_formats.readers.pdf_ocr_types import OcrBlockGeometry, OcrPageResult


def own_pdf(tmp_path):
    pdf = pytest.importorskip('pymupdf')
    path = tmp_path / 'own.pdf'
    with pdf.open() as document:
        for text in ('Own first page', 'Own second page'):
            document.new_page().insert_text((72, 72), text)
        document.save(path)
    return path


@pytest.mark.parametrize('mode', ['structure', 'scan'])
def test_page_warnings_with_and_without_blocks_reach_public_report_and_json(tmp_path, mode):
    path = own_pdf(tmp_path)
    source_bytes = path.read_bytes()

    class Engine:
        is_available = True

        def recognize_pdf_geometry(self, *args, **kwargs):
            return [OcrPageResult(blocks=[OcrBlockGeometry('Own OCR', (30, 150, 200, 180), 0.7)],
                                  warnings=['Own confidence warning']),
                    OcrPageResult(warnings=['Own empty-page warning'])]

    result = read_document(path, options=ImportOptions(pdf_mode=mode, ocr_engine_factory=lambda **kwargs: Engine()))
    assert result.success and not result.assessment_complete and not result.lossless
    for warning in ('Own confidence warning', 'Own empty-page warning'):
        assert warning in result.document.metadata['warnings']
        assert sum(issue.message == warning for issue in result.issues) == 1
    ledger = get_integration(result.document)
    records = [record for record in ledger.preservation if record.issue.code == 'pdf.ocr-provider-warning']
    assert len(records) == 2
    for page, record in enumerate(records, 1):
        assert record.state is PreservationState.OPAQUE
        assert record.issue.location == f'{path}#page={page}/ocr'
        assert record.issue.reason == 'ocr-provider-warning-unassessed'
        assert record.provenance.page == page and record.provenance.source_path == str(path)
        assert record.issue.measurement['pdf_mode'] == mode
    assert path.read_bytes() == source_bytes
    transport = tmp_path / 'transport.json'
    transport.write_text(document_to_json(result.document), encoding='utf-8')
    restored = read_document(transport)
    assert restored.success
    assert all(any(i.message == warning for i in restored.issues)
               for warning in ('Own confidence warning', 'Own empty-page warning'))
    assert get_integration(restored.document).preservation == ledger.preservation
    assert [issue.code for issue in restored.issues] == [issue.code for issue in result.issues]


@pytest.mark.parametrize('mode', ['structure', 'scan'])
@pytest.mark.parametrize('provider', ['absent', 'unavailable', 'late-unavailable', 'empty', 'failed'])
def test_requested_ocr_failure_is_visible_in_both_public_routes(tmp_path, mode, provider):
    path = own_pdf(tmp_path)

    class Engine:
        is_available = provider != 'unavailable'

        def recognize_pdf_geometry(self, *args, **kwargs):
            if provider == 'late-unavailable':
                from opendoc_formats.errors import BackendUnavailableError

                raise BackendUnavailableError('Own backend missing')
            if provider == 'failed':
                raise RuntimeError('Own backend failure')
            return []

    expected = ('OCR backend unavailable: Own backend missing' if provider == 'late-unavailable' else
                'OCR engine requested but none available' if provider in {'absent', 'unavailable'} else
                'OCR engine returned no page results' if provider == 'empty' else 'OCR failed: Own backend failure')
    engine = None if provider == 'absent' else Engine()
    text = read_pdf_scenario(str(path), mode=mode, ocr_engine=engine)
    assert expected in text.warnings
    result = read_document(path, options=ImportOptions(pdf_mode=mode, ocr_engine_factory=lambda **kwargs: engine))
    assert result.success and any(issue.message == expected for issue in result.issues)
    assert not result.lossless
    code = ('pdf.ocr-unavailable' if provider in {'absent', 'unavailable', 'late-unavailable'} else
            'pdf.ocr-empty' if provider == 'empty' else 'pdf.ocr-failed')
    record = next(item for item in get_integration(result.document).preservation if item.issue.code == code)
    assert record.state is PreservationState.OPAQUE and record.issue.reason
    assert record.issue.location == f'{path}#ocr' and record.provenance.page is None
    assert sum(issue.message == expected for issue in result.issues) == 1


def test_fast_mode_neither_calls_ocr_nor_reports_a_missing_engine(tmp_path):
    path = own_pdf(tmp_path)

    def forbidden(**kwargs):
        raise AssertionError('Fast mode initialized OCR')

    result = read_document(path, options=ImportOptions(pdf_mode='fast', ocr_engine_factory=forbidden))
    assert result.success
    assert not any('OCR' in issue.message for issue in result.issues)
    assert not any('OCR' in warning for warning in read_pdf_scenario(str(path), mode='fast').warnings)


def test_repeated_warning_text_keeps_distinct_page_occurrences(tmp_path):
    path = own_pdf(tmp_path)

    class Engine:
        is_available = True

        def recognize_pdf_geometry(self, *args, **kwargs):
            return [OcrPageResult(warnings=['Own repeated warning']) for _ in range(3)]

    result = read_document(path, options=ImportOptions(pdf_mode='structure', ocr_engine_factory=lambda **kwargs: Engine()))
    issues = [item for item in result.issues if item.code == 'pdf.ocr-provider-warning']
    assert len(issues) == 3
    assert [item.location for item in issues] == [f'{path}#page=1/ocr', f'{path}#page=2/ocr', f'{path}#ocr']
    assert [item.measurement['ocr_page_index'] for item in issues] == [0, 1, 2]


def test_cancel_inside_ocr_diagnostics_discards_partial_model(tmp_path, monkeypatch):
    from threading import Event

    from opendoc_formats.readers import pdf_diagnostics

    path = own_pdf(tmp_path)
    source = path.read_bytes()
    stop, calls = Event(), []
    native = pdf_diagnostics.PreservationRecord

    class Engine:
        is_available = True

        def recognize_pdf_geometry(self, *args, **kwargs):
            return [OcrPageResult(warnings=['Own warning one', 'Own warning two'])]

    def first(*args, **kwargs):
        assert not calls, 'OCR diagnostics continued after cancellation'
        result = native(*args, **kwargs)
        calls.append(True)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(pdf_diagnostics, 'PreservationRecord', first)
        result = read_document(path, options=ImportOptions(
            pdf_mode='structure', ocr_engine_factory=lambda **kwargs: Engine(), cancelled=stop.is_set,
        ))
    assert calls == [True] and result.document is None
    assert any(issue.code == 'import.cancelled' for issue in result.issues)
    assert path.read_bytes() == source and read_document(path).success


@pytest.mark.parametrize('mode', ['structure', 'scan'])
@pytest.mark.parametrize('native', [False, True])
def test_ocr_limits_are_never_converted_to_best_effort_warnings(tmp_path, mode, native):
    from opendoc_model import ArtifactLimitError

    from opendoc_formats.errors import ResourceLimitError
    from opendoc_formats.readers.pdf_model import read_pdf_model

    path = own_pdf(tmp_path)
    source = path.read_bytes()
    error = (ResourceLimitError('Own OCR pixel limit') if native else
             ArtifactLimitError('Own OCR pixel limit', path='ocr.pages[0]', quota='ocr pixels', maximum=4))

    class Engine:
        is_available = True

        def recognize_pdf_geometry(self, *args, **kwargs):
            raise error

    with pytest.raises(type(error)) as captured:
        read_pdf_scenario(str(path), mode=mode, ocr_engine=Engine())
    assert captured.value is error
    with pytest.raises(type(error)) as captured:
        read_pdf_model(path=path, mode=mode, ocr_engine_factory=lambda **kwargs: Engine())
    assert captured.value is error
    if native:
        with pytest.raises(ResourceLimitError):
            read_document(path, options=ImportOptions(pdf_mode=mode, ocr_engine_factory=lambda **kwargs: Engine()))
    else:
        result = read_document(path, options=ImportOptions(pdf_mode=mode, ocr_engine_factory=lambda **kwargs: Engine()))
        assert result.document is None and not result.success
        assert result.issues[0].code == 'import.document-limit'
        assert 'ocr.pages[0]' in result.issues[0].location
        assert not any('OCR failed' in item.message for item in result.issues)
    assert path.read_bytes() == source and read_document(path).success
