"""Physical xref-addressed ObjStm containers; historical candidates are never active resolution."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_flate import inflate
from opendoc_formats.native.pdf_syntax import Name, Parser, Reference, SyntaxBudget
from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import AnatomyLimits, BinaryItem


def inspect_object_streams(data: bytes, sections: list[dict[str, Any]], limits: AnatomyLimits, capture: bool,
                           budget: SyntaxBudget, remaining_items: int,
                           remaining_bytes: int) -> tuple[tuple[BinaryItem, ...], dict[str, Any]]:
    from opendoc_formats.anatomy import BinaryItem

    references: list[dict[str, int]] = []
    wanted = set()
    for section in sections:
        checkpoint()
        if section['encrypted_declared']:
            raise UnsupportedDocumentError('pdf:source: object-stream inspection does not decrypt encrypted PDFs')
        for entry in section['entries']:
            checkpoint()
            if entry.get('entry_type') == 2:
                wanted.add(entry['object_stream'])
                references.append({'xref_offset': section['offset'], 'object': entry['object'],
                                   'object_stream': entry['object_stream'], 'index': entry['object_stream_index']})
    candidates: dict[tuple[int, int, int], set[int]] = {}
    for section in sections:
        for entry in section['entries']:
            checkpoint()
            if entry['object'] in wanted and entry['in_use'] is True and 'offset_or_next_free' in entry:
                key = (entry['object'], entry['generation'], entry['offset_or_next_free'])
                candidates.setdefault(key, set()).add(section['offset'])
    items: list[BinaryItem] = []
    used_bytes, used_items = 0, 0
    for (number, generation, offset), source_sections in sorted(candidates.items()):
        checkpoint()
        location = f'pdf:source-objstm={offset}: '
        if not 0 <= offset < len(data):
            raise InvalidDocumentError(location+'container offset outside source')
        parser = Parser(data, offset, limits.max_part_bytes, budget)
        first = parser.take('integer')
        if (first.start != offset or first.value != number or parser.take('integer').value != generation
                or parser.take().value != b'obj'):
            raise InvalidDocumentError(location+'xref container header mismatch')
        if generation != 0:
            raise UnsupportedDocumentError(location+'nonzero container generation outside supported profile')
        dictionary = parser.value()
        if not isinstance(dictionary, dict) or dictionary.get('Type') != Name('ObjStm'):
            raise UnsupportedDocumentError(location+'historical candidate is not an ObjStm container')
        def integer(key: str) -> int:
            value = dictionary.get(key)
            if type(value) is not int or value < 0:
                raise UnsupportedDocumentError(location+key+' must be a direct nonnegative integer')
            return value
        count, start, length = (integer(key) for key in ('N', 'First', 'Length'))
        if used_items+count+1 > remaining_items:
            raise ResourceLimitError(location+'max_items exceeded by container/members')
        if 'F' in dictionary:
            raise UnsupportedDocumentError(location+'external object streams are not opened')
        encoding, parameters = dictionary.get('Filter'), dictionary.get('DecodeParms')
        if isinstance(encoding, list) and len(encoding) == 1:
            encoding = encoding[0]
            if isinstance(parameters, list) and len(parameters) == 1:
                parameters = parameters[0]
        if encoding is not None and encoding != Name('FlateDecode'):
            raise UnsupportedDocumentError(location+'object stream filter outside raw/Flate profile')
        if parameters is not None:
            if (not isinstance(parameters, dict) or set(parameters)-{'Predictor'}
                    or type(parameters.get('Predictor', 1)) is not int or parameters.get('Predictor', 1) != 1):
                raise UnsupportedDocumentError(location+'object stream DecodeParms outside supported profile')
        extends = dictionary.get('Extends')
        if extends is not None and not isinstance(extends, Reference):
            raise InvalidDocumentError(location+'Extends must be an indirect reference')
        if parser.take().value != b'stream' or data[parser.pos:parser.pos+1] not in (b'\r', b'\n'):
            raise InvalidDocumentError(location+'missing stream line ending')
        encoded_start = parser.pos+(2 if data[parser.pos:parser.pos+2] == b'\r\n' else 1)
        encoded_end = encoded_start+length
        if encoded_end > len(data):
            raise InvalidDocumentError(location+'Length outside source')
        if encoded_end-offset > limits.max_part_bytes:
            raise ResourceLimitError(location+'max_part_bytes exceeded by container')
        closing = Parser(data, encoded_end, limits.max_part_bytes, budget)
        if closing.take().value != b'endstream' or closing.take().value != b'endobj':
            raise InvalidDocumentError(location+'Length does not end before endstream/endobj')
        end = closing.pos
        physical = end-offset
        available = min(limits.max_part_bytes, remaining_bytes-used_bytes-physical)
        if physical > limits.max_part_bytes or available < 0 or start > available:
            raise ResourceLimitError(location+'max_part_bytes/max_total_bytes exceeded')
        raw = memoryview(data)[encoded_start:encoded_end]
        if encoding is None:
            if len(raw) > available:
                raise ResourceLimitError(location+'raw object stream exceeds byte budget')
            decoded = bytearray(raw)
        else:
            decoded = inflate(raw, available, location)
        if start > len(decoded):
            raise InvalidDocumentError(location+'First outside decoded container')
        member_items: list[BinaryItem] = []
        try:
            header = Parser(decoded, 0, limits.max_part_bytes, budget, stop=start)
            pairs: list[tuple[int, int]] = []
            numbers = set()
            for index in range(count):
                checkpoint()
                member, relative = header.take('integer').value, header.take('integer').value
                if member <= 0 or member in numbers or relative < 0:
                    raise InvalidDocumentError('invalid/duplicate ObjStm header entry')
                if (index == 0 and relative != 0) or (pairs and relative <= pairs[-1][1]):
                    raise InvalidDocumentError('ObjStm offsets must start at zero and strictly increase')
                numbers.add(member)
                pairs.append((member, relative))
            if header.take().kind != 'eof':
                raise InvalidDocumentError('extra tokens before ObjStm First')
            if not pairs and start != len(decoded):
                raise InvalidDocumentError('unexpected body in empty ObjStm')
            for index, (member, relative) in enumerate(pairs):
                checkpoint()
                begin = start+relative
                stop = start+pairs[index+1][1] if index+1 < len(pairs) else len(decoded)
                if not start <= begin < stop <= len(decoded):
                    raise InvalidDocumentError('ObjStm member range outside decoded container')
                body = Parser(decoded, begin, limits.max_part_bytes, budget, stop=stop)
                kind = body.peek().kind
                body.value()  # Syntax validation only; bytes are the authoritative payload.
                if body.take().kind != 'eof':
                    raise InvalidDocumentError('extra tokens/stream in compressed object')
                payload = memoryview(decoded)[begin:stop]
                details: dict[str, Any] = {'object': member, 'generation': 0, 'index': index, 'object_stream': number,
                           'container_offset': offset, 'decoded_start': begin, 'decoded_end': stop,
                           'source_byte_range': None, 'syntax_kind': kind, 'active_resolution': False}
                member_items.append(BinaryItem(f'pdf:source-objstm={offset}/index={index}/object={member}',
                                               'pdf-compressed-object', len(payload), hashlib.sha256(payload).hexdigest(),
                                               details=tuple(details.items()), payload=bytes(payload) if capture else None))
        except (InvalidDocumentError, ResourceLimitError) as error:
            raise type(error)(location+'decoded syntax: '+str(error)) from error
        container = memoryview(data)[offset:end]
        details = {'object': number, 'generation': generation, 'offset': offset, 'end': end,
                   'encoded_start': encoded_start, 'encoded_end': encoded_end, 'decoded_bytes': len(decoded),
                   'first': start, 'members': count, 'filter': 'FlateDecode' if encoding else None,
                   'xref_sections': sorted(source_sections), 'active_resolution': False,
                   'ownership_proven': False, 'extends_resolved': False,
                   'extends': {'object': extends.object, 'generation': extends.generation} if extends else None}
        items.append(BinaryItem(f'pdf:source-objstm={offset}', 'pdf-object-stream', len(container),
                                hashlib.sha256(container).hexdigest(), details=tuple(details.items()),
                                payload=bytes(container) if capture else None))
        items.extend(member_items)
        used_bytes += physical+len(decoded)
        used_items += count+1
    return tuple(items), {'object_streams_requested': True, 'object_streams_decoded': bool(candidates),
                          'decoded_object_streams': len(candidates), 'object_stream_work_bytes': used_bytes,
                          'compressed_object_references': references,
                          'unresolved_container_numbers': sorted(wanted-{number for number, _, _ in candidates}),
                          'object_stream_reference_links_assessed': False}
