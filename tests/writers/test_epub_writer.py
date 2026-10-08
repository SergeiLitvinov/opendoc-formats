"""Own model fixtures for the finite native EPUB writer and atomic publication."""

import xml.etree.ElementTree as ET
from zipfile import ZIP_STORED, ZipFile

import pytest
from opendoc_model import (
    DocumentModel,
    Formula,
    FormulaFormat,
    Image,
    Paragraph,
    Resource,
    ResourceKind,
    Section,
    Table,
    TableCell,
    TableRow,
    TextRun,
    TextStyle,
    document_from_json,
    document_to_json,
)

from opendoc_formats import ExportOptions, read_document, write_document
from opendoc_formats.readers.epub_package import read_epub_package
from opendoc_formats.writers.epub_writer import _Xhtml, write_epub_model


def test_book_structure_semantics_images_math_links_and_json(tmp_path):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'
    document = DocumentModel(
        metadata={"title": "Own & book", "language": "en"},
        styles={"Heading 1": TextStyle()},
        resources={"pic": Resource("pic", ResourceKind.VECTOR_IMAGE, "image/svg+xml", data=svg)},
        sections=[Section(blocks=[
            Paragraph(content=[TextRun("Chapter")], style_id="Heading 1", properties={"anchor_id": "chapter"}),
            Paragraph(content=[TextRun("Bold", TextStyle(bold=True)), TextRun(" Link", link="#target")]),
            Table(rows=[TableRow(cells=[TableCell(column_span=2, blocks=[Paragraph(content=[TextRun("Merged")])])])]),
            Paragraph(content=[Formula('<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>',
                                       format=FormulaFormat.MATHML)]),
            Image("pic"), Image("pic"),
            Paragraph(content=[TextRun("End")], properties={"anchor_id": "target"}),
        ])],
    )
    output = tmp_path / "own.epub"
    report = write_document(document, output)
    assert report.success, report.to_dict()
    assert not report.lossless and report.metrics["output_verified"]
    assert report.metrics["epub_assets"] == 1
    package = read_epub_package(output)
    assert package.spine == (("chapter", "yes"),)
    with ZipFile(output) as archive:
        first = archive.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == ZIP_STORED and not first.extra
        assert archive.read("mimetype") == b"application/epub+zip"
        nav = ET.fromstring(archive.read("OPS/nav.xhtml"))
        ns = {"h": "http://www.w3.org/1999/xhtml"}
        assert nav.find(".//h:a", ns).get("href") == "chapter.xhtml#chapter"
        chapter = ET.fromstring(archive.read("OPS/chapter.xhtml"))
        assert chapter.find(".//h:a", ns).get("href") == "#target"
        assert len(chapter.findall(".//h:img", ns)) == 2
        image_name = chapter.find(".//h:img", ns).get("src")
        assert archive.read("OPS/" + image_name) == svg
        assert "mathml" in package.items["chapter"].properties
    imported = read_document(output)
    assert imported.success, imported.issues
    blocks = imported.document.sections[0].blocks
    assert blocks[0].plain_text == "Chapter" and blocks[1].content[0].style.bold
    assert isinstance(blocks[2], Table) and blocks[2].rows[0].cells[0].column_span == 2
    assert isinstance(blocks[3].content[0], Formula)
    assert blocks[3].content[0].format is FormulaFormat.MATHML
    assert sum(isinstance(item, Image) for block in blocks if isinstance(block, Paragraph) for item in block.content) == 2
    assert blocks[1].content[1].link.endswith("--target")
    restored = document_from_json(document_to_json(imported.document))
    assert document_to_json(restored) == document_to_json(imported.document)
    assert any(resource.data == svg for resource in restored.resources.values())


def test_no_heading_book_has_nonempty_navigation(tmp_path):
    output = tmp_path / "plain.epub"
    report = write_document(DocumentModel(sections=[Section(blocks=[Paragraph(content=[TextRun("Plain")])])]), output)
    assert report.success, report.to_dict()
    with ZipFile(output) as archive:
        nav = ET.fromstring(archive.read("OPS/nav.xhtml"))
        assert nav.find(".//{http://www.w3.org/1999/xhtml}a").get("href") == "chapter.xhtml"


def test_unsupported_image_does_not_replace_existing_book(tmp_path):
    output = tmp_path / "old.epub"
    output.write_bytes(b"previous")
    model = DocumentModel(resources={"pic": Resource("pic", ResourceKind.VECTOR_IMAGE, "image/tiff", data=b"unsupported")},
                          sections=[Section(blocks=[Image("pic")])])
    report = write_epub_model(model, output)
    assert not report.success and output.read_bytes() == b"previous"
    assert report.issues[-1].feature == "epub.write"


@pytest.mark.parametrize("after_write", [False, True])
def test_cancelled_export_keeps_existing_book(tmp_path, after_write):
    output = tmp_path / "old.epub"
    output.write_bytes(b"previous")
    calls = []

    def cancelled():
        calls.append(True)
        return len(calls) > 1 if after_write else True

    report = write_document(DocumentModel(), output, options=ExportOptions(cancelled=cancelled))
    assert not report.success and report.issues[-1].feature == "export.cancelled"
    assert output.read_bytes() == b"previous"
    assert not list(tmp_path.glob(".opendoc-formats-*"))


def test_xhtml_depth_limit_and_svg_attribute_case():
    parser = _Xhtml()
    with pytest.raises(ValueError, match="limits"):
        parser.feed("<html>" + "<div>" * 128)
    parser = _Xhtml()
    parser.feed('<html><body><svg viewBox="0 0 1 1"><rect width="1"/></svg></body></html>')
    assert parser.root.find(".//svg").get("viewBox") == "0 0 1 1"


def test_unused_source_attachment_is_diagnosed(tmp_path):
    model = DocumentModel(resources={"original": Resource("original", ResourceKind.ATTACHMENT,
                                                          "application/octet-stream", data=b"inert original")})
    output = tmp_path / "inert.epub"
    report = write_document(model, output)
    assert report.success
    assert any(issue.feature == "epub.unreferenced-resource" and issue.location == "resources[original]"
               for issue in report.issues)
    with ZipFile(output) as archive:
        assert all(b"inert original" not in archive.read(name) for name in archive.namelist())


def test_output_limit_preserves_existing_book(tmp_path, monkeypatch):
    import opendoc_formats.writers.epub_writer as writer

    monkeypatch.setattr(writer, "_MAX_BYTES", 10)
    output = tmp_path / "limited.epub"
    output.write_bytes(b"previous")
    report = writer.write_epub_model(DocumentModel(), output)
    assert not report.success and "exceeds" in report.issues[-1].message
    assert output.read_bytes() == b"previous"


def test_sections_become_chapters_with_cross_chapter_links(tmp_path):
    model = DocumentModel(sections=[
        Section(blocks=[Paragraph([TextRun("First", link="#second")], properties={"anchor_id": "first"})]),
        Section(blocks=[Paragraph([TextRun("Second", link="#first")], properties={"anchor_id": "second"})]),
    ])
    output = tmp_path / "chapters.epub"
    report = write_document(model, output)
    assert report.success and report.metrics["epub_spine_items"] == 2
    package = read_epub_package(output)
    assert package.spine == (("chapter", "yes"), ("chapter-2", "yes"))
    with ZipFile(output) as archive:
        ns = "{http://www.w3.org/1999/xhtml}"
        first = ET.fromstring(archive.read("OPS/chapter.xhtml"))
        second = ET.fromstring(archive.read("OPS/chapter-2.xhtml"))
        assert first.find(f".//{ns}a").get("href") == "chapter-2.xhtml#second"
        assert second.find(f".//{ns}a").get("href") == "chapter.xhtml#first"
        nav = ET.fromstring(archive.read("OPS/nav.xhtml"))
        assert [node.get("href") for node in nav.findall(f".//{ns}a")] == ["chapter.xhtml", "chapter-2.xhtml"]
    restored = read_document(output)
    assert restored.success and [section.blocks[0].plain_text for section in restored.document.sections] == ["First", "Second"]
    assert restored.document.sections[0].blocks[0].content[0].link == "#epub-chapter-2.xhtml--second"
    assert restored.document.sections[1].blocks[0].content[0].link == "#epub-chapter.xhtml--first"


def test_missing_internal_link_is_inert_and_diagnosed(tmp_path):
    output = tmp_path / "missing.epub"
    model = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun("Visible", link="#absent")])])])
    report = write_document(model, output)
    assert report.success and not report.lossless
    assert any(issue.feature == "epub.internal-link" for issue in report.issues)
    with ZipFile(output) as archive:
        chapter = ET.fromstring(archive.read("OPS/chapter.xhtml"))
        assert chapter.find(".//{http://www.w3.org/1999/xhtml}a").get("href") is None
