"""Finite common-border visual projection, diagnostics and atomic publication."""

import zipfile
from dataclasses import replace

import pytest
from bs4 import BeautifulSoup
from opendoc_model import (
    Border,
    BorderSet,
    ColorValue,
    DocumentModel,
    Paragraph,
    Section,
    Table,
    TableCell,
    TableRow,
    TextRun,
    compare_documents,
    document_from_dict,
    document_to_dict,
    get_borders,
    set_border,
    set_borders,
)

from opendoc_formats import read_document, write_document


def _fixture():
    table = Table([TableRow([TableCell([Paragraph([TextRun(f'Own {r}:{c}')])]) for c in range(2)]) for r in range(3)])
    line = Border(style='solid', width_pt=1, color=ColorValue.from_hex('112233'))
    set_borders(table, BorderSet({side: line for side in
                                ['top', 'right', 'bottom', 'left', 'inside-horizontal', 'inside-vertical']}))
    return DocumentModel(sections=[Section(blocks=[table])]), table


@pytest.mark.parametrize('extension', ['html', 'epub'])
def test_outer_internal_and_cell_override_are_projected_with_truthful_loss(tmp_path, extension):
    model, table = _fixture()
    set_border(table.rows[1].cells[1], 'left', Border(kind='nil'))
    set_border(table.rows[1].cells[1], 'top', Border(style='double', width_pt=2, color=ColorValue.from_hex('AA5500')))
    before = document_to_dict(model)
    output = tmp_path / ('own.' + extension)
    report = write_document(model, output)
    assert report.success
    assert any(issue.feature == 'table-borders' and issue.location == 'sections[0].blocks[0]' for issue in report.issues)
    if extension == 'html':
        html = output.read_text(encoding='utf-8')
    else:
        with zipfile.ZipFile(output) as archive:
            html = '\n'.join(archive.read(name).decode() for name in archive.namelist() if name.endswith('.xhtml'))
    soup = BeautifulSoup(html, 'html.parser')
    styles = soup.table['style']
    for side in ['top', 'right', 'bottom', 'left']:
        assert f'border-{side}:1pt solid #112233' in styles
    cells = soup.table.find_all('td')
    assert 'border-top:' not in cells[0]['style'] and 'border-left:' not in cells[0]['style']
    assert 'border-left:1pt solid #112233' in cells[1]['style']
    assert 'border-top:1pt solid #112233' in cells[2]['style']
    assert 'border-top:2pt double #AA5500' in cells[3]['style']
    assert 'border-left:0 none' in cells[3]['style']
    assert document_to_dict(model) == before


def test_rowspan_places_internal_separator_at_logical_column(tmp_path):
    model, table = _fixture()
    table.rows[0].cells[0].row_span = 2
    table.rows[1].cells.pop(0)
    output = tmp_path / 'span.html'
    assert write_document(model, output).success
    cells = BeautifulSoup(output.read_text(encoding='utf-8'), 'html.parser').table.find_all('td')
    assert cells[0]['rowspan'] == '2'
    assert 'border-left:1pt solid #112233' in cells[2]['style']


def test_unsupported_visual_border_details_have_located_losses(tmp_path):
    model, table = _fixture()
    set_border(table, 'top', Border(style='dash-dot', offset_pt=2))
    set_border(table.rows[0].cells[0], 'diagonal-down', Border(style='solid'))
    report = write_document(model, tmp_path / 'fallback.html')
    assert report.success
    features = {'html-border-style', 'html-border-width', 'html-border-color', 'html-border-offset', 'html-border-diagonal'}
    assert features <= {issue.feature for issue in report.issues if issue.location}


@pytest.mark.parametrize('excess', ['width', 'span'])
def test_excessive_border_profile_refuses_atomically(tmp_path, excess):
    model, table = _fixture()
    if excess == 'width':
        set_border(table, 'top', Border(style='solid', width_pt=10001))
    else:
        table.rows[0].cells[0].column_span = 10001
    output = tmp_path / 'previous.html'
    output.write_bytes(b'previous artifact')
    report = write_document(model, output)
    assert not report.success
    assert output.read_bytes() == b'previous artifact'


def test_model_opaque_kind_edit_is_warning_and_real_suppression_is_loss(tmp_path):
    model, table = _fixture()
    record = get_borders(table)
    set_borders(table, replace(record, extra={'opaque': [{'kind': 'line'}]}))
    transport = tmp_path / 'own.json'
    assert write_document(model, transport).success
    target = read_document(transport).document
    target_table = target.sections[0].blocks[0]
    updated = get_borders(target_table)
    updated.extra['opaque'][0]['kind'] = 'none'
    set_borders(target_table, updated)
    issues = [issue for issue in compare_documents(model, target).issues if issue.code.startswith('table-border-')]
    assert len(issues) == 1 and issues[0].code == 'table-border-change'
    assert issues[0].severity.value == 'warning'
    suppressed = document_from_dict(document_to_dict(model))
    set_border(suppressed.sections[0].blocks[0], 'top', Border(kind='none'))
    assert any(issue.code == 'table-border-loss' for issue in compare_documents(model, suppressed).issues)
