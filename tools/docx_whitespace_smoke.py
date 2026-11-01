"""Installed DOCX-only profile: visible text, raw snapshots and public JSON/DOCX cycles."""

import importlib.util
import io
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import opendoc_formats
from opendoc_formats import read_document, write_document
from opendoc_formats.docx import DocxPackage
from opendoc_formats.readers.docx import read_docx


def main():
    assert 'site-packages' in Path(opendoc_formats.__file__).parts
    for name in ('fontTools', 'pypdf', 'pymupdf', 'fitz', 'PIL', 'bs4'):
        assert importlib.util.find_spec(name) is None, name
    w = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    relationship = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument'
    body = ('<w:p><w:r><w:t>  A  B  </w:t></w:r></w:p>'
            '<w:p><w:r><w:t xml:space="preserve">  P Q  </w:t></w:r></w:p>'
            '<w:p xml:space="preserve"><w:r><w:t>  C D  </w:t></w:r></w:p>')
    parts = {
        '[Content_Types].xml': ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                                '<Default Extension="rels" '
                                'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                                '<Override PartName="/word/document.xml" '
                                'ContentType="application/vnd.openxmlformats-officedocument.'
                                'wordprocessingml.document.main+xml"/></Types>'),
        '_rels/.rels': ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       f'<Relationship Id="main" Type="{relationship}" Target="word/document.xml"/></Relationships>'),
        'word/document.xml': f'<w:document xmlns:w="{w}"><w:body>{body}<w:sectPr/></w:body></w:document>',
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, value in parts.items():
            archive.writestr(name, value)
    data = stream.getvalue()
    expected = 'A  B\n  P Q  \nC D'
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root/'original.docx'
        source.write_bytes(data)
        with DocxPackage(source) as package:
            assert package.paragraphs[0].text == '  A  B  '
        assert read_docx(source).plain == expected
        result = read_document(source)
        assert result.success, result.issues
        model = result.document
        assert model.metadata['opendoc_formats.docx_settings']['settings_present'] is False
        assert '__doc_defaults__' not in model.styles
        assert (model.sections[0].page.width.pt, model.sections[0].page.height.pt) == (612, 792)
        assert model.sections[0].properties['opendoc_formats.docx_page']['size'] is None
        assert any(issue.code == 'docx.page-geometry' for issue in result.issues)
        for cycle in (1, 2):
            path = root/f'cycle-{cycle}.json'
            assert write_document(model, path).success
            result = read_document(path)
            assert result.success, result.issues
            path = root/f'cycle-{cycle}.docx'
            assert write_document(result.document, path).success
            with zipfile.ZipFile(path) as archive:
                settings = ET.fromstring(archive.read('word/settings.xml'))
                styles = ET.fromstring(archive.read('word/styles.xml'))
                page = ET.fromstring(archive.read('word/document.xml')).find('.//{'+w+'}sectPr')
            assert len(settings) == 0
            assert styles.find('{'+w+'}docDefaults') is None
            assert page is not None and page.find('{'+w+'}pgSz') is None and page.find('{'+w+'}pgMar') is None
            assert read_docx(path).plain == expected
            result = read_document(path)
            assert result.success, result.issues
            model = result.document
        path = root/'visible.txt'
        assert write_document(model, path).success
        assert path.read_text(encoding='utf-8').rstrip('\n') == expected
        assert source.read_bytes() == data
    print('Installed DOCX-only whitespace: Word-derived visible text, raw snapshot and two JSON/DOCX cycles; no font/PDF extras')


if __name__ == '__main__':
    main()
