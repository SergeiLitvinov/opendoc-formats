import builtins
import zlib

import pytest

from opendoc_formats import read_pdf_xmp
from opendoc_formats.errors import InvalidDocumentError, UnsupportedDocumentError

_PACKET = b'<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/">\r\n<?xpacket end="w"?>'


def _pdf(root, metadata, *extra):
    data = b'%PDF-1.7\n'
    offsets = []
    for number, body in enumerate((root, metadata, *extra), start=1):
        offsets.append(len(data))
        data += f'{number} 0 obj\n'.encode()+body+b'\nendobj\n'
    xref = len(data)
    records = b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets)
    size = len(offsets)+1
    return (data+f'xref\n0 {size}\n0000000000 65535 f \n'.encode()+records
            +f'trailer\n<< /Root 1 0 R /Size {size} >>\nstartxref\n{xref}\n%%EOF\n'.encode())


def _stream(payload, extra=b'', length=None):
    length = len(payload) if length is None else length
    value = length if isinstance(length, bytes) else str(length).encode()
    return b'<< /Type /Metadata /Subtype /XML /Length '+value+extra+b' >>\nstream\n'+payload+b'\nendstream'


@pytest.mark.parametrize('flate', [False, True])
def test_extracts_exact_packet_without_loading_pdf_engines(tmp_path, monkeypatch, flate):
    original_import = builtins.__import__

    def no_engines(name, *args, **kwargs):
        assert name.partition('.')[0] not in {'pypdf', 'pdfplumber', 'pymupdf', 'fitz', 'lxml'}
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_engines)
    path = tmp_path/'packet.pdf'
    stream = _stream(zlib.compress(_PACKET), b' /Filter /FlateDecode') if flate else _stream(_PACKET)
    data = _pdf(b'<< /Type /Catalog /Metadata 2 0 R >>', stream)
    path.write_bytes(data)
    assert read_pdf_xmp(path) == _PACKET
    assert path.read_bytes() == data
    path.write_bytes(_pdf(b'<< /Type /Catalog >>', stream))
    assert read_pdf_xmp(path) is None


@pytest.mark.parametrize('reference,stream,error', [
    (b'2 1 R', _stream(_PACKET), InvalidDocumentError),
    (b'2 0 R', _stream(_PACKET, length=3), InvalidDocumentError),
    (b'2 0 R', _stream(_PACKET, b' /F (external.xml)'), UnsupportedDocumentError),
])
def test_refuses_unproved_or_external_stream(tmp_path, reference, stream, error):
    path = tmp_path/'packet.pdf'
    path.write_bytes(_pdf(b'<< /Type /Catalog /Metadata '+reference+b' >>', stream))
    with pytest.raises(error):
        read_pdf_xmp(path)


def test_catalog_in_current_object_stream(tmp_path):
    from tests.native.test_pdf_extends import xref
    from tests.native.test_pdf_object_streams import custom_stream_pdf
    from tests.native.test_pdf_xref_state import latest

    original, _, _ = custom_stream_pdf(members=[b'<< /Type /Catalog /Metadata 9 0 R >>', str(len(_PACKET)).encode()])
    tail = b'9 0 obj\n'+_stream(_PACKET, length=b'8 0 R')+b'\nendobj\n'
    source, offset = xref(original+tail, 10, {7: (2, 4, 0), 8: (2, 4, 1), 9: (1, len(original), 0)},
                          previous=latest(original))
    source = source[:offset]+source[offset:].replace(b'/Root 1 0 R', b'/Root 7 0 R')
    path = tmp_path/'packet.pdf'
    path.write_bytes(source)
    assert read_pdf_xmp(path) == _PACKET


def test_indirect_length_and_ascii_flate_pipeline(tmp_path):
    payload = zlib.compress(_PACKET).hex().encode()+b'>'
    root = b'<< /Type /Catalog /Metadata 2 0 R >>'
    filters = b' /Filter [/ASCIIHexDecode /FlateDecode] /DecodeParms [null << /Predictor 1 >>]'
    path = tmp_path/'chain.pdf'
    path.write_bytes(_pdf(root, _stream(payload, filters, length=b'3 0 R'), str(len(payload)).encode()))
    assert read_pdf_xmp(path) == _PACKET
    path.write_bytes(_pdf(root, _stream(payload+b'junk', filters)))
    with pytest.raises(InvalidDocumentError, match='Trailing input'):
        read_pdf_xmp(path)
    path.write_bytes(_pdf(root, _stream(payload, filters, length=b'3 1 R'), str(len(payload)).encode()))
    with pytest.raises(InvalidDocumentError, match='current xref'):
        read_pdf_xmp(path)
