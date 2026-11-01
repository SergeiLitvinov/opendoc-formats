"""Independent forward TIFF differences and complete PDF originals check native decoding."""

import json
import zlib
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_predictors import layout, undo_tiff
from opendoc_formats.native.pdf_syntax import Name, SyntaxBudget
from opendoc_formats.native.pdf_xref_streams import decode_xref
from tests.native.test_pdf_xref_streams import own_stream_pdf


def tiff_encode(raw, colors, bits, columns):
    """Forward differences over immutable sample arrays; padding is packed independently."""
    components = colors*columns
    row_bytes = (components*bits+7)//8
    padding = row_bytes*8-components*bits
    modulus = 2**bits
    output = bytearray()
    for start in range(0, len(raw), row_bytes):
        number = int.from_bytes(raw[start:start+row_bytes], 'big')
        samples = [(number >> (padding+bits*(components-index-1))) % modulus for index in range(components)]
        differences = samples[:colors]+[(a-b) % modulus for a, b in zip(samples[colors:], samples[:-colors])]
        packed = 0
        for difference in differences:
            packed = packed*modulus+difference
        packed = (packed << padding)+(number % 2**padding)
        output.extend(packed.to_bytes(row_bytes, 'big'))
    return bytes(output)


def generic_stream_pdf(raw, colors, bits, columns):
    encoded = zlib.compress(tiff_encode(raw, colors, bits, columns))
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] >>',
               (f'<< /Length {len(encoded)} /Filter /FlateDecode /DecodeParms << /Predictor 2 '
                f'/Colors {colors} /BitsPerComponent {bits} /Columns {columns} >> >>\nstream\n').encode()
               +encoded+b'\nendstream']
    data = bytearray(b'%PDF-1.7\n')
    offsets = []
    for number, value in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(str(number).encode()+b' 0 obj\n'+value+b'\nendobj\n')
    startxref = len(data)
    data.extend(b'xref\n0 5\n0000000000 65535 f \n')
    for offset in offsets:
        data.extend(f'{offset:010} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n'.encode())
    return bytes(data)


@pytest.mark.parametrize('bits', [1, 2, 4, 8, 16])
@pytest.mark.parametrize('colors', [1, 3, 4])
@pytest.mark.parametrize('columns', [1, 5, 8, 13])
def test_packed_components_carries_row_resets_and_padding_against_independent_mupdf(bits, colors, columns):
    mupdf = pytest.importorskip('pymupdf')
    row_bytes = (colors*bits*columns+7)//8
    raw = bytes((position*73+position//3*31+255) % 256 for position in range(row_bytes*4))
    parameters = {'Predictor': 2, 'Colors': colors, 'BitsPerComponent': bits, 'Columns': columns}
    assert layout(parameters, len(raw), 'pdf:byte=0: ')[3] == len(raw)
    encoded = tiff_encode(raw, colors, bits, columns)
    output = bytearray(encoded)
    undo_tiff(output, colors, bits, columns, 'pdf:byte=0: ')
    assert bytes(output) == raw and encoded == tiff_encode(raw, colors, bits, columns)
    data = generic_stream_pdf(raw, colors, bits, columns)
    with mupdf.open(stream=data, filetype='pdf') as pdf:
        assert not pdf.is_repaired and len(pdf) == 1
        external = pdf.xref_stream(4)
        assert len(external) == len(raw)
        padding = row_bytes*8-colors*bits*columns
        for start in range(0, len(raw), row_bytes):
            # Keep the external byte result intact. MuPDF can discard padding;
            # compare the specified samples separately from exact byte equality.
            assert int.from_bytes(external[start:start+row_bytes], 'big') >> padding == (
                int.from_bytes(raw[start:start+row_bytes], 'big') >> padding)
        if padding == 0:
            assert external == raw
    if bits == 8:
        pypdf = pytest.importorskip('pypdf')
        reader = pypdf.PdfReader(BytesIO(data), strict=True)
        assert reader.get_object(pypdf.generic.IndirectObject(4, 0, reader)).get_data() == raw


@pytest.mark.parametrize('encoded,expected,colors,bits,columns', [
    ('ed', 'b5', 1, 1, 5), ('db39', 'cb35', 1, 2, 3), ('f1ed', 'f0ed', 1, 4, 3),
    ('ffff000200ff', 'ffff00010100', 1, 16, 3), ('fa008008ff80fd0280', 'fa008002ff00ff0180', 3, 8, 3),
])
def test_hand_calculated_vectors_preserve_every_byte_including_nonzero_padding(encoded, expected, colors, bits, columns):
    output = bytearray.fromhex(encoded)
    undo_tiff(output, colors, bits, columns, 'pdf:byte=0: ')
    assert output == bytearray.fromhex(expected)


@pytest.mark.parametrize('bits,colors,columns,widths', [
    (1, 1, 55, (1, 4, 2)), (1, 3, 17, (1, 4, 2)), (2, 1, 27, (1, 4, 2)),
    (4, 1, 13, (1, 4, 2)), (4, 2, 7, (1, 4, 2)), (8, 1, 7, (1, 4, 2)),
    (8, 7, 1, (1, 4, 2)), (16, 1, 4, (1, 5, 2)), (16, 2, 2, (1, 5, 2)),
])
def test_actual_xref_records_metadata_and_raw_source_are_preserved(bits, colors, columns, widths):
    _, offsets, _ = own_stream_pdf()
    records = [(0, 0, 65535)]+[(1, offsets[n], 0) for n in range(1, 5)]+[(2, 4, 0), (1, offsets[6], 0)]
    raw = b''.join(b''.join(value.to_bytes(width, 'big') for value, width in zip(record, widths)) for record in records)
    parameters = f'/DecodeParms << /Predictor 2 /Colors {colors} /BitsPerComponent {bits} /Columns {columns} >>'.encode()
    data, _, _ = own_stream_pdf(payload=raw, widths=str(list(widths)).replace(',', '').encode(), extra=parameters,
                                transform=lambda value: tiff_encode(value, colors, bits, columns))
    snapshot = inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True, capture=True)
    item = snapshot.items[0]
    details = dict(item.details)
    assert details['predictor'] == 2 and details['decode_work_bytes'] == details['decoded_bytes'] == len(raw)
    assert item.payload == data[offsets[6]:details['end']]
    assert details['entries'][0]['generation'] == 65535
    assert details['entries'][5]['object_stream'] == 4 and details['entries'][5]['object_stream_index'] == 0
    assert [entry['offset_or_next_free'] for entry in details['entries'][1:5]] == [offsets[n] for n in range(1, 5)]
    mupdf = pytest.importorskip('pymupdf')
    with mupdf.open(stream=data, filetype='pdf') as reader:
        assert not reader.is_repaired and len(reader) == 1 and reader.metadata['title'] == 'Own compressed metadata'
        external = reader.xref_stream(6)
        row_bytes = sum(widths)
        padding = row_bytes*8-colors*bits*columns
        assert len(external) == len(raw)
        for start in range(0, len(raw), row_bytes):
            assert int.from_bytes(external[start:start+row_bytes], 'big') >> padding == (
                int.from_bytes(raw[start:start+row_bytes], 'big') >> padding)
        if padding == 0:
            assert external == raw
    if bits == 8:
        pypdf = pytest.importorskip('pypdf')
        reader = pypdf.PdfReader(BytesIO(data), strict=True)
        assert len(reader.pages) == 1 and reader.metadata.title == 'Own compressed metadata'
        assert reader.get_object(pypdf.generic.IndirectObject(6, 0, reader)).get_data() == raw


@pytest.mark.parametrize('parameters', [{'Colors': 0}, {'Colors': True}, {'BitsPerComponent': 3},
                                        {'BitsPerComponent': False}, {'Columns': '7'}, {'Columns': 8}])
def test_invalid_tiff_geometry_never_uses_bytewise_fallback(parameters):
    with pytest.raises(InvalidDocumentError, match='pdf:byte=0'):
        layout({'Predictor': 2, 'Columns': 7, **parameters}, 49, 'pdf:byte=0: ')


@pytest.mark.parametrize('damage', ['truncated', 'overrun', 'raw'])
def test_predicted_size_damage_and_missing_filter_refuse(damage):
    def transform(raw):
        value = tiff_encode(raw, 1, 8, 7)
        return value[:-1] if damage == 'truncated' else value+b'\0' if damage == 'overrun' else value
    data, _, _ = own_stream_pdf(extra=b'/DecodeParms << /Predictor 2 /Columns 7 >>',
                                flate=damage != 'raw', transform=transform)
    with pytest.raises(UnsupportedDocumentError if damage == 'raw' else InvalidDocumentError, match='pdf:byte='):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True)


def test_declared_tiff_quota_precedes_flate_and_exact_budget_has_no_row_tags(monkeypatch):
    import opendoc_formats.native.pdf_flate as decoder

    data, offsets, _ = own_stream_pdf(extra=b'/DecodeParms << /Predictor 2 /Columns 7 >>',
                                      transform=lambda raw: tiff_encode(raw, 1, 8, 7))
    item = inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True).items[0]
    physical = dict(item.details)['end']-offsets[6]
    with pytest.raises(ResourceLimitError):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True,
                       limits=replace(AnatomyLimits(), max_total_bytes=physical+48))
    snapshot = inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True,
                              limits=replace(AnatomyLimits(), max_total_bytes=physical+49))
    assert dict(snapshot.details)['xref_decode_work_bytes'] == 49
    def forbidden():
        pytest.fail('TIFF byte quota must precede zlib allocation')
    monkeypatch.setattr(decoder.zlib, 'decompressobj', forbidden)
    dictionary = {'Size': 7, 'W': [1, 4, 2], 'Length': 0, 'Filter': Name('FlateDecode'),
                  'DecodeParms': {'Predictor': 2, 'Columns': 7}}
    with pytest.raises(ResourceLimitError):
        decode_xref(b'endstream endobj', 0, dictionary, part_limit=48, byte_limit=1000,
                    item_limit=100, budget=SyntaxBudget(100, 10))


def test_cancel_inside_wide_row_reconstruction(monkeypatch):
    from opendoc_formats.native import pdf_predictors

    data, offsets, _ = own_stream_pdf(payload=bytes(8197), extra=b'/DecodeParms << /Predictor 2 /Columns 8197 >>')
    data = data[:offsets[6]]+data[offsets[6]:].replace(b'/Size 7', b'/Size 1171')
    stop = Event()
    real = pdf_predictors.checkpoint
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        if calls == 2:
            stop.set()
        real()
    monkeypatch.setattr(pdf_predictors, 'checkpoint', cancel)
    with pytest.raises(OperationCancelledError):
        inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True, cancelled=stop.is_set)
    assert calls == 2


def test_cli_keeps_predicted_bytes_and_refuses_late_damage_without_replacing_output(tmp_path, monkeypatch):
    from tools.document_anatomy import main

    source, output = tmp_path/'source.pdf', tmp_path/'dissected'
    data, _, _ = own_stream_pdf(extra=b'/DecodeParms << /Predictor 2 /Columns 7 >>',
                                transform=lambda raw: tiff_encode(raw, 1, 8, 7))
    source.write_bytes(data)
    monkeypatch.setattr('sys.argv', ['document_anatomy', str(source), '--pdf-source', '--pdf-decode-xrefs',
                                    '--output', str(output)])
    main()
    inventory = json.loads((output/'inventory.json').read_text(encoding='utf-8'))
    item = inventory['items'][0]
    assert item['details']['predictor'] == 2
    assert (output/item['payload_file']).read_bytes() == data[item['details']['offset']:item['details']['end']]
    assert source.read_bytes() == data
    before = (output/'inventory.json').read_bytes()
    bad, _, _ = own_stream_pdf(extra=b'/DecodeParms << /Predictor 2 /Columns 7 >>', transform=lambda raw: raw[:-1])
    source.write_bytes(bad)
    with pytest.raises(InvalidDocumentError):
        main()
    assert (output/'inventory.json').read_bytes() == before and source.read_bytes() == bad
