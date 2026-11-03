"""Historical xref occurrences bind exact container versions, never just matching object numbers."""

import builtins
import hashlib
import json
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from tests.native.test_pdf_object_streams import custom_stream_pdf
from tests.native.test_pdf_xref_state import hybrid_pdf, latest


def inspect(source, **kwargs):
    return inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, pdf_object_streams=True, **kwargs)


def revision(source, *, state='stream', index=0, member=7):
    """Hand-authored bytes and xref records; no Formats/PDF writer creates originals."""
    previous, target = latest(source), len(source)
    records = {}
    if state in ('stream', 'ordinary', 'nonzero'):
        generation = 2 if state == 'nonzero' else 0
        if state == 'stream':
            raw = f'{member} 0 (New own member)'.encode()
            body = (b'<< /Type /ObjStm /N 1 /First 4 /Length '+str(len(raw)).encode()
                    +b' >>\nstream\n'+raw+b'\nendstream')
        else:
            body = b'42'
        source += f'4 {generation} obj\n'.encode()+body+b'\nendobj\n'
        records[4] = (1, target, generation)
    elif state == 'free':
        records[4] = (0, 0, 1)
    elif state == 'compressed':
        records[4] = (2, 4, 0)
    elif state == 'unknown':
        records[4] = (3, 0, 0)
    else:
        assert state == 'inherited'
    xref = len(source)
    records[7], records[11] = (2, 4, index), (1, xref, 0)
    raw = b''.join(bytes([kind])+target.to_bytes(4, 'big')+extra.to_bytes(2, 'big')
                   for kind, target, extra in records.values())
    ranges = ' '.join(f'{number} 1' for number in records)
    source += (f'11 0 obj\n<< /Type /XRef /Size 12 /Root 1 0 R /Info 7 0 R /W [1 4 2] /Index [{ranges}] '
               f'/Prev {previous} /Length {len(raw)} >>\nstream\n'.encode()+raw
               +f'\nendstream\nendobj\nstartxref\n{xref}\n%%EOF\n'.encode())
    return source, target, xref


@pytest.mark.parametrize('inherited', [False, True])
def test_each_revision_uses_its_selected_container_and_exact_decoded_payload(inherited):
    original, _, locations = custom_stream_pdf(members=[b'(Old own member)'], flate=False)
    source, new_container, new_xref = revision(original, state='inherited' if inherited else 'stream')
    before = hashlib.sha256(source).hexdigest()
    snapshot = inspect(source, capture=True)
    details = dict(snapshot.details)
    links = details['compressed_object_links']
    assert len(links) == 2 and all(link['status'] == 'matched-declared-member' for link in links)
    by_xref = {link['xref_offset']: link for link in links}
    old, new = by_xref[latest(original)], by_xref[new_xref]
    assert old['container_offset'] == locations[4]
    assert new['container_offset'] == (locations[4] if inherited else new_container)
    assert new['container_xref'] == (latest(original) if inherited else new_xref)
    items = {item.locator: item for item in snapshot.items}
    assert items[old['member_locator']].payload == b'(Old own member)'
    assert items[new['member_locator']].payload == (b'(Old own member)' if inherited else b'(New own member)')
    for link in links:
        member = items[link['member_locator']]
        assert link['member_sha256'] == hashlib.sha256(member.payload).hexdigest()
        assert link['decoded_range'] == {'start': 4, 'end': 4+len(member.payload)}
        assert not link['object_resolved'] and not link['ownership_proven']
    assert details['object_stream_declared_links_assessed'] and not details['object_stream_reference_links_assessed']
    assert not details['assessment_complete'] and hashlib.sha256(source).hexdigest() == before
    assert inspect(source).to_dict() == snapshot.to_dict()  # Capture is not needed for declarations or hashes.
    json.dumps(snapshot.to_dict())
    pypdf = pytest.importorskip('pypdf')
    expected = 'Old own member' if inherited else 'New own member'
    reader = pypdf.PdfReader(BytesIO(source), strict=True)
    assert reader.get_object(pypdf.generic.IndirectObject(7, 0, reader)) == expected


@pytest.mark.parametrize('state,index,member,status', [
    ('free', 0, 7, 'missing-container'), ('unknown', 0, 7, 'missing-container'),
    ('compressed', 0, 7, 'container-not-uncompressed'), ('ordinary', 0, 7, 'container-not-object-stream'),
    ('nonzero', 0, 7, 'nonzero-container-generation'), ('stream', 1, 7, 'index-out-of-range'),
    ('stream', 0, 8, 'object-number-mismatch'),
])
def test_invalid_links_never_borrow_an_older_matching_container(state, index, member, status):
    original, _, _ = custom_stream_pdf(members=[b'(Old own member)'], flate=False)
    source, _, xref = revision(original, state=state, index=index, member=member)
    links = dict(inspect(source).details)['compressed_object_links']
    row, = [link for link in links if link['xref_offset'] == xref and link['object'] == 7]
    assert row['status'] == status and 'member_locator' not in row
    assert not row['ownership_proven'] and not row['object_resolved']
    old, = [link for link in links if link['xref_offset'] == latest(original)]
    assert old['status'] == 'matched-declared-member'


@pytest.mark.parametrize('override', [None, 'direct', 'free'])
def test_hybrid_primary_priority_is_applied_before_binding_supplement(override):
    source, supplement, _ = hybrid_pdf(table_entry=override)
    row, = dict(inspect(source).details)['compressed_object_links']
    assert row['xref_offset'] == supplement and row['primary_xref'] == latest(source)
    assert row['status'] == ('matched-declared-member' if override is None else 'shadowed-reference')


def test_shared_supplement_with_two_primary_owners_is_explicitly_ambiguous():
    source, supplement, _ = hybrid_pdf()
    previous, offset = latest(source), len(source)
    source += (f'xref\n0 1\n0000000000 65535 f \ntrailer\n<< /Size 10 /Root 1 0 R '
               f'/Prev {previous} /XRefStm {supplement} >>\nstartxref\n{offset}\n%%EOF\n'.encode())
    row, = dict(inspect(source).details)['compressed_object_links']
    assert row['status'] == 'ambiguous-primary-context' and 'member_locator' not in row


def test_cancel_in_link_selection_preserves_existing_cli_output(tmp_path, monkeypatch):
    from opendoc_formats.native import pdf_object_links
    from tools.document_anatomy import main

    source = custom_stream_pdf()[0]
    path, output = tmp_path / 'own.pdf', tmp_path / 'previous'
    path.write_bytes(source)
    output.mkdir()
    marker = output / 'keep.txt'
    marker.write_bytes(b'Own previous output')
    stop = Event()
    original = pdf_object_links.resolve_xrefs

    def selected(*args, **kwargs):
        result = original(*args, **kwargs)
        stop.set()
        return result

    monkeypatch.setattr(pdf_object_links, 'resolve_xrefs', selected)
    with pytest.raises(OperationCancelledError):
        inspect(source, cancelled=stop.is_set)
    monkeypatch.setattr('sys.argv', ['document_anatomy', str(path), '--pdf-source', '--pdf-decode-xrefs',
                                    '--pdf-object-streams', '--max-items', '20', '--output', str(output)])
    with pytest.raises(ResourceLimitError):
        main()
    assert path.read_bytes() == source and marker.read_bytes() == b'Own previous output'
    assert list(output.iterdir()) == [marker]


def test_declared_links_need_no_pdf_or_image_engine(monkeypatch):
    source = custom_stream_pdf()[0]
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in {'pypdf', 'pymupdf', 'fitz', 'PIL', 'pdfplumber', 'fontTools', 'lxml'}:
            raise AssertionError('Unexpected native inspection backend: '+name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    assert all(row['status'] == 'matched-declared-member'
               for row in dict(inspect(source).details)['compressed_object_links'])


def test_link_work_has_an_exact_shared_item_quota():
    source = custom_stream_pdf()[0]
    baseline = inspect(source)
    details = dict(baseline.details)
    maximum = sum(1+len(dict(item.details)['entries']) for item in baseline.items if item.kind == 'pdf-xref-stream')
    maximum += sum(item.kind in ('pdf-object-stream', 'pdf-compressed-object') for item in baseline.items)
    maximum += details['object_stream_link_work_items']
    maximum += details['object_stream_extends_work_items']
    assert inspect(source, limits=replace(AnatomyLimits(), max_items=maximum)).to_dict() == baseline.to_dict()
    with pytest.raises(ResourceLimitError, match='max_items'):
        inspect(source, limits=replace(AnatomyLimits(), max_items=maximum-1))


def test_links_and_index_search_consume_the_same_syntax_work_budget(monkeypatch):
    from opendoc_formats.native import pdf_object_streams

    source = custom_stream_pdf()[0]
    actual = pdf_object_streams.declared_object_links
    measured = {}

    def observed(sections, references, items, budget, maximum, **kwargs):
        measured['before'] = budget.tokens
        result = actual(sections, references, items, budget, maximum, **kwargs)
        measured['after'] = budget.tokens
        return result

    monkeypatch.setattr(pdf_object_streams, 'declared_object_links', observed)
    baseline = inspect(source)
    before, after = measured['before'], measured['after']
    assert after > before
    assert inspect(source, limits=replace(AnatomyLimits(), max_pdf_tokens=after)).to_dict() == baseline.to_dict()
    for limit in (before, after-1):
        with pytest.raises(ResourceLimitError, match='max_pdf_tokens'):
            inspect(source, limits=replace(AnatomyLimits(), max_pdf_tokens=limit))
