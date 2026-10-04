"""Public immutable DOCX snapshots and transactional native text editing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Literal, TypeAlias

from opendoc_formats.native.common import Cancellation, Source, positive_int, publish

PartRole: TypeAlias = Literal["body", "header", "footer", "footnote", "endnote", "other"]
Position: TypeAlias = Literal["before", "after"]


@dataclass(frozen=True)
class DocxLimits:
    max_input_bytes: int = 100 * 1024 * 1024
    max_output_bytes: int = 128 * 1024 * 1024
    max_entries: int = 3000
    max_uncompressed_bytes: int = 200 * 1024 * 1024
    max_part_bytes: int = 32 * 1024 * 1024
    max_compression_ratio: int = 1000
    max_paragraphs: int = 100_000
    max_patches: int = 10_000
    max_text_chars: int = 4_000_000

    def __post_init__(self) -> None:
        for item in fields(self):
            positive_int(getattr(self, item.name), item.name)


@dataclass(frozen=True)
class RunStyle:
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    font_family: str | None = None
    font_size: float | None = None
    style_id: str | None = None


@dataclass(frozen=True)
class RunSnapshot:
    start: int
    end: int
    text: str
    style: RunStyle


@dataclass(frozen=True)
class ParagraphSnapshot:
    id: str
    part: str
    role: PartRole
    index: int
    text: str
    runs: tuple[RunSnapshot, ...]
    is_body: bool
    table_id: str | None
    cell_id: str | None
    has_image: bool
    has_section_break: bool
    has_nested_paragraphs: bool
    has_fields: bool
    has_revisions: bool
    has_embedded_objects: bool
    style_id: str | None

    @property
    def in_table(self) -> bool:
        return self.cell_id is not None


@dataclass(frozen=True)
class BodyItem:
    index: int
    kind: Literal["paragraph", "table", "section", "other"]
    paragraph_id: str | None
    table_id: str | None
    text: str


@dataclass(frozen=True)
class CellSnapshot:
    id: str
    index: int
    text: str
    paragraph_ids: tuple[str, ...]
    grid_span: int
    vertical_merge: bool
    horizontal_merge: bool
    has_nested_tables: bool


@dataclass(frozen=True)
class RowSnapshot:
    id: str
    index: int
    cells: tuple[CellSnapshot, ...]
    text: str
    paragraph_ids: tuple[str, ...]
    has_merge: bool
    has_nested_tables: bool
    has_section_break: bool
    simple: bool


@dataclass(frozen=True)
class TableSnapshot:
    id: str
    part: str
    role: PartRole
    index: int
    grid_columns: int
    rows: tuple[RowSnapshot, ...]
    is_body: bool
    parent_cell_id: str | None


@dataclass(frozen=True)
class PackagePartInfo:
    name: str
    role: PartRole
    size: int
    sha256: str


@dataclass(frozen=True)
class DocxPackageInfo:
    sha256: str
    parts: tuple[PackagePartInfo, ...]
    has_macros: bool
    has_signatures: bool


@dataclass(frozen=True)
class ReplaceTextSpan:
    paragraph_id: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class SetParagraphText:
    paragraph_id: str
    text: str
    append: bool = False


@dataclass(frozen=True)
class InsertParagraph:
    anchor_id: str
    text: str
    position: Position = "before"


@dataclass(frozen=True)
class InsertTableRow:
    anchor_row_id: str
    text: str
    position: Position = "before"


@dataclass(frozen=True)
class SetTableRowText:
    row_id: str
    text: str


DocxPatch: TypeAlias = ReplaceTextSpan | SetParagraphText | InsertParagraph | InsertTableRow | SetTableRowText


@dataclass(frozen=True)
class DocxEditResult:
    output: Path
    sha256: str
    bytes_written: int
    changed_parts: tuple[str, ...]


class DocxPackage:
    """An owned package snapshot; each edit is a copy based on its original IDs/offsets."""

    def __init__(
        self,
        source: Source,
        *,
        limits: DocxLimits = DocxLimits(),
        allow_macros: bool = False,
        cancelled: Cancellation | None = None,
    ) -> None:
        from opendoc_formats.native.docx_package import NativePackage

        if not isinstance(limits, DocxLimits):
            raise TypeError("limits must be DocxLimits")
        if not isinstance(allow_macros, bool):
            raise TypeError("allow_macros must be bool")
        if cancelled is not None and not callable(cancelled):
            raise TypeError("cancelled must be callable")
        self._package = NativePackage(source, limits, allow_macros, cancelled)

    def __enter__(self) -> DocxPackage:
        self._package.check_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._package.close()

    @property
    def closed(self) -> bool:
        return self._package.closed

    @property
    def paragraphs(self) -> tuple[ParagraphSnapshot, ...]:
        self._package.check_open()
        return self._package.paragraphs

    @property
    def body(self) -> tuple[BodyItem, ...]:
        self._package.check_open()
        return self._package.body

    @property
    def tables(self) -> tuple[TableSnapshot, ...]:
        self._package.check_open()
        return self._package.tables

    @property
    def info(self) -> DocxPackageInfo:
        self._package.check_open()
        return self._package.info

    def to_bytes(self, patches: Sequence[DocxPatch] = ()) -> bytes:
        data, _ = self._package.edit(patches)
        return data

    def write(self, output: str | Path, patches: Sequence[DocxPatch] = ()) -> DocxEditResult:
        from hashlib import sha256

        data, changed = self._package.edit(patches)
        target = publish(data, output, self._package.limits.max_output_bytes, self._package.cancelled)
        return DocxEditResult(target, sha256(data).hexdigest(), len(data), changed)


__all__ = [
    "DocxPackage",
    "DocxLimits",
    "ParagraphSnapshot",
    "RunSnapshot",
    "RunStyle",
    "BodyItem",
    "TableSnapshot",
    "RowSnapshot",
    "CellSnapshot",
    "DocxPackageInfo",
    "PackagePartInfo",
    "DocxEditResult",
    "DocxPatch",
    "ReplaceTextSpan",
    "SetParagraphText",
    "InsertParagraph",
    "InsertTableRow",
    "SetTableRowText",
    "PartRole",
    "Position",
]
