"""Own EPUB fixtures for editable XHTML tables and MathML without legacy engines."""

import zipfile

import pytest
from opendoc_model import Formula, FormulaFormat, Table, document_from_json, document_to_json, get_integration

from opendoc_formats import read_document, write_document


def _book(source, body, assets=()):
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            """<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
          <rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>""",
        )
        manifest = "".join(f'<item id="{item_id}" href="{name}" media-type="{media}"/>' for item_id, name, media, _ in assets)
        archive.writestr(
            "OPS/book.opf",
            """<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
          <metadata/><manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/>"""
            + manifest
            + """</manifest>
          <spine><itemref idref="c"/></spine></package>""",
        )
        archive.writestr("OPS/chapter.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body>' + body + "</body></html>")
        for _, name, _, payload in assets:
            archive.writestr("OPS/" + name, payload)


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
    assert {issue.reason for issue in result.issues} == {"source-package-xml"}
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
    record = next(item for item in get_integration(result.document).preservation if item.issue.reason == "invalid-cell-span")
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


def test_standalone_images_svg_and_inert_assets_roundtrip(tmp_path):
    import struct
    import zlib

    from opendoc_model import Image, ResourceKind

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\xff"))
        + chunk(b"IEND", b"")
    )
    source = tmp_path / "assets.epub"
    _book(
        source,
        """<p>Before</p><img id="picture" src="pic.png" alt="Own picture"/>
        <svg id="drawing" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" aria-label="Own vector">
        <rect width="10" height="10" fill="red" onclick="run()"/><script>run()</script>
        <image href="https://example.invalid/remote.png"/></svg><p>After</p>""",
        assets=(
            ("pic", "pic.png", "image/png", png),
            ("font", "font.woff", "font/woff", b"own inert font placeholder"),
            ("audio", "audio.ogg", "audio/ogg", b"own inert audio placeholder"),
        ),
    )
    result = read_document(source)
    assert result.success and not result.lossless and not result.assessment_complete
    blocks = result.document.sections[0].blocks
    assert [blocks[0].plain_text, blocks[-1].plain_text] == ["Before", "After"]
    assert len(blocks) == 4 and isinstance(blocks[1].content[0], Image) and isinstance(blocks[2].content[0], Image)
    assert result.document.resources["epub-pic"].data == png
    assert blocks[1].content[0].provenance.package_part == "/OPS/chapter.xhtml"
    vector = result.document.resources[blocks[2].content[0].resource_id]
    assert vector.kind is ResourceKind.VECTOR_IMAGE and b"viewBox" in vector.data
    assert b"onclick" not in vector.data and b"script" not in vector.data and b"https://" not in vector.data
    assert result.document.resources["epub-font"].kind is ResourceKind.ATTACHMENT
    assert result.document.resources["epub-font"].data == b"own inert font placeholder"
    assert any(issue.reason == "svg-profile-sanitized" for issue in result.issues)
    restored = document_from_json(document_to_json(result.document))
    assert restored.resources == result.document.resources and get_integration(restored) == get_integration(result.document)
    target = tmp_path / "assets.html"
    report = write_document(restored, target)
    assert report.success and not report.lossless, report.to_dict()
    assert any(issue.feature == "epub.asset" for issue in report.issues)
    exported = target.read_text(encoding="utf-8")
    assert "data:image/png;base64" in exported and "data:image/svg+xml;base64" in exported
    assert "own inert font placeholder" not in exported and "own inert audio placeholder" not in exported


def test_external_and_nonimage_references_do_not_alias_local_image(tmp_path):
    source = tmp_path / "references.epub"
    _book(
        source,
        '<img id="remote" src="https:pic.png" alt="Remote"/><img src="font.woff" alt="Not image"/>',
        assets=(
            ("pic", "pic.png", "image/png", b"own unused placeholder"),
            ("font", "font.woff", "font/woff", b"own inert font placeholder"),
        ),
    )
    result = read_document(source)
    assert result.success
    assert [block.plain_text for block in result.document.sections[0].blocks] == ["Remote", "Not image"]
    assert len([issue for issue in result.issues if issue.reason == "missing-image"]) == 2


def test_inline_svg_resource_collision_preserves_manifest_asset(tmp_path):
    import hashlib

    from opendoc_formats.readers.html_resources import clean_xml

    svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'
    digest = hashlib.sha256(clean_xml(svg, "svg", lambda *args: None).encode()).hexdigest()
    item_id = "inline-svg-" + digest
    source = tmp_path / "collision.epub"
    _book(source, svg + svg, assets=((item_id, "other.png", "image/png", b"own inert other asset"),))
    result = read_document(source)
    assert result.success
    resources = result.document.resources
    assert resources["epub-" + item_id].data == b"own inert other asset"
    images = [block.content[0] for block in result.document.sections[0].blocks]
    assert images[0].resource_id == images[1].resource_id and images[0].resource_id != "epub-" + item_id
    assert len(resources) == 4
    assert b"rect" in resources[images[0].resource_id].data
