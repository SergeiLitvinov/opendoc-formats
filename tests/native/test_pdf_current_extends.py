"""Current collection declarations remain separate from physical historical contexts."""

import hashlib
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from tests.native.test_pdf_extends import collection, inspect, stream, xref


def revised(*, state='parent', generation=0, redeclare_user=True):
    original, offsets, previous = collection()
    source = bytearray(original)
    records = {100: (2, 4, 0)} if redeclare_user else {}
    object_number = 4 if state.startswith('root-') else 5
    target = len(source)
    if state in ('free', 'root-free'):
        records[object_number] = (0, 0, 1)
    elif state == 'unknown':
        records[object_number] = (3, 0, 0)
    elif state == 'compressed':
        records[object_number] = (2, 4, 0)
    elif state == 'no-users':
        records[100] = (0, 0, 1)
    else:
        body = b'42' if state in ('ordinary', 'root-ordinary') else stream(101, 'New parent', 4 if state == 'cycle' else None)
        source += f'{object_number} {generation} obj\n'.encode()+body+b'\nendobj\n'
        records[object_number] = (1, target, generation)
    source, current = xref(source, 120, records, previous=previous)
    return source, offsets, previous, current, target


def test_inherited_container_follows_current_target_without_overwriting_historical_link():
    source, offsets, previous, current, target = revised()
    before = hashlib.sha256(source).hexdigest()
    snapshot = inspect(source, capture=True)
    details = dict(snapshot.details)
    historical, = details['object_stream_extends_links']
    selected, = details['object_stream_current_extends_links']
    assert historical['primary_xref'] == previous and historical['target_offset'] == offsets[5]
    assert selected['primary_xref'] == current and selected['source_offset'] == offsets[4]
    assert selected['target_offset'] == target and selected['target_offset'] != historical['target_offset']
    root, = details['object_stream_current_extends_roots']
    assert root['reference_xref'] == current and root['container_xref'] == previous
    assert root['container_offset'] == offsets[4] and root['status'] == 'selected-container'
    assert details['object_stream_current_extends_dag_valid'] is True and details['decoded_object_streams'] == 3
    containers = {dict(item.details)['offset']: item for item in snapshot.items if item.kind == 'pdf-object-stream'}
    assert dict(containers[offsets[4]].details)['historical_xref_contexts'] == [previous]
    assert dict(containers[offsets[4]].details)['xref_sections'] == sorted([previous, current])
    assert dict(containers[target].details)['historical_xref_contexts'] == []
    for container in containers.values():
        value = dict(container.details)
        assert container.payload == source[value['offset']:value['end']]
        assert not value['active_resolution'] and not value['ownership_proven']
    assert not selected['members_inherited'] and not selected['object_resolved']
    assert hashlib.sha256(source).hexdigest() == before and not details['assessment_complete']
    pypdf = pytest.importorskip('pypdf')
    assert pypdf.PdfReader(BytesIO(source), strict=True).metadata.title == 'Own 0'


def test_compressed_user_can_also_be_inherited_without_a_new_reference_record():
    source, offsets, previous, current, target = revised(redeclare_user=False)
    details = dict(inspect(source).details)
    root, = details['object_stream_current_extends_roots']
    link, = details['object_stream_current_extends_links']
    assert root['reference_xref'] == previous and root['container_xref'] == previous
    assert root['context_xref'] == current and root['container_offset'] == offsets[4]
    assert link['target_offset'] == target and link['target_xref'] == current


@pytest.mark.parametrize('state,generation,status', [
    ('free', 0, 'missing-target'), ('unknown', 0, 'missing-target'), ('compressed', 0, 'target-not-uncompressed'),
    ('ordinary', 0, 'target-not-object-stream'), ('parent', 1, 'generation-mismatch'),
])
def test_current_target_failure_never_resurrects_old_parent(state, generation, status):
    source, offsets, previous, current, _ = revised(state=state, generation=generation)
    details = dict(inspect(source).details)
    historical, = details['object_stream_extends_links']
    selected, = details['object_stream_current_extends_links']
    assert historical['target_offset'] == offsets[5] and historical['primary_xref'] == previous
    assert selected['primary_xref'] == current and selected['status'] == status
    assert details['object_stream_current_extends_dag_valid'] is None
    assert details['object_stream_extends_dag_valid'] is True


def test_cycle_created_by_parent_revision_is_only_present_in_current_graph():
    details = dict(inspect(revised(state='cycle')[0]).details)
    assert details['object_stream_extends_dag_valid'] is True
    assert details['object_stream_current_extends_dag_valid'] is False
    assert [row['source_object'] for row in details['object_stream_current_extends_links'] if row['in_cycle']] == [4, 5]
    assert not any(row['in_cycle'] for row in details['object_stream_extends_links'])


@pytest.mark.parametrize('state,status', [('root-free', 'missing-container'), ('root-ordinary', 'container-not-object-stream')])
def test_current_compressed_roots_are_not_claimed_to_be_valid_containers(state, status):
    details = dict(inspect(revised(state=state)[0]).details)
    root, = details['object_stream_current_extends_roots']
    assert root['status'] == status and not root['object_resolved']
    assert details['object_stream_current_extends_links'] == []
    assert details['object_stream_current_extends_dag_valid'] is None


def test_deleted_compressed_users_leave_an_empty_current_projection():
    details = dict(inspect(revised(state='no-users')[0]).details)
    assert details['object_stream_extends_links'] and details['object_stream_current_extends_assessed']
    assert details['object_stream_current_extends_roots'] == [] and details['object_stream_current_extends_links'] == []


@pytest.mark.parametrize('hybrid', [False, True])
def test_current_graph_with_no_revision_uses_selected_primary_not_a_guessed_supplement(hybrid):
    source, _, primary = collection((5, 6, None), hybrid=hybrid)
    details = dict(inspect(source).details)
    assert details['object_stream_current_extends_xref'] == primary
    assert all(row['primary_xref'] == primary for row in details['object_stream_current_extends_links'])


@pytest.mark.parametrize('quota', ['max_items', 'max_pdf_tokens', 'max_total_bytes'])
def test_current_projection_has_an_exact_shared_quota_for_both_parent_versions(quota):
    source = revised()[0]
    baseline = inspect(source).to_dict()
    low, high = 0, 200000
    while low+1 < high:
        middle = (low+high)//2
        try:
            observed = inspect(source, limits=replace(AnatomyLimits(), **{quota: middle})).to_dict()
        except ResourceLimitError:
            low = middle
        else:
            assert observed == baseline
            high = middle
    assert inspect(source, limits=replace(AnatomyLimits(), **{quota: high})).to_dict() == baseline
    # The decoder receives min(part, remaining total); here the total quota is the binding byte budget.
    with pytest.raises(ResourceLimitError, match='byte budget' if quota == 'max_total_bytes' else quota):
        inspect(source, limits=replace(AnatomyLimits(), **{quota: high-1}))


def test_cancel_in_current_pass_preserves_source_and_does_not_leak_scope(tmp_path, monkeypatch):
    from opendoc_formats.native import pdf_extends
    from opendoc_formats.native.pdf_extends import discover_current_extends

    source = revised()[0]
    path = tmp_path/'own.pdf'
    path.write_bytes(source)
    stop = Event()

    def cancel(*args, **kwargs):
        stop.set()
        return discover_current_extends(*args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(pdf_extends, 'discover_current_extends', cancel)
        with pytest.raises(OperationCancelledError):
            inspect(path, cancelled=stop.is_set)
    assert path.read_bytes() == source and dict(inspect(path).details)['object_stream_current_extends_assessed']
