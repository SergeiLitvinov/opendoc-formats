"""Installed native DOCX transactions with lxml alone, using owned ZIP/XML bytes."""

from __future__ import annotations

import importlib.util
import io
import zipfile
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory


def source_package() -> bytes:
    content_types = b'''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Default Extension="bin" ContentType="application/octet-stream"/>
      <Override PartName="/word/document.xml"
       ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    </Types>'''
    relationships = b'''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
       Target="word/document.xml"/>
    </Relationships>'''
    document = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
      <w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Own </w:t></w:r>
        <w:r><w:t>текст</w:t><w:tab/><w:t>tail</w:t></w:r></w:p>
      <w:sectPr/>
    </w:body></w:document>'''.encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.comment = b'Owned native profile'
        for name, payload in [('[Content_Types].xml', content_types), ('_rels/.rels', relationships),
                              ('word/document.xml', document), ('custom/opaque.bin', bytes(range(256)))]:
            info = zipfile.ZipInfo(name, (2020, 1, 2, 3, 4, 6))
            info.comment = b'Keep metadata'
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)
    return stream.getvalue()


def main() -> None:
    import opendoc_formats
    from opendoc_formats.docx import DocxLimits, DocxPackage, ReplaceTextSpan
    from opendoc_formats.errors import OperationCancelledError, ResourceLimitError

    assert 'site-packages' in Path(opendoc_formats.__file__).resolve().parts
    for name in ('docx', 'pptx', 'PIL', 'fontTools', 'pymupdf', 'pypdf', 'bs4'):
        assert importlib.util.find_spec(name) is None, f'Unexpected engine: {name}'
    source = source_package()
    with TemporaryDirectory(prefix='opendoc-formats-native-') as folder:
        target = Path(folder)/'edited.docx'
        with DocxPackage(source) as package:
            assert package.to_bytes() == source
            paragraph, = package.paragraphs
            assert paragraph.text == 'Own текст\ttail' and paragraph.runs[0].style.bold
            patch = ReplaceTextSpan(paragraph.id, 4, 9, 'правка')
            result = package.write(target, [patch])
            assert result.changed_parts == ('word/document.xml',)
        with DocxPackage(target) as edited:
            assert edited.paragraphs[0].text == 'Own правка\ttail'
            assert edited.paragraphs[0].runs[0].style.bold
        with zipfile.ZipFile(io.BytesIO(source)) as original, zipfile.ZipFile(target) as edited_zip:
            assert original.namelist() == edited_zip.namelist()
            assert original.comment == edited_zip.comment
            for info in original.infolist():
                copied = edited_zip.getinfo(info.filename)
                assert (info.date_time, info.comment, info.external_attr) == (
                    copied.date_time, copied.comment, copied.external_attr)
                if info.filename != 'word/document.xml':
                    assert original.read(info.filename) == edited_zip.read(info.filename)
        before = target.read_bytes()
        for kwargs, error in [({'cancelled': lambda: True}, OperationCancelledError),
                              ({'limits': replace(DocxLimits(), max_output_bytes=1)}, ResourceLimitError)]:
            try:
                with DocxPackage(source, **kwargs) as package:
                    package.write(target, [])
            except error:
                pass
            else:
                raise AssertionError(f'Missing {error.__name__}')
            assert target.read_bytes() == before
    print('Native DOCX with lxml only: snapshots, edits, opaque parts, ZIP metadata, limits and cancellation passed')


if __name__ == '__main__':
    main()
