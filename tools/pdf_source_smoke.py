"""Installed base wheel: physical PDF xref inspection without any PDF engine."""

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
    print('Installed base PDF source: effective classic/PNG xrefs and Flate ObjStm; no PDF/image backends')


if __name__ == '__main__':
    main()
