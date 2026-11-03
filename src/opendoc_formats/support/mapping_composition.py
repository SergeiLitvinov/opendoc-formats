"""Bounded composition of explicit occurrence relations using OpenDoc's public codec."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from opendoc_model import (
    DiagnosticIssue,
    DocumentModel,
    IssueSeverity,
    MappingReplacement,
    ObjectMapping,
    ObjectMappingEntry,
    PreservationState,
    ResourceKind,
    object_mapping_from_dict,
    object_mapping_to_dict,
    validate_object_mapping,
)

MAX_OCCURRENCES = 10_000
MAX_BRIDGE_EDGES = 100_000


def compose_object_mappings(
    first: ObjectMapping,
    second: ObjectMapping,
    bridges: Mapping[str, tuple[str, ...] | None],
    *,
    source: DocumentModel | None = None,
    target: DocumentModel | None = None,
) -> ObjectMapping:
    """Compose caller-declared first-target → second-source links; never infer them from pixels or resource IDs.

    Missing/None bridges are unknown; () explicitly declares removal. Splits and merges form one connected group.
    References to the middle snapshot are never exported as references to the original source or final target.
    """
    first = object_mapping_from_dict(object_mapping_to_dict(first))
    second = object_mapping_from_dict(object_mapping_to_dict(second))
    if first.publication not in ('staged', 'published'):
        raise ValueError('Composition requires a materialized first result')
    validate_object_mapping(first, source=source)
    validate_object_mapping(second, target=target)
    if any(len(values) > MAX_OCCURRENCES for mapping in (first, second)
           for values in (mapping.sources, mapping.targets, mapping.entries)):
        raise ValueError('Composition occurrence limit exceeded')
    if not isinstance(bridges, Mapping) or len(bridges) > MAX_OCCURRENCES:
        raise ValueError('Invalid or excessive composition bridges')
    first_targets = {item.id for item in first.targets}
    second_sources = {item.id for item in second.sources}
    copied = {}
    edge_count = 0
    for key, values in bridges.items():
        if key not in first_targets:
            raise ValueError('Bridge refers to an unknown first target')
        if values is not None:
            if (type(values) is not tuple or len(set(values)) != len(values)
                    or any(value not in second_sources for value in values)):
                raise ValueError('Bridge requires unique known second source IDs')
            edge_count += len(values)
            if edge_count > MAX_BRIDGE_EDGES:
                raise ValueError('Composition bridge edge limit exceeded')
        copied[key] = values
    first_owner = {key: index for index, entry in enumerate(first.entries) for key in entry.target_ids or ()}
    second_owner = {key: index for index, entry in enumerate(second.entries) for key in entry.source_ids}
    if set(copied) - set(first_owner):
        raise ValueError('Bridge target is outside the first assessed groups')
    parent = list(range(len(first.entries) + len(second.entries)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    covered = set()
    offset = len(first.entries)
    for key, values in copied.items():
        for value in values or ():
            if value not in second_owner:
                raise ValueError('Bridge source is outside the second assessed groups')
            covered.add(value)
            parent[root(first_owner[key])] = root(offset + second_owner[value])
    groups: dict[int, tuple[list[int], list[int]]] = {}
    for index in range(len(first.entries)):
        groups.setdefault(root(index), ([], []))[0].append(index)
    for index in range(len(second.entries)):
        key = root(offset + index)
        if key in groups:
            groups[key][1].append(index)
    active = second.publication in ('staged', 'published')
    output_entries = []
    used_targets = set()
    complete = active and first.assessment_complete and second.assessment_complete
    targets_by_id = {item.id: item for item in second.targets}
    for number, (left_indices, right_indices) in enumerate(groups.values()):
        left = [first.entries[index] for index in left_indices]
        right = [second.entries[index] for index in right_indices]
        source_ids = tuple(key for entry in left for key in entry.source_ids)
        unknown = any(entry.target_ids is None for entry in left + right)
        removed = any(entry.target_ids == () for entry in left + right)
        for entry in left:
            for key in entry.target_ids or ():
                values = copied.get(key)
                unknown |= values is None
                removed |= values == ()
        unknown |= any(set(entry.source_ids) - covered for entry in right)
        final_ids = tuple(key for entry in right for key in entry.target_ids or ())
        states = {entry.state for entry in left + right}
        replacement = None
        if not active:
            state = PreservationState.REJECTED if second.publication in ('rejected', 'invalidated') else PreservationState.OPAQUE
            final_ids = None
            reason = 'final-result-unpublished'
        elif unknown:
            final_ids = None
            state = PreservationState.OPAQUE
            reason = 'incomplete-bridge-coverage'
            complete = False
        elif not final_ids:
            state = PreservationState.REJECTED if PreservationState.REJECTED in states else PreservationState.LOST
            reason = 'declared-removal-or-absent-targets'
        elif removed or states & {PreservationState.LOST, PreservationState.REJECTED, PreservationState.OPAQUE}:
            state = PreservationState.OPAQUE
            reason = 'partial-loss-or-opaque-stage'
        elif PreservationState.VISUAL in states:
            state = PreservationState.VISUAL
            reason = 'visual-stage-in-chain'
        else:
            state = PreservationState.SEMANTIC
            reason = 'declared-semantic-chain'
        if final_ids:
            used_targets.update(final_ids)
            if state is not PreservationState.SEMANTIC and target is not None:
                resources = [target.resources.get(targets_by_id[key].resource_id) for key in final_ids]
                if all(resource is not None and resource.kind is ResourceKind.RASTER_IMAGE for resource in resources):
                    replacement = MappingReplacement('raster', resources[0].id, 'target')
            if state is PreservationState.VISUAL and replacement is None:
                complete = False
        output_entries.append(ObjectMappingEntry(
            f'composed-{number}', source_ids, state,
            DiagnosticIssue('mapping.composed', IssueSeverity.INFO if state is PreservationState.SEMANTIC
                            else IssueSeverity.ERROR if state is PreservationState.REJECTED else IssueSeverity.LOSS,
                            'Preservation across explicitly joined conversion stages', left[0].issue.location, reason=reason),
            target_ids=final_ids, replacement=replacement,
            extra={'first_entries': [entry.id for entry in left], 'second_entries': [entry.id for entry in right],
                   'partial_loss': removed and bool(final_ids),
                   'stage_states': [entry.state.value for entry in left + right],
                   'stage_locations': [entry.issue.location for entry in left + right],
                   'stage_issues': [{'code': entry.issue.code, 'reason': entry.issue.reason} for entry in left + right]},
        ))
    result = ObjectMapping(
        sources=first.sources, targets=tuple(item for item in second.targets if item.id in used_targets),
        entries=tuple(output_entries), publication=second.publication, output_format=second.output_format,
        result_id=second.result_id, publication_issue=second.publication_issue, assessment_complete=complete,
        extra={'profile': 'explicit-mapping-composition-v1', 'bridge_evidence': 'caller-declaration',
               'scope': 'first-declared-sources', 'first_result_id': first.result_id,
               'second_result_id': second.result_id, 'split_merge': 'connected-explicit-groups',
               'bridges': {key: list(values) if values is not None else None for key, values in copied.items()}},
    )
    # Unassessed original sources keep the result explicitly incomplete.
    if {key for entry in result.entries for key in entry.source_ids} != {item.id for item in result.sources}:
        result = replace(result, assessment_complete=False)
    validate_object_mapping(result, source=source, target=target)
    return object_mapping_from_dict(object_mapping_to_dict(result))
