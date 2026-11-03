"""Finite Word line-spacing declarations, separate from their numeric units."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from typing import Any

from opendoc_model import (
    LINE_SPACING_PROPERTY,
    ArtifactLimitError,
    DocumentLimits,
    IssueSeverity,
    LineSpacing,
    Paragraph,
    TextStyle,
    get_line_spacing,
    set_line_spacing,
)

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
RULE = 'docx_line_spacing_rule'
SNAPSHOT = 'docx_line_spacing_imported'
COMMON_SNAPSHOT = 'docx_line_spacing_common_imported'


def _common_changed(properties: Mapping[str, Any]) -> bool:
    snapshot = properties.get(COMMON_SNAPSHOT)
    return (properties.get(LINE_SPACING_PROPERTY) != snapshot.get('declaration') if isinstance(snapshot, dict)
            else LINE_SPACING_PROPERTY in properties)


def _legacy_changed(properties: Mapping[str, Any]) -> bool:
    snapshot = properties.get(SNAPSHOT)
    if isinstance(snapshot, dict):
        if snapshot.get('key') not in ('line_spacing', 'line_spacing_pt'):
            return True
        if snapshot.get('direct') is False and not any(key in properties for key in ('line_spacing', 'line_spacing_pt', RULE)):
            return False
        other = 'line_spacing' if snapshot['key'] == 'line_spacing_pt' else 'line_spacing_pt'
        if properties.get(other) is not None:
            return True
        return (properties.get(snapshot.get('key')) != snapshot.get('value')
                or properties.get(RULE) != snapshot.get('rule'))
    return any(key in properties for key in ('line_spacing', 'line_spacing_pt', 'docx_line_spacing_unsupported'))


def common_spacing(properties: Mapping[str, Any], limits: DocumentLimits | None = None) -> LineSpacing | None:
    """Use only the public Model codec; do not decode a parallel schema."""
    owner = Paragraph(properties={LINE_SPACING_PROPERTY: properties[LINE_SPACING_PROPERTY]})
    return get_line_spacing(owner, limits=limits)


def _import_common(properties: MutableMapping[str, Any], record: LineSpacing) -> None:
    holder = Paragraph()
    set_line_spacing(holder, record)
    properties[LINE_SPACING_PROPERTY] = holder.properties[LINE_SPACING_PROPERTY]
    properties[COMMON_SNAPSHOT] = {'declaration': deepcopy(properties[LINE_SPACING_PROPERTY])}


def prepare_legacy_spacing_view(owner: Paragraph | TextStyle, limits: DocumentLimits | None = None) -> None:
    """Honor legacy edits only in the caller-owned private preview copy."""
    properties = owner.properties
    if not _legacy_changed(properties) or _common_changed(properties):
        return
    point, multiple, rule = properties.get('line_spacing_pt'), properties.get('line_spacing'), properties.get(RULE)
    if point is not None and multiple is not None:
        return
    rules = {'auto': 'relative', 'atLeast': 'minimum', 'exact': 'exact'}
    if rule not in rules or (rule == 'auto') != (multiple is not None):
        return
    try:
        record = LineSpacing(rules[rule], multiple if rule == 'auto' else point)
    except ValueError:
        return
    set_line_spacing(owner, record, limits=limits)


def default_spacing_owner(root: Any) -> Any:
    from docx.oxml import OxmlElement

    for name in ('docDefaults', 'pPrDefault', 'pPr'):
        child = root.find(W + name)
        if child is None:
            child = OxmlElement('w:' + name)
            if name == 'pPrDefault':
                root.append(child)
            else:
                root.insert(0, child)
        root = child
    return root


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
    return _common_changed(properties) or _legacy_changed(properties)


def import_spacing(properties: MutableMapping[str, Any], formats: list[Any]) -> None:
    import_spacing_nodes(properties, [native._element.pPr for native in formats])


def import_spacing_nodes(properties: MutableMapping[str, Any], owners: list[Any]) -> None:
    from lxml import etree

    properties[COMMON_SNAPSHOT] = {'declaration': None}
    for index, ppr in enumerate(owners):
        nodes = ppr.findall(W + 'spacing') if ppr is not None else []
        node = next((item for item in nodes if W + 'line' in item.attrib or W + 'lineRule' in item.attrib), None)
        if node is None:
            continue
        try:
            if len(nodes) > 1:
                raise ValueError('Ambiguous native spacing container')
            rule, raw = _native(node)
        except ValueError:
            if index == 0:
                properties['docx_line_spacing_unsupported'] = True
                properties['docx_line_spacing_native_xml'] = etree.tostring(node, encoding='unicode')
                _import_common(properties, LineSpacing())
            return
        key = 'line_spacing' if rule == 'auto' else 'line_spacing_pt'
        value = raw / (240 if rule == 'auto' else 20)
        if index == 0:
            properties[key] = value
            properties[RULE] = rule
            record = LineSpacing({'auto': 'relative', 'atLeast': 'minimum', 'exact': 'exact'}[rule], value)
            _import_common(properties, record)
        properties[SNAPSHOT] = {'key': key, 'value': value, 'rule': rule, 'raw': raw,
                                'direct': index == 0, 'declared': W + 'lineRule' in node.attrib}
        return


def export_spacing(
    properties: Mapping[str, Any], owner: Any, report: Any, location: str, *, limits: DocumentLimits | None = None,
) -> None:
    from docx.oxml import OxmlElement

    try:
        if _common_changed(properties) or (LINE_SPACING_PROPERTY in properties and not _legacy_changed(properties)):
            original = properties
            properties = dict(properties)
            for key in ('line_spacing', 'line_spacing_pt', RULE, 'docx_line_spacing_unsupported'):
                properties.pop(key, None)
            if _common_changed(original):
                properties.pop(SNAPSHOT, None)
            if LINE_SPACING_PROPERTY in original:
                record = common_spacing(original, limits)
                if record is None or record.rule is None:
                    raise ValueError('Unknown common line spacing has no native Word representation')
                if record.extra:
                    report.add(IssueSeverity.LOSS, 'line-spacing.extra',
                               'Unknown LineSpacing fields are not represented in Word', location)
                properties[RULE] = {'relative': 'auto', 'minimum': 'atLeast', 'exact': 'exact'}[record.rule]
                properties['line_spacing' if record.rule == 'relative' else 'line_spacing_pt'] = record.value
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
    except ArtifactLimitError:
        raise
    except (ValueError, TypeError, OverflowError) as error:
        report.add(IssueSeverity.ERROR, 'docx.line-spacing', str(error), location)
