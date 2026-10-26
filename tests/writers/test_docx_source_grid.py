"""Explicit source grid survives Word-like normalization without content inference."""

import io
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from opendoc_model import Table, document_from_json, document_to_json, get_integration

from opendoc_formats import DocxProfile, ExportOptions, read_document, write_document
from opendoc_formats.ooxml.source_grid import KEY, W, _parse
from tests.writers.test_docx_flow import crop_merged_model, merged_source_model

R = '{http://schemas.openxmlformats.org/package/2006/relationships}'


@pytest.fixture(scope='module')
def source_bytes(tmp_path_factory):
    root = tmp_path_factory.mktemp('source_grid')
    model = merged_source_model(root/'source.pdf')
    crop_merged_model(model, 'top')
    before = document_to_json(model)
    target = root/'flow.docx'
    result = write_document(model, target, options=ExportOptions(docx_profile=DocxProfile('flow')))
    assert result.success, result.issues
    assert document_to_json(model) == before
    return target.read_bytes()


def normalized(source, fault=None):
    out = io.BytesIO()
    with ZipFile(io.BytesIO(source)) as original, ZipFile(out, 'w') as target:
        for info in original.infolist():
            data = original.read(info.filename)
            if info.filename == 'word/document.xml':
                root = ET.fromstring(data)
                table = root.find('.//'+W+'tbl')
                grid = table.find(W+'tblGrid')
                grid.remove(grid[0])
                grid[0].set(W+'w', '4100' if fault == 'resize' else '4000')
                cells = table.findall(W+'tr/'+W+'tc')
                props = cells[0].find(W+'tcPr')
                props.remove(props.find(W+'gridSpan'))
                cells[0].find('.//'+W+'t').text = 'Entirely different text'
                starts = table.findall('.//'+W+'bookmarkStart')
                ends = table.findall('.//'+W+'bookmarkEnd')
                if fault == 'duplicate':
                    cells[1].find(W+'p').append(ET.fromstring(ET.tostring(starts[0])))
                elif fault in ('missing', 'end-outside', 'reversed'):
                    for parent in table.iter():
                        for child in list(parent):
                            if child in ends or (fault == 'missing' and child in starts):
                                parent.remove(child)
                    if fault == 'end-outside':
                        root.find(W+'body').append(ends[0])
                    elif fault == 'reversed':
                        cells[0].find(W+'p').insert(0, ends[0])
                if fault == 'delete-cell':
                    table.find(W+'tr').remove(cells[1])
                data = ET.tostring(root)
            elif info.filename == 'word/_rels/document.xml.rels' and fault in ('unbound-part', 'ambiguous-part'):
                root = ET.fromstring(data)
                relation = next(node for node in root if 'og-' in node.get('Target', '')
                                and '-props' not in node.get('Target', ''))
                if fault == 'unbound-part':
                    root.remove(relation)
                else:
                    duplicate = ET.fromstring(ET.tostring(relation))
                    duplicate.set('Id', 'rId9999')
                    root.append(duplicate)
                data = ET.tostring(root)
            elif info.filename.startswith('customXml/og-') and '-props' not in info.filename and info.filename.endswith('.xml'):
                root = ET.fromstring(data)
                if fault == 'version':
                    root.set('version', '99')
                elif fault == 'invalid-span':
                    root.set('spans', '3 0')
                data = ET.tostring(root)
            target.writestr(info, data)
    return out.getvalue()


def table_of(result):
    assert result.success, result.issues
    return next(block for block in result.document.sections[0].blocks if isinstance(block, Table))


def test_explicit_snapshot_restores_grid_after_normalization_and_two_cycles(source_bytes, tmp_path):
    path = tmp_path/'normalized.docx'
    path.write_bytes(normalized(source_bytes))
    for _ in range(3):
        result = read_document(path)
        table = table_of(result)
        assert table.properties[KEY]['state'] == 'verified'
        assert list(table.properties.grid_widths_twips) == [2000, 2000, 2000]
        assert [cell.column_span for cell in table.rows[0].cells] == [2, 1]
        assert any(run.text == 'Entirely different text' for p in table.rows[0].cells[0].blocks for run in p.content)
        before = document_to_json(result.document)
        assert write_document(document_from_json(before), path).success
        assert document_to_json(result.document) == before
        with ZipFile(path) as package:
            records = [name for name in package.namelist()
                       if name.endswith('.xml') and _parse(package.read(name)) is not None]
            assert len(records) == 1  # OPC ownership must not accumulate stale copies.


@pytest.mark.parametrize('fault', ['resize', 'delete-cell', 'duplicate', 'missing', 'end-outside',
                                  'reversed', 'unbound-part', 'ambiguous-part', 'version', 'invalid-span'])
def test_unverified_snapshot_never_recreates_source_cells(source_bytes, tmp_path, fault):
    path = tmp_path/'changed.docx'
    path.write_bytes(normalized(source_bytes, fault))
    result = read_document(path)
    table = table_of(result)
    assert [cell.column_span for cell in table.rows[0].cells] == ([1] if fault == 'delete-cell' else [1, 1])
    assert list(table.properties.grid_widths_twips) == ([4100, 2000] if fault == 'resize' else [4000, 2000])
    record = table.properties.get(KEY)
    assert record is None or record['state'] != 'verified'
    assert any(record.issue.code == 'docx.source-grid' for record in get_integration(result.document).preservation)


@pytest.mark.parametrize('payload', [b'<!DOCTYPE grid [<!ENTITY own "x">]><grid/>', b'x'*65537,
                                    b'<grid xmlns="urn:opendoc-formats:source-grid:1" version="1" id="bad"/>'],
                         ids=['doctype', 'byte-budget', 'invalid-id'])
def test_snapshot_parser_does_not_recover_unbounded_or_unknown_profiles(payload):
    assert _parse(payload) is None


@pytest.mark.parametrize('fault', ['snapshot', 'relationship', 'bookmark'])
def test_changed_source_grid_receipt_is_refused_before_publication(tmp_path, monkeypatch, fault):
    from opendoc_formats.writers import docx_flow

    model = merged_source_model(tmp_path/'source.pdf')
    crop_merged_model(model, 'top')
    before, original = document_to_json(model), docx_flow.finalize_flow_mapping

    def tamper(report, path, *, limits):
        data = io.BytesIO()
        with ZipFile(path) as source, ZipFile(data, 'w') as target:
            for info in source.infolist():
                value = source.read(info.filename)
                if fault == 'snapshot' and info.filename.startswith('customXml/og-') and '-props' not in info.filename:
                    root = ET.fromstring(value)
                    root.set('spans', '1 2')
                    value = ET.tostring(root)
                elif fault == 'relationship' and info.filename == 'word/_rels/document.xml.rels':
                    root = ET.fromstring(value)
                    for relation in list(root):
                        if 'og-' in relation.get('Target', ''):
                            root.remove(relation)
                    value = ET.tostring(root)
                elif fault == 'bookmark' and info.filename == 'word/document.xml':
                    root = ET.fromstring(value)
                    root.find('.//'+W+'bookmarkStart').set(W+'name', '_changed')
                    value = ET.tostring(root)
                target.writestr(info, value)
        path.write_bytes(data.getvalue())
        original(report, path, limits=limits)

    monkeypatch.setattr(docx_flow, 'finalize_flow_mapping', tamper)
    target = tmp_path/'previous.docx'
    target.write_bytes(b'previous')
    result = write_document(model, target, options=ExportOptions(docx_profile=DocxProfile('flow')))
    assert not result.success and target.read_bytes() == b'previous'
    assert any('source grid' in issue.message for issue in result.issues)
    assert document_to_json(model) == before
