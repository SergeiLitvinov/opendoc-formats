"""Independent wire fixtures: no document writer or converter creates these originals."""

import io
import struct
import zipfile
import zlib

RGB = b'\xff\x00\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
PR = 'http://schemas.openxmlformats.org/package/2006/relationships'


def own_png(rgb=RGB):
    def chunk(kind, value):
        return struct.pack('>I', len(value))+kind+value+struct.pack('>I', zlib.crc32(kind+value))

    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>2I5B', 2, 2, 8, 2, 0, 0, 0))
            +chunk(b'IDAT', zlib.compress(b'\x00'+rgb[:6]+b'\x00'+rgb[6:]))+chunk(b'IEND', b''))


def zip_bytes(entries, *, compression=zipfile.ZIP_DEFLATED):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=compression) as archive:
        for name, value in entries:
            item = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = compression
            archive.writestr(item, value)
    return output.getvalue()


def own_docx():
    r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    drawing = f'''<w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
      <wp:extent cx="190500" cy="190500"/><wp:docPr id="1" name="Own" descr="Own alt"/>
      <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
      <pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
      <pic:nvPicPr><pic:cNvPr id="1" name="own.png"/><pic:cNvPicPr/></pic:nvPicPr>
      <pic:blipFill><a:blip xmlns:r="{r}" r:embed="rId3"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
      <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="190500" cy="190500"/></a:xfrm>
      <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>'''

    def paragraph(text):
        return f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>'

    def table(content):
        return ('<w:tbl><w:tblPr/><w:tblGrid><w:gridCol w:w="2400"/></w:tblGrid><w:tr><w:tc>'
                '<w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr>'+content+'</w:tc></w:tr></w:tbl>')

    nested = table(paragraph('Nested'))
    body = ('<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Before</w:t></w:r></w:p>'
            +table(paragraph('Cell')+nested+f'<w:p><w:r>{drawing}</w:r></w:p>')
            +'<w:p><w:r><w:t>After </w:t></w:r><w:hyperlink r:id="rId2"><w:r><w:t>Link</w:t></w:r></w:hyperlink></w:p>')
    document = f'<w:document xmlns:w="{W}" xmlns:r="{r}"><w:body>{body}<w:sectPr/></w:body></w:document>'
    types = ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="png" ContentType="image/png"/><Default Extension="bin" ContentType="application/octet-stream"/>'
             '<Override PartName="/word/document.xml" '
             'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    return zip_bytes([
        ('[Content_Types].xml', types),
        ('_rels/.rels', f'<Relationships xmlns="{PR}"><Relationship Id="rId1" Type="{r}/officeDocument" '
                       'Target="word/document.xml"/></Relationships>'),
        ('word/document.xml', document),
        ('word/_rels/document.xml.rels', f'<Relationships xmlns="{PR}"><Relationship Id="rId3" Type="{r}/image" '
                                       f'Target="media/own.png"/><Relationship Id="rId2" Type="{r}/hyperlink" '
                                       'Target="https://example.invalid/own" TargetMode="External"/></Relationships>'),
        ('word/media/own.png', own_png()),
        ('word/embeddings/unknown.bin', b'Own opaque binary\x00\xff\x01'),
    ])


def own_pdf(*, commands=None, page_extra=b'', resource_extra=b'', parent_extra=b''):
    if commands is None:
        commands = (b'BT /F1 12 Tf 30 350 Td (Before) Tj ET\n'
                b'1 w 30 180 m 270 180 l S 30 220 m 270 220 l S 30 260 m 270 260 l S\n'
                b'30 180 m 30 260 l S 150 180 m 150 260 l S 270 180 m 270 260 l S\n'
                b'BT /F1 10 Tf 40 240 Td (R1C1) Tj ET BT /F1 10 Tf 160 240 Td (R1C2) Tj ET\n'
                b'BT /F1 10 Tf 40 200 Td (R2C1) Tj ET BT /F1 10 Tf 160 200 Td (R2C2) Tj ET\n'
                b'q 20 0 0 20 40 80 cm /Im1 Do Q\nBT /F1 12 Tf 30 40 Td (After) Tj ET\n')

    def stream(dictionary, payload):
        return dictionary+b' /Length '+str(len(payload)).encode()+b' >>\nstream\n'+payload+b'\nendstream'

    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 '+parent_extra+b'>>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Contents 5 0 R '+page_extra+
        b'/Resources << /Font << /F1 4 0 R >> '+resource_extra+b'/XObject << /Im1 6 0 R >> >> >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        stream(b'<< /Filter /FlateDecode', zlib.compress(commands)),
        stream(b'<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceRGB '
               b'/BitsPerComponent 8 /Filter /FlateDecode', zlib.compress(RGB)),
    ]
    output = bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(str(index).encode()+b' 0 obj\n'+value+b'\nendobj\n')
    xref = len(output)
    output.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        output.extend(f'{offset:010} 00000 n \n'.encode())
    output.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(output), commands


def own_cfbf(*, version=3, difat=False, high_size_bits=0):
    """Independent sector bytes: interleaved FAT/mini chains and opaque unclaimed data."""
    assert version in (3, 4) and (not difat or version == 3)
    size = 512 if version == 3 else 4096
    fat_count = 110 if difat else 1
    directory, mini_fat, pool = fat_count, fat_count+1, fat_count+2
    first = fat_count+3
    big_chain = ([first, first+2, first+1, first+3, first+5, first+4, first+6, first+7]
                 if version == 3 else [first])
    difat_sector = first+len(big_chain)
    count = 14000 if difat else difat_sector+1
    header, body = bytearray(size), bytearray(count*size)
    header[:8] = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
    struct.pack_into('<5H', header, 24, 0x3e, version, 0xfffe, 9 if version == 3 else 12, 6)
    struct.pack_into('<9I', header, 40, 0 if version == 3 else 1, fat_count, directory, 0, 4096,
                     mini_fat, 1, difat_sector if difat else 0xfffffffe, 1 if difat else 0)
    header[76:512] = b'\xff'*436
    for index in range(min(fat_count, 109)):
        struct.pack_into('<I', header, 76+index*4, index)
    for sector in range(fat_count):
        body[sector*size:(sector+1)*size] = b'\xff'*size

    def fat(index, value):
        block, slot = divmod(index, size//4)
        struct.pack_into('<I', body, block*size+slot*4, value)

    for sector in range(fat_count):
        fat(sector, 0xfffffffd)
    for sector in (directory, mini_fat, pool):
        fat(sector, 0xfffffffe)
    for index, sector in enumerate(big_chain):
        fat(sector, big_chain[index+1] if index+1 < len(big_chain) else 0xfffffffe)
    if difat:
        fat(difat_sector, 0xfffffffc)
        body[difat_sector*size:(difat_sector+1)*size] = b'\xff'*size
        struct.pack_into('<I', body, difat_sector*size, 109)
        struct.pack_into('<I', body, (difat_sector+1)*size-4, 0xfffffffe)
    fat(count-1, 0xfffffffe)
    opaque = b'Own unclaimed allocated bytes\x00\xff'
    body[(count-1)*size:(count-1)*size+len(opaque)] = opaque
    body[mini_fat*size:(mini_fat+1)*size] = b'\xff'*size
    for index, value in enumerate((2, 0xfffffffe, 1)):
        struct.pack_into('<I', body, mini_fat*size+index*4, value)
    small, big = (b'Own small\x00\xff'*14)[:145], bytes(range(256))*16
    body[pool*size:(pool+1)*size] = b'\xa7'*size
    for index, sector in enumerate((0, 2, 1)):
        chunk = small[index*64:(index+1)*64]
        body[pool*size+sector*64:pool*size+sector*64+len(chunk)] = chunk
    for index, sector in enumerate(big_chain):
        body[sector*size:(sector+1)*size] = big[index*size:(index+1)*size]

    def entry(index, name, kind, start=0xfffffffe, length=0, *, left=0xffffffff, right=0xffffffff,
              child=0xffffffff, color=1):
        record = bytearray(128)
        encoded = name.encode('utf-16-le')+b'\x00\x00' if kind else b''
        record[:len(encoded)] = encoded
        struct.pack_into('<HBBIII', record, 64, len(encoded), kind, color, left, right, child)
        struct.pack_into('<IQ', record, 116, start if kind else 0, length | ((high_size_bits << 32) if kind == 2 else 0))
        body[directory*size+index*128:directory*size+(index+1)*128] = record

    for index in range(size//128):
        entry(index, '', 0, color=0)
    entry(0, 'Root Entry', 5, pool, 192, child=1)
    entry(1, 'Small', 2, 0, len(small), left=2, right=3)
    entry(2, 'Large', 2, big_chain[0], len(big), color=0)
    entry(3, 'Folder', 1, color=0)
    return bytes(header+body), small, big
