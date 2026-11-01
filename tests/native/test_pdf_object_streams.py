"""Physical ObjStm syntax, provenance, quotas and external-reader agreement."""

import hashlib
import json
import zlib
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from tests.native.test_pdf_xref_streams import own_stream_pdf


def inspect(data, **kwargs):
    return inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True, pdf_object_streams=True, **kwargs)


def custom_stream_pdf(*, members=None, flate=True, extra=b'', header=None, first=None, count=None, encoded_change=None):
    members = [b'<< /Title (Own compressed metadata) >>', b'42', b'[1 (Two) /Three]', b'null'] if members is None else members
    body = b'\n'.join(members)
    offsets, position = [], 0
    for member in members:
        offsets.append(position)
        position += len(member)+1
    directory = b''.join(f'{7+index} {offset} '.encode() for index, offset in enumerate(offsets)) if header is None else header
    content = directory+body
    encoded = zlib.compress(content) if flate else content
    if encoded_change:
        encoded = encoded_change(encoded)
    # No Formats/PDF writer participates in this original's construction.
    data = bytearray(b'%PDF-1.7\n')
    locations = {}
    objects = [(1, b'<< /Type /Catalog /Pages 2 0 R >>'),
               (2, b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>'),
               (3, b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] >>'),
               (4, b'<< /Type /ObjStm /N '+str(len(members) if count is None else count).encode()
                +b' /First '+str(len(directory) if first is None else first).encode()
                +b' /Length '+str(len(encoded)).encode()+(b' /Filter /FlateDecode' if flate else b'')
                +b' '+extra+b' >>\nstream\n'+encoded+b'\nendstream')]
    for number, value in objects:
        locations[number] = len(data)
        data.extend(str(number).encode()+b' 0 obj\n'+value+b'\nendobj\n')
    xref = len(data)
    records = [(0, 0, 65535)]+[(1, locations[number], 0) for number in range(1, 5)]+[(1, xref, 0)]
    records += [(2, 4, index) for index in range(len(members))]
    index = b'/Index [0 5 6 1 7 '+str(len(members)).encode()+b']' if members else b'/Index [0 5 6 1]'
    raw = b''.join(bytes([kind])+target.to_bytes(4, 'big')+generation.to_bytes(2, 'big')
                   for kind, target, generation in records)
    data.extend(b'6 0 obj\n<< /Type /XRef /Size '+str(7+len(members)).encode()+b' /Root 1 0 R '
                +(b'/Info 7 0 R ' if members else b'')+b'/W [1 4 2] '+index+b' /Length '+str(len(raw)).encode()
                +b' >>\nstream\n'+raw+b'\nendstream\nendobj\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n')
    return bytes(data), content, locations


@pytest.mark.parametrize('flate', [False, True])
def test_own_container_exact_encoded_bytes_decoded_ranges_and_independent_reader(flate):
    data, decoded, locations = custom_stream_pdf(flate=flate)
    original = bytes(data)
    snapshot = inspect(data, capture=True)
    container, *members = snapshot.items[1:]
    info = dict(container.details)
    assert container.kind == 'pdf-object-stream' and info['members'] == 4
    assert container.payload == data[locations[4]:info['end']]
    assert not info['ownership_proven'] and not info['active_resolution']
    for index, member in enumerate(members):
        details = dict(member.details)
        assert details['object'] == index+7 and details['generation'] == 0 and details['index'] == index
        assert member.payload == decoded[details['decoded_start']:details['decoded_end']]
        assert member.sha256 == hashlib.sha256(member.payload).hexdigest()
        assert details['source_byte_range'] is None
    assert members[-1].payload == b'null'  # exact EOF boundary, no synthetic bytes
    assert dict(snapshot.details)['object_streams_decoded']
    assert not dict(snapshot.details)['object_stream_reference_links_assessed']
    assert not dict(snapshot.details)['assessment_complete']
    assert not dict(snapshot.details)['unresolved_container_numbers']
    assert len(dict(snapshot.details)['compressed_object_references']) == 4
    json.dumps(snapshot.to_dict())
    assert data == original
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(data), strict=True)
    assert len(reader.pages) == 1 and reader.metadata.title == 'Own compressed metadata'
    assert reader.get_object(pypdf.generic.IndirectObject(8, 0, reader)) == 42
    assert reader.get_object(pypdf.generic.IndirectObject(9, 0, reader)) == [1, 'Two', '/Three']
    assert isinstance(reader.get_object(pypdf.generic.IndirectObject(10, 0, reader)), pypdf.generic.NullObject)


@pytest.mark.parametrize('value', [b'42', b'1.25', b'/Name', b'(A\\)B)', b'<4142>', b'true', b'null',
                                   b'7 0 R', b'[1 2 /X]', b'<< /K [1 2] >>'])
def test_member_syntax_ends_exactly_at_its_range(value):
    data, _, _ = custom_stream_pdf(members=[value])
    member = inspect(data, capture=True).items[-1]
    assert member.kind == 'pdf-compressed-object' and member.payload == value


@pytest.mark.parametrize('changes', [
    {'header': b'7 0 7 4 ', 'members': [b'null', b'null']},
    {'header': b'7 1 ', 'members': [b'null']},
    {'header': b'7 0 8 0 ', 'members': [b'null', b'null']},
    {'first': 999999}, {'count': 999999}, {'count': 1}, {'count': 6},
    {'members': [b'<< /Unclosed 1']}, {'members': [b'(unterminated']},
    {'members': [b'1 2']}, {'members': [b'<< >> stream\nX\nendstream']},
    {'header': b'7 0 8 9999 ', 'members': [b'null', b'null']},
    {'encoded_change': lambda data: data[:-1]}, {'encoded_change': lambda data: data+b'junk'},
])
def test_bad_directories_syntax_and_encoded_lengths_refuse(changes):
    data, _, _ = custom_stream_pdf(**changes)
    with pytest.raises((InvalidDocumentError, ResourceLimitError)):
        inspect(data)


@pytest.mark.parametrize('damage', ['indirect', 'filter', 'predictor', 'external', 'encryption'])
def test_unsupported_profiles_do_not_execute_or_guess(damage):
    extra = {'filter': b'/Unused 1', 'predictor': b'/DecodeParms << /Predictor 12 >>',
             'external': b'/F (outside.pdf)', 'indirect': b'', 'encryption': b''}[damage]
    data, _, locations = custom_stream_pdf(extra=extra)
    offset = locations[4]
    if damage == 'indirect':
        # Keep xref offsets correct by replacing a value with a same-length indirect reference.
        data, _, _ = custom_stream_pdf(extra=b'/UnusedLong 99')
        data = data.replace(b'/N 4 /First ', b'/N 1 0 R /X ')
    elif damage == 'filter':
        data = data[:offset]+data[offset:].replace(b'/FlateDecode', b'/NoSuchCodec', 1)
    elif damage == 'encryption':
        data, _, _ = custom_stream_pdf(extra=b'/UnusedLong 99')
        # Append Encrypt to the final xref dictionary without moving its object header.
        xref = int(data.rsplit(b'startxref', 1)[1].split()[0])
        data = data[:xref]+data[xref:].replace(b'/Root 1 0 R', b'/Root 1 0 R /Encrypt 99 0 R')
    with pytest.raises(UnsupportedDocumentError):
        inspect(data)


def test_missing_container_is_reported_without_claiming_resolution():
    data, _, _ = own_stream_pdf(payload=b'\x02\0\0\0\x04\0\0', index=b'/Index [5 1]')
    snapshot = inspect(data)
    assert not dict(snapshot.details)['object_streams_decoded']
    assert dict(snapshot.details)['unresolved_container_numbers'] == [4]


@pytest.mark.parametrize('field,maximum', [('max_items', 15), ('max_total_bytes', 300), ('max_pdf_tokens', 60),
                                         ('max_pdf_depth', 1)])
def test_object_streams_share_aggregate_budgets(field, maximum):
    data, _, _ = custom_stream_pdf()
    with pytest.raises(ResourceLimitError):
        inspect(data, limits=replace(AnatomyLimits(), **{field: maximum}))


def test_cancel_during_member_validation(monkeypatch):
    from opendoc_formats.native import pdf_object_streams

    data, _, _ = custom_stream_pdf()
    stop = Event()
    calls = 0
    real = pdf_object_streams.checkpoint
    def checkpoint():
        nonlocal calls
        calls += 1
        if calls == 29:
            stop.set()
        real()
    monkeypatch.setattr(pdf_object_streams, 'checkpoint', checkpoint)
    with pytest.raises(OperationCancelledError):
        inspect(data, cancelled=stop.is_set)
    assert calls == 29


def test_flags_require_explicit_source_xref_decoding_and_boolean():
    data, _, _ = custom_stream_pdf()
    with pytest.raises(ValueError, match='requires pdf_decode_xrefs'):
        inspect_binary(data, pdf_object_streams=True)
    with pytest.raises(TypeError):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True, pdf_object_streams=1)


def test_independent_mupdf_object_stream_original():
    pymupdf = pytest.importorskip('pymupdf')
    pypdf = pytest.importorskip('pypdf')
    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), 'Independent object-stream original')
        data = document.tobytes(use_objstms=1, deflate=True, garbage=4)
    snapshot = inspect(data, capture=True)
    assert dict(snapshot.details)['decoded_object_streams'] >= 1
    reader = pypdf.PdfReader(BytesIO(data), strict=True)
    assert len(reader.pages) == 1 and 'Independent object-stream original' in reader.pages[0].extract_text()
    for item in snapshot.items:
        if item.kind == 'pdf-compressed-object':
            details = dict(item.details)
            assert reader.xref_objStm[details['object']] == (details['object_stream'], details['index'])


def test_history_keeps_both_container_candidates_without_claiming_active_resolution():
    original, _, locations = custom_stream_pdf(flate=False)
    previous = int(original.rsplit(b'startxref', 1)[1].split()[0])
    new_offset = len(original)
    new_container = original[locations[4]:previous].replace(b'Own compressed metadata', b'New compressed metadata')
    data = original+new_container
    xref = len(data)
    records = [(1, new_offset, 0)]+[(2, 4, index) for index in range(4)]+[(1, xref, 0)]
    raw = b''.join(bytes([kind])+target.to_bytes(4, 'big')+index.to_bytes(2, 'big') for kind, target, index in records)
    data += (b'11 0 obj\n<< /Type /XRef /Size 12 /Root 1 0 R /Info 7 0 R /W [1 4 2] /Index [4 1 7 5] '
             +f'/Prev {previous} /Length {len(raw)} >>\nstream\n'.encode()+raw
             +b'\nendstream\nendobj\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n')
    snapshot = inspect(data, capture=True)
    containers = [item for item in snapshot.items if item.kind == 'pdf-object-stream']
    assert len(containers) == 2
    assert [dict(item.details)['offset'] for item in containers] == [locations[4], new_offset]
    titles = [item.payload for item in snapshot.items if item.kind == 'pdf-compressed-object'
              and dict(item.details)['object'] == 7]
    assert b'Own compressed metadata' in titles[0] and b'New compressed metadata' in titles[1]
    assert len(dict(snapshot.details)['compressed_object_references']) == 8
    assert not dict(snapshot.details)['object_stream_reference_links_assessed']
    pypdf = pytest.importorskip('pypdf')
    assert pypdf.PdfReader(BytesIO(data), strict=True).metadata.title == 'New compressed metadata'


def test_extends_is_retained_but_never_followed():
    data, _, _ = custom_stream_pdf(extra=b'/Extends 99 0 R')
    container = next(item for item in inspect(data).items if item.kind == 'pdf-object-stream')
    assert dict(container.details)['extends'] == {'object': 99, 'generation': 0}
    assert not dict(container.details)['extends_resolved']


def test_unknown_decoded_size_is_bounded_inside_flate_and_source_is_unchanged():
    data, _, _ = custom_stream_pdf(members=[b'('+b'A'*1000000+b')'])
    original = bytes(data)
    with pytest.raises(ResourceLimitError, match='decoded stream exceeds byte budget'):
        inspect(data, limits=replace(AnatomyLimits(), max_part_bytes=4096))
    assert data == original


def test_cancel_inside_object_stream_flate(monkeypatch):
    from opendoc_formats.native import pdf_flate

    data, _, _ = custom_stream_pdf(members=[b'('+b'A'*1000000+b')'])
    stop = Event()
    calls = 0
    real = pdf_flate.checkpoint
    def checkpoint():
        nonlocal calls
        calls += 1
        if calls == 4:
            stop.set()
        real()
    monkeypatch.setattr(pdf_flate, 'checkpoint', checkpoint)
    with pytest.raises(OperationCancelledError):
        inspect(data, cancelled=stop.is_set)
    assert calls == 4


def test_cli_records_decoded_payload_addresses_and_preserves_destination_on_late_error(tmp_path, monkeypatch):
    from tools.document_anatomy import main

    source, output = tmp_path/'source.pdf', tmp_path/'dissected'
    data, _, _ = custom_stream_pdf()
    source.write_bytes(data)
    arguments = ['document_anatomy', str(source), '--pdf-source', '--pdf-decode-xrefs', '--pdf-object-streams',
                 '--output', str(output)]
    monkeypatch.setattr('sys.argv', arguments)
    main()
    inventory = json.loads((output/'inventory.json').read_text(encoding='utf-8'))
    members = [item for item in inventory['items'] if item['kind'] == 'pdf-compressed-object']
    assert (output/members[-1]['payload_file']).read_bytes() == b'null'
    assert members[-1]['details']['source_byte_range'] is None
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    malformed, _, _ = custom_stream_pdf(members=[b'(unterminated'])
    source.write_bytes(malformed)
    with pytest.raises(InvalidDocumentError):
        main()
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before
    assert source.read_bytes() == malformed
