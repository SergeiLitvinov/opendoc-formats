"""Context-specific declared ObjStm links, without claiming source ownership or active bodies."""

from __future__ import annotations

from collections.abc import Iterator
from itertools import chain
from typing import TYPE_CHECKING, Any

from opendoc_formats.errors import ResourceLimitError
from opendoc_formats.native.pdf_syntax import SyntaxBudget
from opendoc_formats.native.pdf_xref_state import resolve_xrefs
from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import BinaryItem


def declared_object_links(sections: list[dict[str, Any]], references: list[dict[str, int]],
                          items: list[BinaryItem], budget: SyntaxBudget, maximum: int, *,
                          current_parameters: dict[tuple[int, int, int], dict[str, Any]] | None = None) -> dict[str, Any]:
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
    for item in items:
        work()
        info = dict(item.details)
        if item.kind in ('pdf-object-stream', 'pdf-non-object-stream-candidate'):
            containers[(info['object'], info['generation'], info['offset'])] = item
        elif item.kind == 'pdf-compressed-object':
            members[(info['container_offset'], info['index'])] = item
    indexes: dict[int, dict[int, dict[str, Any]]] = {}
    used = 0
    links: list[dict[str, Any]] = []
    current_links: list[dict[str, Any]] = []
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
        index = indexes[primary]
        own = index.get(reference['object'])
        if own is None or own['xref_offset'] != context:
            row['status'] = 'shadowed-reference'
            continue
        row['reference_record_range'] = own['record_range']
        container = index.get(reference['object_stream'])
        if container is None or container['state'] in ('free', 'unknown-null'):
            row['status'] = 'missing-container'
            continue
        row['container_xref'] = container['xref_offset']
        row['container_record_range'] = container['record_range']
        if container['state'] != 'uncompressed':
            row['status'] = 'container-not-uncompressed'
            continue
        row['container_offset'] = container['offset']
        row['container_generation'] = container['generation']
        if container['generation'] != 0:
            row['status'] = 'nonzero-container-generation'
            continue
        key = reference['object_stream'], container['generation'], container['offset']
        physical = containers.get(key)
        if physical is None:
            row['status'] = 'container-not-inspected'
            continue
        if physical.kind != 'pdf-object-stream':
            row['status'] = 'container-not-object-stream'
            continue
        row['container_locator'] = physical.locator
        row['container_sha256'] = physical.sha256
        observations = dict(physical.details).get('source_integer_observations', {})
        assessment = current_parameters.get(key) if current_parameters is not None and current_context is not None else None
        if assessment is not None:
            row['current_parameters'] = assessment
            if assessment['status'] != 'matched-decoded-parameters':
                row['status'] = 'container-'+assessment['status']
                continue
        elif current_context is not None and any(
            not any(observation['primary_xref'] == current_context for observation in values)
            for values in observations.values()
        ):
            row['status'] = 'container-parameters-not-assessed-in-current-context'
            continue
        member = members.get((container['offset'], reference['index']))
        if member is None:
            row['status'] = 'index-out-of-range'
            continue
        info = dict(member.details)
        row['member_object'] = info['object']
        if info['object'] != reference['object']:
            row['status'] = 'object-number-mismatch'
            continue
        row.update(status='matched-declared-member', member_locator=member.locator, member_sha256=member.sha256,
                   decoded_range={'start': info['decoded_start'], 'end': info['decoded_end']})
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
            else:
                row['target_offset'] = target['offset']
    return {'compressed_object_links': links, 'object_stream_declared_links_assessed': True,
            'compressed_member_reference_declarations': reference_links,
            'object_stream_bound_member_reference_declarations_assessed': True,
            'compressed_object_current_links': current_links,
            'object_stream_current_declared_links_assessed': current is not None,
            'object_stream_current_links_xref': current,
            'object_stream_link_work_items': used}
