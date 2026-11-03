"""Independent inverse pipelines build complete sources; every decoded stage is checked."""

import base64
import hashlib
import json
import zlib
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_stream_decode import decode
from opendoc_formats.native.pdf_syntax import Name, SyntaxBudget
from tests.native.test_pdf_object_streams import custom_stream_pdf, inspect
from tests.native.test_pdf_predictors import png_encode
from tests.native.test_pdf_runlength import encode as rle_encode
from tests.native.test_pdf_tiff_predictor import tiff_encode
from tests.native.test_pdf_xref_streams import own_stream_pdf

CHAINS = [('ASCII85Decode', 'FlateDecode'), ('ASCIIHexDecode', 'FlateDecode'),
          ('ASCIIHexDecode', 'ASCII85Decode', 'FlateDecode'), ('FlateDecode', 'FlateDecode'),
          ('RunLengthDecode', 'ASCII85Decode', 'FlateDecode'), ('FlateDecode', 'ASCII85Decode'),
          ('FlateDecode', 'ASCIIHexDecode'), ('ASCII85Decode', 'RunLengthDecode'),
          ('RunLengthDecode', 'FlateDecode'), ('ASCII85Decode', 'FlateDecode', 'ASCIIHexDecode', 'FlateDecode')]


def encode_chain(raw, filters, parameters):
    outputs, work = {}, {}
    current = raw
    for index in reversed(range(len(filters))):
        name, options = filters[index], parameters[index] or {}
        outputs[index] = current
        if name == 'FlateDecode':
            predictor = options.get('Predictor', 1)
            predicted = (png_encode(current, 1, 1, [0, 1, 2, 3, 4]) if predictor >= 10
                         else tiff_encode(current, 1, 8, 1) if predictor == 2 else current)
            work[index] = len(predicted)
            current = zlib.compress(predicted)
        else:
            work[index] = len(current)
            current = (base64.a85encode(current)+b'~>' if name == 'ASCII85Decode' else current.hex().encode()+b'>'
                       if name == 'ASCIIHexDecode' else rle_encode(current))
    return current, [outputs[index] for index in range(len(filters))], [work[index] for index in range(len(filters))]


def declaration(filters, parameters):
    specs = [b'null' if options is None else b'<< '+b' '.join(b'/'+key.encode()+b' '+str(value).encode()
             for key, value in options.items())+b' >>' for options in parameters]
    return (b'/Filter ['+b' '.join(b'/'+name.encode() for name in filters)+b'] /DecodeParms ['+b' '.join(specs)+b']')


@pytest.mark.parametrize('filters', CHAINS)
@pytest.mark.parametrize('predictor', [1, 2, 12])
@pytest.mark.parametrize('container', [False, True])
def test_complete_xref_and_object_pipelines_and_each_stage_agree_with_independent_readers(filters, predictor, container):
    parameters = [{'Predictor': predictor, 'Columns': 1} if name == 'FlateDecode' else None for name in filters]
    saved = []
    def transform(raw):
        encoded, outputs, work = encode_chain(raw, filters, parameters)
        saved.append((encoded, outputs, work))
        return encoded
    factory = custom_stream_pdf if container else own_stream_pdf
    options = {'encoded_change' if container else 'transform': transform}
    source, a, b = factory(flate=False, extra=declaration(filters, parameters), **options)
    expected, offsets = (a, b) if container else (b, a)
    snapshot = inspect(source, capture=True) if container else inspect_binary(source, pdf_source=True,
                                                                            pdf_decode_xrefs=True, capture=True)
    item = next(i for i in snapshot.items if i.kind == ('pdf-object-stream' if container else 'pdf-xref-stream'))
    details = dict(item.details)
    assert details['filter'] == details['filter_chain'] == list(filters)
    assert details['decode_work_bytes'] == sum(saved[0][2])
    assert details['decoded_bytes'] == len(expected)
    assert item.payload == source[offsets[4 if container else 6]:details['end']]
    for index, stage in enumerate(details['decode_stages']):
        assert stage['filter'] == filters[index] and stage['decoded_bytes'] == len(saved[0][1][index])
        assert stage['decoded_sha256'] == hashlib.sha256(saved[0][1][index]).hexdigest()
        assert stage['decode_work_bytes'] == saved[0][2][index]
        assert stage['input_space'] == ('source' if index == 0 else f'stage[{index-1}]-output')
    if container:
        for member in (i for i in snapshot.items if i.kind == 'pdf-compressed-object'):
            bounds = dict(member.details)
            assert member.payload == expected[bounds['decoded_start']:bounds['decoded_end']]
    mupdf = pytest.importorskip('pymupdf')
    with mupdf.open(stream=source, filetype='pdf') as reader:
        assert not reader.is_repaired and reader.xref_stream(4 if container else 6) == expected
        assert reader.metadata['title'] == 'Own compressed metadata'
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(source), strict=True)
    assert len(reader.pages) == 1 and reader.metadata.title == 'Own compressed metadata'
    assert reader.get_object(pypdf.generic.IndirectObject(4 if container else 6, 0, reader)).get_data() == expected


def test_aggregate_work_and_intermediate_limits_include_every_stage():
    filters = ('ASCII85Decode', 'FlateDecode', 'FlateDecode')
    encoded, outputs, work = encode_chain(b'A'*1000, filters, [None]*3)
    kwargs = {'source_start': 100, 'part_limit': 2000, 'location': 'pdf:byte=100: ', 'expected': 1000}
    actual, info = decode(memoryview(encoded), [Name(n) for n in filters], None,
                          byte_limit=sum(work), budget=SyntaxBudget(100, 10), **kwargs)
    assert actual == b'A'*1000 and info['decode_work_bytes'] == sum(work)
    assert info['decode_work_bytes'] > len(actual)
    with pytest.raises(ResourceLimitError):
        decode(memoryview(encoded), [Name(n) for n in filters], None,
               byte_limit=sum(work)-1, budget=SyntaxBudget(100, 10), **kwargs)
    assert [stage['decoded_bytes'] for stage in info['decode_stages']] == [len(x) for x in outputs]
    # A small compressed input expands into a large hex intermediate, then shrinks.
    encoded, _, _ = encode_chain(b'A'*500, ('FlateDecode', 'ASCIIHexDecode'), [None, None])
    with pytest.raises(ResourceLimitError):
        decode(memoryview(encoded), [Name('FlateDecode'), Name('ASCIIHexDecode')], None, source_start=0,
               part_limit=600, byte_limit=5000, expected=500, location='pdf:byte=0: ', budget=SyntaxBudget(100, 10))


@pytest.mark.parametrize('filters,parameters,error', [
    ([Name('ASCII85Decode'), Name('FlateDecode')], [None], InvalidDocumentError),
    ([Name('ASCII85Decode'), Name('FlateDecode')], {}, UnsupportedDocumentError),
    ([Name('ASCII85Decode'), Name('FlateDecode')], [None, 3], UnsupportedDocumentError),
    ([Name('ASCII85Decode'), Name('UnknownDecode')], None, UnsupportedDocumentError),
    ([Name('ASCII85Decode'), None], None, UnsupportedDocumentError),
    ([Name('ASCII85Decode'), Name('FlateDecode')], [{'Predictor': 1}, None], UnsupportedDocumentError),
])
def test_entire_plan_is_validated_before_any_decoder(monkeypatch, filters, parameters, error):
    from opendoc_formats.native import pdf_stream_decode

    def forbidden(*args, **kwargs):
        pytest.fail('No bytes should be decoded before every filter/parameter is accepted')
    monkeypatch.setitem(pdf_stream_decode.BYTE_DECODERS, 'ASCII85Decode', forbidden)
    with pytest.raises(error, match='pdf:byte=0'):
        decode(memoryview(b'~>'), filters, parameters, source_start=0, part_limit=100, byte_limit=100,
               expected=1, location='pdf:byte=0: ', budget=SyntaxBudget(100, 10))


def test_stage_count_uses_shared_token_budget_before_decode(monkeypatch):
    from opendoc_formats.native import pdf_stream_decode

    def forbidden(*args, **kwargs):
        pytest.fail('Filter stage quota must precede decoding')
    monkeypatch.setitem(pdf_stream_decode.BYTE_DECODERS, 'ASCII85Decode', forbidden)
    with pytest.raises(ResourceLimitError, match='filter stages'):
        decode(memoryview(b'~>'), [Name('ASCII85Decode')]*1000, None, source_start=0, part_limit=100,
               byte_limit=100, expected=1, location='pdf:byte=0: ', budget=SyntaxBudget(8, 10))


def test_cancellation_between_stages_never_enters_next_decoder(monkeypatch):
    from opendoc_formats.native import pdf_stream_decode

    source, _, _ = own_stream_pdf(flate=False, extra=declaration(('ASCII85Decode', 'FlateDecode'), [None, None]),
                                  transform=lambda raw: encode_chain(raw, ('ASCII85Decode', 'FlateDecode'), [None, None])[0])
    stop = Event()
    first = pdf_stream_decode.BYTE_DECODERS['ASCII85Decode']
    def cancel(*args, **kwargs):
        result = first(*args, **kwargs)
        stop.set()
        return result
    def forbidden(*args, **kwargs):
        pytest.fail('Cancelled pipeline must not run the next filter')
    monkeypatch.setitem(pdf_stream_decode.BYTE_DECODERS, 'ASCII85Decode', cancel)
    monkeypatch.setattr(pdf_stream_decode, 'inflate', forbidden)
    with pytest.raises(OperationCancelledError):
        inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, cancelled=stop.is_set)


def test_cli_keeps_physical_payload_and_does_not_replace_output_after_late_filter_failure(tmp_path, monkeypatch):
    from tools.document_anatomy import main

    filters = ('ASCIIHexDecode', 'FlateDecode')
    extra = declaration(filters, [None, None])
    good, _, _ = own_stream_pdf(flate=False, extra=extra, transform=lambda raw: encode_chain(raw, filters, [None, None])[0])
    source, output = tmp_path/'source.pdf', tmp_path/'inventory'
    source.write_bytes(good)
    monkeypatch.setattr('sys.argv', ['anatomy', str(source), '--pdf-source', '--pdf-decode-xrefs', '--output', str(output)])
    main()
    before = (output/'inventory.json').read_bytes()
    record = json.loads(before)['items'][0]
    assert record['details']['filter_chain'] == list(filters)
    assert (output/record['payload_file']).read_bytes() == good[record['details']['offset']:record['details']['end']]
    bad, _, _ = own_stream_pdf(flate=False, extra=extra, transform=lambda raw: b'bad zlib'.hex().encode()+b'>')
    source.write_bytes(bad)
    with pytest.raises(InvalidDocumentError, match=r'filter\[1\]=FlateDecode'):
        main()
    assert source.read_bytes() == bad and (output/'inventory.json').read_bytes() == before
