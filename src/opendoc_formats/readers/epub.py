"""EPUB → Text.

Использует собственный EPUB-контейнер и BeautifulSoup для XHTML.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import opendoc_model as od

from opendoc_formats.types import Block, BlockType, DocFormat, Text


def read_epub(path: Union[str, Path], *, backend: str = "native") -> Text:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return Text(
            source_format=DocFormat.EPUB,
            engine="native-epub",
            warnings=["beautifulsoup4 not installed"],
        )

    from opendoc_formats.readers.epub_package import read_ebooklib_package, read_epub_package

    if backend not in {"native", "ebooklib"}:
        raise ValueError("EPUB backend must be native or ebooklib")
    book = read_epub_package(p) if backend == "native" else read_ebooklib_package(p)
    blocks: list[Block] = []
    plain_parts: list[str] = []

    for item in book.items.values():
        if item.media_type == "application/xhtml+xml":
            soup = BeautifulSoup(item.content, "html.parser")
            for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"]):
                text = tag.get_text(strip=True)
                if not text:
                    continue
                tag_name = tag.name.lower()
                if tag_name.startswith("h"):
                    level = int(tag_name[1])
                    btype = BlockType.HEADING
                elif tag_name == "li":
                    level = 0
                    btype = BlockType.LIST_ITEM
                else:
                    level = 0
                    btype = BlockType.PARAGRAPH
                blocks.append(Block(type=btype, text=text, level=level))
                plain_parts.append(text)

    return Text(
        blocks=blocks,
        plain="\n".join(plain_parts),
        source_format=DocFormat.EPUB,
        engine=book.engine,
        pages=len(blocks),
    )


def read_epub_model(path: Union[str, Path], *, backend: str = "native") -> od.DocumentModel:
    """Import EPUB spine chapters, links, media, and basic CSS into DocumentModel."""
    from opendoc_formats.readers.epub_model import read_epub_model as read_model

    return read_model(path, backend=backend)


__all__ = ["read_epub", "read_epub_model"]
