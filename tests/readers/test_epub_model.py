"""Editable EPUB chapters, hyperlinks, media, and basic CSS."""

import zipfile
from io import BytesIO

import pytest

pytest.importorskip("bs4")
from opendoc_model.document_codec import load_document, save_document
from opendoc_model.document_model import Image, ResourceKind, TextRun
from PIL import Image as PillowImage

from opendoc_formats.readers.epub import read_epub, read_epub_model


def _rich_epub(path):
    buffer = BytesIO()
    PillowImage.new("RGB", (12, 8), "green").save(buffer, format="PNG")
    first = """<html><head><link href="../styles/main.css" rel="stylesheet" type="text/css"/></head>
      <body><h1 id="target">Первая</h1>
      <p class="note">До <a href="https://example.com"><strong>ссылки</strong></a></p>
      <p><img src="../images/picture.png" alt="Схема"/> после</p>
      <ol><li><span class="accent" style="font-style: italic">Пункт</span></li></ol></body></html>"""
    second = '<html><body><p><a href="first.xhtml#target">К первой</a></p></body></html>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", '''<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
          <rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>''')
        archive.writestr("book.opf", '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
          <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier>book-42</dc:identifier>
          <dc:title>Rich book</dc:title><dc:language>ru</dc:language></metadata><manifest>
          <item id="style" href="styles/main.css" media-type="text/css"/>
          <item id="picture" href="images/picture.png" media-type="image/png"/>
          <item id="first" href="chapters/first.xhtml" media-type="application/xhtml+xml"/>
          <item id="second" href="chapters/second.xhtml" media-type="application/xhtml+xml"/>
          <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
          </manifest><spine><itemref idref="nav"/><itemref idref="second"/><itemref idref="first"/></spine></package>''')
        archive.writestr("nav.xhtml", '''<html xmlns="http://www.w3.org/1999/xhtml"
          xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>
          <li><a href="chapters/second.xhtml">Second</a></li>
          <li><a href="chapters/first.xhtml">First</a></li></ol></nav></body></html>''')
        archive.writestr("chapters/first.xhtml", first)
        archive.writestr("chapters/second.xhtml", second)
        archive.writestr("images/picture.png", buffer.getvalue())
        archive.writestr("styles/main.css", ".accent { color: #123456; font-weight: 700 } "
                         "p.note { font-size: 16px; background-color: #ffeecc }")


def test_spine_links_media_css_and_json_roundtrip(tmp_path):
    source = tmp_path / "rich.epub"
    _rich_epub(source)
    model = read_epub_model(source)
    assert model.source_format == "epub"
    assert model.metadata["title"] == "Rich book" and model.metadata["language"] == "ru"
    assert [section.properties["epub"]["title"] for section in model.sections] == ["Second", "First"]
    internal = model.sections[0].blocks[0].content[0]
    assert isinstance(internal, TextRun) and internal.link == "#epub-chapters-first.xhtml--target"
    blocks = model.sections[1].blocks
    external = next(item for block in blocks for item in block.content if isinstance(item, TextRun) and item.text == "ссылки")
    assert external.link == "https://example.com" and external.style.bold
    image = next(item for block in blocks for item in block.content if isinstance(item, Image))
    assert model.resources[image.resource_id].kind is ResourceKind.RASTER_IMAGE
    styled = next(item for block in blocks for item in block.content if isinstance(item, TextRun) and item.text == "Пункт")
    assert styled.style.color == "#123456" and styled.style.bold and styled.style.italic
    note = next(block for block in blocks if block.plain_text.startswith("До "))
    assert note.content[0].style.font_size.pt == 12 and note.content[0].style.background == "#ffeecc"
    assert {resource.kind for resource in model.resources.values()} == {ResourceKind.RASTER_IMAGE, ResourceKind.ATTACHMENT}
    saved = tmp_path / "model.json"
    save_document(model, saved)
    restored = load_document(saved)
    assert restored.sections[0].blocks[0].content[0].link == "#epub-chapters-first.xhtml--target"
    assert restored.resources[image.resource_id].data == model.resources[image.resource_id].data


@pytest.mark.parametrize("reader", [read_epub_model, read_epub])
@pytest.mark.parametrize("backend", ["ebooklib", "unknown"])
def test_removed_backend_has_actionable_error(tmp_path, reader, backend):
    source = tmp_path / "rich.epub"
    _rich_epub(source)
    with pytest.raises(ValueError, match="backend='native'.*opendoc-formats"):
        reader(source, backend=backend)
