"""Bounded AcroForm tree audit independent of widget appearance extraction."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from opendoc_model import PreservationState

_REFERENCE = re.compile(r'(\d+)\s+0\s+R')


def _references(kind: str, raw: str) -> list[int]:
    if kind == 'null':
        return []
    if kind != 'array' or len(raw) > 200_000:
        raise ValueError('Unsupported or excessive AcroForm reference array')
    content = raw.strip()[1:-1]
    if _REFERENCE.sub('', content).strip():
        raise ValueError('AcroForm array requires explicit indirect references')
    return [int(match[1]) for match in _REFERENCE.finditer(content)]


def canonical_field_names(pdf: Any) -> set[str]:
    """Measure named AcroForm nodes, never infer logical fields from widgets."""
    pending = [(xref, 0) for xref in _references(*pdf.xref_get_key(pdf.pdf_catalog(), 'AcroForm/Fields'))]
    visited: set[int] = set()
    names: set[str] = set()
    while pending:
        xref, depth = pending.pop()
        if depth > 64 or len(visited) >= 10_000 or xref in visited or not 0 < xref < pdf.xref_length():
            raise ValueError('Invalid or excessive canonical field graph')
        visited.add(xref)
        children = _references(*pdf.xref_get_key(xref, 'Kids'))
        pending.extend((child, depth + 1) for child in children)
        own = [pdf.xref_get_key(xref, key) for key in ('T', 'TM')]
        if all(kind == 'null' for kind, _ in own):
            continue
        parts: list[str] = []
        parents: set[int] = set()
        node = xref
        while node:
            if len(parents) > 64 or node in parents or not 0 < node < pdf.xref_length():
                raise ValueError('Invalid or excessive field parent chain')
            parents.add(node)
            kind, mapped = pdf.xref_get_key(node, 'TM')
            if kind != 'null':
                if kind != 'string' or len(mapped) > 65_536:
                    raise ValueError('Unsupported field mapping name')
                parts.append(mapped)
                break
            kind, partial = pdf.xref_get_key(node, 'T')
            if kind not in ('null', 'string') or len(partial) > 65_536:
                raise ValueError('Unsupported field partial name')
            parts.append(partial if kind == 'string' else '')
            kind, raw = pdf.xref_get_key(node, 'Parent')
            if kind == 'null':
                break
            match = _REFERENCE.fullmatch(raw.strip()) if kind == 'xref' else None
            if match is None:
                raise ValueError('Unsupported field parent reference')
            node = int(match[1])
        name = '.'.join(reversed(parts))
        if len(name) > 65_536:
            raise ValueError('Excessive qualified field name')
        names.add(name)
    return names


def audit_field_tree(pdf: Any, widgets: set[int], record: Callable[..., None]) -> None:
    catalog = pdf.pdf_catalog()
    roots = _references(*pdf.xref_get_key(catalog, 'AcroForm/Fields'))
    pending = [(xref, 0) for xref in roots]
    visited: set[int] = set()
    while pending:
        xref, depth = pending.pop()
        if len(visited) >= 10_000 or depth > 64:
            raise ValueError('AcroForm tree exceeds node/depth profile')
        if xref <= 0 or xref >= pdf.xref_length() or xref in visited:
            raise ValueError('AcroForm has invalid, cyclic or multiply owned field references')
        visited.add(xref)
        children = _references(*pdf.xref_get_key(xref, 'Kids'))
        if children:
            record('pdf.field-tree', PreservationState.OPAQUE, None, xref, 'hierarchical-field',
                   'Canonical parent field structure is retained only in source PDF')
            pending.extend((child, depth + 1) for child in children)
        elif xref not in widgets:
            record('pdf.field-tree', PreservationState.OPAQUE, None, xref, 'field-without-widget',
                   'Canonical field without a page widget is retained only in source PDF')
        kind, _ = pdf.xref_get_key(xref, 'DV')
        if kind not in ('null', 'string'):
            record('pdf.field-default', PreservationState.OPAQUE, None, xref, 'unsupported-default-value',
                   'Nonstring default field value is retained only in source PDF')
        for key in ('RV', 'DS', 'Q', 'Lock', 'SV'):
            if pdf.xref_get_key(xref, key)[0] != 'null':
                record('pdf.field-properties', PreservationState.OPAQUE, None, xref, 'unsupported-' + key,
                       f'Canonical field {key} is retained only in source PDF')
    for xref in sorted(widgets - visited):
        record('pdf.field-tree', PreservationState.OPAQUE, None, xref, 'widget-outside-field-tree',
               'Widget is not reachable from the canonical AcroForm tree')
    for key in ('XFA', 'CO', 'SigFlags'):
        if pdf.xref_get_key(catalog, 'AcroForm/' + key)[0] != 'null':
            record('pdf.field-properties', PreservationState.OPAQUE, None, catalog, 'unsupported-' + key,
                   f'AcroForm {key} is retained only in source PDF')
