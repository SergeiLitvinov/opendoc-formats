"""Installed native DOCX transactions with lxml alone, using owned ZIP/XML bytes."""

from __future__ import annotations

import importlib.util
import io
import zipfile
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory


def source_package(*, orphans: bool = False, uri_target: tuple[str, str] | None = None,
                   main_part: tuple[str, str, str] | None = None) -> bytes:
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
    parts = [('[Content_Types].xml', content_types), ('_rels/.rels', relationships),
             ('word/document.xml', document), ('custom/opaque.bin', bytes(range(256)))]
    if orphans:
        parts.append(('custom/_rels/missing.xml.rels', b'''<Relationships
          xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="own" Type="urn:own" Target="../word/document.xml"/></Relationships>'''))
    if uri_target is not None:
        encoded, name = uri_target
        parts.extend([
            ('custom/'+name+'.xml', b'<own/>'),
            ('word/_rels/document.xml.rels', ('<Relationships '
             'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="own" Type="urn:own" Target="../custom/'+encoded+'.xml"/></Relationships>').encode()),
        ])
    if main_part is not None:
        physical, target, override = main_part
        transformed = []
        for name, payload in parts:
            if name == 'word/document.xml':
                name = physical
            elif name == '_rels/.rels':
                payload = payload.replace(b'word/document.xml', target.encode())
            elif name == '[Content_Types].xml':
                payload = payload.replace(b'/word/document.xml', override.encode())
            transformed.append((name, payload))
        parts = transformed
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.comment = b'Owned native profile'
        for name, payload in parts:
            info = zipfile.ZipInfo(name, (2020, 1, 2, 3, 4, 6))
            info.comment = b'Keep metadata'
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)
    return stream.getvalue()


def main() -> None:
    import opendoc_formats
    from opendoc_formats.docx import DocxLimits, DocxPackage, ReplaceTextSpan
    from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError

    assert 'site-packages' in Path(opendoc_formats.__file__).resolve().parts
    for name in ('docx', 'pptx', 'PIL', 'fontTools', 'pymupdf', 'pypdf', 'bs4'):
        assert importlib.util.find_spec(name) is None, f'Unexpected engine: {name}'
    source = source_package()
    with TemporaryDirectory(prefix='opendoc-formats-native-') as folder:
        target = Path(folder)/'edited.docx'
        with DocxPackage(source) as package:
            assert package.to_bytes() == source
            relationship, = package.relationships
            assert relationship.owner_status == 'package' and relationship.source_part is None
            assert relationship.target_part == 'word/document.xml' and relationship.target_mode == 'Internal'
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
        orphan_source = source_package(orphans=True)
        try:
            DocxPackage(orphan_source)
        except InvalidDocumentError as error:
            assert 'missing source part' in str(error)
        else:
            raise AssertionError('Strict mode accepted orphan relationships')
        with DocxPackage(orphan_source, inspection_only=True) as package:
            issue, = package.info.issues
            assert issue.feature == 'docx.orphan-relationships' and issue.location == 'custom/_rels/missing.xml.rels'
            assert package.info.inspection_only and package.paragraphs[0].text == 'Own текст\ttail'
            assert package.to_bytes() == orphan_source
            orphan, = [row for row in package.relationships if row.owner_status == 'missing']
            assert orphan.nominal_source_part == 'custom/missing.xml'
            assert orphan.source_part is None and orphan.target_part is None
            patch = ReplaceTextSpan(package.paragraphs[0].id, 0, 3, 'Edited')
            for action in (lambda: package.to_bytes([patch]), lambda: package.write(target)):
                try:
                    action()
                except UnsupportedDocumentError:
                    pass
                else:
                    raise AssertionError('Inspection-only package allowed a mutation')
                assert target.read_bytes() == before
        for encoded, name, error_type in (('%FF', '�', UnsupportedDocumentError), ('%GG', '%GG', InvalidDocumentError),
                                          ('%EF%BF%BD', '�', None)):
            uri_source = source_package(uri_target=(encoded, name))
            for inspection_only in (False, True):
                try:
                    with DocxPackage(uri_source, inspection_only=inspection_only) as package:
                        assert package.to_bytes() == uri_source and not package.info.issues
                except (UnsupportedDocumentError, InvalidDocumentError) as error:
                    assert error_type is not None and isinstance(error, error_type), error
                    assert 'word/_rels/document.xml.rels' in str(error) and 'own' in str(error)
                else:
                    assert error_type is None, 'Invalid URI bound a wrong ZIP part'
        for main_part in (('word/own doc.xml', 'word/own%20doc.xml', '/word/own%20doc.xml'),
                          ('word/own%20doc.xml', 'word/own%20doc.xml', '/word/own%20doc.xml'),
                          ('word/é.xml', './word/%C3%A9.xml', '/word/é.xml')):
            alias_source = source_package(main_part=main_part)
            with DocxPackage(alias_source) as package:
                assert package.to_bytes() == alias_source and package.paragraphs[0].part == main_part[0]
                patch = ReplaceTextSpan(package.paragraphs[0].id, 0, 3, 'Edited')
                changed = package.to_bytes([patch])
            with DocxPackage(changed) as package:
                assert package.paragraphs[0].text == 'Edited текст\ttail' and package.paragraphs[0].part == main_part[0]
    print('Native DOCX with lxml only: snapshots, edits, orphan diagnostics, URI aliases, limits and cancellation passed')


if __name__ == '__main__':
    main()
