"""Physical xref streams built without Formats/PDF writers, checked by pypdf."""

import json
import zlib
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError


def own_stream_pdf(*, flate=True, extra=b'', payload=None, widths=b'[1 4 2]', index=b'', transform=None):
    data = bytearray(b'%PDF-1.7\n')
    offsets = {0: 0}
    objects = (b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] >>')
    info = b'5 0 << /Title (Own compressed metadata) >>'
    objects += (b'<< /Type /ObjStm /N 1 /First 4 /Length '+str(len(info)).encode()
                +b' >>\nstream\n'+info+b'\nendstream',)
    for number, value in enumerate(objects, 1):
        offsets[number] = len(data)
        data.extend(str(number).encode()+b' 0 obj\n'+value+b'\nendobj\n')
    offsets[6] = len(data)
    records = [(0, 0, 65535)]+[(1, offsets[number], 0) for number in range(1, 5)]+[(2, 4, 0), (1, offsets[6], 0)]
    raw = b''.join(bytes([kind])+target.to_bytes(4, 'big')+generation.to_bytes(2, 'big')
                   for kind, target, generation in records) if payload is None else payload
    transformed = transform(raw) if transform else raw
    encoded = zlib.compress(transformed) if flate else transformed
    dictionary = (b'<< /Type /XRef /Size 7 /Root 1 0 R /Info 5 0 R /W '+widths+b' '+index
                  +b' /Length '+str(len(encoded)).encode()+(b' /Filter /FlateDecode' if flate else b'')+b' '+extra+b' >>')
    data.extend(b'6 0 obj\n'+dictionary+b'\nstream\n'+encoded+b'\nendstream\nendobj\n'
                +b'startxref\n'+str(offsets[6]).encode()+b'\n%%EOF\n')
    return bytes(data), offsets, raw


@pytest.mark.parametrize('flate', [False, True])
def test_raw_and_flate_records_compressed_references_original_payload_and_independent_reader(flate):
    data, offsets, raw = own_stream_pdf(flate=flate)
    snapshot = inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True, capture=True)
    assert len(snapshot.items) == 1
    item = snapshot.items[0]
    details = dict(item.details)
    assert item.kind == 'pdf-xref-stream' and details['stream_entries_decoded']
    assert item.payload == data[details['offset']:details['end']]
    assert item.payload.endswith(b'endobj') and details['decoded_bytes'] == len(raw)
    assert details['entries'][0]['generation'] == 65535
    for entry in details['entries'][1:5]+details['entries'][6:]:
        assert entry['offset_or_next_free'] == offsets[entry['object']]
    compressed = details['entries'][5]
    assert compressed['object_stream'] == 4 and compressed['object_stream_index'] == 0
    assert compressed['generation'] == 0 and 'offset_or_next_free' not in compressed
    assert dict(snapshot.details)['classic_entries'] == 0
    assert not dict(snapshot.details)['object_streams_decoded']
    assert not dict(snapshot.details)['assessment_complete']
    json.dumps(snapshot.to_dict())
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(data), strict=True)
    assert len(reader.pages) == 1 and reader.metadata.title == 'Own compressed metadata'
    for entry in details['entries']:
        if entry['entry_type'] == 1:
            assert reader.xref[0][entry['object']] == entry['offset_or_next_free']
    assert reader.xref_objStm[5] == (4, 0)


def test_zero_width_defaults_sparse_index_unknown_future_types_and_original_dictionary_mode():
    data, _, _ = own_stream_pdf(flate=False, payload=(9).to_bytes(4, 'big'), widths=b'[0 4 0]', index=b'/Index [6 1]')
    snapshot = inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True)
    entry = dict(snapshot.items[0].details)['entries'][0]
    assert entry['entry_type'] == 1 and entry['generation'] == 0 and entry['offset_or_next_free'] == 9
    data, _, _ = own_stream_pdf(flate=False, payload=b'\x07\x00\x00\x00\x04\x00\x03', index=b'/Index [6 1]')
    entry = dict(inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True).items[0].details)['entries'][0]
    assert entry['in_use'] is None and entry['raw_fields'] == [7, 4, 3]
    legacy = inspect_binary(data, pdf_source=True, capture=True).items[0]
    assert legacy.kind == 'pdf-xref-stream-dictionary' and legacy.payload.endswith(b'>>')


@pytest.mark.parametrize('hybrid', [False, True])
def test_stream_records_remain_physical_across_hybrid_and_incremental_links(hybrid):
    data, offsets, _ = own_stream_pdf()
    target = len(data)
    data += b'7 0 obj\n<< /Title (Own appended metadata) >>\nendobj\n'
    offset = len(data)
    link = b'/XRefStm ' if hybrid else b'/Prev '
    data += (f'xref\n7 1\n{target:010} 00000 n \ntrailer\n<< /Size 8 /Root 1 0 R /Info 7 0 R '.encode()
             +link+str(offsets[6]).encode()+b' >>\nstartxref\n'+str(offset).encode()+b'\n%%EOF\n')
    snapshot = inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True)
    assert dict(snapshot.details)['xref_sections'] == 2 and dict(snapshot.details)['classic_entries'] == 1
    table, stream = snapshot.items
    assert dict(table.details)['entries'][0]['offset_or_next_free'] == target
    assert dict(stream.details)['hybrid_supplement'] is hybrid
    assert dict(stream.details)['entries'][5]['object_stream'] == 4
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(data), strict=True)
    assert len(reader.pages) == 1 and reader.metadata.title == 'Own appended metadata'


def test_single_filter_array_and_explicit_no_prediction():
    data, _, _ = own_stream_pdf(extra=b'/DecodeParms [<< /Predictor 1 >>]')
    data = data.replace(b'/Filter /FlateDecode', b'/Filter [/FlateDecode]')
    result = inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True)
    assert dict(result.items[0].details)['decoded_bytes'] == 49


@pytest.mark.parametrize('extra,widths,index,payload,exception', [
    (b'', b'[1 4]', b'', None, InvalidDocumentError),
    (b'', b'[1 true 2]', b'', None, InvalidDocumentError),
    (b'', b'[1 9 2]', b'', None, UnsupportedDocumentError),
    (b'', b'[0 0 0]', b'', None, UnsupportedDocumentError),
    (b'', b'[1 4 2]', b'/Index [0 4 3 4]', None, InvalidDocumentError),
    (b'', b'[1 4 2]', b'/Index [0 8]', None, InvalidDocumentError),
    (b'', b'[1 4 2]', b'/Index [1 0]', None, InvalidDocumentError),
    (b'', b'[1 4 2]', b'/Index [0]', None, InvalidDocumentError),
    (b'/DecodeParms << /Predictor 2 /Columns 7 >>', b'[1 4 2]', b'', None, UnsupportedDocumentError),
    (b'/F (external)', b'[1 4 2]', b'', None, UnsupportedDocumentError),
    (b'', b'[1 4 2]', b'', b'too short', InvalidDocumentError),
    (b'', b'[1 4 2]', b'', b'\0'*1000000, InvalidDocumentError),
    (b'', b'[1 4 2]', b'/Index [6 1]', b'\x02\0\0\0\x07\0\0', InvalidDocumentError),
], ids=[f'profile-{index}' for index in range(13)])
def test_invalid_or_unsupported_stream_profiles_refuse(extra, widths, index, payload, exception):
    data, _, _ = own_stream_pdf(extra=extra, widths=widths, index=index, payload=payload)
    original = bytes(data)
    with pytest.raises(exception, match='pdf:byte='):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True)
    assert data == original


@pytest.mark.parametrize('damage', ['filter', 'indirect-length', 'truncated', 'junk', 'terminator', 'length', 'zlib'])
def test_encoded_boundaries_and_zlib_corruption_are_not_repaired(damage):
    data, _, _ = own_stream_pdf()
    error = InvalidDocumentError
    if damage == 'filter':
        data = data.replace(b'/FlateDecode', b'/LZWDecode')
        error = UnsupportedDocumentError
    elif damage == 'indirect-length':
        data, offsets, _ = own_stream_pdf()
        offset = offsets[6]
        data = data[:offset]+data[offset:].replace(b'/Length ', b'/Length 9 0 R /Unused ', 1)
        error = UnsupportedDocumentError
    elif damage == 'truncated':
        data = data.replace(b'\nendstream\nendobj\nstartxref', b'\nendstream\nendobx\nstartxref')
    elif damage == 'junk':
        # Keep the declared Length valid while inserting junk inside compressed bytes.
        data, offsets, _ = own_stream_pdf()
        prefix, tail = data[:offsets[6]], data[offsets[6]:]
        import re
        length = int(re.search(rb'/Length ([0-9]+)', tail)[1])
        tail = tail.replace(b'/Length '+str(length).encode(), b'/Length '+str(length+1).encode())
        tail = tail.replace(b'\nendstream', b'X\nendstream')
        data = prefix+tail
    elif damage == 'terminator':
        data = data.replace(b'\nendstream\nendobj\nstartxref', b'\nendstrxxx\nendobj\nstartxref')
    elif damage == 'length':
        data, offsets, _ = own_stream_pdf()
        data = data[:offsets[6]]+data[offsets[6]:].replace(b'/Length ', b'/Length 999999 /Unused ', 1)
    else:
        data, offsets, _ = own_stream_pdf()
        start = data.index(b'\nstream\n', offsets[6])+8
        data = data[:start]+b'NO'+data[start+2:]
    with pytest.raises(error):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True)


@pytest.mark.parametrize('field,maximum', [('max_items', 7), ('max_total_bytes', 90), ('max_part_bytes', 40)])
def test_aggregate_and_entry_budgets(field, maximum):
    data, _, _ = own_stream_pdf()
    with pytest.raises(ResourceLimitError):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True,
                       limits=replace(AnatomyLimits(), **{field: maximum}))


def test_cancel_inside_decoding_preserves_source(monkeypatch):
    from opendoc_formats.native import pdf_xref_streams

    data, _, _ = own_stream_pdf()
    stop = Event()
    count = 0
    real = pdf_xref_streams.checkpoint
    def checkpoint():
        nonlocal count
        count += 1
        if count == 5:
            stop.set()
        real()
    monkeypatch.setattr(pdf_xref_streams, 'checkpoint', checkpoint)
    with pytest.raises(OperationCancelledError):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True, cancelled=stop.is_set)
    assert count == 5


def test_decode_flag_requires_source_profile_and_exact_boolean():
    data, _, _ = own_stream_pdf()
    with pytest.raises(ValueError, match='requires pdf_source'):
        inspect_binary(data, pdf_decode_xrefs=True)
    with pytest.raises(TypeError):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=1)


def test_multi_chunk_decoding_and_preflight_before_zlib(monkeypatch):
    import random

    from opendoc_formats.native import pdf_flate

    random_values = random.Random(42)
    # Structural stress fixture, not a semantically resolvable PDF: offsets
    # deliberately point nowhere. The inspector does not claim otherwise.
    raw = b'\0\0\0\0\0\xff\xff'+b''.join(
        b'\x01'+random_values.getrandbits(32).to_bytes(4, 'big')+b'\0\0' for _ in range(19999))
    data, offsets, _ = own_stream_pdf(payload=raw)
    data = data[:offsets[6]]+data[offsets[6]:].replace(b'/Size 7', b'/Size 20000')
    snapshot = inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True)
    details = dict(snapshot.items[0].details)
    assert len(details['entries']) == 20000 and details['decoded_bytes'] == 140000
    assert details['encoded_end']-details['encoded_start'] > 65536
    assert details['entries'][-1]['decoded_end'] == len(raw)
    def forbidden():
        pytest.fail('byte quota must be checked before constructing the decoder')
    monkeypatch.setattr(pdf_flate.zlib, 'decompressobj', forbidden)
    with pytest.raises(ResourceLimitError):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True,
                       limits=replace(AnatomyLimits(), max_total_bytes=100000))


def test_cli_dissection_keeps_encoded_source_span_and_json_evidence(tmp_path, monkeypatch):
    from tools.document_anatomy import main

    data, _, _ = own_stream_pdf()
    source, output = tmp_path/'source.pdf', tmp_path/'dissected'
    source.write_bytes(data)
    monkeypatch.setattr('sys.argv', ['document_anatomy', str(source), '--pdf-source', '--pdf-decode-xrefs',
                                    '--output', str(output)])
    main()
    inventory = json.loads((output/'inventory.json').read_text(encoding='utf-8'))
    item = inventory['items'][0]
    assert item['kind'] == 'pdf-xref-stream'
    assert item['details']['stream_entries_decoded']
    assert (output/item['payload_file']).read_bytes() == data[item['details']['offset']:item['details']['end']]
    assert source.read_bytes() == data
