"""Installed base wheel: physical PDF xref inspection without any PDF engine."""

import importlib.util
from pathlib import Path

import opendoc_formats
from opendoc_formats.anatomy import inspect_binary


def main():
    assert 'site-packages' in Path(opendoc_formats.__file__).parts
    for name in ('pypdf', 'pdfplumber', 'pymupdf', 'fitz'):
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
    print('Installed base PDF source profile: two physical xref sections and exact payloads; no PDF backends')


if __name__ == '__main__':
    main()
