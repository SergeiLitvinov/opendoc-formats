"""Finite direct paragraph spacing and pagination, with live style inheritance."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, MutableMapping
from typing import Any

from opendoc_model import DocumentModel, IssueSeverity, Paragraph

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SNAPSHOT = 'docx_paragraph_flow_imported'
FIELDS = {
    'space_before_pt': ('spacing', ('before', 'beforeLines', 'beforeAutospacing')),
    'space_after_pt': ('spacing', ('after', 'afterLines', 'afterAutospacing')),
    'keep_together': ('keepLines', ('val',)),
    'keep_with_next': ('keepNext', ('val',)),
    'page_break_before': ('pageBreakBefore', ('val',)),
    'widow_control': ('widowControl', ('val',)),
}


def import_flow(properties: MutableMapping[str, Any], owner: Any) -> None:
    snapshot = {}
    for key, (tag, names) in FIELDS.items():
        nodes = owner.findall(W + tag) if owner is not None else []
        if not nodes:
            continue
        allowed = {'before', 'after', 'beforeLines', 'afterLines', 'beforeAutospacing', 'afterAutospacing',
                   'line', 'lineRule'} if tag == 'spacing' else {'val'}
        foreign = any(len(node) or not set(node.attrib) <= {W + name for name in allowed} for node in nodes)
        attributes = {name: node.get(W + name) for node in nodes for name in names if node.get(W + name) is not None}
        if tag == 'spacing' and not attributes and len(nodes) == 1 and not foreign:
            continue
        record: dict[str, Any] = {'value': None}
        try:
            if len(nodes) != 1 or foreign:
                record['foreign'] = foreign
                raise ValueError('Ambiguous or extended paragraph flow declaration')
            if tag == 'spacing':
                raw = attributes.get(names[0], '')
                if (set(attributes) != {names[0]} or len(raw) > 10 or not re.fullmatch('[0-9]+', raw)
                        or int(raw) >= 2**31):
                    raise ValueError('Unsupported paragraph spacing units')
                value: float | bool = int(raw) / 20
            else:
                raw = nodes[0].get(W + 'val', 'true')
                if raw not in {'true', 'false', 'on', 'off', '1', '0'}:
                    raise ValueError('Unsupported paragraph pagination flag')
                value = raw in {'true', 'on', '1'}
            record['value'] = properties[key] = value
        except ValueError:
            record['unsupported'] = True
        snapshot[key] = record
    if snapshot:
        properties[SNAPSHOT] = snapshot


def unresolved_flow(properties: Mapping[str, Any], key: str) -> bool:
    snapshot = properties.get(SNAPSHOT, {})
    record = snapshot.get(key, {}) if isinstance(snapshot, dict) else {}
    return (isinstance(record, dict) and bool(record.get('unsupported'))
            and (bool(record.get('foreign')) or key not in properties))


def native_flow_supported(node: Any) -> bool:
    properties: dict[str, Any] = {}
    import_flow(properties, node.getparent())
    return not any(record.get('unsupported') for record in properties.get(SNAPSHOT, {}).values())


def flow_needs_patch(properties: Mapping[str, Any]) -> bool:
    snapshot = properties.get(SNAPSHOT, {})
    if not isinstance(snapshot, dict):
        return True
    return any(not isinstance(snapshot.get(key, {}), dict)
               or properties.get(key) != snapshot.get(key, {}).get('value')
               or snapshot.get(key, {}).get('unsupported') for key in FIELDS)


def export_flow(properties: Mapping[str, Any], owner: Any, report: Any, location: str) -> None:
    snapshot = properties.get(SNAPSHOT, {})
    for key, (tag, names) in FIELDS.items():
        try:
            if unresolved_flow(properties, key):
                raise ValueError('Unresolved native paragraph flow requires explicit replacement or None; '
                                 'unknown extensions require native resolution')
            if key not in properties and (not isinstance(snapshot, dict) or key not in snapshot):
                continue
            value = properties.get(key)
            raw = None
            if value is not None:
                if tag == 'spacing':
                    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                        raise ValueError('Paragraph spacing must be finite nonnegative points')
                    scaled = round(value * 20)
                    if not 0 <= scaled < 2**31 or not math.isclose(value * 20, scaled, rel_tol=0, abs_tol=1e-7):
                        raise ValueError('Paragraph spacing cannot be represented exactly in native units')
                    raw = str(scaled)
                else:
                    if type(value) is not bool:
                        raise ValueError('Paragraph pagination requires a boolean')
                    raw = '1' if value else '0'
            nodes = owner.findall(W + tag)
            if len(nodes) > 1:
                raise ValueError('Ambiguous target paragraph flow declaration')
            if tag != 'spacing':
                for node in nodes:
                    owner.remove(node)
                nodes = []
            if raw is not None:
                node = getattr(owner, 'get_or_add_' + tag)()
                for name in names:
                    node.attrib.pop(W + name, None)
                node.set(W + names[0], raw)
            elif tag == 'spacing':
                for node in nodes:
                    for name in names:
                        node.attrib.pop(W + name, None)
        except (ValueError, TypeError, OverflowError) as error:
            report.add(IssueSeverity.ERROR, 'docx.paragraph-flow', str(error), f'{location}.{key}')


def effective_flow(document: DocumentModel, paragraph: Paragraph, key: str) -> Any:
    properties = paragraph.properties
    current = paragraph.style_id
    seen = set()
    while True:
        if unresolved_flow(properties, key):
            return None
        if properties.get(key) is not None:
            return properties[key]
        if current is None or current in seen or current not in document.styles:
            return None
        seen.add(current)
        properties = document.styles[current].properties
        current = properties.get('base_style_id')
