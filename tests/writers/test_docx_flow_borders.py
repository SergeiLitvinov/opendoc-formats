"""Independent measured strokes, native cell borders and atomic binary verification."""

import io
from threading import Event
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from opendoc_model import (
    ArtifactLimitError,
    Border,
    BorderSet,
    Table,
    TableCell,
    document_from_json,
    document_to_json,
    get_borders,
    set_borders,
)

from opendoc_formats import DocxProfile, ExportOptions, get_object_mapping, read_document, write_document
from opendoc_formats.ooxml.table_grid import native_grid
from tests.writers.test_docx_flow import _crop, cell_edge_style, crop_merged_model, grid_source_model, merged_source_model

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def source_case(root, mode):
    if mode.startswith('merged'):
        model = merged_source_model(root/'source.pdf', styled=True)
        if mode != 'merged':
            crop_merged_model(model, mode.removeprefix('merged-'))
    else:
        model = grid_source_model(root/'source.pdf', fragmented=True, cell_styled=True)
        if mode == 'crop':
            _crop(model)
    return model


def border_view(table):
    return {(row, column): {side: (border.width_pt, border.color.to_hex().upper())
                            for side, border in get_borders(cell).sides.items()}
            for row, column, cell in native_grid(table)[1]}


@pytest.mark.parametrize('mode', ['plain', 'crop', 'merged', 'merged-top', 'merged-bottom'])
def test_cell_strokes_and_merges_survive_two_native_json_cycles(tmp_path, mode):
    model = source_case(tmp_path, mode)
    before = document_to_json(model)
    target = tmp_path/'flow.docx'
    report = write_document(model, target, options=ExportOptions(docx_profile=DocxProfile('flow')))
    assert report.success, report.issues
    assert document_to_json(model) == before
    mapping = get_object_mapping(report)
    assert mapping.publication == 'published'
    assert len(mapping.sources) == (8 if mode.startswith('merged') else 24)
    assert sum(len(entry.source_ids) for entry in mapping.entries) == len(mapping.sources)
    assert mapping.targets[0].extra['cell_borders']
    expected = {}
    table = next(block for block in model.sections[0].blocks if isinstance(block, Table))
    for row, column, cell in native_grid(table)[1]:
        left, top, right, bottom = cell.properties['pdf_cell_bbox']
        if mode.startswith('merged'):
            vertical = {70: (.5, (1, 0, 0)), 170: (.75, (1, 0, 1)),
                        270: (2.25, (0, 1, 1)), 370: (1.5, (0, 1, 0))}
            horizontal = {150: (1, (0, 0, 0)), 190: (.5, (1, 0, 0)),
                          230: (1.5, (0, 1, 0)), 270: (3, (0, 0, 1))}
            values = [horizontal[top], vertical[left], horizontal[bottom], vertical[right]]
        else:
            values = [cell_edge_style('h', top, left), cell_edge_style('v', left, top),
                      cell_edge_style('h', bottom, left), cell_edge_style('v', right, top)]
        expected[row, column] = {side: (width, '#'+''.join(f'{round(channel*255):02X}' for channel in color))
                                 for side, (width, color) in zip(('top', 'left', 'bottom', 'right'), values)}
    for cycle in range(3):
        with ZipFile(target) as package:
            assert not any(name.startswith('word/media/') for name in package.namelist())
        imported = read_document(target)
        assert imported.success, imported.issues
        restored = next(block for block in imported.document.sections[0].blocks if isinstance(block, Table))
        assert border_view(restored) == expected
        assert [(r, c, cell.row_span, cell.column_span) for r, c, cell in native_grid(restored)[1]] == [
            (r, c, cell.row_span, cell.column_span) for r, c, cell in native_grid(table)[1]]
        if cycle < 2:
            target = tmp_path/f'native-{cycle}.docx'
            assert write_document(document_from_json(document_to_json(imported.document)), target).success


@pytest.mark.parametrize('fault', ['width', 'color', 'duplicate', 'merge-continuation'])
def test_changed_native_cell_border_is_refused_before_publication(tmp_path, monkeypatch, fault):
    from opendoc_formats.writers import docx_flow

    model = source_case(tmp_path, 'merged')
    before, original = document_to_json(model), docx_flow.finalize_flow_mapping

    def tamper(report, path, *, limits):
        output = io.BytesIO()
        with ZipFile(path) as source, ZipFile(output, 'w') as target:
            for info in source.infolist():
                value = source.read(info.filename)
                if info.filename == 'word/document.xml':
                    root = ET.fromstring(value)
                    borders = root.find('.//'+W+'tcBorders')
                    if fault == 'duplicate':
                        borders.append(ET.fromstring(ET.tostring(borders[0])))
                    elif fault == 'merge-continuation':
                        for cell in root.findall('.//'+W+'tc'):
                            merge = cell.find(W+'tcPr/'+W+'vMerge')
                            if merge is not None and merge.get(W+'val', 'continue') == 'continue':
                                cell.find(W+'tcPr/'+W+'tcBorders/'+W+'top').set(W+'val', 'single')
                                break
                    else:
                        borders[0].set(W+('sz' if fault == 'width' else 'color'), '12' if fault == 'width' else 'FFFFFF')
                    value = ET.tostring(root)
                target.writestr(info, value)
        path.write_bytes(output.getvalue())
        original(report, path, limits=limits)

    monkeypatch.setattr(docx_flow, 'finalize_flow_mapping', tamper)
    target = tmp_path/'previous.docx'
    target.write_bytes(b'previous')
    report = write_document(model, target, options=ExportOptions(docx_profile=DocxProfile('flow')))
    assert not report.success and target.read_bytes() == b'previous'
    assert any('cell border' in issue.message for issue in report.issues)
    assert document_to_json(model) == before


def test_cancel_inside_cell_border_planning_is_atomic(tmp_path, monkeypatch):
    from opendoc_formats.writers import docx_flow_borders

    model = source_case(tmp_path, 'merged')
    before, stop, calls = document_to_json(model), Event(), []
    original = docx_flow_borders.checkpoint

    def checkpoint():
        calls.append(True)
        if len(calls) == 10:
            stop.set()
        original()

    monkeypatch.setattr(docx_flow_borders, 'checkpoint', checkpoint)
    target = tmp_path/'previous.docx'
    target.write_bytes(b'previous')
    report = write_document(model, target, options=ExportOptions(docx_profile=DocxProfile('flow'), cancelled=stop.is_set))
    assert not report.success and target.read_bytes() == b'previous'
    assert document_to_json(model) == before and len(calls) == 10


def test_style_change_within_one_logical_side_is_not_flattened():
    from opendoc_formats.writers.docx_flow_borders import plan_cell_borders

    cell = TableCell(properties={'pdf_cell_bbox': [0, 0, 10, 10]})
    matches = [((0, 0, 5, 0), None, '', (1, '000000'), None),
               ((5, 0, 10, 0), None, '', (2, 'FF0000'), None)]
    with pytest.raises(ValueError, match='one complete native border style'):
        plan_cell_borders(matches, [(0, 0, cell)])


def test_cell_border_matching_has_its_own_bounded_work(monkeypatch):
    from opendoc_formats.writers import docx_flow_borders

    monkeypatch.setattr(docx_flow_borders, 'MAX_BORDER_COMPARISONS', 3)
    cell = TableCell(properties={'pdf_cell_bbox': [0, 0, 10, 10]})
    matches = [((0, 0, 10, 0), None, '', (1, '000000'), None)]*4
    with pytest.raises(ArtifactLimitError, match='matching work exceeded'):
        docx_flow_borders.plan_cell_borders(matches, [(0, 0, cell)])


def test_edited_cell_border_requires_explicit_reconciliation(tmp_path):
    model = source_case(tmp_path, 'merged')
    table = next(block for block in model.sections[0].blocks if isinstance(block, Table))
    set_borders(table.rows[0].cells[0], BorderSet({'top': Border(kind='line', style='solid', width_pt=6)}))
    before = document_to_json(model)
    target = tmp_path/'previous.docx'
    target.write_bytes(b'previous')
    report = write_document(model, target, options=ExportOptions(docx_profile=DocxProfile('flow')))
    assert not report.success and target.read_bytes() == b'previous'
    assert document_to_json(model) == before


@pytest.mark.parametrize('crop', [False, True])
@pytest.mark.parametrize('fragmented', [False, True])
def test_six_native_table_border_roles_keep_distinct_source_styles(tmp_path, crop, fragmented):
    model = grid_source_model(tmp_path/'source.pdf', styled=True, fragmented=fragmented)
    if crop:
        _crop(model)
    target = tmp_path/'roles.docx'
    report = write_document(model, target, options=ExportOptions(docx_profile=DocxProfile('flow')))
    assert report.success, report.issues
    assert 'cell_borders' not in get_object_mapping(report).targets[0].extra
    expected = {'top': (.75, '#FF00FF') if crop else (1, '#000000'), 'left': (.5, '#FF0000'),
                'bottom': (3, '#0000FF'), 'right': (2.25, '#00FFFF') if crop else (1.5, '#00FF00'),
                'inside-horizontal': (.75, '#FF00FF'), 'inside-vertical': (2.25, '#00FFFF')}
    for _ in range(3):
        result = read_document(target)
        assert result.success, result.issues
        table = next(block for block in result.document.sections[0].blocks if isinstance(block, Table))
        assert {side: (border.width_pt, border.color.to_hex().upper())
                for side, border in get_borders(table).sides.items()} == expected
        assert write_document(document_from_json(document_to_json(result.document)), target).success
