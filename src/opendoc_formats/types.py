"""Lightweight extraction results; rich documents use OpenDoc.DocumentModel."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DocFormat(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    HTML = "html"
    LATEX = "latex"
    MODEL = "model"
    TXT = "txt"
    DJVU = "djvu"
    EPUB = "epub"
    BIB = "bib"  # библиография как plain text
    UNKNOWN = "unknown"


class BlockType(str, Enum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST_ITEM = "list_item"
    TABLE = "table"
    CAPTION = "caption"
    EQUATION = "equation"
    CODE = "code"
    PAGE_BREAK = "page_break"
    UNKNOWN = "unknown"


@dataclass
class Block:
    """Структурный блок текста (параграф/заголовок/таблица/...)."""

    type: BlockType
    text: str = ""
    level: int = 0
    page: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Table:
    """Таблица как список строк."""

    rows: list[list[str]] = field(default_factory=list)
    page: int = 0


@dataclass
class Text:
    """Извлечённое из документа содержимое.

    Не зависит от исходного формата. ``blocks`` хранит структурную
    разметку; ``plain`` — плоский текст (для grep/fuzzy/keyword); ``tables``
    — таблицы отдельно, чтобы не терять структуру.
    """

    blocks: list[Block] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    plain: str = ""
    language: str = "und"
    source_format: DocFormat = DocFormat.UNKNOWN
    engine: str = ""  # какой движок достал (pdfplumber / pypdf / pymupdf / ...)
    warnings: list[str] = field(default_factory=list)
    pages: int = 0

    def __bool__(self) -> bool:
        return bool(self.plain or self.blocks or self.tables)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocks": [
                {
                    "type": b.type.value if hasattr(b.type, "value") else str(b.type),
                    "text": b.text,
                    "level": b.level,
                    "page": b.page,
                    "meta": b.meta,
                }
                for b in self.blocks
            ],
            "tables": [{"page": t.page, "rows": t.rows} for t in self.tables],
            "plain": self.plain,
            "language": self.language,
            "source_format": self.source_format.value if hasattr(self.source_format, "value") else str(self.source_format),
            "engine": self.engine,
            "warnings": self.warnings,
            "pages": self.pages,
        }
