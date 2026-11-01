"""Physical xref/trailer links and classic entries; no backend normalization."""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError
from opendoc_formats.native.pdf_syntax import SPACE, Name, Parser, SyntaxBudget
from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import AnatomyLimits, BinaryItem


def inspect_pdf_source(data: bytes, limits: AnatomyLimits, capture: bool, *,
                       decode_streams: bool = False, object_streams: bool = False, resolve_records: bool = False
                       ) -> tuple[tuple[BinaryItem, ...], dict[str, Any]]:
    from opendoc_formats.anatomy import BinaryItem

    header = re.search(rb'%PDF-[12]\.[0-9]', data[:1024])
    if header is None:
        raise InvalidDocumentError('pdf:source: PDF header absent from first 1024 bytes')
    eof = data.rfind(b'%%EOF')
    if eof < 0 or any(byte not in SPACE for byte in data[eof+5:]):
        raise InvalidDocumentError('pdf:source: missing terminal EOF or trailing non-whitespace bytes')
    tail = data.rfind(b'startxref', max(0, eof-limits.max_part_bytes), eof)
    if tail < 0:
        raise InvalidDocumentError('pdf:source: terminal startxref not found in bounded tail')
    budget = SyntaxBudget(limits.max_pdf_tokens, limits.max_pdf_depth)
    parser = Parser(data, tail, limits.max_part_bytes, budget)
    if parser.take().value != b'startxref':
        raise InvalidDocumentError('pdf:source: invalid startxref')
    offset = parser.take('integer').value
    if any(byte not in SPACE for byte in data[parser.pos:eof]):
        raise InvalidDocumentError('pdf:source: invalid terminal offset/EOF sequence')
    if offset < 0 or offset >= len(data):
        raise InvalidDocumentError('pdf:source: startxref outside source')
    startxref = offset
    pending: list[tuple[int, tuple[int, ...], bool]] = [(offset, (), False)]
    seen: dict[int, dict[str, Any]] = {}
    expanded_primary: set[int] = set()
    items, sections = [], []
    total, count, decoded_total, decode_work_total = 0, 0, 0, 0

    def integer(dictionary: dict[str, Any], key: str, optional: bool = False) -> int | None:
        value = dictionary.get(key)
        if optional and key not in dictionary:
            return None
        if type(value) is not int or value < 0:
            raise InvalidDocumentError(f'pdf:byte={offset}: /{key} must be a direct nonnegative integer')
        return value

    while pending:
        checkpoint()
        offset, ancestors, hybrid = pending.pop()
        if len(ancestors) >= limits.max_pdf_depth:
            raise ResourceLimitError(f'pdf:byte={offset}: max_pdf_depth exceeded by xref chain')
        if offset in ancestors:
            raise InvalidDocumentError(f'pdf:byte={offset}: cyclic xref links')
        if not 0 <= offset < len(data):
            raise InvalidDocumentError(f'pdf:byte={offset}: xref link outside source')
        if offset in seen:
            if hybrid and seen[offset]['kind'] != 'stream':
                raise InvalidDocumentError(f'pdf:byte={offset}: XRefStm does not target a stream')
            if not hybrid and offset not in expanded_primary:
                expanded_primary.add(offset)
                if seen[offset]['prev'] is not None:
                    pending.append((seen[offset]['prev'], (*ancestors, offset), False))
            continue
        parser = Parser(data, offset, limits.max_part_bytes, budget)
        first = parser.take()
        if first.start != offset:
            raise InvalidDocumentError(f'pdf:byte={offset}: xref pointer does not point to a token')
        entries: list[dict[str, Any]] = []
        stream_details: dict[str, Any] = {}
        stream = first.kind == 'integer'
        if stream:
            object_number = first.value
            generation = parser.take('integer').value
            if object_number <= 0 or not 0 <= generation <= 65535 or parser.take().value != b'obj':
                raise InvalidDocumentError(f'pdf:byte={offset}: invalid xref stream object header')
            dictionary_start = parser.peek().start
            dictionary = parser.value()
            if not isinstance(dictionary, dict) or dictionary.get('Type') != Name('XRef'):
                raise InvalidDocumentError(f'pdf:byte={offset}: expected /Type /XRef dictionary')
            dictionary_end = parser.pos
            if parser.take().value != b'stream':
                raise InvalidDocumentError(f'pdf:byte={offset}: expected xref stream keyword')
            if data[parser.pos:parser.pos+1] not in (b'\r', b'\n'):
                raise InvalidDocumentError(f'pdf:byte={parser.pos}: stream keyword must end its line')
            end = dictionary_end
            kind = 'pdf-xref-stream-dictionary'
            if decode_streams:
                from opendoc_formats.native.pdf_xref_streams import decode_xref

                stream_start = parser.pos+(2 if data[parser.pos:parser.pos+2] == b'\r\n' else 1)
                entries, end, stream_details = decode_xref(
                    data, stream_start, dictionary, part_limit=limits.max_part_bytes,
                    byte_limit=limits.max_total_bytes-total-decode_work_total-(stream_start-offset),
                    item_limit=limits.max_items-count-1, budget=budget)
                if end-offset > limits.max_part_bytes:
                    raise ResourceLimitError(f'pdf:byte={offset}: max_part_bytes exceeded by xref stream')
                count += len(entries)
                decoded_total += stream_details['decoded_bytes']
                decode_work_total += stream_details['decode_work_bytes']
                kind = 'pdf-xref-stream'
        else:
            if first.value != b'xref' or hybrid:
                raise InvalidDocumentError(f'pdf:byte={offset}: expected classic xref section')
            numbers = set()
            while parser.peek().value != b'trailer':
                first_number = parser.take('integer').value
                amount = parser.take('integer').value
                if first_number < 0 or amount < 0 or count+amount+1 > limits.max_items:
                    raise ResourceLimitError(f'pdf:byte={parser.pos}: max_items exceeded by xref entries')
                for object_number in range(first_number, first_number+amount):
                    checkpoint()
                    if object_number in numbers:
                        raise InvalidDocumentError(f'pdf:byte={parser.pos}: overlapping xref subsections')
                    numbers.add(object_number)
                    entry_start = parser.peek().start
                    target = parser.take('integer').value
                    generation = parser.take('integer').value
                    state = parser.take().value
                    if target < 0 or not 0 <= generation <= 65535 or state not in {b'n', b'f'}:
                        raise InvalidDocumentError(f'pdf:byte={entry_start}: invalid classic xref entry')
                    match = None
                    if state == b'n' and target < len(data):
                        expression = rb'([0-9]+)[\x00\t\n\x0c\r ]+([0-9]+)[\x00\t\n\x0c\r ]+obj(?=[\x00\t\n\x0c\r /<])'
                        match = re.compile(expression).match(data, target, min(len(data), target+128))
                    matched = bool(match and int(match[1]) == object_number and int(match[2]) == generation)
                    entries.append({'object': object_number, 'generation': generation, 'offset_or_next_free': target,
                                    'in_use': state == b'n', 'entry_start': entry_start,
                                    'entry_end': parser.pos, 'object_header_matches': matched if state == b'n' else None})
                    count += 1
            parser.take()
            dictionary_start = parser.peek().start
            dictionary = parser.value()
            if not isinstance(dictionary, dict):
                raise InvalidDocumentError(f'pdf:byte={offset}: expected trailer dictionary')
            dictionary_end = parser.pos
            end = dictionary_end
            kind = 'pdf-classic-xref'
        size = integer(dictionary, 'Size')
        if size is None or size == 0 or any(entry['object'] >= size for entry in entries):
            raise InvalidDocumentError(f'pdf:byte={offset}: xref object exceeds trailer Size')
        previous = integer(dictionary, 'Prev', optional=True)
        supplement = integer(dictionary, 'XRefStm', optional=True)
        count += 1
        total += end-offset
        if count > limits.max_items or total+decode_work_total > limits.max_total_bytes:
            raise ResourceLimitError(f'pdf:byte={offset}: max_items/max_total_bytes exceeded')
        section = {'offset': offset, 'end': end, 'kind': 'stream' if stream else 'table', 'size': size,
                   'prev': previous, 'xref_stream': supplement, 'hybrid_supplement': hybrid,
                   'dictionary_start': dictionary_start, 'dictionary_end': dictionary_end,
                   'stream_entries_decoded': decode_streams if stream else None, 'entries': entries,
                   'encrypted_declared': 'Encrypt' in dictionary, **stream_details}
        raw = memoryview(data)[offset:end]
        items.append(BinaryItem(f'pdf:source-xref={offset}', kind, len(raw), hashlib.sha256(raw).hexdigest(),
                                details=tuple(section.items()), payload=bytes(raw) if capture else None))
        sections.append(section)
        seen[offset] = section
        path = (*ancestors, offset)
        if previous is not None and not hybrid:
            pending.append((previous, path, False))
        if not hybrid:
            expanded_primary.add(offset)
        if supplement is not None:
            pending.append((supplement, path, True))
    resolution: dict[str, Any] = {'xref_resolution_requested': False}
    if resolve_records:
        from opendoc_formats.native.pdf_xref_state import resolve_xrefs

        resolution = resolve_xrefs(sections, startxref, limits.max_items-count)
        count += len(resolution['effective_xref_entries'])
    object_details: dict[str, Any] = {'object_streams_requested': False, 'object_streams_decoded': False}
    if object_streams:
        from opendoc_formats.native.pdf_object_streams import inspect_object_streams

        additional, object_details = inspect_object_streams(
            data, sections, limits, capture, budget, limits.max_items-count,
            limits.max_total_bytes-total-decode_work_total)
        items.extend(additional)
    return tuple(items), {'representation': 'physical-xref-sections-and-source-dictionaries',
                          'header_offset': header.start(), 'header': header[0].decode('ascii'),
                          'startxref': startxref, 'terminal_eof_offset': eof,
                          'xref_sections': len(sections),
                          'classic_entries': sum(len(section['entries']) for section in sections if section['kind'] == 'table'),
                          'decoded_xref_bytes': decoded_total,
                          'xref_decode_work_bytes': decode_work_total,
                          'has_xref_streams': any(section['kind'] == 'stream' for section in sections),
                          'backend_used': False, 'assessment_complete': False,
                          **object_details,
                          **resolution,
                          'limitations': ['No object ownership proof or active/semantic resolution',
                                          'Lexical object header match does not prove object ownership',
                                          'Xref sections alone do not identify revisions in linearized/hybrid files']}
