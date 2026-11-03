"""Exercise the installed HTML extra without unrelated format engines."""

import importlib.util
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
