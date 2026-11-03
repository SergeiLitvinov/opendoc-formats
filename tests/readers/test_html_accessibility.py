"""Own static fixtures: semantic HTML survives two editable JSON cycles."""

import pytest

pytest.importorskip("bs4")
pytest.importorskip("tinycss2")

from bs4 import BeautifulSoup
from opendoc_model.document_codec import document_from_json, document_to_json

from opendoc_formats import read_document, write_document


def test_table_name_header_associations_and_languages(tmp_path):
    source = tmp_path / "source.html"
    source.write_text(
        '<html lang="en"><head><title>Measurements</title></head><body>'
        '<h1 id="report">Report</h1><p><a href="#measurements">Measurements</a></p>'
        '<h2>Procedure</h2><ol start="3"><li>Prepare</li><li>Record</li></ol>'
        '<table id="measurements"><caption><b><a href="#report">Measurement</a></b> '
        '<span lang="fr">résultats</span></caption>'
        '<thead><tr><th id="sample" scope="col">Sample</th><th id="value" scope="col">Value</th></tr></thead>'
        '<tbody><tr><th id="a" scope="row">A</th><td headers="a value">12</td></tr></tbody>'
        '<tfoot><tr><td colspan="2">Total</td></tr></tfoot></table>'
        '<p lang=""><span lang="de">Deutsch</span> unknown</p></body></html>', encoding="utf-8",
    )
    original = source.read_bytes()
    for cycle in range(2):
        imported = read_document(source)
        assert imported.success
        model = document_from_json(document_to_json(imported.document))
        assert model.metadata["language"] == "en"
        target = tmp_path / f"cycle-{cycle}.html"
        assert write_document(model, target).success
        soup = BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser")
        assert soup.html["lang"] == "en"
        table = soup.find("table", id="measurements")
        assert len(soup.find_all("caption")) == 1
        assert table.caption.get_text(" ", strip=True) == "Measurement résultats"
        assert table.caption.b is None  # Formatting uses semantic model TextStyle and inline CSS.
        assert "font-weight:700" in str(table.caption)
        assert table.caption.find("a", href="#report").get_text() == "Measurement"
        assert table.caption.find("span", lang="fr").get_text() == "résultats"
        assert [(cell["id"], cell["scope"]) for cell in table.find_all("th")] == [
            ("sample", "col"), ("value", "col"), ("a", "row"),
        ]
        assert table.tbody.td["headers"] == ["a", "value"]
        assert table.tfoot.td["colspan"] == "2"
        assert [node.name for node in soup.select("h1,h2")] == ["h1", "h2"]
        assert soup.ol["start"] == "3"
        assert soup.find("a", href="#measurements") is not None
        ids = [node["id"] for node in soup.find_all(id=True)]
        assert len(ids) == len(set(ids))
        assert soup.find("span", lang="de").get_text() == "Deutsch"
        assert soup.find("span", lang="").get_text() == " unknown"
        source = target
    assert (tmp_path / "source.html").read_bytes() == original


def test_rowgroup_boundaries_and_orphan_caption_are_not_silent(tmp_path):
    source = tmp_path / "groups.html"
    source.write_text('<table><caption>Groups</caption><tbody><tr><th scope="rowgroup">A</th></tr></tbody>'
                      '<tbody><tr><th scope="rowgroup">B</th></tr></tbody></table>')
    imported = read_document(source)
    target = tmp_path / "groups-out.html"
    assert write_document(imported.document, target).success
    soup = BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser")
    assert len(soup.table.find_all("tbody", recursive=False)) == 2
    assert [cell["scope"] for cell in soup.table.find_all("th")] == ["rowgroup", "rowgroup"]
    imported.document.sections[0].blocks.pop()
    report = write_document(imported.document, target)
    assert report.success
    assert any(issue.feature == "html-accessibility" for issue in report.issues)
    assert "Groups" in target.read_text(encoding="utf-8")


def test_caption_blocks_keep_list_structure_and_nested_ownership(tmp_path):
    source = tmp_path / "caption-list.html"
    source.write_text('<table><caption><p>Legend</p><ol start="2"><li>First</li>'
                      '<li>Second</li></ol></caption><tr><td>12</td></tr></table>')
    for cycle in range(2):
        imported = read_document(source)
        target = tmp_path / f"caption-list-{cycle}.html"
        assert write_document(document_from_json(document_to_json(imported.document)), target).success
        soup = BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser")
        assert len(soup.find_all("ol")) == 1
        assert soup.table.caption.ol["start"] == "2"
        assert [item.get_text() for item in soup.table.caption.ol.find_all("li")] == ["First", "Second"]
        source = target


@pytest.mark.parametrize("language", ["", "fr", 'en\" onclick=\"alert(1)'])
def test_document_language_is_preserved_and_escaped(tmp_path, language):
    from html import escape

    source = tmp_path / "input.html"
    source.write_text(f'<html lang="{escape(language, quote=True)}"><body><p>Text</p></body></html>')
    imported = read_document(source)
    target = tmp_path / "out.html"
    assert write_document(document_from_json(document_to_json(imported.document)), target).success
    soup = BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser")
    assert soup.html["lang"] == language
    assert not soup.find_all(attrs={"onclick": True})


def test_unsupported_aria_and_invalid_scope_are_located(tmp_path):
    source = tmp_path / "aria.html"
    source.write_text('<html><body><p id="notice" role="alert" aria-live="polite">Notice</p>'
                      '<table><tr><th id="bad" scope="bad">Label</th></tr></table></body></html>')
    imported = read_document(source)
    issues = [issue for issue in imported.issues if issue.code == "html-accessibility" and issue.severity.value == "loss"]
    assert len(issues) == 2
    assert all(issue.location for issue in issues)
    target = tmp_path / "out.html"
    assert write_document(imported.document, target).success
    soup = BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser")
    assert not soup.find_all(attrs={"role": True})
    assert "scope" not in soup.th.attrs


def test_empty_caption_and_nested_table_ownership(tmp_path):
    source = tmp_path / "nested.html"
    source.write_text('<table id="outer"><caption></caption><tr><td>'
                      '<table id="inner"><caption>Inner</caption><tr><th scope="col">Name</th></tr></table>'
                      '</td></tr></table>')
    for cycle in range(2):
        imported = read_document(source)
        target = tmp_path / f"out-{cycle}.html"
        assert write_document(document_from_json(document_to_json(imported.document)), target).success
        soup = BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser")
        assert soup.find("table", id="outer").find("caption", recursive=False).get_text() == ""
        assert soup.find("table", id="inner").caption.get_text() == "Inner"
        source = target
