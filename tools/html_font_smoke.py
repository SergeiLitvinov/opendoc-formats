"""Exercise installed self-contained HTML resource fonts without optional engines."""

import base64
import hashlib
import importlib.util
import re
from pathlib import Path
from tempfile import TemporaryDirectory

import opendoc_model as od

import opendoc_formats
from opendoc_formats import write_document


def main():
    for module in (opendoc_formats, od):
        assert 'site-packages' in Path(module.__file__).parts
    for name in ('fontTools', 'PIL', 'docx', 'pptx', 'lxml', 'bs4', 'tinycss2', 'pymupdf', 'pypdf'):
        assert importlib.util.find_spec(name) is None, name
    fixtures = Path(__file__).resolve().parents[1]/'tests/native/data'
    with TemporaryDirectory(prefix='opendoc_html_fonts_') as directory:
        for filename, media, kind, text in (
            ('ligature-post3.ttf', 'font/ttf', 'truetype', 'fi ti fi'),
            ('own-cff.otf', 'font/otf', 'opentype', 'AB'),
        ):
            source = (fixtures/filename).read_bytes()
            alias = 'ODF Embedded '+hashlib.sha256(source).hexdigest()[:12]
            style = od.TextStyle(font_family='Unrelated declared family', font_size=od.Length(20))
            od.set_font_reference(style, od.FontReference('font', 0))
            model = od.DocumentModel(sections=[od.Section(blocks=[od.Paragraph([od.TextRun(text, style)])])], resources={
                'font': od.Resource('font', od.ResourceKind.FONT, media, source),
            })
            for cycle in range(2):
                model = od.document_from_json(od.document_to_json(model))
                before = od.document_to_json(model)
                output = Path(directory)/f'{filename}-{cycle}.html'
                report = write_document(model, output)
                assert report.success, report.issues
                assert report.metrics['font_resolution']['substitution_count'] == 0
                assert report.metrics['font_embedding']['source_bytes'] == len(source)
                assert report.metrics['font_embedding']['embedded_bytes'] == len(source)
                html = output.read_text(encoding='utf-8')
                data = re.findall(r'data:font/(?:ttf|otf);base64,([^"]+)', html)
                assert [base64.b64decode(value, validate=True) for value in data] == [source]
                assert f'format("{kind}")' in html
                assert f'font-family:&quot;{alias}&quot;' in html and text in html
                assert od.document_to_json(model) == before
    print('Installed base HTML export without fontTools: TTF/OTF full programs, bindings and two JSON cycles passed')


if __name__ == '__main__':
    main()
