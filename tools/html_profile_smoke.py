"""Exercise the installed HTML extra without unrelated format engines."""

import base64
import importlib.util
import sys
import tempfile
from pathlib import Path

import opendoc_model as od
from bs4 import BeautifulSoup
from opendoc_model.document_codec import document_from_json, document_to_json

from opendoc_formats import ExportOptions, read_document, write_document


def font_roundtrip(root):
    fixtures = Path(__file__).resolve().parents[1]/'tests/native/data'
    for name, media, text in [('ligature-post3.ttf', 'font/ttf', 'fi ti fi'), ('own-cff.otf', 'font/otf', 'AB')]:
        data = (fixtures/name).read_bytes()
        style = od.TextStyle(font_family='Unrelated declared family', font_size=od.Length(20))
        od.set_font_reference(style, od.FontReference('own', 0))
        model = od.DocumentModel(sections=[od.Section(blocks=[od.Paragraph([od.TextRun(text, style)])])], resources={
            'own': od.Resource('own', od.ResourceKind.FONT, media, data=data),
        })
        for cycle in range(2):
            target = root/f'{name}-{cycle}.html'
            before = od.document_to_json(model)
            report = write_document(model, target)
            assert report.success, report.issues
            assert od.document_to_json(model) == before
            result = read_document(target)
            assert result.success, result.issues
            model = od.document_from_json(od.document_to_json(result.document))
            fonts = [r for r in model.resources.values() if r.kind is od.ResourceKind.FONT]
            assert len(fonts) == 1 and fonts[0].data == data
            runs = model.sections[0].blocks[0].content
            assert ''.join(run.text for run in runs) == text
            for run in runs:
                ref = od.get_font_reference(run.style)
                assert ref is not None and ref.face_index == 0 and model.resources[ref.resource_id].data == data


def main():
    for engine in ("lxml", "docx", "pptx", "pymupdf", "pypdf", "PIL", "ebooklib", "fontTools"):
        assert importlib.util.find_spec(engine) is None, f"Unexpected engine: {engine}"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        if '--dom-only' in sys.argv:
            assert importlib.util.find_spec('tinycss2') is None
            source = root/'semantic.html'
            source.write_text('<style>/* } ; */ body h1 + p > .marked:first-child '
                              '{ /* ; */ color:rgba(18,52,86,0.5) !important; font-size:inherit; '
                              'background-color:currentColor }</style>'
                              '<body>'
                              '<h1>Title</h1><p style="font-size:16px;font-family: \'Own Sans\', serif">Own '
                              '<span class="marked" style="font-weight:bold;color:#000000">'
                              'bold</span> text</p></body>', encoding='utf-8')
            result = read_document(source)
            assert result.success, result.issues
            heading, paragraph = result.document.sections[0].blocks
            assert heading.plain_text == 'Title' and paragraph.plain_text == 'Own bold text'
            styled, = [run for run in paragraph.content if run.text == 'bold']
            assert styled.style.bold and styled.style.color.to_hex() == '#123456'
            assert styled.style.color.alpha == 0.5
            assert styled.style.background == styled.style.color
            assert styled.style.font_size == od.Length(12)
            assert styled.style.font_family == 'Own Sans'
            fixtures = Path(__file__).resolve().parents[1]/'tests/native/data'
            for filename, media in [('ligature-post3.ttf', 'ttf'), ('own-cff.otf', 'otf')]:
                data = (fixtures/filename).read_bytes()
                payload = base64.b64encode(data).decode('ascii')
                uri = f'data:font/{media};base64,{payload}'
                family = 'Шрифт 文' if media == 'ttf' else 'Épreuve'
                descriptors = (
                    f"SRC: url({uri}); font-family: '{family}'"
                    if media == 'ttf'
                    else f"font-style: ITALIC; font-weight: BOLD; src: url( '{uri}' ) FORMAT(opentype); font-family: '{family}'"
                )
                variant = '' if media == 'ttf' else ';font-weight:700;font-style:italic'
                source.write_text(
                    f'<style>@FONT-FACE {{ {descriptors} }}'
                    f'.own {{font-family:"{family}"{variant}}}</style><p class="own">AB</p>',
                    encoding='utf-8',
                )
                result = read_document(source)
                assert result.success, result.issues
                run, = result.document.sections[0].blocks[0].content
                ref = od.get_font_reference(run.style)
                assert run.text == 'AB' and ref is not None and ref.face_index == 0
                assert run.style.font_family == family
                assert result.document.resources[ref.resource_id].data == data
            font_roundtrip(root)
            source.write_text('<p style="color:hsla(-240,100%,50%,.25)">'
                              '<span style="color:currentColor">Green</span></p>', encoding='utf-8')
            result = read_document(source)
            assert result.success, result.issues
            green = result.document.sections[0].blocks[0].content[0].style.color
            assert green.to_hex().upper() == '#00FF00' and green.alpha == 0.25
            source.write_text('<p style="color:var(--custom)">Needs CSS</p>', encoding='utf-8')
            result = read_document(source)
            assert not result.success and result.issues[0].code == 'import.backend-unavailable'
            print('Installed HTML DOM profile preserves static TTF/OTF across HTML and JSON cycles without tinycss2')
            return
        source = root / "source.html"
        source.write_text('<html lang="en"><body><table id="measurements"><caption>'
                          '<b>Own measurements</b></caption><thead><tr>'
                          '<th id="value" scope="col">Value</th></tr></thead>'
                          '<tbody><tr><th id="sample" scope="row">A</th>'
                          '<td headers="sample value"><span lang="fr">douze</span></td></tr></tbody>'
                          '</table></body></html>', encoding="utf-8")
        original = source.read_bytes()
        for cycle in range(2):
            imported = read_document(source)
            assert imported.success, imported.issues
            model = document_from_json(document_to_json(imported.document))
            target = root / f"cycle-{cycle}.html"
            report = write_document(model, target)
            assert report.success, report.to_dict()
            parsed = BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser")
            assert parsed.html["lang"] == "en"
            assert parsed.table.caption.get_text() == "Own measurements"
            assert "font-weight:700" in str(parsed.table.caption)
            assert [(cell["id"], cell["scope"]) for cell in parsed.table.find_all("th")] == [
                ("value", "col"), ("sample", "row"),
            ]
            assert parsed.table.td["headers"] == ["sample", "value"]
            assert parsed.table.td.find("span", lang="fr").get_text() == "douze"
            ids = [node["id"] for node in parsed.find_all(id=True)]
            assert len(ids) == len(set(ids))
            previous = target.read_bytes()
            polls = 0

            def stop_export():
                nonlocal polls
                polls += 1
                return polls >= 12

            cancelled = write_document(model, target, options=ExportOptions(cancelled=stop_export))
            assert polls == 12 and not cancelled.success
            assert any(issue.feature == 'export.cancelled' for issue in cancelled.issues)
            assert target.read_bytes() == previous
            source = target
        assert (root / "source.html").read_bytes() == original
        font_roundtrip(root)
    print("Installed minimal HTML profile passed: two JSON cycles, languages and table semantics")
    print('HTML TTF/OTF import/export: full programs and FontReference retained without fontTools')


if __name__ == "__main__":
    main()
