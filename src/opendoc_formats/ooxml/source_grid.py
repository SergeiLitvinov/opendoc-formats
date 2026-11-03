"""Explicit native grid snapshot, bound by a whole-table hidden Word bookmark."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from opendoc_model import IssueSeverity, Table

from opendoc_formats.support.cancellation import checkpoint

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
NS = 'urn:opendoc-formats:source-grid:1'
KEY = 'docx_source_grid_identity'
PREFIX = '_og_'
MAX_BYTES = 65536


def capture_source_grid(table: Table) -> None:
    if len(table.rows) == 1 and len(table.rows[0].cells) >= 2 and any(c.column_span > 1 for c in table.rows[0].cells):
        table.properties[KEY] = {'id': uuid4().hex, 'grid': list(table.properties.grid_widths_twips),
                                 'spans': [cell.column_span for cell in table.rows[0].cells], 'state': 'verified'}


def _valid(record: dict) -> bool:
    return (isinstance(record.get('id'), str) and re.fullmatch('[0-9a-f]{32}', record['id']) is not None
            and isinstance(record.get('grid'), list) and 2 <= len(record['grid']) <= 256
            and isinstance(record.get('spans'), list) and 2 <= len(record['spans']) <= 256
            and all(type(n) is int and 0 < n < 2**31 for n in record['grid'])
            and all(type(n) is int and 0 < n <= 256 for n in record['spans'])
            and sum(record['spans']) == len(record['grid']))


def _parse(data: bytes) -> dict | None:
    if len(data) > MAX_BYTES or b'<!DOCTYPE' in data.upper():
        return None
    from lxml import etree

    try:
        root = etree.fromstring(data, etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True))
        if root.tag != '{'+NS+'}grid' or root.get('version') != '1' or len(root):
            return None
        record = {'id': root.get('id'), 'grid': [int(n) for n in root.get('widths', '').split()],
                  'spans': [int(n) for n in root.get('spans', '').split()]}
        return record if _valid(record) else None
    except (ValueError, etree.XMLSyntaxError):
        return None


def _nearest_table(node: Any) -> Any:
    while node is not None and node.tag != W+'tbl':
        node = node.getparent()
    return node


def import_source_grid(source: Any, target: Table) -> None:
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    starts = [node for node in source._tbl.iter(W+'bookmarkStart')
              if node.get(W+'name', '').startswith(PREFIX) and _nearest_table(node) is source._tbl]
    if not starts:
        return
    target.properties[KEY] = {'state': 'unverified', 'reason': 'Source grid binding is missing or ambiguous'}
    if len(starts) != 1:
        return
    name, identifier = starts[0].get(W+'name'), starts[0].get(W+'id')
    root = source.part.element
    if sum(node.get(W+'name') == name for node in root.iter(W+'bookmarkStart')) != 1:
        return
    ends = [node for node in root.iter(W+'bookmarkEnd') if node.get(W+'id') == identifier]
    if len(ends) != 1 or _nearest_table(ends[0]) is not source._tbl:
        return
    started = False
    for node in source._tbl.iter():
        checkpoint()
        if node is starts[0]:
            started = True
        if node is ends[0] and not started:
            return
    candidates, work = [], 0
    for relation in source.part.rels.values():
        checkpoint()
        if relation.is_external or relation.reltype != RT.CUSTOM_XML:
            continue
        payload = relation.target_part.blob
        work += len(payload)
        if work > 1024*1024:
            return
        record = _parse(payload)
        if record is not None and PREFIX+record['id'] == name:
            record['part'] = str(relation.target_part.partname)
            props = [r for r in relation.target_part.rels.values() if not r.is_external and r.reltype == RT.CUSTOM_XML_PROPS]
            if len(props) == 1:
                record['props_part'] = str(props[0].target_part.partname)
            candidates.append(record)
    if len(candidates) != 1:
        return
    record = candidates[0]
    target.properties[KEY] = {**record, 'state': 'stale', 'reason': 'Native cell boundaries no longer match source grid'}
    if len(target.rows) != 1 or len(target.rows[0].cells) != len(record['spans']):
        return
    native = list(target.properties.grid_widths_twips)
    if not native or any(type(n) is not int or n <= 0 for n in native):
        return
    original_edges, native_edges = [0], [0]
    for width in record['grid']:
        original_edges.append(original_edges[-1]+width)
    for width in native:
        native_edges.append(native_edges[-1]+width)
    a = b = 0
    for cell, span in zip(target.rows[0].cells, record['spans'], strict=True):
        checkpoint()
        a += cell.column_span
        b += span
        if a >= len(native_edges) or native_edges[a] != original_edges[b] or cell.row_span != 1:
            return
    if a != len(native) or native_edges[-1] != original_edges[-1]:
        return
    target.properties['grid_widths_twips'] = record['grid']
    for cell, span in zip(target.rows[0].cells, record['spans'], strict=True):
        cell.column_span = span
    target.properties[KEY] = {**record, 'state': 'verified'}


def export_source_grid(source: Table, target: Any, report: Any, location: str) -> None:
    record = source.properties.get(KEY)
    if record is None:
        return
    if (not isinstance(record, dict) or not _valid(record) or record.get('state') != 'verified'
            or len(source.rows) != 1 or record['grid'] != list(source.properties.grid_widths_twips)
            or record['spans'] != [cell.column_span for cell in source.rows[0].cells]
            or any(cell.row_span != 1 for cell in source.rows[0].cells)):
        report.add(IssueSeverity.WARNING, 'docx.source-grid', 'Unverified source grid is not restored', location)
        return
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml import OxmlElement
    from lxml import etree

    checkpoint()
    package, owner = target.part.package, target.part
    identifier = record['id']
    grid = etree.Element('{'+NS+'}grid', nsmap={None: NS}, version='1', id=identifier,
                         widths=' '.join(map(str, record['grid'])), spans=' '.join(map(str, record['spans'])))
    item = Part(PackURI('/customXml/og-'+identifier+'.xml'), 'application/xml', etree.tostring(grid), package)
    props = Part(PackURI('/customXml/og-'+identifier+'-props.xml'),
                 'application/vnd.openxmlformats-officedocument.customXmlProperties+xml',
                 ('<ds:datastoreItem xmlns:ds="http://schemas.openxmlformats.org/officeDocument/2006/customXml" '
                  'ds:itemID="{'+str(uuid4()).upper()+'}"><ds:schemaRefs/></ds:datastoreItem>').encode(), package)
    if record.get('part'):
        item._opendoc_source_part = record['part']
    if record.get('props_part'):
        props._opendoc_source_part = record['props_part']
    item.relate_to(props, RT.CUSTOM_XML_PROPS)
    owner.relate_to(item, RT.CUSTOM_XML)
    starts = list(owner.element.iter(W+'bookmarkStart'))
    existing = [n for n in starts if n.get(W+'name') == PREFIX+identifier]
    if existing:
        if len(existing) != 1 or _nearest_table(existing[0]) is not target._tbl:
            raise ValueError('Duplicate source grid bookmark')
        ends = [n for n in owner.element.iter(W+'bookmarkEnd') if n.get(W+'id') == existing[0].get(W+'id')]
        if len(ends) != 1 or _nearest_table(ends[0]) is not target._tbl:
            raise ValueError('Incomplete source grid bookmark')
        return
    number = max([int(n.get(W+'id', '0')) for n in starts]+[0])+1
    start, end = OxmlElement('w:bookmarkStart'), OxmlElement('w:bookmarkEnd')
    start.set(W+'id', str(number))
    start.set(W+'name', PREFIX+identifier)
    end.set(W+'id', str(number))
    first, last = target.rows[0].cells[0], target.rows[0].cells[-1]
    paragraph = first.paragraphs[0]._p
    paragraph.insert(1 if paragraph.find(W+'pPr') is not None else 0, start)
    last.paragraphs[-1]._p.append(end)


def verify_source_grid(package: Any, root: Any, number: int, record: dict) -> None:
    from xml.etree import ElementTree as ET

    checkpoint()
    name = 'customXml/og-'+record['id']+'.xml'
    if package.getinfo(name).file_size > MAX_BYTES:
        raise ValueError('Native Word source grid exceeds byte budget')
    actual = _parse(package.read(name))
    if actual != {key: record[key] for key in ('id', 'grid', 'spans')}:
        raise ValueError('Native Word source grid snapshot changed')
    relations = ET.fromstring(package.read('word/_rels/document.xml.rels'))
    custom = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml'
    if sum(r.get('Type') == custom and r.get('Target') == '../'+name for r in relations) != 1:
        raise ValueError('Native Word source grid relationship changed')
    table = root.find(W+'body').findall(W+'tbl')[number]
    starts = [n for n in root.iter(W+'bookmarkStart') if n.get(W+'name') == PREFIX+record['id']]
    if len(starts) != 1 or starts[0] not in set(table.iter()):
        raise ValueError('Native Word source grid bookmark changed')
    ends = [n for n in root.iter(W+'bookmarkEnd') if n.get(W+'id') == starts[0].get(W+'id')]
    if len(ends) != 1 or ends[0] not in set(table.iter()):
        raise ValueError('Native Word source grid bookmark changed')
