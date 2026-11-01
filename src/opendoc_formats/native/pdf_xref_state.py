"""Select declared PDF xref records: current table, hybrid supplement, then Prev."""

from __future__ import annotations

from typing import Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.support.cancellation import checkpoint


def resolve_xrefs(sections: list[dict[str, Any]], startxref: int, maximum: int) -> dict[str, Any]:
    """Resolve index precedence only, not object ownership, bodies or generation-qualified references."""
    by_offset = {section['offset']: section for section in sections}
    selected: dict[int, dict[str, Any]] = {}
    order: list[dict[str, Any]] = []
    visited = set()
    offset: int | None = startxref
    while offset is not None:
        checkpoint()
        if offset in visited:
            raise InvalidDocumentError(f'pdf:byte={offset}: cyclic primary xref chain')
        visited.add(offset)
        if offset not in by_offset:
            raise UnsupportedDocumentError(f'pdf:byte={offset}: primary xref section was not inspected')
        primary = by_offset[offset]
        group = [primary]
        supplement = primary['xref_stream']
        if supplement is not None:
            if primary['kind'] != 'table':
                raise UnsupportedDocumentError(f'pdf:byte={offset}: XRefStm requires a classic primary section')
            if supplement not in by_offset or by_offset[supplement]['kind'] != 'stream':
                raise InvalidDocumentError(f'pdf:byte={offset}: missing hybrid xref stream')
            secondary = by_offset[supplement]
            if secondary['xref_stream'] is not None:
                raise UnsupportedDocumentError(f'pdf:byte={supplement}: nested hybrid XRefStm outside supported profile')
            group.append(secondary)
        for section in group:
            checkpoint()
            if section['kind'] == 'stream' and not section['stream_entries_decoded']:
                raise UnsupportedDocumentError(f'pdf:byte={section["offset"]}: xref stream records must be decoded')
            search_index = len(order)
            order.append({'xref_offset': section['offset'], 'primary_xref_offset': offset,
                          'role': 'primary' if section is primary else 'hybrid-supplement',
                          'ignored_prev': section['prev'] if section is not primary else None})
            for entry in section['entries']:
                checkpoint()
                number = entry['object']
                if number in selected:
                    continue
                if len(selected) >= maximum:
                    raise ResourceLimitError(f'pdf:byte={section["offset"]}: max_items exceeded by effective xref records')
                kind = entry.get('entry_type', 1 if entry['in_use'] else 0)
                record = {'object': number, 'entry_type': kind, 'generation': entry.get('generation'),
                          'xref_offset': section['offset'], 'primary_xref_offset': offset,
                          'search_index': search_index, 'ownership_proven': False, 'object_resolved': False}
                if 'entry_start' in entry:
                    record['record_range'] = {'space': 'source', 'start': entry['entry_start'], 'end': entry['entry_end']}
                else:
                    record['record_range'] = {'space': 'decoded-xref', 'start': entry['decoded_start'],
                                              'end': entry['decoded_end']}
                if kind == 0:
                    record.update(state='free', next_free=entry['offset_or_next_free'])
                elif kind == 1:
                    record.update(state='uncompressed', offset=entry['offset_or_next_free'])
                elif kind == 2:
                    record.update(state='compressed', object_stream=entry['object_stream'],
                                  index=entry['object_stream_index'])
                else:
                    # ISO future types are null entries, not holes allowing resurrection.
                    record.update(state='unknown-null', raw_fields=entry['raw_fields'])
                selected[number] = record
        offset = primary['prev']
    return {'xref_resolution_requested': True, 'xref_record_selection_complete': True,
            'xref_search_order': order, 'effective_xref_entries': [selected[number] for number in sorted(selected)],
            'object_resolution_complete': False}
