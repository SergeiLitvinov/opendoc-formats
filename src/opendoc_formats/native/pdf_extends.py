"""Context-selected ObjStm collection declarations; never member inheritance or ownership proof."""

from __future__ import annotations

from collections import deque
from typing import Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError
from opendoc_formats.native.pdf_syntax import Name, Parser, Reference, SyntaxBudget
from opendoc_formats.native.pdf_xref_state import resolve_xrefs
from opendoc_formats.support.cancellation import checkpoint

Key = tuple[int, int, int]
Node = tuple[Key, int]


def discover_current_extends(data: bytes, sections: list[dict[str, Any]], candidates: dict[Key, set[int]],
                             budget: SyntaxBudget, maximum: int, window: int) -> dict[str, Any]:
    """Project current compressed-reference roots separately from historical declarations."""
    current = sections[0]['offset']
    records = resolve_xrefs(sections, current, maximum, budget=budget)['effective_xref_entries']
    used = len(records)
    index = {record['object']: record for record in records}
    roots = []
    selected: dict[Key, set[int]] = {}
    for record in records:
        checkpoint()
        budget.tokens += 1
        if budget.tokens > budget.maximum:
            raise ResourceLimitError('pdf:current-Extends: max_pdf_tokens exceeded')
        if record['state'] != 'compressed':
            continue
        if used >= maximum:
            raise ResourceLimitError('pdf:current-Extends: max_items exceeded by roots')
        used += 1
        row: dict[str, Any] = {'object': record['object'], 'object_stream': record['object_stream'],
                              'index': record['index'], 'context_xref': current, 'reference_xref': record['xref_offset'],
                              'reference_record_range': record['record_range'],
                              'ownership_proven': False, 'object_resolved': False}
        roots.append(row)
        container = index.get(record['object_stream'])
        if container is not None:
            row.update(container_xref=container['xref_offset'], container_record_range=container['record_range'],
                       container_state=container['state'], container_generation=container['generation'])
        if container is None or container['state'] in ('free', 'unknown-null'):
            row['status'] = 'missing-container'
            continue
        if container['state'] != 'uncompressed':
            row['status'] = 'container-not-uncompressed'
            continue
        if container['generation'] != 0:
            row['status'] = 'nonzero-container-generation'
            continue
        key = record['object_stream'], 0, container['offset']
        row.update(status='selected-container', container_offset=container['offset'], container_xref=container['xref_offset'])
        selected.setdefault(key, set()).add(current)
    profiles: dict[Key, bool] = {}
    result = discover_extends(data, sections, selected, budget, maximum-used, window, profiles=profiles)
    for row in roots:
        checkpoint()
        if row['status'] == 'selected-container' and not profiles[(row['object_stream'], 0, row['container_offset'])]:
            row['status'] = 'container-not-object-stream'
    for key, contexts in selected.items():
        checkpoint()
        candidates.setdefault(key, set()).update(contexts)
    valid = result['object_stream_extends_dag_valid']
    if valid is not False and any(row['status'] != 'selected-container' for row in roots):
        valid = None
    return {'object_stream_current_extends_assessed': True, 'object_stream_current_extends_xref': current,
            'object_stream_current_extends_roots': roots,
            'object_stream_current_extends_links': result['object_stream_extends_links'],
            'object_stream_current_extends_dag_valid': valid,
            'object_stream_current_extends_work_items': used+result['object_stream_extends_work_items']}


def discover_extends(data: bytes, sections: list[dict[str, Any]], candidates: dict[Key, set[int]],
                     budget: SyntaxBudget, maximum: int, window: int, *,
                     profiles: dict[Key, bool] | None = None) -> dict[str, Any]:
    """Expand physical candidates before decoding, so all declared scalar contexts are validated together."""
    used = 0

    def work(*, item: bool = False) -> None:
        nonlocal used
        checkpoint()
        budget.tokens += 1
        if budget.tokens > budget.maximum:
            raise ResourceLimitError('pdf:Extends: max_pdf_tokens exceeded')
        if item:
            if used >= maximum:
                raise ResourceLimitError('pdf:Extends: max_items exceeded')
            used += 1

    parents: dict[int, set[int]] = {}
    by_offset = {}
    for section in sections:
        work()
        by_offset[section['offset']] = section
        if section['xref_stream'] is not None:
            parents.setdefault(section['xref_stream'], set()).add(section['offset'])
    primaries = set()
    offset = sections[0]['offset'] if sections else None
    while offset is not None and offset not in primaries:
        work()
        primaries.add(offset)
        offset = by_offset[offset]['prev']
    pending = deque((key, context) for key in sorted(candidates) for context in sorted(candidates[key]))
    visited: set[Node] = set()
    dictionaries: dict[Key, tuple[bool, Reference | None]] = {}
    indexes: dict[int, dict[int, dict[str, Any]]] = {}
    rows = []
    edges: dict[Node, Node] = {}
    row_by_node = {}
    while pending:
        node = pending.popleft()
        if node in visited:
            continue
        work(item=True)
        visited.add(node)
        key, context = node
        number, generation, offset = key
        location = f'pdf:source-objstm={offset}: '
        if key not in dictionaries:
            if not 0 <= offset < len(data):
                raise InvalidDocumentError(location+'container offset outside source')
            parser = Parser(data, offset, window, budget)
            token = parser.take('integer')
            if (token.start != offset or token.value != number or parser.take('integer').value != generation
                    or parser.take().value != b'obj'):
                raise InvalidDocumentError(location+'xref container header mismatch')
            value = parser.value()
            object_stream = isinstance(value, dict) and value.get('Type') == Name('ObjStm')
            reference = value.get('Extends') if object_stream else None
            if reference is not None and not isinstance(reference, Reference):
                raise InvalidDocumentError(location+'Extends must be an indirect reference')
            dictionaries[key] = object_stream, reference
            if profiles is not None:
                profiles[key] = object_stream
        _, reference = dictionaries[key]
        if reference is None:
            continue
        work(item=True)
        row: dict[str, Any] = {'source_object': number, 'source_generation': generation, 'source_offset': offset,
                              'context_xref': context, 'target_object': reference.object,
                              'target_generation': reference.generation, 'ownership_proven': False,
                              'object_resolved': False, 'members_inherited': False, 'in_cycle': False}
        rows.append(row)
        row_by_node[node] = row
        owners = parents.get(context, set())
        if len(owners) > 1 or owners and context in primaries:
            row['status'] = 'ambiguous-primary-context'
            continue
        primary = next(iter(owners)) if owners else context
        row['primary_xref'] = primary
        if primary not in indexes:
            records = resolve_xrefs(sections, primary, maximum-used, budget=budget)['effective_xref_entries']
            used += len(records)
            indexes[primary] = {record['object']: record for record in records}
        entry = indexes[primary].get(reference.object)
        if entry is None or entry['state'] in ('free', 'unknown-null'):
            row['status'] = 'missing-target'
            continue
        row['target_xref'], row['target_record_range'] = entry['xref_offset'], entry['record_range']
        if entry['generation'] != reference.generation:
            row['status'] = 'generation-mismatch'
            continue
        if entry['state'] != 'uncompressed':
            row['status'] = 'target-not-uncompressed'
            continue
        if reference.generation != 0:
            row['status'] = 'nonzero-target-generation'
            continue
        target_key = reference.object, reference.generation, entry['offset']
        row['target_offset'] = entry['offset']
        row['status'] = 'pending-target-profile'
        edges[node] = target_key, context
        candidates.setdefault(target_key, set()).add(context)
        pending.append((target_key, context))
    for node, target in edges.items():
        work()
        row_by_node[node]['status'] = ('matched-declared-extends' if dictionaries[target[0]][0]
                                       else 'target-not-object-stream')
    # Each declaration has at most one outgoing edge. Iterative paths give linear cycle detection.
    finished: set[Node] = set()
    cyclic: set[Node] = set()
    for seed in edges:
        work()
        path: dict[Node, int] = {}
        node = seed
        while node in edges and node not in finished and node not in path:
            work()
            path[node] = len(path)
            node = edges[node]
        if node in path:
            cyclic.update(list(path)[path[node]:])
        finished.update(path)
    for node in cyclic:
        row_by_node[node]['in_cycle'] = True
    complete = all(row['status'] == 'matched-declared-extends' for row in rows)
    return {'object_stream_extends_declared_links_assessed': True, 'object_stream_extends_links': rows,
            'object_stream_extends_work_items': used,
            'object_stream_extends_dag_valid': False if cyclic else True if complete else None}
