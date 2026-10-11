"""Finite Word line-spacing declarations, separate from their numeric units."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, MutableMapping
from typing import Any

from opendoc_model import IssueSeverity

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
RULE = 'docx_line_spacing_rule'
SNAPSHOT = 'docx_line_spacing_imported'


def _native(node: Any) -> tuple[str, int]:
    rule = node.get(W + 'lineRule', 'auto')
    value = node.get(W + 'line')
    if len(node) or rule not in {'auto', 'exact', 'atLeast'} or not isinstance(value, str):
        raise ValueError('Unsupported native line-spacing declaration')
    if len(value) > 10 or not re.fullmatch('[0-9]+', value) or not 0 < int(value) < 2**31:
        raise ValueError('Line spacing must be a bounded positive native integer')
    return rule, int(value)


def native_spacing_supported(node: Any) -> bool:
    if W + 'line' not in node.attrib and W + 'lineRule' not in node.attrib:
        return True
    try:
        _native(node)
        return True
    except ValueError:
        return False


def spacing_needs_patch(properties: Mapping[str, Any]) -> bool:
    snapshot = properties.get(SNAPSHOT)
    if isinstance(snapshot, dict):
        if not isinstance(snapshot.get('key'), str) or snapshot['key'] not in ('line_spacing', 'line_spacing_pt'):
            return True
        return (properties.get(snapshot.get('key')) != snapshot.get('value')
                or properties.get(RULE) != snapshot.get('rule'))
    return any(key in properties for key in ('line_spacing', 'line_spacing_pt', 'docx_line_spacing_unsupported'))


def import_spacing(properties: MutableMapping[str, Any], formats: list[Any]) -> None:
    from lxml import etree

    for index, native in enumerate(formats):
        ppr = native._element.pPr
        nodes = ppr.findall(W + 'spacing') if ppr is not None else []
        node = next((item for item in nodes if W + 'line' in item.attrib or W + 'lineRule' in item.attrib), None)
        if node is None:
            continue
        try:
            if len(nodes) > 1:
                raise ValueError('Ambiguous native spacing container')
            rule, raw = _native(node)
        except ValueError:
            properties['docx_line_spacing_unsupported'] = True
            properties['docx_line_spacing_native_xml'] = etree.tostring(node, encoding='unicode')
            return
        key = 'line_spacing' if rule == 'auto' else 'line_spacing_pt'
        value = raw / (240 if rule == 'auto' else 20)
        properties[key] = value
        properties[RULE] = rule
        properties[SNAPSHOT] = {'key': key, 'value': value, 'rule': rule, 'raw': raw,
                                'direct': index == 0, 'declared': W + 'lineRule' in node.attrib}
        return


def export_spacing(properties: Mapping[str, Any], owner: Any, report: Any, location: str) -> None:
    from docx.oxml import OxmlElement

    try:
        pt, multiple = properties.get('line_spacing_pt'), properties.get('line_spacing')
        snapshot = properties.get(SNAPSHOT)
        rule = properties.get(RULE)
        if pt is None and multiple is None:
            if properties.get('docx_line_spacing_unsupported') and RULE not in properties:
                raise ValueError('Unresolved source line spacing requires an explicit replacement or removal')
            if rule is not None:
                raise ValueError('Line-spacing rule requires a value')
            for node in owner.findall(W + 'spacing'):
                node.attrib.pop(W + 'line', None)
                node.attrib.pop(W + 'lineRule', None)
            return
        if pt is not None and multiple is not None:
            raise ValueError('Absolute and relative line spacing cannot be declared together')
        key, value, scale = ('line_spacing_pt', pt, 20) if pt is not None else ('line_spacing', multiple, 240)
        if rule is None:
            rule = 'exact' if pt is not None else 'auto'
            if snapshot is not None:
                raise ValueError('Imported line-spacing rule was removed without its value')
        if rule not in ({'exact', 'atLeast'} if pt is not None else {'auto'}):
            raise ValueError('Line-spacing rule does not match the value units')
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError('Line spacing must be a positive finite value')
        unchanged = (isinstance(snapshot, dict) and snapshot.get('key') == key
                     and snapshot.get('value') == value and snapshot.get('rule') == rule)
        if unchanged and snapshot.get('direct') is False:
            return
        raw = snapshot.get('raw') if unchanged else round(value * scale)
        if (type(raw) is not int or not 0 < raw < 2**31
                or not math.isclose(value * scale, raw, rel_tol=0, abs_tol=1e-7)):
            raise ValueError('Line spacing cannot be represented exactly in native units')
        nodes = owner.findall(W + 'spacing')
        if len(nodes) > 1:
            raise ValueError('Ambiguous target spacing container')
        node = nodes[0] if nodes else OxmlElement('w:spacing')
        node.set(W + 'line', str(raw))
        if unchanged and snapshot.get('declared') is False:
            node.attrib.pop(W + 'lineRule', None)
        else:
            node.set(W + 'lineRule', rule)
        if not nodes:
            owner.insert_element_before(node, 'w:ind', 'w:contextualSpacing', 'w:mirrorIndents', 'w:suppressOverlap',
                                        'w:jc', 'w:textDirection', 'w:textAlignment')
    except (ValueError, TypeError, OverflowError) as error:
        report.add(IssueSeverity.ERROR, 'docx.line-spacing', str(error), location)
