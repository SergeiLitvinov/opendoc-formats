"""Source-index precedence, generations and hybrid rules; bodies are not resolved."""

import json
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from tests.binary_fixtures import own_pdf
from tests.native.test_pdf_xref_streams import own_stream_pdf


def latest(data):
    return int(data.rsplit(b'startxref', 1)[1].split()[0])


def inspect(data, **kwargs):
    return inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True, pdf_resolve_xrefs=True, **kwargs)


def records(snapshot):
    return {entry['object']: entry for entry in dict(snapshot.details)['effective_xref_entries']}


def append_classic(data, *, generation=0, title=b'Own metadata', free=False):
    previous, target = latest(data), len(data)
    if not free:
        data += b'7 '+str(generation).encode()+b' obj\n<< /Title ('+title+b') >>\nendobj\n'
    offset = len(data)
    data += (f'xref\n7 1\n{0 if free else target:010} {generation:05} {"f" if free else "n"} \ntrailer\n'
             f'<< /Size 8 /Root 1 0 R /Prev {previous} '.encode()
             +(b'' if free else f'/Info 7 {generation} R '.encode())
             +f'>>\nstartxref\n{offset}\n%%EOF\n'.encode())
    return data, target


def test_latest_generation_reuse_and_exact_source_provenance_agree_with_independent_reader():
    original, _ = own_pdf()
    first, _ = append_classic(original)
    freed, _ = append_classic(first, generation=1, free=True)
    reused, target = append_classic(freed, generation=1, title=b'Reused own metadata')
    snapshot = inspect(reused)
    chosen = records(snapshot)[7]
    assert chosen['generation'] == 1 and chosen['state'] == 'uncompressed' and chosen['offset'] == target
    assert chosen['xref_offset'] == latest(reused) and chosen['search_index'] == 0
    span = chosen['record_range']
    assert span['space'] == 'source' and b'00001 n' in reused[span['start']:span['end']]
    assert not chosen['object_resolved'] and not chosen['ownership_proven']
    assert dict(snapshot.details)['xref_record_selection_complete']
    assert not dict(snapshot.details)['object_resolution_complete'] and not dict(snapshot.details)['assessment_complete']
    assert len(dict(snapshot.details)['xref_search_order']) == 4
    json.dumps(snapshot.to_dict())
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(reused), strict=True)
    assert len(reader.pages) == 1 and reader.metadata.title == 'Reused own metadata'
    assert reader.xref[1][7] == chosen['offset']


def test_free_entry_shadows_previous_generation_instead_of_resurrecting_old_body():
    original, _ = own_pdf()
    before, _ = append_classic(original)
    deleted, _ = append_classic(before, generation=1, free=True)
    entry = records(inspect(deleted))[7]
    assert entry['state'] == 'free' and entry['generation'] == 1 and entry['next_free'] == 0
    assert 'offset' not in entry
    assert records(inspect(before))[7]['state'] == 'uncompressed'
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(deleted), strict=True)
    assert len(reader.pages) == 1 and reader.xref_free_entry[1][7]


def hybrid_pdf(*, table_entry=None):
    original, _ = own_pdf()
    previous = latest(original)
    # Reserve hidden IDs as free in the original classic table.
    tail = original[previous:].replace(b'0 7\n', b'0 10\n', 1)
    tail = tail.replace(b'trailer', b'0000000000 65535 f \n'*3+b'trailer', 1).replace(b'/Size 7', b'/Size 10')
    data = original[:previous]+tail
    target = len(data)
    member = b'8 0 << /Title (Own hybrid metadata) >>'
    data += (b'7 0 obj\n<< /Type /ObjStm /N 1 /First 4 /Length '+str(len(member)).encode()
             +b' >>\nstream\n'+member+b'\nendstream\nendobj\n')
    direct = len(data)
    if table_entry == 'direct':
        data += b'8 0 obj\n<< /Title (Own table priority) >>\nendobj\n'
    supplement = len(data)
    raw = b'\x02\0\0\0\x07\0\0'+b'\x01'+supplement.to_bytes(4, 'big')+b'\0\0'
    data += (b'9 0 obj\n<< /Type /XRef /Size 10 /W [1 4 2] /Index [8 2] /Length 14 >>\nstream\n'
             +raw+b'\nendstream\nendobj\n')
    offset = len(data)
    data += f'xref\n7 {2 if table_entry else 1}\n{target:010} 00000 n \n'.encode()
    if table_entry:
        address, generation, state = (direct, 0, 'n') if table_entry == 'direct' else (0, 1, 'f')
        data += f'{address:010} {generation:05} {state} \n'.encode()
    data += (f'trailer\n<< /Size 10 /Root 1 0 R /Info 8 0 R /Prev {previous} /XRefStm {supplement} >>\n'
             f'startxref\n{offset}\n%%EOF\n').encode()
    return data, supplement, direct


def test_hybrid_stream_precedes_old_free_record_and_agrees_with_pypdf():
    data, supplement, _ = hybrid_pdf()
    snapshot = inspect(data, pdf_object_streams=True)
    entry = records(snapshot)[8]
    assert entry['state'] == 'compressed' and entry['object_stream'] == 7 and entry['index'] == 0
    assert entry['xref_offset'] == supplement and entry['search_index'] == 1
    assert entry['record_range'] == {'space': 'decoded-xref', 'start': 0, 'end': 7}
    assert [row['role'] for row in dict(snapshot.details)['xref_search_order']] == [
        'primary', 'hybrid-supplement', 'primary']
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(data), strict=True)
    assert len(reader.pages) == 1 and reader.metadata.title == 'Own hybrid metadata'
    assert reader.xref_objStm[8] == (7, 0)


@pytest.mark.parametrize('table_entry', ['direct', 'free'])
def test_current_classic_table_has_priority_over_its_hybrid_supplement(table_entry):
    data, _, direct = hybrid_pdf(table_entry=table_entry)
    snapshot = inspect(data)
    entry = records(snapshot)[8]
    assert entry['xref_offset'] == latest(data) and entry['search_index'] == 0
    if table_entry == 'direct':
        assert entry['state'] == 'uncompressed' and entry['offset'] == direct
        pymupdf = pytest.importorskip('pymupdf')
        with pymupdf.open(stream=data, filetype='pdf') as native:
            assert native.page_count == 1 and native.metadata['title'] == 'Own table priority'
    else:
        assert entry['state'] == 'free' and entry['generation'] == 1


def test_unknown_future_record_is_null_and_shadows_older_compressed_record():
    data, _, _ = own_stream_pdf()
    previous, offset = latest(data), len(data)
    raw = b'\x07\0\0\0\x04\0\0'
    data += (b'7 0 obj\n<< /Type /XRef /Size 8 /Root 1 0 R /W [1 4 2] /Index [5 1] /Length 7 '
             +f'/Prev {previous} >>\nstream\n'.encode()+raw
             +b'\nendstream\nendobj\nstartxref\n'+str(offset).encode()+b'\n%%EOF\n')
    entry = records(inspect(data))[5]
    assert entry['state'] == 'unknown-null' and entry['entry_type'] == 7
    assert 'object_stream' not in entry and entry['raw_fields'] == [7, 4, 0]


def test_forward_prev_offsets_are_followed_as_search_links_without_claiming_revision_order():
    original, _ = own_pdf()
    previous = latest(original)
    # A structural forward-link fixture, not a claim of full linearized conformance.
    data = original[:previous]
    first = len(data)
    head = b'xref\n0 1\n0000000000 65535 f \ntrailer\n<< /Size 7 /Root 1 0 R /Prev 0000000000 >>\n'
    main = first+len(head)
    data += head.replace(b'0000000000 >>', f'{main:010} >>'.encode())
    data += original[previous:].split(b'startxref')[0]
    data += b'startxref\n'+str(first).encode()+b'\n%%EOF\n'
    snapshot = inspect(data)
    order = dict(snapshot.details)['xref_search_order']
    assert [row['xref_offset'] for row in order] == [first, main]
    pypdf = pytest.importorskip('pypdf')
    assert len(pypdf.PdfReader(BytesIO(data), strict=True).pages) == 1


def test_effective_records_and_objstm_members_share_item_budget():
    data, _, _ = own_stream_pdf()
    with pytest.raises(ResourceLimitError):
        inspect(data, pdf_object_streams=True, limits=replace(AnatomyLimits(), max_items=15))
    snapshot = inspect(data, pdf_object_streams=True, limits=replace(AnatomyLimits(), max_items=17))
    assert len(records(snapshot)) == 7 and dict(snapshot.details)['decoded_object_streams'] == 1


def test_section_seen_as_supplement_and_later_primary_still_expands_its_prev():
    data, supplement, _ = hybrid_pdf()
    current = latest(data)
    snapshot = inspect(data)
    previous = dict(snapshot.items[0].details)['prev']
    # Structural role-reuse fixture; no claim of full hybrid/linearized conformance.
    insertion = f'/Prev {previous} '.encode()
    stream_part = data[supplement:current].replace(b'/Length 14', insertion+b'/Length 14')
    new_current = supplement+len(stream_part)
    tail = data[current:].replace(f'/Prev {previous}'.encode(), f'/Prev {supplement}'.encode())
    tail = tail.replace(f'startxref\n{current}'.encode(), f'startxref\n{new_current}'.encode())
    data = data[:supplement]+stream_part+tail
    result = inspect(data)
    order = dict(result.details)['xref_search_order']
    assert [row['xref_offset'] for row in order] == [new_current, supplement, supplement, previous]
    assert len(result.items) == 3 and records(result)[1]['state'] == 'uncompressed'
    assert order[1]['ignored_prev'] == previous


def test_cli_preserves_physical_items_and_writes_effective_record_evidence(tmp_path, monkeypatch):
    from tools.document_anatomy import main

    data, _, _ = hybrid_pdf()
    source, output = tmp_path/'source.pdf', tmp_path/'inventory'
    source.write_bytes(data)
    monkeypatch.setattr('sys.argv', ['document_anatomy', str(source), '--pdf-source', '--pdf-decode-xrefs',
                                    '--pdf-resolve-xrefs', '--output', str(output)])
    main()
    inventory = json.loads((output/'inventory.json').read_text(encoding='utf-8'))
    assert inventory['details']['xref_record_selection_complete']
    assert any(row['object'] == 8 and row['state'] == 'compressed'
               for row in inventory['details']['effective_xref_entries'])
    assert all(item['kind'] in {'pdf-classic-xref', 'pdf-xref-stream'} for item in inventory['items'])
    assert source.read_bytes() == data


def test_cancel_during_record_selection(monkeypatch):
    from opendoc_formats.native import pdf_xref_state

    data, _, _ = own_stream_pdf()
    stop = Event()
    calls = 0
    real = pdf_xref_state.checkpoint
    def checkpoint():
        nonlocal calls
        calls += 1
        if calls == 5:
            stop.set()
        real()
    monkeypatch.setattr(pdf_xref_state, 'checkpoint', checkpoint)
    with pytest.raises(OperationCancelledError):
        inspect(data, cancelled=stop.is_set)
    assert calls == 5


def test_flags_require_explicit_xref_decode_and_boolean():
    data, _, _ = own_stream_pdf()
    with pytest.raises(ValueError, match='requires pdf_decode_xrefs'):
        inspect_binary(data, pdf_resolve_xrefs=True)
    with pytest.raises(TypeError):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True, pdf_resolve_xrefs=1)
