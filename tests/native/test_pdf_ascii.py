"""Independent stdlib forward encodings and hand-calculated PDF ASCII vectors."""

import base64
import json
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError
from opendoc_formats.native.pdf_byte_filters import ascii85, ascii_hex
from opendoc_formats.support.cancellation import cancellation_scope
from tests.native.test_pdf_object_streams import custom_stream_pdf, inspect
from tests.native.test_pdf_runlength import generic_pdf
from tests.native.test_pdf_xref_streams import own_stream_pdf


def encode(raw, name, whitespace=b''):
    body = raw.hex().encode() if name == 'ASCIIHexDecode' else base64.a85encode(raw)
    return whitespace.join(bytes([value]) for value in body)+(b'>' if name == 'ASCIIHexDecode' else b'~>')


@pytest.mark.parametrize('raw', [b'', b'\0', b'\0'*2, b'\0'*3, b'\0'*4, b'\xff', b'\xff'*2, b'\xff'*3, b'\xff'*4,
                               b'A', b'AB', b'ABC', b'ABCD', bytes(range(256)), bytes(range(256))*20])
@pytest.mark.parametrize('kind', ['hex', '85'])
def test_complete_and_partial_groups_match_independent_stdlib_forward_encoding(raw, kind):
    encoded = raw.hex().encode()+b'>' if kind == 'hex' else base64.a85encode(raw)+b'~>'
    original = bytearray(encoded+b'ignored trailing data')
    decoder = ascii_hex if kind == 'hex' else ascii85
    decoded, consumed = decoder(memoryview(original), len(raw), 'pdf:byte=0: ', expected=len(raw))
    assert decoded == raw and consumed == len(encoded)
    assert original == bytearray(encoded+b'ignored trailing data')


@pytest.mark.parametrize('encoded,expected', [(b'>', b''), (b'f>', b'\xf0'), (b'AbC>', b'\xab\xc0'),
                                             (b'0\0 \t\r\n\fF>', b'\x0f')])
def test_hex_case_odd_nibble_and_all_pdf_whitespace(encoded, expected):
    decoded, consumed = ascii_hex(memoryview(encoded), 100, 'pdf:byte=0: ')
    assert decoded == expected and consumed == len(encoded)


@pytest.mark.parametrize('encoded,expected', [(b'~>', b''), (b'z~>', b'\0'*4), (b'!!!!!~>', b'\0'*4),
                                             (b'!!~>', b'\0'), (b'!!!~>', b'\0'*2), (b'!!!!~>', b'\0'*3),
                                             (b's8W-!~>', b'\xff'*4), (b'!\0 \t\r\n\f!!!!~>', b'\0'*4)])
def test_base85_zero_groups_partial_groups_uint32_boundary_and_pdf_whitespace(encoded, expected):
    decoded, consumed = ascii85(memoryview(encoded), 100, 'pdf:byte=0: ')
    assert decoded == expected and consumed == len(encoded)


@pytest.mark.parametrize('encoded', [b'', b'0', b'GG>', b'<00>', b'00\xff>', b'00v>', b'00\v>'])
def test_hex_malformed_data_is_not_repaired(encoded):
    with pytest.raises(InvalidDocumentError, match='pdf:byte=0'):
        ascii_hex(memoryview(encoded), 100, 'pdf:byte=0: ')


@pytest.mark.parametrize('encoded', [b'', b'z', b'!~>', b'!z~>', b'uuuuu~>', b'uu~>',
                                   b'z~', b'z~x', b'y~>', b'v~>', b'\xff~>', b'z\v~>'])
def test_base85_malformed_groups_overflow_nonpdf_shorthand_and_eod_refuse(encoded):
    with pytest.raises(InvalidDocumentError, match='pdf:byte=0'):
        ascii85(memoryview(encoded), 100, 'pdf:byte=0: ')


@pytest.mark.parametrize('decoder,encoded', [(ascii_hex, b'ff'*1000+b'>'), (ascii85, b'z'*1000+b'~>')])
def test_output_quota_and_declared_length_are_checked_during_decoding(decoder, encoded):
    with pytest.raises(ResourceLimitError, match='byte budget'):
        decoder(memoryview(encoded), 100, 'pdf:byte=0: ')
    with pytest.raises(InvalidDocumentError, match='declared record length'):
        decoder(memoryview(encoded), 100, 'pdf:byte=0: ', expected=1)
    with pytest.raises(InvalidDocumentError, match='EOD disagrees'):
        decoder(memoryview(b'>' if decoder is ascii_hex else b'~>'), 100, 'pdf:byte=0: ', expected=1)


@pytest.mark.parametrize('decoder,eod', [(ascii_hex, b'>'), (ascii85, b'~>')])
def test_cancel_inside_long_whitespace_without_output_allocation(monkeypatch, decoder, eod):
    from opendoc_formats.native import pdf_byte_filters

    source = b' '*10000+eod
    stop = Event()
    real = pdf_byte_filters.checkpoint
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        if calls == 2:
            stop.set()
        real()
    monkeypatch.setattr(pdf_byte_filters, 'checkpoint', cancel)
    with pytest.raises(OperationCancelledError):
        with cancellation_scope(stop.is_set, 'ASCII filter'):
            decoder(memoryview(source), 1, 'pdf:byte=0: ')
    assert calls == 2


@pytest.mark.parametrize('name', ['ASCIIHexDecode', 'ASCII85Decode'])
@pytest.mark.parametrize('raw', [b'', b'A', b'AB', b'ABC', b'ABCD', b'\0'*4,
                               b'\xff', b'\xff'*2, b'\xff'*3, b'\xff'*4, bytes(range(256))])
def test_complete_pdf_streams_agree_with_independent_readers(name, raw):
    source = generic_pdf(encode(raw, name), name)
    mupdf = pytest.importorskip('pymupdf')
    with mupdf.open(stream=source, filetype='pdf') as reader:
        assert not reader.is_repaired and reader.xref_stream(4) == raw
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(source), strict=True)
    assert reader.get_object(pypdf.generic.IndirectObject(4, 0, reader)).get_data() == raw


@pytest.mark.parametrize('name', ['ASCIIHexDecode', 'ASCII85Decode'])
@pytest.mark.parametrize('container', [False, True])
@pytest.mark.parametrize('whitespace', [b'', b' \t\r\n\f', b'\0'])
@pytest.mark.parametrize('trailing', [b'', b'\xffignored'])
def test_xref_and_objstm_records_original_spans_eod_and_pdf_whitespace(name, container, whitespace, trailing):
    factory = custom_stream_pdf if container else own_stream_pdf
    options = {'encoded_change' if container else 'transform': lambda raw: encode(raw, name, whitespace)+trailing}
    source, expected, offsets = factory(flate=False, extra=b'/Filter /'+name.encode(), **options)
    if not container:
        # The xref fixture returns its offsets before the decoded byte array.
        offsets, expected = expected, offsets
    snapshot = inspect(source, capture=True) if container else inspect_binary(source, pdf_source=True,
                                                                            pdf_decode_xrefs=True, capture=True)
    kind = 'pdf-object-stream' if container else 'pdf-xref-stream'
    item = next(item for item in snapshot.items if item.kind == kind)
    details = dict(item.details)
    assert details['filter'] == name and details['decoded_bytes'] == len(expected)
    assert details['trailing_encoded_bytes'] == len(trailing)
    assert details['encoded_data_end']+len(trailing) == details['encoded_end']
    assert item.payload == source[offsets[4 if container else 6]:details['end']]
    if container:
        for member in (item for item in snapshot.items if item.kind == 'pdf-compressed-object'):
            data = dict(member.details)
            assert member.payload == expected[data['decoded_start']:data['decoded_end']]
    else:
        assert details['entries'][5]['object_stream'] == 4
    mupdf = pytest.importorskip('pymupdf')
    with mupdf.open(stream=source, filetype='pdf') as reader:
        assert not reader.is_repaired and reader.xref_stream(4 if container else 6) == expected
    # Keep current pypdf's NUL-hex and trailing-ASCII85 limitations visible in
    # evidence; native bytes and independent MuPDF still cover these variants.
    if not ((name == 'ASCIIHexDecode' and whitespace == b'\0') or (name == 'ASCII85Decode' and trailing)):
        pypdf = pytest.importorskip('pypdf')
        reader = pypdf.PdfReader(BytesIO(source), strict=True)
        assert reader.metadata.title == 'Own compressed metadata'
        assert reader.get_object(pypdf.generic.IndirectObject(4 if container else 6, 0, reader)).get_data() == expected


def test_odd_hex_nibble_in_actual_xref_preserves_original_record_bytes():
    source, _, expected = own_stream_pdf(flate=False, extra=b'/Filter /ASCIIHexDecode',
                                        transform=lambda raw: raw.hex().encode()[:-1]+b'>')
    assert expected[-1] == 0
    snapshot = inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True)
    assert dict(snapshot.items[0].details)['entries'][6]['generation'] == 0
    mupdf = pytest.importorskip('pymupdf')
    with mupdf.open(stream=source, filetype='pdf') as reader:
        assert reader.xref_stream(6) == expected


@pytest.mark.parametrize('name', ['ASCIIHexDecode', 'ASCII85Decode'])
@pytest.mark.parametrize('container', [False, True])
def test_single_filter_null_parameters_and_nonempty_parameters_refusal(name, container):
    from opendoc_formats.errors import UnsupportedDocumentError

    factory = custom_stream_pdf if container else own_stream_pdf
    options = {'encoded_change' if container else 'transform': lambda raw: encode(raw, name)}
    source, _, _ = factory(flate=False, extra=b'/Filter [/'+name.encode()+b'] /DecodeParms [null]', **options)
    inspect(source) if container else inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True)
    source, _, _ = factory(flate=False, extra=b'/Filter /'+name.encode()+b' /DecodeParms << /Predictor 1 >>', **options)
    with pytest.raises(UnsupportedDocumentError, match=name):
        inspect(source) if container else inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True)


def test_ascii85_zero_shorthand_expansion_in_objstm_is_bounded():
    from dataclasses import replace

    source, _, _ = custom_stream_pdf(members=[b'('+b'\0'*2000+b')'], flate=False, extra=b'/Filter /ASCII85Decode',
                                     encoded_change=lambda raw: encode(raw, 'ASCII85Decode'))
    with pytest.raises(ResourceLimitError, match='ASCII data exceeds decoded byte budget'):
        inspect(source, limits=replace(AnatomyLimits(), max_part_bytes=1024))


@pytest.mark.parametrize('name', ['ASCIIHexDecode', 'ASCII85Decode'])
def test_cli_decoding_and_late_missing_eod_do_not_replace_existing_output(tmp_path, monkeypatch, name):
    from tools.document_anatomy import main

    source, output = tmp_path/'source.pdf', tmp_path/'inventory'
    data, _, _ = own_stream_pdf(flate=False, extra=b'/Filter /'+name.encode(), transform=lambda raw: encode(raw, name))
    source.write_bytes(data)
    monkeypatch.setattr('sys.argv', ['anatomy', str(source), '--pdf-source', '--pdf-decode-xrefs', '--output', str(output)])
    main()
    before = (output/'inventory.json').read_bytes()
    assert json.loads(before)['items'][0]['details']['filter'] == name
    assert source.read_bytes() == data
    size = 1 if name == 'ASCIIHexDecode' else 2
    bad, _, _ = own_stream_pdf(flate=False, extra=b'/Filter /'+name.encode(), transform=lambda raw: encode(raw, name)[:-size])
    source.write_bytes(bad)
    with pytest.raises(InvalidDocumentError):
        main()
    assert source.read_bytes() == bad and (output/'inventory.json').read_bytes() == before
