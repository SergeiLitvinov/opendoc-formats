"""Own EPUB fixtures for editable XHTML tables and MathML without legacy engines."""

import zipfile

import pytest
from opendoc_model import Formula, FormulaFormat, Table, document_from_json, document_to_json, get_integration

from opendoc_formats import read_document, write_document


def _book(source, body):
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            """<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
          <rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>""",
        )
        archive.writestr(
            "OPS/book.opf",
            """<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
          <metadata/><manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
          <spine><itemref idref="c"/></spine></package>""",
        )
        archive.writestr("OPS/chapter.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body>' + body + "</body></html>")


def test_tables_math_links_mixed_cells_order_and_json(tmp_path):
    source = tmp_path / "own.epub"
    _book(
        source,
        """<p>Before <math xmlns="http://www.w3.org/1998/Math/MathML" id="inline"><mi>x</mi></math> after</p>
      <table id="data"><caption>Own caption</caption><thead><tr><th colspan="2">Header</th></tr></thead>
      <tbody><tr><td rowspan="2">Left</td><td><a href="#target">Link</a></td></tr>
      <tr><td>First<p>Middle</p>Last<table id="nested"><tr><td>Nested</td></tr></table>Tail</td></tr></tbody></table>
      <math xmlns="http://www.w3.org/1998/Math/MathML" id="display" display="block"><mfrac><mn>1</mn><mn>2</mn></mfrac></math>
      <p id="target">End</p>""",
    )
    result = read_document(source)
    assert result.success and not result.assessment_complete
    assert not result.issues
    blocks = result.document.sections[0].blocks
    assert len(blocks) == 5 and blocks[0].plain_text == "Before x after" and blocks[1].plain_text == "Own caption"
    inline = blocks[0].content[1]
    assert isinstance(inline, Formula) and inline.format is FormulaFormat.MATHML and not inline.display
    table = blocks[2]
    assert isinstance(table, Table) and len(table.rows) == 3
    assert table.rows[0].cells[0].column_span == 2 and table.rows[0].cells[0].blocks[0].content[0].style.bold
    assert table.rows[1].cells[0].row_span == 2
    assert table.rows[1].cells[1].blocks[0].content[0].link == "#epub-chapter.xhtml--target"
    mixed = table.rows[2].cells[0].blocks
    assert [block.plain_text for block in mixed if not isinstance(block, Table)] == ["First", "Middle", "Last", "Tail"]
    assert isinstance(mixed[3], Table) and mixed[3].rows[0].cells[0].blocks[0].plain_text == "Nested"
    assert blocks[3].content[0].display and blocks[4].plain_text == "End"
    assert table.provenance.package_part == "/OPS/chapter.xhtml"
    assert inline.provenance.package_part == "/OPS/chapter.xhtml" and inline.provenance.object_id == "inline"
    restored = document_from_json(document_to_json(result.document))
    assert document_to_json(restored) == document_to_json(result.document)
    output = tmp_path / "own.html"
    report = write_document(restored, output)
    assert report.success, report.to_dict()
    exported = output.read_text(encoding="utf-8")
    assert exported.count("<table") == 2 and 'rowspan="2"' in exported and 'colspan="2"' in exported
    assert "mfrac" in exported and "Nested" in exported


@pytest.mark.parametrize("value", ["0", "-1", "999999", "bad"])
def test_invalid_cell_span_has_located_loss(tmp_path, value):
    source = tmp_path / "invalid.epub"
    _book(source, f'<table><tr><td id="cell" colspan="{value}">Own cell</td></tr></table>')
    result = read_document(source)
    assert result.success and result.document.sections[0].blocks[0].rows[0].cells[0].column_span == 1
    record = get_integration(result.document).preservation[0]
    assert record.issue.reason == "invalid-cell-span" and record.issue.location.endswith("OPS/chapter.xhtml#cell")
    assert record.provenance.package_part == "/OPS/chapter.xhtml"


def test_math_actions_and_script_text_are_not_executed_or_imported(tmp_path):
    source = tmp_path / "inert.epub"
    _book(
        source,
        """<p>Before<script>throw new Error("inert")</script><math xmlns="http://www.w3.org/1998/Math/MathML"
        id="math" onclick="run()"><mi>x</mi><script>run()</script></math> after</p>""",
    )
    result = read_document(source)
    assert result.success
    formula = next(item for item in result.document.sections[0].blocks[0].content if isinstance(item, Formula))
    assert "onclick" not in formula.value and "script" not in formula.value
    assert "throw new Error" not in result.document.sections[0].blocks[0].plain_text
    assert any(issue.reason == "math-profile-sanitized" for issue in result.issues)


@pytest.mark.parametrize("mode", ["tables", "containers"])
def test_table_profile_nesting_limits_reject_excessive_source(tmp_path, mode):
    source = tmp_path / "deep.epub"
    if mode == "tables":
        body = "<table><tr><td>" * 19 + "Own text" + "</td></tr></table>" * 19
    else:
        body = "<table><tr><td>" + "<div>" * 66 + "<p>Own text</p>" + "</div>" * 66 + "</td></tr></table>"
    _book(source, body)
    with pytest.raises(ValueError, match="nesting exceeds profile limit"):
        read_document(source)
