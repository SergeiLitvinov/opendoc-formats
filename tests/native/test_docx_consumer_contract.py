"""Independent OPC originals establish consumer-visible text and editing contracts."""

import io
import zipfile

import pytest

from opendoc_formats.docx import DocxPackage, ReplaceTextSpan
from opendoc_formats.errors import InvalidDocumentError
from tests.binary_fixtures import PR, W, own_docx, zip_bytes


def original(body, extra=()):
    with zipfile.ZipFile(io.BytesIO(own_docx())) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts['word/document.xml'] = f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'.encode()
    parts.update(extra)
    return zip_bytes(list(parts.items()))


def coherent(paragraph):
    assert ''.join(run.text for run in paragraph.runs) == paragraph.text
    assert all(paragraph.text[run.start:run.end] == run.text for run in paragraph.runs)


def test_tab_stops_are_properties_while_real_run_tabs_keep_their_offsets():
    data = original('<w:p><w:pPr><w:tabs><w:tab w:val="left" w:pos="720"/>'
                    '<w:tab w:val="right" w:pos="1440"/></w:tabs></w:pPr>'
                    '<w:r><w:rPr><w:b/></w:rPr><w:t>Модель</w:t><w:tab/><w:t>100</w:t></w:r></w:p>')
    with DocxPackage(data) as package:
        paragraph = package.paragraphs[0]
        assert paragraph.text == 'Модель\t100'
        coherent(paragraph)
        changed = package.to_bytes([ReplaceTextSpan(paragraph.id, 7, 10, '200')])
        assert package.to_bytes() == data
    with DocxPackage(changed) as package:
        assert package.paragraphs[0].text == 'Модель\t200'
        coherent(package.paragraphs[0])
    with zipfile.ZipFile(io.BytesIO(changed)) as archive:
        assert b'w:pos="720"' in archive.read('word/document.xml')
        assert b'w:pos="1440"' in archive.read('word/document.xml')


@pytest.mark.parametrize('start,end,replacement,expected,native', [
    (0, 3, 'Тип', 'Тип-100', True),
    (3, 3, 'X', 'ТМГX-100', True),
    (4, 4, 'X', 'ТМГ-X100', True),
    (3, 4, '-', 'ТМГ-100', False),
    (3, 4, '', 'ТМГ100', False),
])
def test_nobreak_hyphen_text_runs_offsets_and_native_boundary_edits(start, end, replacement, expected, native):
    data = original('<w:p><w:r><w:t>ТМГ</w:t><w:noBreakHyphen/><w:t>100</w:t></w:r></w:p>')
    with DocxPackage(data) as package:
        paragraph = package.paragraphs[0]
        assert paragraph.text == 'ТМГ-100'
        coherent(paragraph)
        changed = package.to_bytes([ReplaceTextSpan(paragraph.id, start, end, replacement)])
        assert package.to_bytes() == data
    with DocxPackage(changed) as package:
        assert package.paragraphs[0].text == expected
        coherent(package.paragraphs[0])
    with zipfile.ZipFile(io.BytesIO(changed)) as archive:
        assert (b'<w:noBreakHyphen' in archive.read('word/document.xml')) == native


def test_cell_text_keeps_empty_paragraph_boundaries_and_physical_merged_cell():
    data = original('<w:tbl><w:tblGrid><w:gridCol/><w:gridCol/></w:tblGrid><w:tr><w:tc>'
                    '<w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>10</w:t></w:r></w:p>'
                    '<w:p/><w:p><w:r><w:t>кВт</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
    with DocxPackage(data) as package:
        row = package.tables[0].rows[0]
        assert len(row.cells) == 1 and row.cells[0].grid_span == 2 and row.has_merge
        cell = row.cells[0]
        paragraphs = {item.id: item for item in package.paragraphs}
        assert [paragraphs[key].text for key in cell.paragraph_ids] == ['10', '', 'кВт']
        assert cell.text == '10\n\nкВт'
        assert package.to_bytes() == data


def test_missing_relationship_owner_remains_an_explicit_rejection():
    data = original('<w:p/>', [('private/_rels/absent.xml.rels', (
        f'<Relationships xmlns="{PR}"><Relationship Id="own" Type="urn:own" '
        'Target="../word/document.xml"/></Relationships>').encode())])
    with pytest.raises(InvalidDocumentError, match='missing source part'):
        DocxPackage(data)
