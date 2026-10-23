"""EPUB → Text.

Использует собственный EPUB-контейнер и BeautifulSoup для XHTML.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Union

import opendoc_model as od

from opendoc_formats.support.cancellation import check_cancelled
from opendoc_formats.support.text_diagnostics import append_text_warning
from opendoc_formats.types import Block, BlockType, DocFormat, Text


def read_epub(path: Union[str, Path], *, backend: str = "native", cancelled: Callable[[], bool] | None = None) -> Text:
    check_cancelled(cancelled, 'EPUB text import')
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        result = Text(
            source_format=DocFormat.EPUB,
            engine="native-epub",
        )
        append_text_warning(result, od.DiagnosticIssue(
            'epub.text-backend-unavailable', od.IssueSeverity.LOSS, 'beautifulsoup4 not installed',
            str(p), reason='epub-text-backend-unavailable',
        ), od.Provenance('epub', str(p), object_id='text-extraction'))
        return result

    from opendoc_formats.readers.epub_package import read_epub_package

    if backend != "native":
        raise ValueError("EPUB supports backend='native' only; install opendoc-formats[epub]")
    book = read_epub_package(p, cancelled=cancelled)
    blocks: list[Block] = []
    plain_parts: list[str] = []

    for item in book.items.values():
        check_cancelled(cancelled, 'EPUB text chapter')
        if item.media_type == "application/xhtml+xml":
            soup = BeautifulSoup(item.content, "html.parser")
            for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"]):
                check_cancelled(cancelled, 'EPUB text block')
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

    check_cancelled(cancelled, 'EPUB text completion')
    return Text(
        blocks=blocks,
        plain="\n".join(plain_parts),
        source_format=DocFormat.EPUB,
        engine=book.engine,
        pages=len(blocks),
    )


def read_epub_model(path: Union[str, Path], *, backend: str = "native", include_nonlinear: bool = False,
                    cancelled: Callable[[], bool] | None = None) -> od.DocumentModel:
    """Import EPUB spine chapters, links, media, and basic CSS into DocumentModel."""
    from opendoc_formats.readers.epub_model import read_epub_model as read_model

    return read_model(path, backend=backend, include_nonlinear=include_nonlinear, cancelled=cancelled)


__all__ = ["read_epub", "read_epub_model"]
