"""Physical xref-addressed ObjStm containers; historical candidates are never active resolution."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_current_parameters import Parameters
from opendoc_formats.native.pdf_object_links import declared_object_links
from opendoc_formats.native.pdf_source_integers import SourceIntegers
from opendoc_formats.native.pdf_stream_decode import decode
from opendoc_formats.native.pdf_syntax import Name, Parser, Reference, SyntaxBudget, finish_stream
from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import AnatomyLimits, BinaryItem


def _candidate_end(parser: Parser, value: Any, location: str,
                    stream_length: Callable[[], int]) -> tuple[int, dict[str, int]]:
    """Bound an ordinary candidate without decoding or searching its stream bytes."""
    token = parser.take()
    if token.value == b'endobj':
        return parser.pos, {}
    if token.value != b'stream' or not isinstance(value, dict):
        raise InvalidDocumentError(location+'expected endobj or dictionary stream')
    length = stream_length()
    try:
        extent = finish_stream(parser, length)
    except InvalidDocumentError as error:
        raise InvalidDocumentError(location+str(error)) from error
    return parser.pos, extent


def inspect_object_streams(data: bytes, sections: list[dict[str, Any]], limits: AnatomyLimits, capture: bool,
                           budget: SyntaxBudget, remaining_items: int,
                           remaining_bytes: int, *, info_member: tuple[int, int, int] | None = None,
                           capture_scalar_members: bool = False,
                           page_members: dict[str, Any] | None = None,
                           ) -> tuple[tuple[BinaryItem, ...], dict[str, Any]]:
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
    from opendoc_formats.native.pdf_extends import discover_current_extends, discover_extends

    extends_details = discover_extends(data, sections, candidates, budget, remaining_items, limits.max_part_bytes)
    historical_contexts = {key: sorted(contexts) for key, contexts in candidates.items()}
    remaining_items -= extends_details['object_stream_extends_work_items']
    extends_details['object_stream_current_extends_assessed'] = False
    if extends_details['object_stream_extends_links']:
        current_details = discover_current_extends(data, sections, candidates, budget, remaining_items, limits.max_part_bytes)
        remaining_items -= current_details['object_stream_current_extends_work_items']
        extends_details['object_stream_extends_work_items'] += current_details['object_stream_current_extends_work_items']
        extends_details.update(current_details)
    used_bytes, used_items, decoded_count, non_containers = 0, 0, 0, 0
    member_reference_items = 0
    decoded_numbers: set[int] = set()
    integers = SourceIntegers(data, sections, limits.max_part_bytes, budget)
    parameter_references: dict[tuple[int, int, int], Parameters] = {}
    for (number, generation, offset), source_sections in sorted(candidates.items()):
        checkpoint()
        # Current Extends discovery may revisit a historical physical container.
        # Its current parameters are assessed separately, never merged into the
        # historical interpretation used to decode these physical member items.
        parameter_contexts = set(historical_contexts.get((number, generation, offset), ())) or source_sections
        location = f'pdf:source-objstm={offset}: '
        if used_items+integers.items >= remaining_items:
            raise ResourceLimitError(location+'max_items exceeded by candidate')
        if not 0 <= offset < len(data):
            raise InvalidDocumentError(location+'container offset outside source')
        parser = Parser(data, offset, limits.max_part_bytes, budget)
        first = parser.take('integer')
        if (first.start != offset or first.value != number or parser.take('integer').value != generation
                or parser.take().value != b'obj'):
            raise InvalidDocumentError(location+'xref container header mismatch')
        syntax_kind = parser.peek().kind
        dictionary = parser.value()
        integer_sources: dict[str, list[dict[str, Any]]] = {}
        decoded_parameters: Parameters = {}

        def resolve_integer(key: str, reference: Reference) -> int:
            resolved, evidence = integers.read(reference, parameter_contexts, item_limit=remaining_items-used_items,
                                               byte_limit=remaining_bytes-used_bytes, location=location+key+': ')
            integer_sources[key] = evidence
            decoded_parameters[key] = reference, resolved
            return resolved

        def integer(key: str) -> int:
            value = dictionary.get(key) if isinstance(dictionary, dict) else None
            if isinstance(value, Reference):
                return resolve_integer(key, value)
            if type(value) is not int or value < 0:
                raise UnsupportedDocumentError(location+key+' must be a nonnegative integer or supported source reference')
            return value

        if not isinstance(dictionary, dict) or dictionary.get('Type') != Name('ObjStm'):
            end, stream_range = _candidate_end(parser, dictionary, location, lambda: integer('Length'))
            physical = end-offset
            if used_items+integers.items+1 > remaining_items:
                raise ResourceLimitError(location+'max_items exceeded by ordinary candidate')
            if physical > limits.max_part_bytes or used_bytes+integers.bytes+physical > remaining_bytes:
                raise ResourceLimitError(location+'max_part_bytes/max_total_bytes exceeded by ordinary candidate')
            payload = memoryview(data)[offset:end]
            declared_type = dictionary.get('Type') if isinstance(dictionary, dict) else None
            candidate_details: dict[str, Any] = {'object': number, 'generation': generation, 'offset': offset, 'end': end,
                       'syntax_kind': syntax_kind, 'candidate_status': 'not-object-stream',
                       'declared_type': declared_type.value if isinstance(declared_type, Name) else None,
                       'xref_sections': sorted(source_sections), 'historical_xref_contexts': historical_contexts.get(
                           (number, generation, offset), []), 'active_resolution': False,
                       'ownership_proven': False, **stream_range}
            if integer_sources:
                candidate_details['source_integer_observations'] = integer_sources
            items.append(BinaryItem(f'pdf:source-objstm={offset}', 'pdf-non-object-stream-candidate', physical,
                                    hashlib.sha256(payload).hexdigest(), details=tuple(candidate_details.items()),
                                    payload=bytes(payload) if capture else None))
            used_bytes += physical
            used_items += 1
            non_containers += 1
            continue
        if generation != 0:
            raise InvalidDocumentError(location+'object stream container generation must be zero')
        count, start, length = (integer(key) for key in ('N', 'First', 'Length'))
        if used_items+integers.items+count+1 > remaining_items:
            raise ResourceLimitError(location+'max_items exceeded by container/members')
        if dictionary.get('F') is not None:
            raise UnsupportedDocumentError(location+'external object streams are not opened')
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
        filters = dictionary.get('Filter')
        options = dictionary.get('DecodeParms')

        def filter_name(value: Any, path: str) -> Any:
            checkpoint()
            if not isinstance(value, Reference):
                return value
            resolved, evidence = integers.read_name(value, parameter_contexts, item_limit=remaining_items-used_items,
                                                    byte_limit=remaining_bytes-used_bytes, location=location+path+': ')
            integer_sources[path] = evidence
            decoded_parameters[path] = value, resolved
            return Name(resolved)

        def filter_parameters(values: Any, path: str) -> Any:
            checkpoint()
            if isinstance(values, Reference):
                resolved, evidence = integers.read_parameters(
                    values, parameter_contexts, item_limit=remaining_items-used_items,
                    byte_limit=remaining_bytes-used_bytes, location=location+path+': ',
                )
                integer_sources[path] = evidence
                decoded_parameters[path] = values, resolved
                return resolved
            if not isinstance(values, dict):
                return values
            result = values.copy()
            for key in ('Predictor', 'Colors', 'BitsPerComponent', 'Columns', 'EarlyChange'):
                if isinstance(reference := values.get(key), Reference):
                    result[key] = resolve_integer(path+'/'+key, reference)
            return result

        if isinstance(filters, list):
            filters = [filter_name(value, f'Filter[{index}]') for index, value in enumerate(filters)]
        else:
            filters = filter_name(filters, 'Filter')
        if isinstance(options, list):
            options = [filter_parameters(stage, f'DecodeParms[{index}]') for index, stage in enumerate(options)]
        else:
            options = filter_parameters(options, 'DecodeParms')
        if used_items+integers.items+count+1 > remaining_items:
            raise ResourceLimitError(location+'max_items exceeded by container/members/filter parameters')
        available = remaining_bytes-used_bytes-integers.bytes-physical
        if physical > limits.max_part_bytes or available < 0 or start > available:
            raise ResourceLimitError(location+'max_part_bytes/max_total_bytes exceeded')
        decoded, decode_info = decode(memoryview(data)[encoded_start:encoded_end], filters,
                                      options, source_start=encoded_start,
                                      part_limit=limits.max_part_bytes, byte_limit=available, location=location, budget=budget)
        if start > len(decoded):
            raise InvalidDocumentError(location+'First outside decoded container')
        member_items: list[BinaryItem] = []
        reference_items = 0
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
                member_references: list[dict[str, Any]] = []

                def observe(reference: Reference, reference_start: int, reference_end: int) -> None:
                    nonlocal reference_items
                    checkpoint()
                    if used_items+integers.items+count+1+reference_items >= remaining_items:
                        raise ResourceLimitError('max_items exceeded by member references')
                    reference_items += 1
                    digest = hashlib.sha256(memoryview(decoded)[reference_start:reference_end]).hexdigest()
                    member_references.append({'object': reference.object, 'generation': reference.generation,
                                              'decoded_start': reference_start, 'decoded_end': reference_end,
                                              'sha256': digest})

                body = Parser(decoded, begin, limits.max_part_bytes, budget, stop=stop, reference_observer=observe)
                kind = body.peek().kind
                is_info = (offset, index, member) == info_member
                # The metadata reader compares repeated top-level entries from raw bytes.
                value = body.value(allow_duplicate_keys=is_info)
                if body.take().kind != 'eof':
                    raise InvalidDocumentError('extra tokens/stream in compressed object')
                payload = memoryview(decoded)[begin:stop]
                details: dict[str, Any] = {'object': member, 'generation': 0, 'index': index, 'object_stream': number,
                           'container_offset': offset, 'decoded_start': begin, 'decoded_end': stop,
                           'source_byte_range': None, 'syntax_kind': kind, 'active_resolution': False}
                if type(value) is int and value >= 0:
                    details['nonnegative_integer'] = value
                if member_references:
                    details['indirect_references'] = member_references
                keep_payload = capture or is_info or (
                    capture_scalar_members and (kind == 'string' or isinstance(value, Reference)))
                locator = f'pdf:source-objstm={offset}/index={index}/object={member}'
                if page_members is not None and (
                    type(value) is int
                    or (isinstance(value, list) and all(isinstance(child, Reference) for child in value))
                    or (isinstance(value, dict) and value.get('Type') in (Name('Catalog'), Name('Pages'), Name('Page')))
                ):
                    page_members[locator] = value
                member_items.append(BinaryItem(locator,
                                               'pdf-compressed-object', len(payload), hashlib.sha256(payload).hexdigest(),
                                               details=tuple(details.items()),
                                               payload=bytes(payload) if keep_payload else None))
        except (InvalidDocumentError, ResourceLimitError) as error:
            raise type(error)(location+'decoded syntax: '+str(error)) from error
        container = memoryview(data)[offset:end]
        details = {'object': number, 'generation': generation, 'offset': offset, 'end': end,
                   'encoded_start': encoded_start, 'encoded_end': encoded_end, 'decoded_bytes': len(decoded),
                   'first': start, 'members': count,
                   'xref_sections': sorted(source_sections), 'historical_xref_contexts': historical_contexts.get(
                       (number, generation, offset), []), 'active_resolution': False,
                   'ownership_proven': False, 'extends_resolved': False,
                   'extends': {'object': extends.object, 'generation': extends.generation} if extends else None, **decode_info}
        if integer_sources:
            details['source_integer_observations'] = integer_sources
            details['parameter_xref_contexts'] = sorted(parameter_contexts)
            parameter_references[(number, generation, offset)] = decoded_parameters
        items.append(BinaryItem(f'pdf:source-objstm={offset}', 'pdf-object-stream', len(container),
                                hashlib.sha256(container).hexdigest(), details=tuple(details.items()),
                                payload=bytes(container) if capture else None))
        items.extend(member_items)
        used_bytes += physical+decode_info['decode_work_bytes']
        used_items += count+1+reference_items
        member_reference_items += reference_items
        decoded_count += 1
        decoded_numbers.add(number)
    from opendoc_formats.native.pdf_current_parameters import assess

    current_parameters = assess(parameter_references, integers, item_limit=remaining_items-used_items,
                                byte_limit=remaining_bytes-used_bytes)
    links = declared_object_links(sections, references, items, budget, remaining_items-used_items-integers.items,
                                  current_parameters=current_parameters, parameters=parameter_references,
                                  integers=integers, byte_limit=remaining_bytes-used_bytes)
    return tuple(items), {'object_streams_requested': True, 'object_streams_decoded': bool(decoded_count),
                          'decoded_object_streams': decoded_count, 'non_object_stream_candidates': non_containers,
                          'object_stream_work_bytes': (used_bytes+integers.bytes+links['object_stream_target_header_work_bytes']
                                                       +links['object_stream_target_body_work_bytes']),
                          'source_integer_work_bytes': integers.bytes, 'source_integer_work_items': integers.items,
                          'object_stream_member_reference_items': member_reference_items,
                          'compressed_object_references': references,
                          'unresolved_container_numbers': sorted(wanted-decoded_numbers),
                          'object_stream_reference_links_assessed': False, **links, **extends_details}
