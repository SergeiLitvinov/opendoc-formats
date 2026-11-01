"""Independent byte-level PDF/RunLength originals, exact payloads and bounded failures."""

import hashlib
import itertools
import json
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_runlength import unpack
from tests.native.test_pdf_object_streams import custom_stream_pdf, inspect
from tests.native.test_pdf_xref_streams import own_stream_pdf


def encode(raw, *, literal=False):
    if literal:
        return b''.join(bytes([len(raw[i:i+128])-1])+raw[i:i+128] for i in range(0, len(raw), 128))+b'\x80'
    output = bytearray()
    for value, grouped in itertools.groupby(raw):
        count = len(list(grouped))
        while count:
            amount = min(128, count)
            output.extend(bytes([0, value]) if amount == 1 else bytes([257-amount, value]))
            count -= amount
    return bytes(output)+b'\x80'


def generic_pdf(encoded, filter_name='RunLengthDecode'):
    data = bytearray(b'%PDF-1.7\n')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] >>',
               f'<< /Length {len(encoded)} /Filter /{filter_name} >>\nstream\n'.encode()+encoded+b'\nendstream']
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f'{number} 0 obj\n'.encode()+body+b'\nendobj\n')
    xref = len(data)
    data.extend(b'xref\n0 5\n0000000000 65535 f \n')
    data.extend(b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets))
    data.extend(f'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(data)


@pytest.mark.parametrize('tag', range(256))
def test_every_control_byte_matches_hand_derived_run_length_and_keeps_input(tag):
    if tag < 128:
        expected = bytes((128+index) % 256 for index in range(tag+1))
        raw = bytes([tag])+expected+b'\x80'
    elif tag == 128:
        expected, raw = b'', b'\x80'
    else:
        expected, raw = b'\x80'*(257-tag), bytes([tag, 128, 128])
    original = bytearray(raw)
    actual, consumed = unpack(memoryview(original), len(expected), 'pdf:byte=0: ', expected=len(expected))
    assert actual == expected and consumed == len(raw) and original == bytearray(raw)


@pytest.mark.parametrize('literal', [False, True])
@pytest.mark.parametrize('raw', [b'', b'\x80', b'A'*2, b'A'*128, b'A'*129,
                               bytes(range(127)), bytes(range(128)), bytes(range(256)), b'AABB\0\x80\xff'*100])
def test_complete_streams_agree_byte_for_byte_with_independent_pdf_decoders(raw, literal):
    source = generic_pdf(encode(raw, literal=literal))
    mupdf = pytest.importorskip('pymupdf')
    with mupdf.open(stream=source, filetype='pdf') as reader:
        assert not reader.is_repaired and len(reader) == 1 and reader.xref_stream(4) == raw
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(source), strict=True)
    assert reader.get_object(pypdf.generic.IndirectObject(4, 0, reader)).get_data() == raw


@pytest.mark.parametrize('literal', [False, True])
@pytest.mark.parametrize('trailing', [b'', b'\n', b'\x80ignored\xff\0'])
def test_xref_records_eod_boundary_and_complete_original_bytes(literal, trailing):
    source, offsets, expected = own_stream_pdf(flate=False, extra=b'/Filter /RunLengthDecode',
                                              transform=lambda raw: encode(raw, literal=literal)+trailing)
    snapshot = inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, capture=True)
    item = snapshot.items[0]
    info = dict(item.details)
    assert info['filter'] == 'RunLengthDecode' and info['decoded_bytes'] == info['decode_work_bytes'] == len(expected)
    assert info['trailing_encoded_bytes'] == len(trailing)
    assert source[info['encoded_data_end']-1] == 128 and info['encoded_data_end']+len(trailing) == info['encoded_end']
    assert item.payload == source[offsets[6]:info['end']]
    assert info['entries'][0]['generation'] == 65535
    assert info['entries'][5]['object_stream'] == 4 and info['entries'][5]['object_stream_index'] == 0
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(source), strict=True)
    assert len(reader.pages) == 1 and reader.metadata.title == 'Own compressed metadata'
    assert reader.get_object(pypdf.generic.IndirectObject(6, 0, reader)).get_data() == expected
    mupdf = pytest.importorskip('pymupdf')
    with mupdf.open(stream=source, filetype='pdf') as reader:
        assert not reader.is_repaired and reader.xref_stream(6) == expected


@pytest.mark.parametrize('literal', [False, True])
@pytest.mark.parametrize('trailing', [b'', b'\x80after EOD'])
def test_object_container_members_and_exact_source_span_agree_with_external_readers(literal, trailing):
    source, expected, offsets = custom_stream_pdf(flate=False, extra=b'/Filter /RunLengthDecode',
                                                 encoded_change=lambda raw: encode(raw, literal=literal)+trailing)
    snapshot = inspect(source, capture=True)
    container = next(item for item in snapshot.items if item.kind == 'pdf-object-stream')
    info = dict(container.details)
    assert info['filter'] == 'RunLengthDecode' and info['decoded_bytes'] == len(expected)
    assert info['trailing_encoded_bytes'] == len(trailing) and info['encoded_data_end']+len(trailing) == info['encoded_end']
    assert container.payload == source[offsets[4]:info['end']]
    members = [item for item in snapshot.items if item.kind == 'pdf-compressed-object']
    assert members[-1].payload == b'null' and len(members) == 4
    for member in members:
        entry = dict(member.details)
        assert member.payload == expected[entry['decoded_start']:entry['decoded_end']]
        assert not entry['active_resolution'] and member.sha256 == hashlib.sha256(member.payload).hexdigest()
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(source), strict=True)
    assert reader.metadata.title == 'Own compressed metadata'
    assert reader.get_object(pypdf.generic.IndirectObject(8, 0, reader)) == 42
    mupdf = pytest.importorskip('pymupdf')
    with mupdf.open(stream=source, filetype='pdf') as reader:
        assert not reader.is_repaired and reader.xref_stream(4) == expected


@pytest.mark.parametrize('raw', [b'', b'\0', b'\x7fshort\x80', b'\x81', b'\xffA', b'\0A'])
def test_missing_eod_and_truncated_runs_refuse(raw):
    with pytest.raises(InvalidDocumentError, match='pdf:byte=0'):
        unpack(memoryview(raw), 1000, 'pdf:byte=0: ')


def test_repeat_expansion_and_declared_count_fail_without_returning_partial_data():
    raw = memoryview(b'\x81A'*10000+b'\x80')
    with pytest.raises(ResourceLimitError, match='byte budget'):
        unpack(raw, 1024, 'pdf:byte=0: ')
    with pytest.raises(InvalidDocumentError, match='declared record length'):
        unpack(raw, 1024, 'pdf:byte=0: ', expected=49)
    with pytest.raises(InvalidDocumentError, match='EOD disagrees'):
        unpack(memoryview(b'\0A\x80'), 1024, 'pdf:byte=0: ', expected=2)


def test_unknown_object_stream_length_expansion_obeys_remaining_byte_budget():
    source, _, _ = custom_stream_pdf(members=[b'('+b'A'*10000+b')'], flate=False,
                                     extra=b'/Filter /RunLengthDecode', encoded_change=encode)
    with pytest.raises(ResourceLimitError, match='RunLengthDecode exceeds decoded byte budget'):
        inspect(source, limits=replace(AnatomyLimits(), max_part_bytes=1024))


@pytest.mark.parametrize('container', [False, True])
def test_nonempty_parameters_refuse_and_null_single_array_is_accepted(container):
    factory = custom_stream_pdf if container else own_stream_pdf
    kwargs = {'encoded_change': encode} if container else {'transform': encode}
    source, _, _ = factory(flate=False, extra=b'/Filter [/RunLengthDecode] /DecodeParms [null]', **kwargs)
    inspect(source) if container else inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True)
    source, _, _ = factory(flate=False, extra=b'/Filter /RunLengthDecode /DecodeParms << /Predictor 1 >>', **kwargs)
    with pytest.raises(UnsupportedDocumentError, match='RunLengthDecode'):
        inspect(source) if container else inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True)


def test_exact_combined_xref_budget_and_preflight_before_decoder(monkeypatch):
    from opendoc_formats.native import pdf_stream_decode

    source, offsets, expected = own_stream_pdf(flate=False, extra=b'/Filter /RunLengthDecode', transform=encode)
    snapshot = inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True)
    physical = dict(snapshot.items[0].details)['end']-offsets[6]
    inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True,
                   limits=replace(AnatomyLimits(), max_total_bytes=physical+len(expected)))
    with pytest.raises(ResourceLimitError):
        inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True,
                       limits=replace(AnatomyLimits(), max_total_bytes=physical+len(expected)-1))
    def forbidden(*args, **kwargs):
        pytest.fail('Declared byte quota must precede the RunLength decoder')
    monkeypatch.setitem(pdf_stream_decode.BYTE_DECODERS, 'RunLengthDecode', forbidden)
    with pytest.raises(ResourceLimitError):
        inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, limits=replace(AnatomyLimits(), max_total_bytes=48))


def test_cancel_inside_run_reconstruction(monkeypatch):
    from opendoc_formats.native import pdf_runlength

    # Structural stress source, not an assertion of valid active object bodies.
    source, offsets, _ = own_stream_pdf(flate=False, extra=b'/Filter /RunLengthDecode', payload=bytes(7000),
                                       transform=lambda raw: encode(raw, literal=True))
    source = source[:offsets[6]]+source[offsets[6]:].replace(b'/Size 7', b'/Size 1000')
    stop = Event()
    real = pdf_runlength.checkpoint
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        if calls == 3:
            stop.set()
        real()
    monkeypatch.setattr(pdf_runlength, 'checkpoint', cancel)
    with pytest.raises(OperationCancelledError):
        inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, cancelled=stop.is_set)
    assert calls == 3


def test_cli_evidence_and_late_eod_failure_leave_existing_output_unchanged(tmp_path, monkeypatch):
    from tools.document_anatomy import main

    source, output = tmp_path/'source.pdf', tmp_path/'inventory'
    good, _, _ = own_stream_pdf(flate=False, extra=b'/Filter /RunLengthDecode', transform=encode)
    source.write_bytes(good)
    monkeypatch.setattr('sys.argv', ['anatomy', str(source), '--pdf-source', '--pdf-decode-xrefs', '--output', str(output)])
    main()
    before = (output/'inventory.json').read_bytes()
    record = json.loads(before)['items'][0]
    assert record['details']['filter'] == 'RunLengthDecode'
    assert source.read_bytes() == good
    bad, _, _ = own_stream_pdf(flate=False, extra=b'/Filter /RunLengthDecode', transform=lambda raw: encode(raw)[:-1])
    source.write_bytes(bad)
    with pytest.raises(InvalidDocumentError):
        main()
    assert (output/'inventory.json').read_bytes() == before and source.read_bytes() == bad
