"""Explicit group relations, native format cycles and publication refusal."""

import json
from dataclasses import replace

import pytest
from opendoc_model import (
    DiagnosticIssue,
    DocumentModel,
    IssueSeverity,
    MappingReplacement,
    ObjectMapping,
    ObjectMappingEntry,
    ObjectOccurrence,
    PreservationState,
    Provenance,
    Resource,
    ResourceKind,
    document_from_json,
    document_to_json,
    object_mapping_from_dict,
    object_mapping_to_dict,
    validate_object_mapping,
    with_mapping_publication,
)

from opendoc_formats import ExportOptions, compose_object_mappings, get_object_mapping, read_document, write_document
from tests.writers.test_pdf_mapping import _document


def _occ(name):
    return ObjectOccurrence(name, provenance=Provenance('own-test'))


def _entry(name, sources, targets, state=PreservationState.SEMANTIC):
    return ObjectMappingEntry(name, sources, state, DiagnosticIssue(
        'own-stage', IssueSeverity.INFO if state is PreservationState.SEMANTIC else IssueSeverity.LOSS,
        'Own declaration', 'sections[0].blocks[0]', reason='own-declaration',
    ), targets)


def _maps():
    first = ObjectMapping(sources=(_occ('a'),), targets=(_occ('middle'),),
                          entries=(_entry('first', ('a',), ('middle',)),), publication='published',
                          output_format='middle', result_id='own-first', assessment_complete=True)
    second = ObjectMapping(sources=(_occ('b'),), targets=(_occ('final'),),
                           entries=(_entry('second', ('b',), ('final',)),), publication='published',
                           output_format='final', result_id='own-final', assessment_complete=True)
    return first, second


def test_semantic_chain_keeps_final_identity_and_roundtrips():
    first, second = _maps()
    before = object_mapping_to_dict(first), object_mapping_to_dict(second)
    composed = compose_object_mappings(first, second, {'middle': ('b',)})
    assert composed.assessment_complete and composed.entries[0].state is PreservationState.SEMANTIC
    assert composed.result_id == 'own-final' and composed.publication == 'published'
    assert composed.sources == first.sources and composed.targets == second.targets
    for _ in range(2):
        composed = object_mapping_from_dict(json.loads(json.dumps(object_mapping_to_dict(composed))))
    assert (object_mapping_to_dict(first), object_mapping_to_dict(second)) == before


@pytest.mark.parametrize('bridges', [{}, {'middle': None}])
def test_missing_bridge_is_unknown_not_lost_or_guessed(bridges):
    first, second = _maps()
    composed = compose_object_mappings(first, second, bridges)
    assert not composed.assessment_complete and not composed.targets
    assert composed.entries[0].target_ids is None and composed.entries[0].state is PreservationState.OPAQUE


def test_explicit_removal_is_known_lost():
    first, second = _maps()
    composed = compose_object_mappings(first, second, {'middle': ()})
    assert composed.assessment_complete and not composed.targets
    assert composed.entries[0].state is PreservationState.LOST and composed.entries[0].target_ids == ()
    assert composed.entries[0].issue.location


def test_explicit_split_and_merge_are_connected_groups():
    first, second = _maps()
    second = replace(second, sources=(_occ('b'), _occ('c')),
                     targets=(_occ('x'), _occ('y')),
                     entries=(_entry('b', ('b',), ('x',)), _entry('c', ('c',), ('y',))))
    split = compose_object_mappings(first, second, {'middle': ('b', 'c')})
    assert split.assessment_complete and split.entries[0].target_ids == ('x', 'y')
    first = replace(first, sources=(_occ('a'), _occ('d')),
                    targets=(_occ('middle'), _occ('other')),
                    entries=(_entry('a', ('a',), ('middle',)), _entry('d', ('d',), ('other',))))
    merged = compose_object_mappings(first, second, {'middle': ('b',), 'other': ('b',)})
    assert merged.assessment_complete and len(merged.entries) == 1
    assert merged.entries[0].source_ids == ('a', 'd') and merged.entries[0].target_ids == ('x',)


def test_foreign_merge_input_is_unknown_without_false_coverage():
    first, second = _maps()
    second = replace(second, sources=(_occ('b'), _occ('outside')),
                     entries=(_entry('merge', ('b', 'outside'), ('final',)),))
    composed = compose_object_mappings(first, second, {'middle': ('b',)})
    assert not composed.assessment_complete and composed.entries[0].target_ids is None


def test_partial_removal_keeps_survivor_with_opaque_loss():
    first, second = _maps()
    first = replace(first, targets=(_occ('middle'), _occ('removed')),
                    entries=(_entry('split', ('a',), ('middle', 'removed')),))
    composed = compose_object_mappings(first, second, {'middle': ('b',), 'removed': ()})
    assert composed.assessment_complete and composed.entries[0].target_ids == ('final',)
    assert composed.entries[0].state is PreservationState.OPAQUE and composed.entries[0].extra['partial_loss']


def test_visual_loss_cannot_become_semantic_or_reuse_middle_replacement():
    first, second = _maps()
    first = replace(first, entries=(replace(first.entries[0], state=PreservationState.VISUAL,
                                           issue=DiagnosticIssue('vector-loss', IssueSeverity.LOSS, 'Rasterized',
                                                                 reason='rasterized'),
                                           replacement=MappingReplacement('raster', 'middle-png', 'target')),))
    second = replace(second, targets=(ObjectOccurrence('final', resource_id='actual-png'),))
    target = DocumentModel(resources={
        'actual-png': Resource('actual-png', ResourceKind.RASTER_IMAGE, 'image/png', data=b'own-raster-declaration'),
    })
    composed = compose_object_mappings(first, second, {'middle': ('b',)}, target=target)
    assert composed.assessment_complete and composed.entries[0].state is PreservationState.VISUAL
    assert composed.entries[0].replacement == MappingReplacement('raster', 'actual-png', 'target')
    unknown = compose_object_mappings(first, second, {'middle': ('b',)})
    assert not unknown.assessment_complete and unknown.entries[0].replacement is None


@pytest.mark.parametrize('state', ['rejected', 'invalidated', 'attempted'])
def test_unpublished_second_cannot_claim_targets(state):
    first, second = _maps()
    second = with_mapping_publication(second, state)
    composed = compose_object_mappings(first, second, {'middle': ('b',)})
    assert composed.publication == state and not composed.targets and not composed.assessment_complete
    assert composed.entries[0].target_ids is None and composed.entries[0].replacement is None


@pytest.mark.parametrize('bridges', [{'unknown': ('b',)}, {'middle': ('unknown',)},
                                    {'middle': ('b', 'b')}, {'middle': ['b']}])
def test_invalid_bridges_are_rejected(bridges):
    first, second = _maps()
    with pytest.raises(ValueError):
        compose_object_mappings(first, second, bridges)


def test_limits_and_unmaterialized_first_are_rejected(monkeypatch):
    from opendoc_formats.support import mapping_composition as module

    first, second = _maps()
    with pytest.raises(ValueError):
        compose_object_mappings(with_mapping_publication(first, 'rejected'), second, {})
    monkeypatch.setattr(module, 'MAX_BRIDGE_EDGES', 0)
    with pytest.raises(ValueError, match='edge limit'):
        compose_object_mappings(first, second, {'middle': ('b',)})
    monkeypatch.setattr(module, 'MAX_OCCURRENCES', 0)
    with pytest.raises(ValueError, match='occurrence limit'):
        compose_object_mappings(first, second, {})


def test_native_two_cycles_reorder_delete_and_quality_refusal(tmp_path):
    original = _document()
    initial = tmp_path / 'first.pdf'
    first = get_object_mapping(write_document(original, initial))
    assert all(item.node_id and item.resource_id for item in first.targets)
    before = object_mapping_to_dict(first)
    current = initial
    composed = first
    for cycle in range(2):
        middle = document_from_json(document_to_json(read_document(current).document))
        middle.sections[0].blocks.reverse()
        output = tmp_path / f'cycle-{cycle}.pdf'
        report = write_document(middle, output)
        assert report.success, report.to_dict()
        second = get_object_mapping(report)
        validate_object_mapping(second, source=middle, target=read_document(output).document)
        source_nodes = {item.node_id: item.id for item in second.sources}
        bridges = {item.id: (source_nodes[item.node_id],) for item in composed.targets}
        composed = compose_object_mappings(composed, second, bridges, source=original,
                                           target=read_document(output).document)
        assert composed.assessment_complete and all(entry.state is PreservationState.VISUAL for entry in composed.entries)
        assert len(composed.sources) == len(composed.targets) == 2
        composed = object_mapping_from_dict(json.loads(json.dumps(object_mapping_to_dict(composed))))
        current = output
    middle = read_document(current).document
    middle.sections[0].blocks.pop()
    final = tmp_path / 'deleted.pdf'
    second = get_object_mapping(write_document(middle, final))
    source_nodes = {item.node_id: item.id for item in second.sources}
    bridges = {item.id: (source_nodes[item.node_id],) if item.node_id in source_nodes else () for item in composed.targets}
    deleted = compose_object_mappings(composed, second, bridges, source=original, target=read_document(final).document)
    assert deleted.assessment_complete and len(deleted.sources) == 2 and len(deleted.targets) == 1
    assert {entry.state for entry in deleted.entries} == {PreservationState.LOST, PreservationState.VISUAL}
    previous = final.read_bytes()

    def reject(report, staged):
        next_map = get_object_mapping(report)
        source_nodes = {item.node_id: item.id for item in next_map.sources}
        links = {item.id: (source_nodes[item.node_id],) if item.node_id in source_nodes else () for item in composed.targets}
        candidate = compose_object_mappings(composed, next_map, links, source=original, target=read_document(staged).document)
        report.metrics['object_mapping'] = object_mapping_to_dict(candidate)
        return all(entry.state is PreservationState.SEMANTIC for entry in candidate.entries)

    refused = write_document(middle, final, options=ExportOptions(quality_gate=reject))
    assert not refused.success and final.read_bytes() == previous
    rejected = get_object_mapping(refused)
    assert rejected.publication == 'rejected' and rejected.sources == composed.sources and not rejected.targets
    assert all(entry.replacement is None and entry.target_ids is None for entry in rejected.entries)
    assert object_mapping_to_dict(first) == before and initial.exists()
