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


def inspect_pdf_source(data: bytes, limits: AnatomyLimits, capture: bool) -> tuple[tuple[BinaryItem, ...], dict[str, Any]]:
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
    seen: dict[int, str] = {}
    items, sections = [], []
    total, count = 0, 0

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
            if hybrid and seen[offset] != 'stream':
                raise InvalidDocumentError(f'pdf:byte={offset}: XRefStm does not target a stream')
            continue
        parser = Parser(data, offset, limits.max_part_bytes, budget)
        first = parser.take()
        if first.start != offset:
            raise InvalidDocumentError(f'pdf:byte={offset}: xref pointer does not point to a token')
        entries = []
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
        if count > limits.max_items or total > limits.max_total_bytes:
            raise ResourceLimitError(f'pdf:byte={offset}: max_items/max_total_bytes exceeded')
        section = {'offset': offset, 'end': end, 'kind': 'stream' if stream else 'table', 'size': size,
                   'prev': previous, 'xref_stream': supplement, 'hybrid_supplement': hybrid,
                   'dictionary_start': dictionary_start, 'dictionary_end': dictionary_end,
                   'stream_entries_decoded': False if stream else None, 'entries': entries,
                   'encrypted_declared': 'Encrypt' in dictionary}
        raw = memoryview(data)[offset:end]
        items.append(BinaryItem(f'pdf:source-xref={offset}', kind, len(raw), hashlib.sha256(raw).hexdigest(),
                                details=tuple(section.items()), payload=bytes(raw) if capture else None))
        sections.append(section)
        seen[offset] = 'stream' if stream else 'table'
        path = (*ancestors, offset)
        if previous is not None and not hybrid:
            pending.append((previous, path, False))
        if supplement is not None:
            pending.append((supplement, path, True))
    return tuple(items), {'representation': 'physical-xref-sections-and-source-dictionaries',
                          'header_offset': header.start(), 'header': header[0].decode('ascii'),
                          'startxref': startxref, 'terminal_eof_offset': eof,
                          'xref_sections': len(sections), 'classic_entries': count-len(sections),
                          'has_xref_streams': any(section['kind'] == 'stream' for section in sections),
                          'backend_used': False, 'assessment_complete': False,
                          'object_streams_decoded': False,
                          'limitations': ['No stream decoding, object boundary proof or active/semantic resolution',
                                          'Lexical object header match does not prove object ownership',
                                          'Xref sections alone do not identify revisions in linearized/hybrid files']}
