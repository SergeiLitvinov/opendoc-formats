"""Installed base wheel: physical PDF xref inspection without any PDF engine."""

import base64
import importlib.util
import zlib
from pathlib import Path

import opendoc_formats
from opendoc_formats.anatomy import inspect_binary


def main():
    assert 'site-packages' in Path(opendoc_formats.__file__).parts
    for name in ('pypdf', 'pdfplumber', 'pymupdf', 'fitz', 'PIL'):
        assert importlib.util.find_spec(name) is None, name
    source = bytearray(b'%PDF-1.7\n')
    positions = []
    for index, value in enumerate((b'<< /Type /Catalog /Pages 2 0 R >>',
                                   b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                                   b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] >>'), 1):
        positions.append(len(source))
        source.extend(str(index).encode()+b' 0 obj\n'+value+b'\nendobj\n')
    previous = len(source)
    source.extend(b'xref\n0 4\n0000000000 65535 f \n')
    for offset in positions:
        source.extend(f'{offset:010} 00000 n \n'.encode())
    source.extend(f'trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{previous}\n%%EOF\n'.encode())
    target = len(source)
    source.extend(b'4 0 obj\n<< /Title (Own standalone source) >>\nendobj\n')
    current = len(source)
    source.extend((f'xref\n4 1\n{target:010} 00000 n \ntrailer\n'
                   f'<< /Size 5 /Root 1 0 R /Info 4 0 R /Prev {previous} >>\n'
                   f'startxref\n{current}\n%%EOF\n').encode())
    original = bytes(source)
    snapshot = inspect_binary(original, pdf_source=True, capture=True)
    assert dict(snapshot.details)['xref_sections'] == 2
    assert not dict(snapshot.details)['backend_used'] and not dict(snapshot.details)['assessment_complete']
    for item in snapshot.items:
        details = dict(item.details)
        assert item.payload == original[details['offset']:details['end']]
        assert all(entry['object_header_matches'] for entry in details['entries'] if entry['in_use'])
    assert bytes(source) == original
    # Append an Up-predicted Flate index: an existing object and the index itself.
    offset = len(original)
    first = b'\x01'+target.to_bytes(4, 'big')+b'\0\0'
    second = b'\x01'+offset.to_bytes(4, 'big')+b'\0\0'
    encoded = zlib.compress(b'\x02'+first+b'\x02'+bytes((value-previous) % 256 for value, previous in zip(second, first)))
    source = (original+b'5 0 obj\n<< /Type /XRef /Size 6 /W [1 4 2] /Index [4 2] /Root 1 0 R '
              +f'/Prev {current} /Length {len(encoded)} /Filter /FlateDecode '.encode()
              +b'/DecodeParms << /Predictor 12 /Columns 7 >> >>\nstream\n'
              +encoded+b'\nendstream\nendobj\nstartxref\n'+str(offset).encode()+b'\n%%EOF\n')
    decoded = inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, capture=True)
    assert dict(decoded.details)['xref_sections'] == 3
    stream = decoded.items[0]
    assert stream.kind == 'pdf-xref-stream'
    assert dict(stream.details)['predictor'] == 12 and dict(stream.details)['decode_work_bytes'] == 16
    assert dict(stream.details)['entries'][0]['offset_or_next_free'] == target
    record = dict(stream.details)['entries'][1]
    assert record['object'] == 5 and record['offset_or_next_free'] == offset
    assert stream.payload == source[offset:dict(stream.details)['end']]
    container_offset = len(source)
    title = b'<< /Title (Own base ObjStm) >>'
    directory = f'7 0 8 {len(title)+1} '.encode()
    content = directory+title+b'\n42'
    encoded = zlib.compress(content)
    source += (b'6 0 obj\n<< /Type /ObjStm /N 2 '+f'/First {len(directory)} /Length {len(encoded)} '.encode()
               +b'/Filter /FlateDecode >>\nstream\n'+encoded+b'\nendstream\nendobj\n')
    xref = len(source)
    records = [(1, container_offset, 0), (2, 6, 0), (2, 6, 1), (1, xref, 0)]
    raw = b''.join(bytes([kind])+target.to_bytes(4, 'big')+index.to_bytes(2, 'big') for kind, target, index in records)
    source += (b'9 0 obj\n<< /Type /XRef /Size 10 /Root 1 0 R /Info 7 0 R /W [1 4 2] /Index [6 4] '
               +f'/Prev {offset} /Length {len(raw)} >>\nstream\n'.encode()+raw
               +b'\nendstream\nendobj\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n')
    inventory = inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, pdf_object_streams=True,
                               pdf_resolve_xrefs=True, capture=True)
    assert dict(inventory.details)['xref_sections'] == 4
    assert dict(inventory.details)['decoded_object_streams'] == 1
    members = [item for item in inventory.items if item.kind == 'pdf-compressed-object']
    assert [item.payload for item in members] == [title+b'\n', b'42']
    container = next(item for item in inventory.items if item.kind == 'pdf-object-stream')
    assert container.payload == source[container_offset:dict(container.details)['end']]
    assert not dict(inventory.details)['object_stream_reference_links_assessed']
    effective = {record['object']: record for record in dict(inventory.details)['effective_xref_entries']}
    assert len(effective) == 10 and effective[7]['state'] == 'compressed' and effective[7]['object_stream'] == 6
    assert effective[6]['offset'] == container_offset and effective[0]['state'] == 'free'
    assert dict(inventory.details)['xref_record_selection_complete']
    assert not dict(inventory.details)['object_resolution_complete']
    # A TIFF-predicted index uses complete 16-bit components, not byte differences.
    tiff_offset = len(source)
    raw = b''.join(b'\x01'+value.to_bytes(5, 'big')+b'\0\0' for value in (xref, tiff_offset))
    differences = bytearray()
    for start in range(0, len(raw), 8):
        samples = [int.from_bytes(raw[start+column:start+column+2], 'big') for column in range(0, 8, 2)]
        for value in samples[:1]+[(right-left) % 65536 for right, left in zip(samples[1:], samples[:-1])]:
            differences.extend(value.to_bytes(2, 'big'))
    encoded = zlib.compress(differences)
    source += (b'10 0 obj\n<< /Type /XRef /Size 11 /Root 1 0 R /W [1 5 2] /Index [9 2] '
               +f'/Prev {xref} /Length {len(encoded)} /Filter /FlateDecode '.encode()
               +b'/DecodeParms << /Predictor 2 /BitsPerComponent 16 /Columns 4 >> >>\nstream\n'+encoded
               +b'\nendstream\nendobj\nstartxref\n'+str(tiff_offset).encode()+b'\n%%EOF\n')
    result = inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, pdf_resolve_xrefs=True,
                            pdf_object_streams=True, capture=True)
    item = result.items[0]
    details = dict(item.details)
    assert details['predictor'] == 2 and details['decode_work_bytes'] == len(raw)
    assert item.payload == source[tiff_offset:details['end']]
    effective = {record['object']: record for record in dict(result.details)['effective_xref_entries']}
    assert effective[9]['offset'] == xref and effective[10]['offset'] == tiff_offset
    assert effective[7]['object_stream'] == 6 and len(effective) == 11
    # Both an object container and the next xref use parameterless RunLength.
    rle_container = len(source)
    title = b'<< /Title (Own RunLength ObjStm) >>'
    content = b'12 0 '+title
    encoded = bytes([len(content)-1])+content+b'\x80'
    source += (b'11 0 obj\n<< /Type /ObjStm /N 1 /First 5 /Filter /RunLengthDecode '
               +f'/Length {len(encoded)} >>\nstream\n'.encode()+encoded+b'\nendstream\nendobj\n')
    rle_xref = len(source)
    records = [(1, rle_container, 0), (2, 11, 0), (1, rle_xref, 0)]
    raw = b''.join(bytes([kind])+value.to_bytes(4, 'big')+index.to_bytes(2, 'big') for kind, value, index in records)
    encoded = bytes([len(raw)-1])+raw+b'\x80'
    source += (b'13 0 obj\n<< /Type /XRef /Size 14 /Root 1 0 R /Info 12 0 R /W [1 4 2] /Index [11 3] '
               +f'/Prev {tiff_offset} /Length {len(encoded)} /Filter /RunLengthDecode >>\nstream\n'.encode()+encoded
               +b'\nendstream\nendobj\nstartxref\n'+str(rle_xref).encode()+b'\n%%EOF\n')
    result = inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, pdf_resolve_xrefs=True,
                            pdf_object_streams=True, capture=True)
    details = dict(result.items[0].details)
    assert details['filter'] == 'RunLengthDecode' and details['trailing_encoded_bytes'] == 0
    assert result.items[0].payload == source[rle_xref:details['end']]
    member = next(item for item in result.items if item.kind == 'pdf-compressed-object' and dict(item.details)['object'] == 12)
    assert member.payload == title
    effective = {record['object']: record for record in dict(result.details)['effective_xref_entries']}
    assert effective[11]['offset'] == rle_container and effective[12]['object_stream'] == 11
    assert effective[13]['offset'] == rle_xref and len(effective) == 14
    ascii_container = len(source)
    title = b'<< /Title (Own ASCII ObjStm) >>'
    content = b'15 0 '+title
    encoded = content.hex().encode()+b'>'
    source += (b'14 0 obj\n<< /Type /ObjStm /N 1 /First 5 /Filter /ASCIIHexDecode '
               +f'/Length {len(encoded)} >>\nstream\n'.encode()+encoded+b'\nendstream\nendobj\n')
    ascii_xref = len(source)
    records = [(1, ascii_container, 0), (2, 14, 0), (1, ascii_xref, 0)]
    raw = b''.join(bytes([kind])+value.to_bytes(4, 'big')+index.to_bytes(2, 'big') for kind, value, index in records)
    encoded = base64.a85encode(raw)+b'~>'
    source += (b'16 0 obj\n<< /Type /XRef /Size 17 /Root 1 0 R /Info 15 0 R /W [1 4 2] /Index [14 3] '
               +f'/Prev {rle_xref} /Length {len(encoded)} /Filter /ASCII85Decode >>\nstream\n'.encode()+encoded
               +b'\nendstream\nendobj\nstartxref\n'+str(ascii_xref).encode()+b'\n%%EOF\n')
    result = inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, pdf_resolve_xrefs=True,
                            pdf_object_streams=True, capture=True)
    details = dict(result.items[0].details)
    assert details['filter'] == 'ASCII85Decode' and details['trailing_encoded_bytes'] == 0
    assert result.items[0].payload == source[ascii_xref:details['end']]
    member = next(item for item in result.items if item.kind == 'pdf-compressed-object' and dict(item.details)['object'] == 15)
    assert member.payload == title
    effective = {record['object']: record for record in dict(result.details)['effective_xref_entries']}
    assert effective[14]['offset'] == ascii_container and effective[15]['object_stream'] == 14
    assert effective[16]['offset'] == ascii_xref and len(effective) == 17
    chain_container = len(source)
    title = b'<< /Title (Own pipeline ObjStm) >>'
    content = b'18 0 '+title
    predicted = b''.join(b'\0'+bytes([value]) for value in content)
    compressed = zlib.compress(predicted)
    encoded = base64.a85encode(compressed)+b'~>'
    source += (b'17 0 obj\n<< /Type /ObjStm /N 1 /First 5 /Filter [/ASCII85Decode /FlateDecode] '
               +b'/DecodeParms [null << /Predictor 12 /Columns 1 >>] '
               +f'/Length {len(encoded)} >>\nstream\n'.encode()+encoded+b'\nendstream\nendobj\n')
    chain_xref = len(source)
    records = [(1, chain_container, 0), (2, 17, 0), (1, chain_xref, 0)]
    raw = b''.join(bytes([kind])+value.to_bytes(4, 'big')+index.to_bytes(2, 'big') for kind, value, index in records)
    predicted = b''.join(b'\0'+raw[start:start+7] for start in range(0, len(raw), 7))
    compressed = zlib.compress(predicted)
    encoded = compressed.hex().encode()+b'>'
    source += (b'19 0 obj\n<< /Type /XRef /Size 20 /Root 1 0 R /Info 18 0 R /W [1 4 2] /Index [17 3] '
               +b'/Filter [/ASCIIHexDecode /FlateDecode] /DecodeParms [null << /Predictor 12 /Columns 7 >>] '
               +f'/Prev {ascii_xref} /Length {len(encoded)} >>\nstream\n'.encode()+encoded
               +b'\nendstream\nendobj\nstartxref\n'+str(chain_xref).encode()+b'\n%%EOF\n')
    result = inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, pdf_resolve_xrefs=True,
                            pdf_object_streams=True, capture=True)
    details = dict(result.items[0].details)
    assert details['filter_chain'] == ['ASCIIHexDecode', 'FlateDecode']
    assert details['decode_work_bytes'] == len(compressed)+len(predicted)
    assert result.items[0].payload == source[chain_xref:details['end']]
    member = next(item for item in result.items if item.kind == 'pdf-compressed-object' and dict(item.details)['object'] == 18)
    assert member.payload == title
    effective = {record['object']: record for record in dict(result.details)['effective_xref_entries']}
    assert effective[17]['offset'] == chain_container and effective[18]['object_stream'] == 17
    assert effective[19]['offset'] == chain_xref and len(effective) == 20
    print('Installed base PDF source: raw, Flate/TIFF/PNG, RunLength, ASCII and pipelines; no PDF/image backends')


if __name__ == '__main__':
    main()
