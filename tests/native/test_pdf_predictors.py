"""Independent forward PNG rows and external PDF/PNG decoders check inverse prediction."""

import struct
import zlib
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_predictors import layout, undo_png
from opendoc_formats.native.pdf_syntax import Name, SyntaxBudget
from opendoc_formats.native.pdf_xref_streams import decode_xref
from tests.native.test_pdf_xref_streams import own_stream_pdf


def png_encode(raw, row_bytes, stride, tags):
    """Own forward encoder uses immutable complete rows, independent of in-place inverse."""
    result = bytearray()
    previous = bytes(row_bytes)
    for row_number, start in enumerate(range(0, len(raw), row_bytes)):
        row = raw[start:start+row_bytes]
        tag = tags[row_number % len(tags)]
        result.append(tag)
        for column, sample in enumerate(row):
            left = row[column-stride] if column >= stride else 0
            up = previous[column]
            corner = previous[column-stride] if column >= stride else 0
            choices = (0, left, up, (left+up)//2,
                       min((left, up, corner), key=lambda candidate: abs(left+up-corner-candidate)))
            result.append((sample-choices[tag]) % 256)
        previous = row
    return bytes(result)


@pytest.mark.parametrize('predictor', range(10, 16))
def test_complete_pdf_all_declared_png_predictors_use_actual_row_tags_and_agree_with_pypdf(predictor):
    data, offsets, raw = own_stream_pdf(
        extra=f'/DecodeParms << /Predictor {predictor} /Columns 7 >>'.encode(),
        transform=lambda value: png_encode(value, 7, 1, [0, 1, 2, 3, 4, 0, 4]))
    snapshot = inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True, capture=True)
    item = snapshot.items[0]
    details = dict(item.details)
    assert details['predictor'] == predictor and details['decoded_bytes'] == len(raw)
    assert details['decode_work_bytes'] == 56
    assert dict(snapshot.details)['decoded_xref_bytes'] == 49
    assert dict(snapshot.details)['xref_decode_work_bytes'] == 56
    assert item.payload == data[offsets[6]:details['end']]
    for entry in details['entries']:
        if entry['entry_type'] == 1:
            assert entry['offset_or_next_free'] == offsets[entry['object']]
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(data), strict=True)
    assert len(reader.pages) == 1 and reader.metadata.title == 'Own compressed metadata'
    assert reader.get_object(pypdf.generic.IndirectObject(6, 0, reader)).get_data() == raw


@pytest.mark.parametrize('bits,colors,columns', [(1, 1, 13), (2, 1, 5), (4, 1, 3), (8, 1, 7),
                                               (16, 1, 7), (8, 3, 7), (8, 4, 7)])
@pytest.mark.parametrize('tag', range(5))
def test_packed_16bit_and_multicomponent_rows_agree_with_independent_png_decoder(bits, colors, columns, tag):
    image = pytest.importorskip('PIL.Image')
    row_bytes = (bits*colors*columns+7)//8
    stride = (bits*colors+7)//8
    raw = bytes((position*37+position//3*11+17) % 256 for position in range(row_bytes*4))
    encoded = png_encode(raw, row_bytes, stride, [tag])
    parameters = {'Predictor': 15, 'BitsPerComponent': bits, 'Colors': colors, 'Columns': columns}
    _, actual_row, actual_stride, work = layout(parameters, len(raw), 'pdf:byte=0: ')
    output = bytearray(encoded)
    undo_png(output, actual_row, actual_stride, 'pdf:byte=0: ')
    assert bytes(output) == raw and work == len(encoded)

    def chunk(name, payload):
        return struct.pack('>I', len(payload))+name+payload+struct.pack('>I', zlib.crc32(name+payload))
    header = struct.pack('>IIBBBBB', columns, 4, bits, {1: 0, 3: 2, 4: 6}[colors], 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', header)+chunk(b'IDAT', zlib.compress(encoded))+chunk(b'IEND', b'')
    with image.open(BytesIO(png)) as decoded:
        if bits == 8:
            assert decoded.tobytes() == raw
        elif bits == 16:
            assert [decoded.getpixel((x, y)) for y in range(4) for x in range(columns)] == [
                int.from_bytes(raw[offset:offset+2], 'big') for offset in range(0, len(raw), 2)]
        else:
            expected = []
            for start in range(0, len(raw), row_bytes):
                row = int.from_bytes(raw[start:start+row_bytes], 'big')
                for column in range(columns):
                    sample = (row >> (row_bytes*8-(column+1)*bits)) & ((1 << bits)-1)
                    expected.append(sample*255//((1 << bits)-1))
            grayscale = decoded.convert('L')
            assert [grayscale.getpixel((x, y)) for y in range(4) for x in range(columns)] == expected


def test_default_geometry_allows_predictor_rows_inside_xref_records():
    data, offsets, _ = own_stream_pdf(extra=b'/DecodeParms << /Predictor 12 >>',
                                      transform=lambda raw: png_encode(raw, 1, 1, [2]))
    item = inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True).items[0]
    details = dict(item.details)
    assert details['decode_work_bytes'] == 98 and details['decoded_bytes'] == 49
    assert details['entries'][6]['offset_or_next_free'] == offsets[6]
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(data), strict=True)
    assert len(reader.pages) == 1 and reader.metadata.title == 'Own compressed metadata'


@pytest.mark.parametrize('parameters', [
    {'Colors': 0}, {'Colors': True}, {'Columns': -1}, {'Columns': False},
    {'BitsPerComponent': 3}, {'BitsPerComponent': '8'}, {'Columns': 8},
])
def test_invalid_geometry_and_incomplete_rows_refuse(parameters):
    with pytest.raises(InvalidDocumentError, match='pdf:byte=0'):
        layout({'Predictor': 15, 'Columns': 7, **parameters}, 49, 'pdf:byte=0: ')


@pytest.mark.parametrize('damage', ['row-tag', 'truncated', 'overrun', 'raw-predictor'])
def test_predicted_stream_damage_never_falls_back_to_unpredicted_records(damage):
    def transform(raw):
        encoded = png_encode(raw, 7, 1, [4])
        if damage == 'row-tag':
            return b'\x05'+encoded[1:]
        if damage == 'truncated':
            return encoded[:-1]
        if damage == 'overrun':
            return encoded+b'\0'
        return encoded
    data, _, _ = own_stream_pdf(flate=damage != 'raw-predictor',
                               extra=b'/DecodeParms << /Predictor 15 /Columns 7 >>', transform=transform)
    expected = UnsupportedDocumentError if damage == 'raw-predictor' else InvalidDocumentError
    with pytest.raises(expected, match='pdf:byte='):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True)


@pytest.mark.parametrize('field,maximum', [('part_limit', 55), ('byte_limit', 55)])
def test_png_tag_budget_is_checked_before_constructing_zlib_decoder(monkeypatch, field, maximum):
    import opendoc_formats.native.pdf_flate as decoder

    predicted = png_encode(bytes(49), 7, 1, [0])
    encoded = zlib.compress(predicted)
    dictionary = {'Size': 7, 'W': [1, 4, 2], 'Length': len(encoded), 'Filter': Name('FlateDecode'),
                  'DecodeParms': {'Predictor': 15, 'Columns': 7}}
    def forbidden():
        pytest.fail('PNG output/tag quota must precede zlib')
    monkeypatch.setattr(decoder.zlib, 'decompressobj', forbidden)
    limits = {'part_limit': 1000, 'byte_limit': 1000, field: maximum+(len(encoded) if field == 'byte_limit' else 0)}
    with pytest.raises(ResourceLimitError, match='PNG row tags'):
        decode_xref(encoded+b'\nendstream\nendobj', 0, dictionary, item_limit=100,
                    budget=SyntaxBudget(100, 10), **limits)


def test_cancel_inside_in_place_png_reconstruction(monkeypatch):
    import opendoc_formats.native.pdf_predictors as predictors

    data, _, _ = own_stream_pdf(extra=b'/DecodeParms << /Predictor 15 /Columns 7 >>',
                               transform=lambda raw: png_encode(raw, 7, 1, [4]))
    stop = Event()
    real = predictors.checkpoint
    calls = 0
    def checkpoint():
        nonlocal calls
        calls += 1
        if calls == 4:
            stop.set()
        real()
    monkeypatch.setattr(predictors, 'checkpoint', checkpoint)
    with pytest.raises(OperationCancelledError):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True, cancelled=stop.is_set)
    assert calls == 4


def test_combined_physical_and_decoded_budget_counts_predictor_tags():
    data, offsets, _ = own_stream_pdf(extra=b'/DecodeParms << /Predictor 12 /Columns 7 >>',
                                      transform=lambda raw: png_encode(raw, 7, 1, [2]))
    item = inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True).items[0]
    physical = dict(item.details)['end']-offsets[6]
    with pytest.raises(ResourceLimitError):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True,
                       limits=replace(AnatomyLimits(), max_total_bytes=physical+55))
    result = inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True,
                            limits=replace(AnatomyLimits(), max_total_bytes=physical+56))
    assert dict(result.details)['xref_decode_work_bytes'] == 56
