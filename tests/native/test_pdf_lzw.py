"""Independent LZW encoder, prescribed bit vectors and complete byte-level PDFs."""

import base64
import hashlib
from io import BytesIO

import pytest

from opendoc_formats.anatomy import inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError
from opendoc_formats.native.pdf_lzw import unpack
from opendoc_formats.native.pdf_stream_decode import decode
from opendoc_formats.native.pdf_syntax import Name, SyntaxBudget
from opendoc_formats.support.cancellation import cancellation_scope
from tests.native.test_pdf_filter_pipeline import declaration
from tests.native.test_pdf_object_streams import custom_stream_pdf, inspect
from tests.native.test_pdf_predictors import png_encode
from tests.native.test_pdf_runlength import generic_pdf
from tests.native.test_pdf_tiff_predictor import tiff_encode
from tests.native.test_pdf_xref_streams import own_stream_pdf


def pack(codes, early=1):
    # Bit writer works from symbols, independently of phrase encoding/decoding.
    bits = []
    width, entries, previous = 9, 258, False
    for code in codes:
        bits.append(format(code, f'0{width}b'))
        if code == 256:
            width, entries, previous = 9, 258, False
        elif code != 257:
            if previous:
                entries += 1
                if width < 12 and entries == (1 << width)-early:
                    width += 1
            previous = True
    text = ''.join(bits)
    text += '0'*(-len(text) % 8)
    return int(text, 2).to_bytes(len(text)//8, 'big') if text else b''


def encode(raw, early=1):
    # Forward longest-match encoder; reset well before dictionary saturation.
    table = {bytes([value]): value for value in range(256)}
    codes, phrase = [256], b''
    for value in raw:
        candidate = phrase+bytes([value])
        if candidate in table:
            phrase = candidate
            continue
        codes.append(table[phrase])
        table[candidate] = len(table)+2
        phrase = bytes([value])
        if len(table) == 3000:
            codes.append(256)
            table = {bytes([byte]): byte for byte in range(256)}
    if phrase:
        codes.append(table[phrase])
    return pack(codes+[257], early)


def stream_pdf(encoded, early):
    source = generic_pdf(encoded, 'LZWDecode')
    if early == 0:
        source = source.replace(b'/Filter /LZWDecode', b'/Filter /LZWDecode /DecodeParms << /EarlyChange 0 >>')
        head, _ = source.rsplit(b'startxref\n', 1)
        source = head+b'startxref\n'+str(source.index(b'xref\n0 5')).encode()+b'\n%%EOF\n'
    return source


def external(source, object_number, expected, *, predicted=None, pypdf_mode='exact'):
    mupdf = pytest.importorskip('pymupdf')
    with mupdf.open(stream=source, filetype='pdf') as reader:
        assert not reader.is_repaired and reader.xref_stream(object_number) == expected
    pypdf = pytest.importorskip('pypdf')
    if predicted is not None and object_number == 6:
        # pypdf 6.19 does not apply LZW PNG predictors and cannot read this xref.
        with pytest.raises(pypdf.errors.PdfReadError, match='Unknown xref type'):
            pypdf.PdfReader(BytesIO(source), strict=True)
        return
    reader = pypdf.PdfReader(BytesIO(source), strict=True)
    if pypdf_mode == 'early0-error':
        with pytest.raises(pypdf.errors.PdfStreamError, match='LZW code'):
            reader.get_object(pypdf.generic.IndirectObject(object_number, 0, reader)).get_data()
        return
    actual = reader.get_object(pypdf.generic.IndirectObject(object_number, 0, reader)).get_data()
    if pypdf_mode == 'early0-mismatch':
        assert actual != expected  # Preserve the independent decoder disagreement.
    else:
        assert actual == (predicted if predicted is not None else expected)


@pytest.mark.parametrize('early', [0, 1])
@pytest.mark.parametrize('raw', [b'', b'A', b'AAA', b'A'*30000, bytes(range(256))*80,
                               hashlib.shake_256(b'Independent LZW original').digest(20000)],
                         ids=['empty', 'literal', 'special', 'long-repeat', 'byte-range', 'random-resets'])
def test_forward_encoder_and_external_readers(raw, early):
    encoded = encode(raw, early)
    actual, consumed = unpack(memoryview(encoded+b'trailing'), len(raw), 'pdf:byte=0: ', early_change=early)
    assert actual == raw and consumed == len(encoded)
    external(stream_pdf(encoded, early), 4, raw,
             pypdf_mode='early0-error' if early == 0 and len(raw) >= 20000 and raw != b'A'*30000 else 'exact')


@pytest.mark.parametrize('early', [0, 1])
@pytest.mark.parametrize('count', [253, 254, 255, 256, 765, 766, 767, 768, 1789, 1790, 1791, 1792, 3838, 3839])
def test_all_width_boundaries_full_dictionary_and_clear(early, count):
    raw = bytes(i % 256 for i in range(count))
    encoded = pack([256, *raw, 256, 65, 258, 257], early)
    expected = raw+b'AAA'
    actual, consumed = unpack(memoryview(encoded), len(expected), 'pdf:byte=0: ', early_change=early)
    assert actual == expected and consumed == len(encoded)
    external(stream_pdf(encoded, early), 4, expected,
             pypdf_mode=('early0-mismatch' if count <= 256 else 'early0-error')
             if early == 0 and count >= 254 else 'exact')


def test_hand_calculated_msb_vector_special_phrase_and_nonzero_padding():
    # 256, 65, 258, 257 in nine bits = 80 10 60 50 10 (four padding bits).
    raw = bytes.fromhex('801060501f')
    assert unpack(memoryview(raw+b'unchanged'), 3, 'pdf:byte=0: ') == (b'AAA', 5)
    assert unpack(memoryview(pack([65, 257])), 1, 'pdf:byte=0: ')[0] == b'A'
    assert unpack(memoryview(pack([256, 256, 257])), 0, 'pdf:byte=0: ')[0] == b''


@pytest.mark.parametrize('codes', [[257], [256, 65, 257], [256, 65, 258, 257]])
def test_eod_with_expected_size_and_quota(codes):
    raw = pack(codes)
    expected = 0 if codes == [257] else 1 if 258 not in codes else 3
    assert len(unpack(memoryview(raw), expected, 'pdf:byte=0: ', expected=expected)[0]) == expected
    with pytest.raises(InvalidDocumentError, match='decoded length'):
        unpack(memoryview(raw), 100, 'pdf:byte=0: ', expected=expected+1)
    if expected:
        with pytest.raises(ResourceLimitError, match='byte budget'):
            unpack(memoryview(raw), expected-1, 'pdf:byte=0: ')
        with pytest.raises(InvalidDocumentError, match='record length'):
            unpack(memoryview(raw), 100, 'pdf:byte=0: ', expected=expected-1)


@pytest.mark.parametrize('raw', [b'', b'\x80', pack([256, 65]), pack([256, 258, 257]),
                               pack([256, 65, 259, 257]), pack([256, *([65]*3840), 257])])
def test_corruption_and_full_table_without_clear_refuse(raw):
    with pytest.raises(InvalidDocumentError, match='pdf:byte=7'):
        unpack(memoryview(raw), 100000, 'pdf:byte=7: ')


@pytest.mark.parametrize('early', [-1, 2, True, '1', None])
def test_invalid_earlychange_refuses_before_decoder(monkeypatch, early):
    from opendoc_formats.native import pdf_stream_decode
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid whole plan must not start decoding')
    monkeypatch.setattr(pdf_stream_decode, 'unpack_lzw', forbidden)
    with pytest.raises(InvalidDocumentError, match='EarlyChange'):
        decode(memoryview(b''), Name('LZWDecode'), {'EarlyChange': early}, source_start=0,
               part_limit=100, byte_limit=100, location='pdf:byte=0: ', budget=SyntaxBudget(100, 10))


@pytest.mark.parametrize('container', [False, True])
@pytest.mark.parametrize('early', [0, 1])
@pytest.mark.parametrize('predictor', [1, 2, 12])
@pytest.mark.parametrize('chain', [False, True])
def test_complete_sources_predictors_pipeline_and_exact_payload(container, early, predictor, chain):
    filters = ('ASCII85Decode', 'LZWDecode') if chain else ('LZWDecode',)
    parameters = ([None] if chain else [])+[{'EarlyChange': early, 'Predictor': predictor, 'Columns': 1}]
    saved = []
    def transform(raw):
        predicted = (png_encode(raw, 1, 1, [0, 1, 2, 3, 4]) if predictor >= 10
                     else tiff_encode(raw, 1, 8, 1) if predictor == 2 else raw)
        encoded = encode(predicted, early)
        saved.append((len(predicted), len(encoded)))
        return base64.a85encode(encoded)+b'~>' if chain else encoded+b'preserved trailing'
    factory = custom_stream_pdf if container else own_stream_pdf
    source, a, b = factory(flate=False, extra=declaration(filters, parameters),
                           **{'encoded_change' if container else 'transform': transform})
    expected, offsets = (a, b) if container else (b, a)
    snapshot = inspect(source, capture=True) if container else inspect_binary(source, pdf_source=True,
                                                                            pdf_decode_xrefs=True, capture=True)
    item = next(i for i in snapshot.items if i.kind == ('pdf-object-stream' if container else 'pdf-xref-stream'))
    details = dict(item.details)
    assert item.payload == source[offsets[4 if container else 6]:details['end']]
    assert details['filter_chain'] == list(filters)
    assert details['decoded_bytes'] == len(expected)
    assert details['decode_work_bytes'] == saved[0][0]+(saved[0][1] if chain else 0)
    assert details['decode_stages'][-1]['decoded_sha256'] == hashlib.sha256(expected).hexdigest()
    if not chain:
        assert details['trailing_encoded_bytes'] == len(b'preserved trailing')
    external(source, 4 if container else 6, expected,
             predicted=png_encode(expected, 1, 1, [0, 1, 2, 3, 4]) if predictor == 12 else None)


def test_cancellation_during_clear_codes_and_long_expansion():
    for raw in [pack([256]*1000+[257]), encode(b'A'*30000)]:
        calls = 0
        def cancel():
            nonlocal calls
            calls += 1
            return calls > 20
        with pytest.raises(OperationCancelledError):
            with cancellation_scope(cancel, 'LZW'):
                unpack(memoryview(raw), 50000, 'pdf:byte=0: ')


@pytest.mark.parametrize('early', [0, 1])
def test_full_dictionary_can_end_without_extra_clear(early):
    raw = bytes(i % 256 for i in range(3839))
    assert unpack(memoryview(pack([256, *raw, 257], early)), len(raw), 'pdf:byte=0: ', early_change=early)[0] == raw


def test_lzw_pipeline_aggregate_exact_boundary():
    raw = b'own decoded stream'*100
    inner = encode(raw)
    encoded = base64.a85encode(inner)+b'~>'
    options = dict(source_start=0, part_limit=10000, location='pdf:byte=0: ', expected=len(raw))
    filters = [Name('ASCII85Decode'), Name('LZWDecode')]
    actual, info = decode(memoryview(encoded), filters, None, byte_limit=len(inner)+len(raw),
                          budget=SyntaxBudget(100, 10), **options)
    assert actual == raw and info['decode_work_bytes'] == len(inner)+len(raw)
    with pytest.raises(ResourceLimitError):
        decode(memoryview(encoded), filters, None, byte_limit=len(inner)+len(raw)-1,
               budget=SyntaxBudget(100, 10), **options)


def test_cli_late_lzw_failure_keeps_source_and_existing_destination(tmp_path, monkeypatch):
    from tools.document_anatomy import main
    extra = b'/Filter /LZWDecode'
    good, _, _ = own_stream_pdf(flate=False, extra=extra, transform=encode)
    source, output = tmp_path/'source.pdf', tmp_path/'inventory'
    source.write_bytes(good)
    monkeypatch.setattr('sys.argv', ['anatomy', str(source), '--pdf-source', '--pdf-decode-xrefs', '--output', str(output)])
    main()
    before = (output/'inventory.json').read_bytes()
    bad, _, _ = own_stream_pdf(flate=False, extra=extra, transform=lambda raw: pack([256, 65]))
    source.write_bytes(bad)
    with pytest.raises(InvalidDocumentError, match='LZW'):
        main()
    assert source.read_bytes() == bad and (output/'inventory.json').read_bytes() == before
