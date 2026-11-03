"""Independent PDF collection declarations: selected targets, no inherited members, bounded graph work."""

import builtins
import hashlib
import json
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError


def stream(member, title, target=None, generation=0):
    raw = f'{member} 0 << /Title ({title}) >>'.encode()
    extends = f' /Extends {target} {generation} R' if target is not None else ''
    return (f'<< /Type /ObjStm /N 1 /First {len(str(member))+3} /Length {len(raw)}{extends} >>\nstream\n'.encode()
            +raw+b'\nendstream')


def xref(data, number, records, *, previous=None):
    offset = len(data)
    records = {**records, number: (1, offset, 0)}
    raw = b''.join(bytes([kind])+target.to_bytes(4, 'big')+extra.to_bytes(2, 'big')
                   for kind, target, extra in records.values())
    ranges = ' '.join(f'{item} 1' for item in records)
    prev = f'/Prev {previous} ' if previous is not None else ''
    data += (f'{number} 0 obj\n<< /Type /XRef /Size {max(101,max(records)+1)} /Root 1 0 R /Info 100 0 R '
             f'/W [1 4 2] /Index [{ranges}] {prev}/Length {len(raw)} >>\nstream\n'.encode()+raw
             +f'\nendstream\nendobj\nstartxref\n{offset}\n%%EOF\n'.encode())
    return bytes(data), offset


def collection(targets=(5, None), *, target_state='normal', reference_generation=0, hybrid=False):
    data = bytearray(b'%PDF-1.7\n')
    bodies = {1: b'<< /Type /Catalog /Pages 2 0 R >>', 2: b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
              3: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] >>'}
    bodies.update({4+index: stream(100+index, 'Own '+str(index), target,
                                 reference_generation if index == 0 else 0) for index, target in enumerate(targets)})
    if target_state == 'ordinary':
        bodies[5] = b'<< /Type /Ordinary >>'
    locations, records = {}, {0: (0, 0, 65535)}
    for number, body in bodies.items():
        generation = 1 if number == 5 and target_state == 'generation' else 0
        locations[number] = len(data)
        records[number] = (1, len(data), generation)
        data += f'{number} {generation} obj\n'.encode()+body+b'\nendobj\n'
    if target_state == 'free':
        records[5] = (0, 0, 1)
    if target_state == 'compressed':
        records[5] = (2, 4, 0)
    records[100] = (2, 4, 0)  # Other containers have no type-2 users and must be discovered through Extends.
    source, primary = xref(data, 80, records)
    if hybrid:
        supplement = primary
        primary = len(source)
        source += (f'xref\n80 1\n{supplement:010} 00000 n \n'
                   f'trailer\n<< /Size 104 /Root 1 0 R /Info 100 0 R /XRefStm {supplement} >>\n'
                   f'startxref\n{primary}\n%%EOF\n').encode()
    return source, locations, primary


def inspect(source, **kwargs):
    return inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, pdf_object_streams=True, **kwargs)


@pytest.mark.parametrize('hybrid', [False, True])
def test_unreferenced_parent_chain_is_discovered_with_exact_source_bytes_and_no_inheritance(hybrid):
    source, offsets, primary = collection((5, 6, None), hybrid=hybrid)
    before = hashlib.sha256(source).hexdigest()
    snapshot = inspect(source, capture=True)
    details = dict(snapshot.details)
    links = details['object_stream_extends_links']
    assert [(row['source_object'], row['target_object']) for row in links] == [(4, 5), (5, 6)]
    assert all(row['status'] == 'matched-declared-extends' and row['primary_xref'] == primary for row in links)
    assert details['object_stream_extends_dag_valid'] is True
    assert details['decoded_object_streams'] == 3 and len(details['compressed_object_references']) == 1
    assert all(not row['members_inherited'] and not row['ownership_proven'] and not row['object_resolved'] for row in links)
    containers = [item for item in snapshot.items if item.kind == 'pdf-object-stream']
    for container in containers:
        info = dict(container.details)
        assert container.payload == source[offsets[info['object']]:info['end']]
        assert not info['active_resolution'] and not info['extends_resolved']
    assert len([item for item in snapshot.items if item.kind == 'pdf-compressed-object']) == 3
    assert not details['assessment_complete'] and hashlib.sha256(source).hexdigest() == before
    assert inspect(source).to_dict() == snapshot.to_dict()
    json.dumps(snapshot.to_dict())
    if not hybrid:
        pypdf = pytest.importorskip('pypdf')
        reader = pypdf.PdfReader(BytesIO(source), strict=True)
        assert reader.metadata.title == 'Own 0' and len(reader.pages) == 1


@pytest.mark.parametrize('state,generation,status', [
    ('free', 0, 'missing-target'), ('generation', 0, 'generation-mismatch'),
    ('generation', 1, 'nonzero-target-generation'), ('compressed', 0, 'target-not-uncompressed'),
    ('ordinary', 0, 'target-not-object-stream'),
])
def test_unresolved_target_profiles_are_located_without_repair_or_member_substitution(state, generation, status):
    source, _, _ = collection(target_state=state, reference_generation=generation)
    details = dict(inspect(source).details)
    row, = details['object_stream_extends_links']
    assert row['source_object'] == 4 and row['target_object'] == 5 and row['status'] == status
    assert details['object_stream_extends_dag_valid'] is None
    assert not row['ownership_proven'] and not row['members_inherited']


@pytest.mark.parametrize('targets,cycles', [((4,), [4]), ((5, 4), [4, 5]), ((5, 6, 5), [5, 6])])
def test_self_and_multi_node_cycles_are_finite_and_only_cycle_edges_are_marked(targets, cycles):
    details = dict(inspect(collection(targets)[0]).details)
    assert details['object_stream_extends_dag_valid'] is False
    assert [row['source_object'] for row in details['object_stream_extends_links'] if row['in_cycle']] == cycles


def test_incremental_contexts_select_their_own_parent_version():
    original, offsets, previous = collection()
    source = bytearray(original)
    records = {100: (2, 4, 0)}
    for number, body in ((5, stream(101, 'New parent')), (4, stream(100, 'New child', 5))):
        records[number] = (1, len(source), 0)
        source += f'{number} 0 obj\n'.encode()+body+b'\nendobj\n'
    source, current = xref(source, 120, records, previous=previous)
    links = dict(inspect(source).details)['object_stream_extends_links']
    by_context = {row['primary_xref']: row for row in links}
    assert by_context[previous]['target_offset'] == offsets[5]
    assert by_context[current]['target_offset'] == records[5][1]
    assert len(links) == 2 and all(row['status'] == 'matched-declared-extends' for row in links)
    pypdf = pytest.importorskip('pypdf')
    assert pypdf.PdfReader(BytesIO(source), strict=True).metadata.title == 'New child'


def test_inherited_source_declaration_is_not_silently_promoted_to_latest_active_scope():
    original, offsets, previous = collection()
    source = bytearray(original)
    replacement = len(source)
    source += b'5 0 obj\n'+stream(101, 'New parent')+b'\nendobj\n'
    source, current = xref(source, 120, {5: (1, replacement, 0), 100: (2, 4, 0)}, previous=previous)
    details = dict(inspect(source).details)
    row, = details['object_stream_extends_links']
    assert row['context_xref'] == previous and row['primary_xref'] != current
    assert row['target_offset'] == offsets[5] and row['target_offset'] != replacement
    assert not row['object_resolved'] and not details['assessment_complete']


@pytest.mark.parametrize('quota', ['max_items', 'max_pdf_tokens'])
def test_exact_shared_quota_boundary_and_one_below_refusal(quota):
    source = collection((5, 6, None))[0]
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
    with pytest.raises(ResourceLimitError, match=quota):
        inspect(source, limits=replace(AnatomyLimits(), **{quota: high-1}))


def test_cancellation_and_no_backend_imports_preserve_source(tmp_path, monkeypatch):
    from opendoc_formats.native import pdf_extends

    source = collection()[0]
    path = tmp_path/'own.pdf'
    path.write_bytes(source)
    native_import = builtins.__import__

    def minimal(name, *args, **kwargs):
        if name.split('.')[0] in {'pypdf', 'pymupdf', 'fitz', 'pdfplumber', 'PIL', 'fontTools'}:
            raise AssertionError('Unexpected backend: '+name)
        return native_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', minimal)
    stop, calls = Event(), 0
    native_checkpoint = pdf_extends.checkpoint

    def cancel():
        nonlocal calls
        calls += 1
        if calls == 7:
            stop.set()
        native_checkpoint()

    with monkeypatch.context() as context:
        context.setattr(pdf_extends, 'checkpoint', cancel)
        with pytest.raises(OperationCancelledError):
            inspect(path, cancelled=stop.is_set)
    assert path.read_bytes() == source and calls == 7
    assert dict(inspect(path).details)['object_stream_extends_dag_valid']
