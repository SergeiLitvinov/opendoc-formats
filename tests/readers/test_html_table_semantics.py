"""Common table declarations survive public HTML/JSON cycles and explicit edits."""

from dataclasses import replace

from bs4 import BeautifulSoup
from opendoc_model import (
    get_table_cell_semantics,
    get_table_row_semantics,
    get_table_semantics,
    set_table_cell_semantics,
    set_table_row_semantics,
    set_table_semantics,
)

from opendoc_formats import read_document, write_document


def test_duplicate_source_ids_keep_text_and_diagnose_ambiguous_associations(tmp_path):
    source = tmp_path / 'duplicates.html'
    source.write_text(
        '<table><caption id="caption">First</caption><tr><th id="h">A</th><td headers="h">B</td></tr></table>'
        '<table><caption id="caption">Second</caption><tr><th id="h">C</th><td headers="h">D</td></tr></table>',
        encoding='utf-8',
    )
    original = source.read_bytes()
    imported = read_document(source)
    assert imported.success
    assert any(issue.code == 'html-table-semantics' and issue.location for issue in imported.issues)
    assert not imported.document.validate()
    assert all(get_table_semantics(node) is None for node in imported.document.sections[0].blocks
               if hasattr(node, 'rows'))
    transport = tmp_path / 'transport.json'
    assert write_document(imported.document, transport).success
    output = tmp_path / 'output.html'
    assert write_document(read_document(transport).document, output).success
    assert BeautifulSoup(output.read_text(encoding='utf-8'), 'html.parser').body.get_text(strip=True) == 'FirstABSecondCD'
    assert source.read_bytes() == original


def _source(tmp_path):
    path = tmp_path / 'source.html'
    path.write_text('<table><thead><tr><th id="heading" scope="col">Name</th></tr></thead>'
                    '<tbody><tr><td headers="heading">Value</td></tr></tbody></table>', encoding='utf-8')
    return path


def test_common_table_headers_and_groups_survive_two_public_cycles(tmp_path):
    path = _source(tmp_path)
    source = path.read_bytes()
    original = read_document(path).document
    expected = original.sections[0].blocks[0]
    for cycle in range(2):
        result = read_document(path)
        assert result.success
        table = result.document.sections[0].blocks[0]
        assert get_table_semantics(table) == get_table_semantics(expected)
        assert get_table_row_semantics(table.rows[0]).group_id == 'group-0'
        assert get_table_cell_semantics(table.rows[0].cells[0]).scope == 'column'
        assert get_table_cell_semantics(table.rows[1].cells[0]).headers == ('heading',)
        transport = tmp_path / f'cycle-{cycle}.json'
        assert write_document(result.document, transport).success
        path = transport.with_suffix('.html')
        assert write_document(read_document(transport).document, path).success
        soup = BeautifulSoup(path.read_text(encoding='utf-8'), 'html.parser')
        assert soup.th['scope'] == 'col'
        assert soup.td['headers'] == ['heading']
    assert (tmp_path / 'source.html').read_bytes() == source


def test_common_edits_override_source_html_attributes(tmp_path):
    model = read_document(_source(tmp_path)).document
    table = model.sections[0].blocks[0]
    header, data = table.rows[0].cells[0], table.rows[1].cells[0]
    set_table_cell_semantics(header, replace(get_table_cell_semantics(header), id='edited', scope='row'))
    set_table_cell_semantics(data, replace(get_table_cell_semantics(data), headers=('edited',)))
    record = get_table_semantics(table)
    set_table_semantics(table, replace(record, row_groups=(replace(record.row_groups[0], kind='body'), record.row_groups[1])))
    output = tmp_path / 'edited.html'
    assert write_document(model, output).success
    soup = BeautifulSoup(output.read_text(encoding='utf-8'), 'html.parser')
    assert soup.thead is None
    assert soup.th['id'] == 'edited' and soup.th['scope'] == 'row'
    assert soup.td['headers'] == ['edited']


def test_removed_common_declarations_do_not_resurrect_legacy_attributes(tmp_path):
    model = read_document(_source(tmp_path)).document
    table = model.sections[0].blocks[0]
    set_table_semantics(table, None)
    for row in table.rows:
        set_table_row_semantics(row, None)
        for cell in row.cells:
            set_table_cell_semantics(cell, None)
    transport = tmp_path / 'removed.json'
    assert write_document(model, transport).success
    output = tmp_path / 'removed.html'
    assert write_document(read_document(transport).document, output).success
    soup = BeautifulSoup(output.read_text(encoding='utf-8'), 'html.parser')
    assert soup.th is None and soup.thead is None
    assert not soup.find_all(headers=True) and not soup.find_all(scope=True)


def test_invalid_header_reference_is_diagnosed_without_fabricated_semantics(tmp_path):
    source = tmp_path / 'invalid.html'
    source.write_text('<table><tr><td headers="missing">Value</td></tr></table>', encoding='utf-8')
    result = read_document(source)
    assert result.success
    assert any(issue.code == 'html-table-semantics' for issue in result.issues)
    table = result.document.sections[0].blocks[0]
    assert get_table_semantics(table) is None
    assert table.rows[0].cells[0].properties['html_headers'] == 'missing'


def test_common_caption_anchor_follows_explicit_association_and_removal(tmp_path):
    from opendoc_model import Anchor, Paragraph, TextRun, get_anchor, set_anchor

    source = tmp_path / 'caption.html'
    source.write_text('<table id="measurements"><caption>Original caption</caption><tr><td>1</td></tr></table>', encoding='utf-8')
    model = read_document(source).document
    caption, table = model.sections[0].blocks
    assert get_table_semantics(table).caption_ids == (get_anchor(caption).id,)
    assert get_anchor(table).id == 'measurements'
    new_caption = Paragraph(content=[TextRun('Replacement caption')])
    set_anchor(new_caption, Anchor('new-caption'))
    model.sections[0].blocks.append(new_caption)
    set_table_semantics(table, replace(get_table_semantics(table), caption_ids=('new-caption',)))
    output = tmp_path / 'reassigned.html'
    assert write_document(model, output).success
    soup = BeautifulSoup(output.read_text(encoding='utf-8'), 'html.parser')
    assert soup.caption.get_text() == 'Replacement caption'
    assert soup.get_text().count('Replacement caption') == 1
    assert soup.find('p', string='Original caption') is not None
    set_table_semantics(table, replace(get_table_semantics(table), caption_ids=()))
    transport = tmp_path / 'caption-removed.json'
    assert write_document(model, transport).success
    assert write_document(read_document(transport).document, output).success
    soup = BeautifulSoup(output.read_text(encoding='utf-8'), 'html.parser')
    assert soup.caption is None
    assert soup.find('p', string='Replacement caption') is not None


def test_empty_caption_keeps_common_anchor_identity_in_two_cycles(tmp_path):
    from opendoc_model import get_anchor

    path = tmp_path / 'empty-caption.html'
    path.write_text('<table><caption></caption><tr><td>1</td></tr></table>', encoding='utf-8')
    expected = None
    for cycle in range(2):
        model = read_document(path).document
        caption, table = model.sections[0].blocks
        identity = (get_anchor(table).id, get_anchor(caption).id, get_table_semantics(table).caption_ids)
        if expected is None:
            expected = identity
        assert identity == expected
        transport = tmp_path / f'empty-{cycle}.json'
        assert write_document(model, transport).success
        path = transport.with_suffix('.html')
        assert write_document(read_document(transport).document, path).success
        assert BeautifulSoup(path.read_text(encoding='utf-8'), 'html.parser').caption.get_text() == ''
