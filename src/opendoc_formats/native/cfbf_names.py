"""CFBF sibling-name order: UTF-16 unit length, then simple uppercase unit values."""

from __future__ import annotations

import struct
import unicodedata
from typing import TYPE_CHECKING, Any

from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.native.cfbf import _Entry


def _uppercase_unit(unit: int) -> int:
    if 0xd800 <= unit <= 0xdfff:
        return unit
    char = chr(unit)
    upper = char.upper()
    if len(upper) == 1:
        return ord(upper)
    # Greek prosgegrammeni has a simple uppercase/titlecase form even when full
    # uppercase expands into multiple scalars. Other full expansions stay unchanged.
    title = char.title()
    return ord(title) if len(title) == 1 else unit


def _name_key(name: str) -> tuple[int, tuple[int, ...]]:
    encoded = name.encode('utf-16-le')
    units = tuple(_uppercase_unit(unit) for (unit,) in struct.iter_unpack('<H', encoded))
    return len(encoded)+2, units


def directory_name_order(entries: tuple[_Entry, ...], links_valid: bool) -> dict[str, Any]:
    """Check full sibling subtrees in source order; never repair an invalid pointer graph."""
    result: dict[str, Any] = {'directory_name_order_assessed': False, 'directory_name_order_valid': None,
                             'directory_name_order_findings': (),
                             'directory_name_comparison_unicode_version': unicodedata.unidata_version}
    if not links_valid:
        return result
    active = {}
    for entry in entries:
        checkpoint()
        active[entry.index] = dict(entry.details)
    findings = []

    def finding(code: str, index: int, previous: int, owner: int) -> None:
        details = active[index]
        findings.append({'code': code, 'location': f'cfbf:directory={index}/name',
                         'offset': details['entry_offset'], 'name': details['name'],
                         'related_directory': previous, 'storage_owner': owner})

    for entry in entries:
        checkpoint()
        if entry.kind not in (1, 5):
            continue
        current = active[entry.index]['child']
        pending: list[int] = []
        seen: dict[tuple[int, tuple[int, ...]], int] = {}
        previous_key = None
        previous_index = 0
        # Pointer validation established one incoming edge, reachability and no cycles.
        # In-order monotonicity checks ancestors too, unlike checking only adjacent edges.
        while current in active or pending:
            checkpoint()
            while current in active:
                checkpoint()
                pending.append(current)
                current = active[current]['left_sibling']
            index = pending.pop()
            details = active[index]
            key = _name_key(details['name'])
            if key in seen:
                finding('duplicate-sibling-name', index, seen[key], entry.index)
            if previous_key is not None and key < previous_key:
                finding('sibling-name-order', index, previous_index, entry.index)
            seen.setdefault(key, index)
            previous_key, previous_index = key, index
            current = details['right_sibling']
    result.update(directory_name_order_assessed=True, directory_name_order_valid=not findings,
                  directory_name_order_findings=tuple(findings))
    return result
