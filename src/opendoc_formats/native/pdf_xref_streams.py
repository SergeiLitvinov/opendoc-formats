"""Bounded, opt-in decoding of physical PDF xref records, never object streams."""

from __future__ import annotations

from typing import Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_stream_decode import decode
from opendoc_formats.native.pdf_syntax import Parser, Reference, SyntaxBudget
from opendoc_formats.support.cancellation import checkpoint


def hybrid_length(data: bytes, reference: Reference, table: dict[str, Any], *, part_limit: int,
                  budget: SyntaxBudget) -> dict[str, int]:
    """Read an indirect length from the declaring classic table without scanning."""
    location = f"pdf:xref={table['offset']}: "
    for entry in table['entries']:
        checkpoint()
        if entry['object'] != reference.object:
            continue
        if not entry['in_use'] or entry['generation'] != reference.generation:
            break
        offset = entry['offset_or_next_free']
        if not 0 <= offset < len(data):
            raise InvalidDocumentError(location+'indirect xref Length header mismatch')
        parser = Parser(data, offset, part_limit, budget)
        first = parser.take('integer')
        if (first.start != offset or first.value != reference.object or parser.take('integer').value != reference.generation
                or parser.take().value != b'obj'):
            raise InvalidDocumentError(location+'indirect xref Length header mismatch')
        length = parser.take('integer').value
        if length < 0 or parser.take().value != b'endobj':
            raise InvalidDocumentError(location+'indirect xref Length must contain one nonnegative integer')
        if offset < table['end'] and parser.pos > table['offset']:
            raise InvalidDocumentError(location+'indirect xref Length overlaps its declaring table')
        return {'object': reference.object, 'generation': reference.generation, 'offset': offset,
                'end': parser.pos, 'value': length, 'table': table['offset']}
    raise UnsupportedDocumentError(location+'indirect xref Length requires an in-use entry in the declaring table')


def decode_xref(data: bytes, start: int, dictionary: dict[str, Any], *, part_limit: int,
                byte_limit: int, item_limit: int, budget: SyntaxBudget,
                length_source: dict[str, int] | None = None) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """Return records, physical endobj end and stream evidence."""
    location = f'pdf:byte={start}: '

    def invalid(message: str) -> InvalidDocumentError:
        return InvalidDocumentError(location+message)

    size, widths, index, length = (dictionary.get(key) for key in ('Size', 'W', 'Index', 'Length'))
    if length_source is not None:
        length = length_source['value']
    if type(size) is not int or size <= 0:
        raise invalid('xref Size must be a positive direct integer')
    if (not isinstance(widths, list) or len(widths) != 3
            or any(type(value) is not int or value < 0 for value in widths)):
        raise invalid('xref W must contain three nonnegative direct integers')
    if max(widths) > 8 or sum(widths) == 0:
        raise UnsupportedDocumentError(location+'xref field widths outside the 1..24-byte record profile')
    if index is None:
        index = [0, size]
    if (not isinstance(index, list) or not index or len(index) % 2
            or any(type(value) is not int or value < 0 for value in index)):
        raise invalid('xref Index must contain direct nonnegative start/count pairs')
    ranges: list[tuple[int, int]] = []
    amount = 0
    for position in range(0, len(index), 2):
        checkpoint()
        first, count = index[position:position+2]
        if not count or first+count > size:
            raise invalid('xref Index range outside Size or empty')
        ranges.append((first, first+count))
        amount += count
        if amount > item_limit:
            raise ResourceLimitError(location+'max_items exceeded by xref stream records')
    ordered = sorted(ranges)
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise invalid('overlapping xref Index ranges')
    expected = amount*sum(widths)
    if expected > part_limit or expected > byte_limit:
        raise ResourceLimitError(location+'decoded xref exceeds max_part_bytes/max_total_bytes')
    if type(length) is not int or length < 0:
        raise UnsupportedDocumentError(location+'xref decoding requires a direct nonnegative Length')
    if length > part_limit or length+expected > byte_limit:
        raise ResourceLimitError(location+'encoded/decoded xref exceeds byte budget')
    end = start+length
    if end > len(data):
        raise invalid('xref stream Length outside source')
    if dictionary.get('F') is not None:
        raise UnsupportedDocumentError(location+'external xref streams are not opened')
    parser = Parser(data, end, part_limit, budget)
    if parser.take().value != b'endstream' or parser.take().value != b'endobj':
        raise invalid('xref Length does not end before endstream/endobj')
    decoded, decode_info = decode(memoryview(data)[start:end], dictionary.get('Filter'), dictionary.get('DecodeParms'),
                                  source_start=start, part_limit=part_limit, byte_limit=byte_limit-(parser.pos-start),
                                  expected=expected, location=location, budget=budget)
    entries: list[dict[str, Any]] = []
    cursor = 0
    for first, stop in ranges:
        for number in range(first, stop):
            checkpoint()
            record_start = cursor
            fields = []
            for width in widths:
                fields.append(int.from_bytes(decoded[cursor:cursor+width], 'big'))
                cursor += width
            kind, target, generation = fields
            if widths[0] == 0:
                kind = 1
            entry: dict[str, Any] = {'object': number, 'entry_type': kind,
                                     'decoded_start': record_start, 'decoded_end': cursor}
            if kind in (0, 1):
                if generation > 65535:
                    raise invalid('xref generation exceeds 65535')
                entry.update(generation=generation, offset_or_next_free=target, in_use=kind == 1)
            elif kind == 2:
                if target == 0 or target >= size:
                    raise invalid('compressed object stream number outside Size')
                entry.update(generation=0, in_use=True, object_stream=target, object_stream_index=generation)
            else:
                # Future types are retained, never reinterpreted as byte offsets.
                entry.update(in_use=None, raw_fields=fields)
            entries.append(entry)
    return entries, parser.pos, {'encoded_start': start, 'encoded_end': end, 'decoded_bytes': expected,
                                'record_widths': widths, 'index': index, **decode_info}
