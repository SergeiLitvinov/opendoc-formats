"""Editable EPUB chapters, hyperlinks, media, and basic CSS."""

from io import BytesIO

import pytest

pytest.importorskip("ebooklib")
pytest.importorskip("bs4")
from ebooklib import epub
from opendoc.document_codec import load_document, save_document
from opendoc.document_model import Image, ResourceKind, TextRun
from PIL import Image as PillowImage

from opendoc_formats.readers.epub import read_epub_model


def _rich_epub(path):
    book = epub.EpubBook()
    book.set_identifier("book-42")
    book.set_title("Rich book")
    book.set_language("ru")
    css = epub.EpubItem(
        uid="style",
        file_name="styles/main.css",
        media_type="text/css",
        content=b".accent { color: #123456; font-weight: 700 } p.note { font-size: 16px; background-color: #ffeecc }",
    )
    buffer = BytesIO()
    PillowImage.new("RGB", (12, 8), "green").save(buffer, format="PNG")
    picture = epub.EpubItem(uid="picture", file_name="images/picture.png", media_type="image/png", content=buffer.getvalue())
    first = epub.EpubHtml(title="First", file_name="chapters/first.xhtml", lang="ru")
    first.content = """<html><head><link href="../styles/main.css" rel="stylesheet" type="text/css"/></head>
      <body><h1 id="target">Первая</h1>
      <p class="note">До <a href="https://example.com"><strong>ссылки</strong></a></p>
      <p><img src="../images/picture.png" alt="Схема"/> после</p>
      <ol><li><span class="accent" style="font-style: italic">Пункт</span></li></ol></body></html>"""
    first.add_link(href="../styles/main.css", rel="stylesheet", type="text/css")
    second = epub.EpubHtml(title="Second", file_name="chapters/second.xhtml", lang="ru")
    second.content = '<html><body><p><a href="first.xhtml#target">К первой</a></p></body></html>'
    for item in (css, picture, first, second, epub.EpubNcx(), epub.EpubNav()):
        book.add_item(item)
    book.toc = (
        epub.Link("chapters/second.xhtml", "Second", "second"),
        epub.Link("chapters/first.xhtml", "First", "first"),
    )
    book.spine = ["nav", second, first]
    epub.write_epub(str(path), book)


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
