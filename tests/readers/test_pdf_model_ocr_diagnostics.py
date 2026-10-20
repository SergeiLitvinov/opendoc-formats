"""OCR provider warnings survive rich PDF import and the public JSON transport."""

import pytest
from opendoc_model import document_to_json

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
        assert any(issue.message == warning for issue in result.issues)
    assert path.read_bytes() == source_bytes
    transport = tmp_path / 'transport.json'
    transport.write_text(document_to_json(result.document), encoding='utf-8')
    restored = read_document(transport)
    assert restored.success
    assert all(any(i.message == warning for i in restored.issues)
               for warning in ('Own confidence warning', 'Own empty-page warning'))


@pytest.mark.parametrize('mode', ['structure', 'scan'])
@pytest.mark.parametrize('provider', ['absent', 'unavailable', 'empty', 'failed'])
def test_requested_ocr_failure_is_visible_in_both_public_routes(tmp_path, mode, provider):
    path = own_pdf(tmp_path)

    class Engine:
        is_available = provider != 'unavailable'

        def recognize_pdf_geometry(self, *args, **kwargs):
            if provider == 'failed':
                raise RuntimeError('Own backend failure')
            return []

    expected = ('OCR engine requested but none available' if provider in {'absent', 'unavailable'} else
                'OCR engine returned no page results' if provider == 'empty' else 'OCR failed: Own backend failure')
    engine = None if provider == 'absent' else Engine()
    text = read_pdf_scenario(str(path), mode=mode, ocr_engine=engine)
    assert expected in text.warnings
    result = read_document(path, options=ImportOptions(pdf_mode=mode, ocr_engine_factory=lambda **kwargs: engine))
    assert result.success and any(issue.message == expected for issue in result.issues)
    assert not result.lossless


def test_fast_mode_neither_calls_ocr_nor_reports_a_missing_engine(tmp_path):
    path = own_pdf(tmp_path)

    def forbidden(**kwargs):
        raise AssertionError('Fast mode initialized OCR')

    result = read_document(path, options=ImportOptions(pdf_mode='fast', ocr_engine_factory=forbidden))
    assert result.success
    assert not any('OCR' in issue.message for issue in result.issues)
    assert not any('OCR' in warning for warning in read_pdf_scenario(str(path), mode='fast').warnings)
