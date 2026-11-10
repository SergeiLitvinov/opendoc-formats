"""Context-specific declared ObjStm links, without claiming source ownership or active bodies."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from itertools import chain
from typing import TYPE_CHECKING, Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_current_parameters import Key, Parameters, assess_context
from opendoc_formats.native.pdf_syntax import Parser, Reference, SyntaxBudget, finish_stream
from opendoc_formats.native.pdf_xref_state import resolve_xrefs
from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import BinaryItem
    from opendoc_formats.native.pdf_source_integers import SourceIntegers


def declared_object_links(sections: list[dict[str, Any]], references: list[dict[str, int]],
                          items: list[BinaryItem], budget: SyntaxBudget, maximum: int, *,
                          current_parameters: dict[Key, dict[str, Any]], parameters: dict[Key, Parameters],
                          integers: SourceIntegers, byte_limit: int) -> dict[str, Any]:
    """Match each occurrence only against its own unambiguous primary xref context."""
    location = 'pdf:object-links: '

    def work() -> None:
        checkpoint()
        budget.tokens += 1
        if budget.tokens > budget.maximum:
            raise ResourceLimitError(location+'max_pdf_tokens exceeded by declared object links')

    parents: dict[int, set[int]] = {}
    by_offset = {}
    for section in sections:
        work()
        by_offset[section['offset']] = section
        if section['xref_stream'] is not None:
            parents.setdefault(section['xref_stream'], set()).add(section['offset'])
    primary_contexts = set()
    offset = sections[0]['offset'] if sections else None
    while offset is not None and offset not in primary_contexts:
        work()
        primary_contexts.add(offset)
        offset = by_offset[offset]['prev']
    containers = {}
    members = {}
    has_references = False
    for item in items:
        work()
        info = dict(item.details)
        if item.kind in ('pdf-object-stream', 'pdf-non-object-stream-candidate'):
            containers[(info['object'], info['generation'], info['offset'])] = item
        elif item.kind == 'pdf-compressed-object':
            members[(info['container_offset'], info['index'])] = item
            has_references = has_references or bool(info.get('indirect_references'))
    indexes: dict[int, dict[int, dict[str, Any]]] = {}
    used = 0
    links: list[dict[str, Any]] = []
    current_links: list[dict[str, Any]] = []
    historical_parameters: dict[tuple[Key, int], dict[str, Any]] = {}
    ordinary_targets: dict[tuple[Key, int | None], dict[str, Any]] = {}
    header_bytes = body_bytes = 0
    current = sections[0]['offset'] if sections else None

    def occurrences() -> Iterator[tuple[dict[str, int], int | None]]:
        nonlocal used
        for reference in references:
            yield reference, None
        if current is None or not references:
            return
        if current not in indexes:
            selected = resolve_xrefs(sections, current, maximum-used, budget=budget)['effective_xref_entries']
            used += len(selected)
            indexes[current] = {entry['object']: entry for entry in selected}
        for entry in indexes[current].values():
            work()
            if entry['state'] == 'compressed':
                yield {'xref_offset': entry['xref_offset'], 'object': entry['object'],
                       'object_stream': entry['object_stream'], 'index': entry['index']}, current

    def match_member(reference: dict[str, int], row: dict[str, Any], primary: int,
                     current_context: int | None, *, pending_bytes: int = 0) -> None:
        nonlocal maximum
        index = indexes[primary]
        own = index.get(reference['object'])
        if own is None or own['xref_offset'] != context:
            row['status'] = 'shadowed-reference'
            return
        row['reference_record_range'] = own['record_range']
        container = index.get(reference['object_stream'])
        if container is None or container['state'] in ('free', 'unknown-null'):
            row['status'] = 'missing-container'
            return
        row['container_xref'] = container['xref_offset']
        row['container_record_range'] = container['record_range']
        if container['state'] != 'uncompressed':
            row['status'] = 'container-not-uncompressed'
            return
        row['container_offset'] = container['offset']
        row['container_generation'] = container['generation']
        if container['generation'] != 0:
            row['status'] = 'nonzero-container-generation'
            return
        key = reference['object_stream'], container['generation'], container['offset']
        physical = containers.get(key)
        if physical is None:
            row['status'] = 'container-not-inspected'
            return
        if physical.kind != 'pdf-object-stream':
            row['status'] = 'container-not-object-stream'
            return
        row['container_locator'] = physical.locator
        row['container_sha256'] = physical.sha256
        observations = dict(physical.details).get('source_integer_observations', {})
        if current_context is None:
            for values in observations.values():
                for observation in values:
                    work()
                    scalar_record = index.get(observation['object'])
                    if (scalar_record is not None and scalar_record['state'] == 'uncompressed'
                            and scalar_record['generation'] == observation['generation']
                            and scalar_record['offset'] == observation['offset']):
                        break
                else:
                    cache_key = key, primary
                    if cache_key not in historical_parameters:
                        before = integers.items
                        historical_parameters[cache_key] = assess_context(
                            parameters[key], integers, primary, item_limit=before+maximum-used,
                            byte_limit=byte_limit-header_bytes-body_bytes-pending_bytes, scope='historical')
                        maximum -= integers.items-before
                    historical = historical_parameters[cache_key]
                    row['historical_parameters'] = historical
                    if historical['status'] != 'matched-decoded-parameters':
                        row['status'] = 'container-'+historical['status']
                    break
            if 'status' in row:
                return
        assessment = current_parameters.get(key) if current_context is not None else None
        if assessment is not None:
            row['current_parameters'] = assessment
            if assessment['status'] != 'matched-decoded-parameters':
                row['status'] = 'container-'+assessment['status']
                return
        elif current_context is not None and any(
            not any(observation['primary_xref'] == current_context for observation in values)
            for values in observations.values()
        ):
            row['status'] = 'container-parameters-not-assessed-in-current-context'
            return
        member = members.get((container['offset'], reference['index']))
        if member is None:
            row['status'] = 'index-out-of-range'
            return
        info = dict(member.details)
        row['member_object'] = info['object']
        if info['object'] != reference['object']:
            row['status'] = 'object-number-mismatch'
            return
        row.update(status='matched-declared-member', member_locator=member.locator, member_sha256=member.sha256,
                   decoded_range={'start': info['decoded_start'], 'end': info['decoded_end']})

    for reference, current_context in occurrences():
        location = f'pdf:xref={reference["xref_offset"]}/object={reference["object"]}: '
        work()
        if used >= maximum:
            raise ResourceLimitError(location+'max_items exceeded by declared object links')
        used += 1
        row: dict[str, Any] = {**reference, 'generation': 0, 'ownership_proven': False, 'object_resolved': False}
        (links if current_context is None else current_links).append(row)
        if current_context is not None:
            row['context_xref'] = current_context
        context = reference['xref_offset']
        candidates = parents.get(context, set())
        if current_context is None and (len(candidates) > 1 or (candidates and context in primary_contexts)):
            row['status'] = 'ambiguous-primary-context'
            continue
        primary = current_context if current_context is not None else next(iter(candidates)) if candidates else context
        row['primary_xref'] = primary
        if primary not in indexes:
            selected = resolve_xrefs(sections, primary, maximum-used, budget=budget)['effective_xref_entries']
            used += len(selected)
            indexes[primary] = {entry['object']: entry for entry in selected}
        match_member(reference, row, primary, current_context)
    # A target is useful only if its member was checked in the same projection.
    member_links: dict[tuple[str, int, int], dict[str, Any]] = {}
    if has_references:
        for link in chain(links, current_links):
            work()
            if 'primary_xref' in link and link['status'] != 'shadowed-reference':
                scope = 'current' if 'context_xref' in link else 'historical'
                member_links[scope, link['primary_xref'], link['object']] = link

    def compressed_candidate(target: dict[str, Any], primary: int, current_context: int | None,
                             *, pending_bytes: int = 0) -> dict[str, Any]:
        nonlocal used
        scope = 'current' if current_context is not None else 'historical'
        key = scope, primary, target['object']
        candidate = member_links.get(key)
        if candidate is None:
            if used >= maximum:
                raise ResourceLimitError(location+'max_items exceeded by inherited member checks')
            used += 1
            candidate = {}
            reference = {'xref_offset': target['xref_offset'], 'object': target['object'],
                         'object_stream': target['object_stream'], 'index': target['index']}
            match_member(reference, candidate, primary, current_context, pending_bytes=pending_bytes)
            member_links[key] = candidate
        return candidate

    def read_stream_length(reference: Reference, primary: int, current_context: int | None,
                           prefix_bytes: int) -> tuple[int, dict[str, Any]]:
        nonlocal maximum
        target = indexes[primary].get(reference.object)
        if target is not None and target['state'] == 'compressed':
            if reference.generation != 0:
                raise InvalidDocumentError(location+'Length: compressed scalar generation must be zero')
            candidate = compressed_candidate(target, primary, current_context, pending_bytes=prefix_bytes)
            if candidate['status'] != 'matched-declared-member':
                raise InvalidDocumentError(location+'Length: '+candidate['status'])
            member = members[candidate['container_offset'], target['index']]
            value = dict(member.details).get('nonnegative_integer')
            if type(value) is not int:
                raise UnsupportedDocumentError(location+'Length: compressed scalar must be a nonnegative direct integer')
            return value, {'object': reference.object, 'generation': 0, 'value': value,
                           'primary_xref': primary, 'selected_xref': target['xref_offset'],
                           'record_range': target['record_range'], 'member_locator': member.locator,
                           'decoded_range': candidate['decoded_range'], 'sha256': member.sha256,
                           'ownership_proven': False}
        before = integers.items
        try:
            value, observations = integers.read(reference, {primary}, item_limit=before+maximum-used,
                                                byte_limit=byte_limit-header_bytes-body_bytes-prefix_bytes,
                                                location=location+'Length: ', explicit_primary=True)
        finally:
            maximum -= integers.items-before
        return value, observations[0]

    def ordinary_target(number: int, generation: int, offset: int, primary: int,
                        current_context: int | None) -> dict[str, Any]:
        nonlocal header_bytes, body_bytes, used
        identity = number, generation, offset
        cached = ordinary_targets.get((identity, None)) or ordinary_targets.get((identity, primary))
        if cached is not None:
            return cached
        context = None
        if used >= maximum:
            raise ResourceLimitError(location+'max_items exceeded by target header checks')
        used += 1
        data = integers.data
        if not 0 <= offset < len(data):
            result: dict[str, Any] = {'target_header_status': 'offset-outside-source'}
        else:
            remaining = byte_limit-integers.bytes-header_bytes-body_bytes
            if remaining <= 0:
                raise ResourceLimitError(location+'max_total_bytes exceeded by target header checks')
            window = min(integers.part_limit, remaining)
            parser = Parser(data, offset, window, budget,
                            window_quota='max_total_bytes' if remaining < integers.part_limit else 'max_part_bytes')
            try:
                first = parser.take('integer')
                second = parser.take('integer')
                keyword = parser.take('keyword')
                if first.start != offset or first.value != number or second.value != generation or keyword.value != b'obj':
                    result = {'target_header_status': 'header-mismatch'}
                else:
                    result = {'target_header_status': 'matched-header',
                              'target_header_range': {'offset': offset, 'length': keyword.end-offset},
                              'target_header_sha256': hashlib.sha256(memoryview(data)[offset:keyword.end]).hexdigest()}
            except InvalidDocumentError:
                result = {'target_header_status': 'invalid-header-syntax'}
            header_cost = parser.pos-offset+int(parser.pos < parser.end)
            header_bytes += header_cost
            if result['target_header_status'] == 'matched-header':
                try:
                    value = parser.value()
                    closing = parser.take()
                    if closing.value == b'endobj':
                        status = 'matched-ordinary-body'
                    elif closing.value == b'stream' and isinstance(value, dict):
                        length = value.get('Length')
                        if 'F' in value:
                            status = 'external-stream-not-assessed'
                        elif isinstance(length, Reference):
                            context = primary
                            prefix_cost = parser.pos-offset+int(parser.pos < parser.end)
                            before_bytes = integers.bytes
                            try:
                                length, evidence = read_stream_length(length, primary, current_context, prefix_cost-header_cost)
                            except (InvalidDocumentError, UnsupportedDocumentError) as error:
                                status = ('invalid-indirect-stream-length' if isinstance(error, InvalidDocumentError)
                                          else 'unsupported-indirect-stream-length')
                                result['target_stream_length_error'] = str(error)
                            else:
                                result['target_stream_length_observation'] = evidence
                                remaining -= integers.bytes-before_bytes
                                parser.end = min(parser.end, offset+remaining)
                                if remaining < integers.part_limit:
                                    parser.window_quota = 'max_total_bytes'
                                result['target_stream_extent'] = finish_stream(parser, length)
                                status = 'matched-stream-body'
                        elif type(length) is not int or length < 0:
                            status = 'invalid-stream-length'
                        else:
                            result['target_stream_extent'] = finish_stream(parser, length)
                            status = 'matched-stream-body'
                    else:
                        status = 'missing-endobj'
                    result['target_body_status'] = status
                    if status in {'matched-ordinary-body', 'matched-stream-body'}:
                        result.update(target_object_range={'offset': offset, 'length': parser.pos-offset},
                                      target_object_sha256=hashlib.sha256(memoryview(data)[offset:parser.pos]).hexdigest())
                except InvalidDocumentError:
                    result['target_body_status'] = 'invalid-body-syntax'
                body_bytes += parser.pos-offset+int(parser.pos < parser.end)-header_cost
        ordinary_targets[identity, context] = result
        return result

    reference_links = []
    for source in chain(links, current_links):
        work()
        if source['status'] != 'matched-declared-member':
            continue
        member_details = dict(members[(source['container_offset'], source['index'])].details)
        for reference in member_details.get('indirect_references', ()):
            location = f'pdf:{source["member_locator"]}:reference={reference["decoded_start"]}: '
            work()
            if used >= maximum:
                raise ResourceLimitError(location+'max_items exceeded by member reference declarations')
            used += 1
            row = {'source_member_locator': source['member_locator'], 'source_xref': source['xref_offset'],
                   'primary_xref': source['primary_xref'],
                   'source_context': 'current' if 'context_xref' in source else 'historical',
                   'reference': reference, 'target_body_resolved': False, 'ownership_proven': False}
            reference_links.append(row)
            target = indexes[source['primary_xref']].get(reference['object'])
            if target is None:
                row['status'] = 'missing-target'
                continue
            row.update(target_xref=target['xref_offset'], target_record_range=target['record_range'],
                       target_state=target['state'])
            if target['state'] in {'free', 'unknown-null'}:
                row['status'] = 'free-target' if target['state'] == 'free' else 'unknown-target'
                continue
            generation = 0 if target['state'] == 'compressed' else target['generation']
            row['target_generation'] = generation
            if reference['generation'] != generation:
                row['status'] = 'generation-mismatch'
                continue
            row['status'] = 'matched-'+target['state']+'-declaration'
            if target['state'] == 'compressed':
                row.update(target_object_stream=target['object_stream'], target_index=target['index'])
                candidate = compressed_candidate(target, source['primary_xref'], source.get('context_xref'))
                row['target_member_status'] = candidate['status']
                if candidate['status'] == 'matched-declared-member':
                    row.update(target_member_locator=candidate['member_locator'],
                               target_member_sha256=candidate['member_sha256'],
                               target_decoded_range=candidate['decoded_range'])
            else:
                row['target_offset'] = target['offset']
                row.update(ordinary_target(reference['object'], generation, target['offset'], source['primary_xref'],
                                           source.get('context_xref')))

    # Equal ranges can describe the same object (for example, an xref stream).
    # Compare distinct ranges and keep one overlap witness per range.
    target_ranges: dict[tuple[int, int], list[tuple[dict[str, Any], str]]] = {}
    for row in reference_links:
        work()
        if (span := row.get('target_object_range')) is not None:
            start = span['offset']
            target_ranges.setdefault((start, start+span['length']), []).append((row, 'target_range'))
        observation = row.get('target_stream_length_observation')
        if observation is not None and 'offset' in observation:
            scalar_span = observation['offset'], observation['end']
            target_ranges.setdefault(scalar_span, []).append((row, 'target_stream_length_range'))
    if target_ranges:
        known = set(target_ranges)
        for section in sections:
            work()
            known.add((section['offset'], section['end']))
        for item in containers.values():
            work()
            info = dict(item.details)
            known.add((info['offset'], info['end']))
        for scalar in integers.scalars.values():
            work()
            known.add((scalar['offset'], scalar['end']))
        overlaps: dict[tuple[int, int], tuple[int, int]] = {}
        active = (-1, -1)
        for span in sorted(known):
            work()
            if span[0] < active[1]:
                overlaps.setdefault(span, active)
                overlaps.setdefault(active, span)
            if span[1] > active[1]:
                active = span
        for span, rows in target_ranges.items():
            overlap = overlaps.get(span)
            for row, field in rows:
                work()
                row[field+'_status'] = 'overlap' if overlap is not None else 'disjoint-from-inspected-ranges'
                if overlap is not None:
                    row[field+'_overlap'] = {'offset': overlap[0], 'length': overlap[1]-overlap[0]}
    return {'compressed_object_links': links, 'object_stream_declared_links_assessed': True,
            'compressed_member_reference_declarations': reference_links,
            'object_stream_bound_member_reference_declarations_assessed': True,
            'compressed_object_current_links': current_links,
            'object_stream_current_declared_links_assessed': current is not None,
            'object_stream_current_links_xref': current,
            'object_stream_link_work_items': used, 'object_stream_target_header_work_bytes': header_bytes,
            'object_stream_target_body_work_bytes': body_bytes}
