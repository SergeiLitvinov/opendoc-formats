"""Exercise the installed HTML extra without unrelated format engines."""

import importlib.util
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup
from opendoc_model.document_codec import document_from_json, document_to_json

from opendoc_formats import read_document, write_document


def main():
    for engine in ("lxml", "docx", "pptx", "pymupdf", "pypdf", "PIL", "ebooklib"):
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
            source = target
        assert (root / "source.html").read_bytes() == original
    print("Installed minimal HTML profile passed: two JSON cycles, languages and table semantics")


if __name__ == "__main__":
    main()
