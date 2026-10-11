"""Direct Word layout declarations using existing versioned property bags."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, MutableMapping
from dataclasses import replace
from decimal import Decimal
from typing import Any

from opendoc_model import (
    TAB_STOPS_PROPERTY,
    TABLE_INDENT_PROPERTY,
    DocumentModel,
    IssueSeverity,
    PackageGraph,
    Paragraph,
    Table,
    TableIndent,
    TabStop,
    TabStops,
    TextStyle,
    get_tab_stops,
    get_table_indent,
    set_tab_stops,
    set_table_indent,
)

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ALIGNMENTS = {'clear', 'left', 'center', 'right', 'decimal', 'bar', 'num', 'start', 'end'}
LEADERS = {'none', 'dot', 'hyphen', 'underscore', 'heavy', 'middleDot'}
MAX_TABS = 256
COMMON_LEADERS = {'none': 'none', 'dot': 'dot', 'hyphen': 'dash', 'underscore': 'line',
                  'heavy': 'heavy', 'middleDot': 'middle-dot'}


def _native_points(value: str | None) -> float:
    if value is None or len(value) > 12 or re.fullmatch(r'[+-]?[0-9]+', value) is None:
        raise ValueError('Expected a bounded signed twips value')
    number = int(value)
    if not -(2**31) <= number < 2**31:
        raise ValueError('Twips value exceeds signed 32-bit range')
    return number / 20


def _twips(value: object) -> str:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Position must be finite points')
    scaled = Decimal(str(value)) * 20
    if scaled != scaled.to_integral_value() or not -(2**31) <= scaled < 2**31:
        raise ValueError('Position cannot be represented exactly in signed twips')
    return str(round(scaled))


def _indent(node: Any) -> float:
    if len(node) or set(node.attrib) - {W + 'w', W + 'type'} or node.get(W + 'type', 'dxa') != 'dxa':
        raise ValueError('Unsupported table indentation declaration')
    return _native_points(node.get(W + 'w'))


def _tabs(node: Any) -> list[dict]:
    if node.attrib or len(node) > MAX_TABS:
        raise ValueError('Unsupported or excessive tab declarations')
    result = []
    for tab in node:
        alignment, leader = tab.get(W + 'val'), tab.get(W + 'leader', 'none')
        if (tab.tag != W + 'tab' or len(tab) or set(tab.attrib) - {W + 'val', W + 'leader', W + 'pos'}
                or alignment not in ALIGNMENTS or leader not in LEADERS):
            raise ValueError('Unsupported tab stop declaration')
        result.append({'position_pt': _native_points(tab.get(W + 'pos')), 'alignment': alignment, 'leader': leader})
    if len({item['position_pt'] for item in result}) != len(result):
        raise ValueError('Duplicate explicit tab positions are outside the semantic profile')
    return result


def native_layout_supported(node: Any) -> bool:
    """Diagnose unsupported declarations without executing or resolving native content."""
    try:
        (_indent if node.tag == W + 'tblInd' else _tabs)(node)
        parent = node.getparent()
        return parent is not None and len(parent.findall(node.tag)) == 1
    except ValueError:
        return False


def import_layout(properties: MutableMapping[str, Any], owner: Any, *, table: bool = False) -> None:
    """Import direct declarations only; style inheritance remains in the preserved style graph."""
    if owner is None:
        return
    tag, key = ('tblInd', 'docx_table_indent_pt') if table else ('tabs', 'docx_tab_stops')
    nodes = owner.findall(W + tag)
    if not nodes:
        return
    properties[key + '_imported'] = True
    if len(nodes) == 1 and native_layout_supported(nodes[0]):
        properties[key] = (_indent if table else _tabs)(nodes[0])
        if not table and any(item['alignment'] in ('start', 'end', 'num') for item in properties[key]):
            from lxml import etree

            properties['docx_tabs_native_xml'] = etree.tostring(nodes[0], encoding='unicode')
    else:
        properties[key + '_unsupported'] = True


def import_common_layout(source: Table | Paragraph) -> None:
    """Lift direct native declarations into the public OpenDoc contract through its own setters."""
    if isinstance(source, Table):
        key = 'docx_table_indent_pt'
        if key in source.properties:
            set_table_indent(source, TableIndent(source.properties.pop(key)))
        elif source.properties.get(key + '_unsupported'):
            set_table_indent(source, TableIndent(extra={'docx_unsupported': True}))
        if source.properties.get(key + '_imported'):
            source.properties[key + '_common_imported'] = True
        return
    values = source.properties.pop('docx_tab_stops', None)
    if source.properties.get('docx_tab_stops_imported'):
        source.properties['docx_tab_stops_common_imported'] = True
    if values is None:
        if source.properties.get('docx_tab_stops_unsupported'):
            set_tab_stops(source, TabStops(extra={'docx_unsupported': True}))
        return
    stops = []
    for item in values:
        if item['alignment'] == 'clear':
            stops.append(TabStop(item['position_pt'], kind='clear'))
        else:
            alignment = item['alignment'] if item['alignment'] in ('left', 'right', 'center', 'decimal', 'bar') else None
            extra = {'docx_alignment': item['alignment']} if alignment is None else {}
            stops.append(TabStop(item['position_pt'], alignment=alignment, leader=COMMON_LEADERS[item['leader']], extra=extra))
    set_tab_stops(source, TabStops(tuple(stops)))


def inherited_tab_positions(source: Paragraph, document: DocumentModel) -> tuple[float, ...]:
    """Resolve native explicit fallback positions only; never synthesize automatic intervals."""
    positions: set[float] = set()
    from lxml import etree

    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    for style in document.styles.values():
        if style.properties.style_type == 'document-default':
            raw = style.properties.get('paragraph_defaults_xml')
            if raw:
                if not isinstance(raw, str) or len(raw.encode()) > 65536:
                    raise ValueError('Paragraph defaults exceed the native profile')
                try:
                    root = etree.fromstring(raw.encode(), parser)
                except etree.XMLSyntaxError as error:
                    raise ValueError('Invalid paragraph defaults XML') from error
                for node in root.iter(W + 'tabs'):
                    for item in _tabs(node):
                        (positions.discard if item['alignment'] == 'clear' else positions.add)(item['position_pt'])
    chain = []
    identifier = source.style_id
    seen = set()
    while identifier:
        if identifier in seen or len(seen) >= 64:
            raise ValueError('Cyclic or excessive paragraph style inheritance')
        seen.add(identifier)
        style = document.styles.get(identifier)
        if style is None:
            raise ValueError('Unknown paragraph style fallback')
        chain.append(style)
        identifier = style.properties.base_style_id
    for style in reversed(chain):
        if style.properties.get('docx_tab_stops_unsupported'):
            raise ValueError('Unsupported inherited tab declarations')
        for item in style.properties.get('docx_tab_stops') or []:
            (positions.discard if item['alignment'] == 'clear' else positions.add)(item['position_pt'])
        if len(positions) > MAX_TABS:
            raise ValueError('Inherited explicit tab limit exceeded')
    return tuple(sorted(positions))


def _common_value(properties: Mapping[str, Any], *, table: bool, inherited: tuple[float, ...]) -> object:
    if table:
        record = get_table_indent(Table(properties=dict(properties)))
        if record is None:
            return None
        if record.value_pt is None:
            raise ValueError('Unknown table indent cannot be represented as a native displacement')
        return record.value_pt
    record = get_tab_stops(Paragraph(properties=dict(properties)))
    if record is None:
        return None
    if record.extra.get('docx_unsupported') and not record.stops:
        raise ValueError('Unresolved native tabs require explicit replacement or removal of the declaration')
    result = []
    declared = {stop.position_pt for stop in record.stops}
    if not record.inherit:
        result.extend({'position_pt': position, 'alignment': 'clear', 'leader': 'none'}
                      for position in inherited if position not in declared)
    for stop in record.stops:
        if stop.kind == 'clear':
            alignment, leader = 'clear', 'none'
        else:
            alignment = stop.alignment or stop.extra.get('docx_alignment')
            leader = {value: key for key, value in COMMON_LEADERS.items()}.get(stop.leader)
            if alignment is None or leader is None:
                raise ValueError('Unknown tab alignment/leader cannot be inferred')
        result.append({'position_pt': stop.position_pt, 'alignment': alignment, 'leader': leader})
    return sorted(result, key=lambda item: item['position_pt'])


def export_layout(properties: Mapping[str, Any], owner: Any, report: Any, location: str, *, table: bool = False,
                  inherited: tuple[float, ...] = ()) -> None:
    """Explicit edit/deletion wins; unsupported or inexact declarations reject publication."""
    from docx.oxml import OxmlElement

    tag, key = ('tblInd', 'docx_table_indent_pt') if table else ('tabs', 'docx_tab_stops')
    try:
        common_key = TABLE_INDENT_PROPERTY if table else TAB_STOPS_PROPERTY
        if (key not in properties and common_key not in properties and properties.get(key + '_unsupported')
                and not properties.get(key + '_common_imported')):
            raise ValueError('Unsupported source layout requires an explicit replacement or deletion')
        value = _common_value(properties, table=table, inherited=inherited) if (
            common_key in properties or properties.get(key + '_imported') and key not in properties
        ) else properties.get(key)
        if not table and common_key in properties:
            declaration = get_tab_stops(Paragraph(properties=dict(properties)))
            if declaration is not None and not declaration.inherit:
                report.add(IssueSeverity.LOSS, 'docx.tab-stops-materialized',
                           'Replacing tab set materialized as clears of current explicit style positions', location)
            if declaration is not None and any(stop.extra.get('docx_alignment') and stop.alignment is None
                                               for stop in declaration.stops):
                report.add(IssueSeverity.LOSS, 'docx.tab-stops-semantics',
                           'Native alignment retained without a known format-neutral alignment', location)
        node = None
        if value is not None:
            node = OxmlElement('w:' + tag)
            if table:
                node.set(W + 'w', _twips(value))
                node.set(W + 'type', 'dxa')
            else:
                if type(value) is not list or len(value) > MAX_TABS:
                    raise ValueError('Tab stops require a bounded list')
                for item in value:
                    if (type(item) is not dict or set(item) != {'position_pt', 'alignment', 'leader'}
                            or item['alignment'] not in ALIGNMENTS or item['leader'] not in LEADERS):
                        raise ValueError('Invalid tab stop properties')
                    child = OxmlElement('w:tab')
                    child.set(W + 'pos', _twips(item['position_pt']))
                    child.set(W + 'val', item['alignment'])
                    child.set(W + 'leader', item['leader'])
                    node.append(child)
                if not value:
                    node = None
        for previous in list(owner.findall(W + tag)):
            owner.remove(previous)
        if node is not None:
            successors = ('w:tblBorders', 'w:shd', 'w:tblLayout', 'w:tblCellMar', 'w:tblLook', 'w:tblCaption',
                          'w:tblDescription', 'w:tblPrChange') if table else (
                              'w:suppressAutoHyphens', 'w:kinsoku', 'w:wordWrap', 'w:overflowPunct', 'w:topLinePunct',
                              'w:autoSpaceDE', 'w:autoSpaceDN', 'w:bidi', 'w:adjustRightInd', 'w:snapToGrid',
                              'w:spacing', 'w:ind', 'w:contextualSpacing', 'w:mirrorIndents', 'w:suppressOverlap',
                              'w:jc', 'w:textDirection', 'w:textAlignment', 'w:textboxTightWrap', 'w:outlineLvl',
                              'w:divId', 'w:cnfStyle', 'w:rPr', 'w:sectPr', 'w:pPrChange',
                          )
            owner.insert_element_before(node, *successors)
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        report.add(IssueSeverity.ERROR, 'docx.' + ('table-indent' if table else 'tab-stops'), str(error), location)


def retain_layout_styles(graph: PackageGraph, styles: Mapping[str, TextStyle], report: Any) -> PackageGraph:
    """Patch only owned tab declarations in a copied source style part, retaining unrelated native properties."""
    from docx.oxml import OxmlElement, parse_xml
    from lxml import etree

    from opendoc_formats.ooxml.package import RELATIONSHIP_TYPE
    from opendoc_formats.ooxml.spacing import export_spacing, spacing_needs_patch
    from opendoc_formats.ooxml.word_color import apply_color, color_needs_patch, default_color_owner

    selected = {key: style for key, style in styles.items() if any(name in style.properties for name in (
        'docx_tab_stops', 'docx_tab_stops_imported', 'docx_tab_stops_unsupported',
    )) or spacing_needs_patch(style.properties) or color_needs_patch(style)}
    part = graph.related_part(graph.root, RELATIONSHIP_TYPE['styles'])
    if not selected or part is None:
        return graph
    try:
        root = parse_xml(part.data)
        if root.tag != W + 'styles':
            raise ValueError('Source styles part has an unexpected root')
        for identifier, style in selected.items():
            if style.properties.style_type == 'document-default':
                if color_needs_patch(style):
                    apply_color(default_color_owner(root), style)
                continue
            nodes = [node for node in root.findall(W + 'style') if node.get(W + 'styleId') == identifier]
            if len(nodes) != 1:
                report.add(IssueSeverity.ERROR, 'docx.tab-stops',
                           'Style binding is missing or ambiguous', f'styles[{identifier}]')
                continue
            if color_needs_patch(style):
                apply_color(nodes[0].get_or_add_rPr(), style)
            if not spacing_needs_patch(style.properties) and not any(name in style.properties for name in (
                'docx_tab_stops', 'docx_tab_stops_imported', 'docx_tab_stops_unsupported',
            )):
                continue
            owner = nodes[0].find(W + 'pPr')
            if owner is None:
                owner = OxmlElement('w:pPr')
                nodes[0].insert_element_before(owner, 'w:rPr', 'w:tblPr', 'w:trPr', 'w:tcPr', 'w:tblStylePr')
            export_layout(style.properties, owner, report, f'styles[{identifier}]')
            if spacing_needs_patch(style.properties):
                export_spacing(style.properties, owner, report, f'styles[{identifier}]')
        parts = dict(graph.parts)
        parts[part.name] = replace(part, data=etree.tostring(root, encoding='UTF-8', xml_declaration=True))
        return replace(graph, parts=parts)
    except (ValueError, etree.XMLSyntaxError) as error:
        report.add(IssueSeverity.ERROR, 'docx.tab-stops', str(error), 'styles')
        return graph
