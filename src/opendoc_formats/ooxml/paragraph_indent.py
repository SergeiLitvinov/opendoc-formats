"""Finite direct Word paragraph indents and live native inheritance."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, MutableMapping
from typing import Any

from opendoc_model import DocumentModel, IssueSeverity, Paragraph

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SNAPSHOT = 'docx_paragraph_indents_imported'
ATTRIBUTES = {
    'left_indent_pt': ('left', 'start', 'leftChars', 'startChars'),
    'right_indent_pt': ('right', 'end', 'rightChars', 'endChars'),
    'first_line_indent_pt': ('firstLine', 'hanging', 'firstLineChars', 'hangingChars'),
}


def _value(attributes: Mapping[str, str], key: str) -> float | None:
    allowed = {'firstLine', 'hanging'} if key == 'first_line_indent_pt' else {ATTRIBUTES[key][0]}
    if not attributes:
        return None
    if len(attributes) != 1 or not set(attributes) <= allowed:
        raise ValueError('Unsupported paragraph indent units or direction')
    name, raw = next(iter(attributes.items()))
    if len(raw) > 11 or not re.fullmatch(r'-?[0-9]+', raw) or not -(2**31) < int(raw) < 2**31:
        raise ValueError('Paragraph indent must be a bounded native integer')
    if name in {'firstLine', 'hanging'} and int(raw) < 0:
        raise ValueError('First-line and hanging magnitudes must be nonnegative')
    return int(raw) / (-20 if name == 'hanging' else 20)


def import_indents(properties: MutableMapping[str, Any], owner: Any) -> None:
    nodes = owner.findall(W + 'ind') if owner is not None else []
    known_attributes = {W + name for names in ATTRIBUTES.values() for name in names}
    foreign = any(len(node) or not set(node.attrib) <= known_attributes for node in nodes)
    snapshot = {}
    for key, names in ATTRIBUTES.items():
        attributes = {name: node.get(W + name) for node in nodes for name in names if node.get(W + name) is not None}
        if not attributes and len(nodes) < 2 and not foreign:
            continue
        record: dict[str, Any] = {'value': None}
        try:
            if len(nodes) > 1 or foreign:
                record['foreign'] = foreign
                raise ValueError('Ambiguous paragraph indent container')
            record['value'] = _value(attributes, key)
            if record['value'] is not None:
                properties[key] = record['value']
        except ValueError:
            record['unsupported'] = True
        snapshot[key] = record
    if snapshot:
        properties[SNAPSHOT] = snapshot


def native_indents_supported(node: Any) -> bool:
    properties: dict[str, Any] = {}
    import_indents(properties, node.getparent())
    return not any(record.get('unsupported') for record in properties.get(SNAPSHOT, {}).values())


def indents_need_patch(properties: Mapping[str, Any]) -> bool:
    snapshot = properties.get(SNAPSHOT, {})
    if not isinstance(snapshot, dict):
        return True
    for key in ATTRIBUTES:
        record = snapshot.get(key, {})
        if not isinstance(record, dict) or properties.get(key) != record.get('value') or record.get('unsupported'):
            return True
    return False


def unresolved_indent(properties: Mapping[str, Any], key: str) -> bool:
    snapshot = properties.get(SNAPSHOT, {})
    return (isinstance(snapshot, dict) and isinstance(snapshot.get(key), dict)
            and bool(snapshot[key].get('unsupported')) and (snapshot[key].get('foreign') or key not in properties))


def export_indents(properties: Mapping[str, Any], owner: Any, report: Any, location: str) -> None:
    from docx.oxml import OxmlElement

    snapshot = properties.get(SNAPSHOT, {})
    for key, names in ATTRIBUTES.items():
        try:
            record = snapshot.get(key, {}) if isinstance(snapshot, dict) else {}
            if isinstance(record, dict) and record.get('foreign'):
                raise ValueError('Unknown indent extension requires native resolution before export')
            if unresolved_indent(properties, key):
                raise ValueError('Unresolved native paragraph indent requires explicit replacement or None')
            value = properties.get(key)
            if value is None and key not in properties and (not isinstance(snapshot, dict) or key not in snapshot):
                continue
            raw = None
            if value is not None:
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError('Paragraph indent must be a finite number of points')
                raw = round(value * 20)
                if not -(2**31) < raw < 2**31 or not math.isclose(value * 20, raw, rel_tol=0, abs_tol=1e-7):
                    raise ValueError('Paragraph indent cannot be represented exactly in native units')
            nodes = owner.findall(W + 'ind')
            if len(nodes) > 1:
                raise ValueError('Ambiguous target paragraph indent container')
            node = nodes[0] if nodes else OxmlElement('w:ind')
            for name in names:
                node.attrib.pop(W + name, None)
            if raw is not None:
                name = ('hanging' if raw < 0 else 'firstLine') if key == 'first_line_indent_pt' else names[0]
                node.set(W + name, str(abs(raw) if key == 'first_line_indent_pt' else raw))
                if not nodes:
                    owner.insert_element_before(node, 'w:contextualSpacing', 'w:mirrorIndents', 'w:suppressOverlap',
                                                'w:jc', 'w:textDirection', 'w:textAlignment')
        except (ValueError, TypeError, OverflowError) as error:
            report.add(IssueSeverity.ERROR, 'docx.paragraph-indent', str(error), f'{location}.{key}')


def effective_indent(document: DocumentModel, paragraph: Paragraph, key: str) -> Any:
    """Resolve the finite native axis without bypassing an unknown declaration."""
    properties = paragraph.properties
    current = paragraph.style_id
    seen = set()
    while True:
        if unresolved_indent(properties, key):
            return None
        if properties.get(key) is not None:
            return properties[key]
        if current is None or current in seen or current not in document.styles:
            return None
        seen.add(current)
        properties = document.styles[current].properties
        current = properties.get('base_style_id')
