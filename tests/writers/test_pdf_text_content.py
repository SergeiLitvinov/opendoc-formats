"""Own native text relative to its original, not only successive generated PDFs."""

import unicodedata

import pymupdf
import pytest
from opendoc_model import (
    Box,
    DocumentModel,
    Length,
    PageSettings,
    Paragraph,
    Section,
    TextRun,
)

from opendoc_formats import read_document, write_document


def _text(path):
    with pymupdf.open(path) as pdf:
        return ''.join(unicodedata.normalize('NFKC', ''.join(page.get_text() for page in pdf)).split())


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_small_pdf_keeps_original_text_in_two_public_json_cycles(tmp_path, rotation):
    source = tmp_path / 'own-small.pdf'
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=240, height=200)
        page.insert_text((20, 30), 'Own PDF acceptance', fontsize=10)
        page.insert_text((20, 65), 'Second own line', fontsize=10)
        page.set_rotation(rotation)
        pdf.save(source)
    original, expected = source.read_bytes(), _text(source)
    path = source
    for cycle in range(2):
        imported = read_document(path)
        assert imported.success
        transport = tmp_path / f'cycle-{cycle}.json'
        assert write_document(imported.document, transport).success
        output = transport.with_suffix('.pdf')
        report = write_document(read_document(transport).document, output)
        assert report.success, report.issues
        assert _text(output) == expected
        assert report.metrics['pdf_text_checked_runs'] >= 2
        assert any(issue.feature == 'pdf-text-layout' and issue.location for issue in report.issues)
        path = output
    assert source.read_bytes() == original


def test_real_text_omission_refuses_before_replacing_previous_pdf(tmp_path):
    model = DocumentModel(sections=[Section(
        page=PageSettings(width=Length(240), height=Length(200),
                          margin_left=Length(40), margin_right=Length(40),
                          margin_top=Length(40), margin_bottom=Length(40)),
        blocks=[Paragraph([TextRun('W' * 300)], box=Box(0, 0, 20, 10))],
    )])
    output = tmp_path / 'previous.pdf'
    output.write_bytes(b'previous artifact')
    report = write_document(model, output)
    assert not report.success
    assert any(issue.feature == 'pdf-text-content'
               and issue.location == 'sections[0].blocks[0].content[0]' for issue in report.issues)
    assert output.read_bytes() == b'previous artifact'


def test_duplicate_plain_text_requires_each_occurrence(tmp_path):
    from opendoc_model import ConversionReport

    from opendoc_formats.writers.pdf_text_verify import verify_section_text

    section = Section(blocks=[Paragraph([TextRun('Own duplicate')]), Paragraph([TextRun('Own duplicate')])])
    report = ConversionReport(tmp_path / 'own.pdf')
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((50, 80), 'Own duplicate')
        verify_section_text(pdf, section, report, 'sections[0]')
    assert not report.success
    assert report.metrics['pdf_text_checked_runs'] == 1
    assert any(issue.location == 'sections[0].blocks[1].content[0]' for issue in report.issues)


def test_running_header_cannot_mask_missing_body_text(tmp_path):
    from opendoc_model import ConversionReport

    from opendoc_formats.writers.pdf_text_verify import verify_section_text

    section = Section(blocks=[Paragraph([TextRun('Own duplicate')])], headers=[Paragraph([TextRun('Own duplicate')])])
    report = ConversionReport(tmp_path / 'own.pdf')
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((80, 30), 'Own duplicate')
        verify_section_text(pdf, section, report, 'sections[0]')
    assert not report.success
    assert any(issue.location == 'sections[0].blocks[0].content[0]' for issue in report.issues)
