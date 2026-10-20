"""Геометрический слой импорта PDF без семантических эвристик."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from statistics import median
from typing import Any, TypeAlias

from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.support.cancellation import check_cancelled

PdfBox: TypeAlias = tuple[float, float, float, float]


@dataclass(frozen=True)
class PdfSpanGeometry:
    text: str
    bbox: PdfBox
    origin: tuple[float, float]
    font: str = ""
    size: float = 0.0
    flags: int = 0
    color: int = 0
    ascender: float | None = None
    descender: float | None = None


@dataclass(frozen=True)
class PdfLineGeometry:
    spans: tuple[PdfSpanGeometry, ...]
    bbox: PdfBox
    direction: tuple[float, float] = (1.0, 0.0)
    writing_mode: int = 0
    quad: tuple[tuple[float, float], ...] = ()

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)


@dataclass(frozen=True)
class PdfTextBlockGeometry:
    lines: tuple[PdfLineGeometry, ...]
    bbox: PdfBox
    number: int

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text)


@dataclass(frozen=True)
class PdfImageGeometry:
    bbox: PdfBox
    number: int
    width: int = 0
    height: int = 0
    extension: str = ""
    colorspace: str = ""


@dataclass(frozen=True)
class PdfTableCellGeometry:
    row: int
    column: int
    text: str
    bbox: PdfBox | None = None


@dataclass(frozen=True)
class PdfTableGeometry:
    rows: tuple[tuple[str, ...], ...]
    cells: tuple[PdfTableCellGeometry, ...]
    bbox: PdfBox
    number: int
    strategy: str = "lines_strict"
    column_edges: tuple[float, ...] = ()
    row_edges: tuple[float, ...] = ()

    @property
    def text(self) -> str:
        return "\n".join(" | ".join(row) for row in self.rows)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return max((len(row) for row in self.rows), default=0)


@dataclass(frozen=True)
class PdfPageGeometry:
    number: int
    width: float
    height: float
    rotation: int = 0
    text_blocks: tuple[PdfTextBlockGeometry, ...] = ()
    image_blocks: tuple[PdfImageGeometry, ...] = ()
    tables: tuple[PdfTableGeometry, ...] = ()
    extracted_images: tuple[Any, ...] = ()
    vector_drawings: tuple[Any, ...] = ()


@dataclass
class PdfGeometryDocument:
    pages: list[PdfPageGeometry] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    engine: str = "pymupdf"
    warnings: list[str] = field(default_factory=list)


def extract_pdf_geometry(path: str | Path, *, exclude_interactions: bool = False,
                         cancelled: Callable[[], bool] | None = None) -> PdfGeometryDocument:
    """Извлечь координатную структуру PDF через PyMuPDF."""

    import fitz  # type: ignore[import-not-found]

    check_cancelled(cancelled, 'PDF geometry')
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    pages: list[PdfPageGeometry] = []
    from opendoc_formats.readers.pdf_content import content_only_pdf

    with (content_only_pdf(source, cancelled=cancelled) if exclude_interactions else fitz.open(str(source))) as document:
        metadata = {str(key): str(value or "") for key, value in (document.metadata or {}).items()}
        warnings: list[str] = []
        for page_index, page in enumerate(document):
            check_cancelled(cancelled, 'PDF geometry page')
            # Table analysis may mutate the backend page's crop/rotation temporarily.
            width, height, rotation = float(page.rect.width), float(page.rect.height), int(page.rotation)
            # Keep hidden glyphs as source content. The measured clip scope,
            # rather than destructive extraction, determines their visibility.
            raw = page.get_text("dict", sort=False, flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP,
                                clip=fitz.INFINITE_RECT()) or {}
            check_cancelled(cancelled, 'PDF native text extraction')
            text_blocks: list[PdfTextBlockGeometry] = []
            image_blocks: list[PdfImageGeometry] = []
            for block_index, block in enumerate(raw.get("blocks", [])):
                block_number = int(block.get("number", block_index))
                if block.get("type") == 0:
                    text_blocks.append(_text_block(block, block_number))
                elif block.get("type") == 1:
                    image_blocks.append(
                        PdfImageGeometry(
                            bbox=_box(block.get("bbox")),
                            number=block_number,
                            width=int(block.get("width", 0)),
                            height=int(block.get("height", 0)),
                            extension=str(block.get("ext", "")),
                            colorspace=str(block.get("cs-name", "")),
                        )
                    )
            tables = _find_tables(page, warnings, page_index + 1, cancelled=cancelled)
            check_cancelled(cancelled, 'PDF table analysis')
            pages.append(
                PdfPageGeometry(
                    number=page_index + 1,
                    width=width,
                    height=height,
                    rotation=rotation,
                    text_blocks=tuple(text_blocks),
                    image_blocks=tuple(image_blocks),
                    tables=tuple(tables),
                )
            )
    check_cancelled(cancelled, 'PDF geometry completion')
    return PdfGeometryDocument(pages=pages, metadata=metadata, warnings=warnings)


def _find_tables(page: Any, warnings: list[str], page_number: int, *,
                 cancelled: Callable[[], bool] | None = None) -> list[PdfTableGeometry]:
    for strategy in ("lines_strict", "text"):
        check_cancelled(cancelled, 'PDF table strategy')
        try:
            kwargs = {"strategy": strategy}
            if strategy == "text":
                kwargs.update({"min_words_vertical": 2, "min_words_horizontal": 2})
            finder = page.find_tables(**kwargs)
            words = page.get_text('words') if strategy == 'text' else ()
            tables = [
                _table_geometry(table, index, strategy)
                for index, table in enumerate(finder.tables)
                if _valid_table(table, strategy) and (strategy != 'text' or _text_table_keeps_words(table, words))
            ]
            if tables:
                return tables
        except OperationCancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - layout analysis is best-effort
            warnings.append(f"pymupdf tables page {page_number} ({strategy}): {type(error).__name__}: {error}")
    return []


def _text_table_keeps_words(table: Any, words: Any) -> bool:
    """Virtual text-table edges must not cut native words into different cells."""
    bands = []
    for row in table.rows:
        cells = [cell for cell in row.cells if cell is not None]
        if cells:
            bands.append((min(cell[1] for cell in cells), max(cell[3] for cell in cells),
                          sorted({coordinate for cell in cells for coordinate in (cell[0], cell[2])})))
    bands.sort(key=lambda band: band[0])
    starts = [band[0] for band in bands]
    for word in words:
        x0, y0, x1, y1 = word[:4]
        center = (y0 + y1) / 2
        index = bisect_right(starts, center) - 1
        if index < 0 or center > bands[index][1]:
            continue
        edges = bands[index][2][1:-1]
        edge = bisect_right(edges, x0 + .5)
        if edge < len(edges) and edges[edge] < x1 - .5:
            return False
    return True


def _valid_table(table: Any, strategy: str) -> bool:
    rows, row_indices, column_indices = _table_axes(table)
    if len(row_indices) < 2 or len(column_indices) < 2:
        return False
    cells = [rows[row][column].strip() for row in row_indices for column in column_indices]
    populated = sum(bool(value) for value in cells)
    if populated < 4 or populated / max(len(cells), 1) < 0.5:
        return False
    if strategy == "text":
        dense_rows = sum(sum(bool(rows[row][column]) for column in column_indices) >= 2 for row in row_indices)
        return (
            dense_rows >= 2
            and dense_rows / len(row_indices) >= 0.75
            and _text_table_has_regular_row_spacing(table, rows, row_indices, column_indices)
        )
    return True


def _text_table_has_regular_row_spacing(
    table: Any,
    rows: list[list[str]],
    row_indices: list[int],
    column_indices: list[int],
) -> bool:
    """Отсечь страницы, ошибочно собранные в безрамочную таблицу.

    Текстовая стратегия PyMuPDF продолжает виртуальные линии через всю страницу.
    Поэтому независимые шапка, абзац и подпись иногда выглядят как таблица. У
    настоящей таблицы вертикальные интервалы между заполненными строками остаются
    сопоставимыми с высотой самих строк.
    """

    bands: list[tuple[float, float]] = []
    for row_index in row_indices:
        source_row = table.rows[row_index]
        boxes = [
            source_row.cells[column_index]
            for column_index in column_indices
            if rows[row_index][column_index] and source_row.cells[column_index] is not None
        ]
        if boxes:
            bands.append((min(float(box[1]) for box in boxes), max(float(box[3]) for box in boxes)))
    if len(bands) < 2:
        return False
    heights = [max(end - start, 1.0) for start, end in bands]
    gaps = [max(next_start - end, 0.0) for (_, end), (next_start, _) in zip(bands, bands[1:], strict=False)]
    return max(gaps, default=0.0) <= max(36.0, median(heights) * 2.5)


def _table_geometry(table: Any, number: int, strategy: str) -> PdfTableGeometry:
    rows, row_indices, column_indices = _table_axes(table)
    if strategy == 'lines_strict':
        row_indices = list(range(len(rows)))
        column_indices = list(range(max(map(len, rows), default=0)))
    extracted = tuple(tuple(rows[row][column] for column in column_indices) for row in row_indices)
    cells: list[PdfTableCellGeometry] = []
    for row_index, source_row_index in enumerate(row_indices):
        source_row = table.rows[source_row_index]
        for column_index, source_column_index in enumerate(column_indices):
            bbox = source_row.cells[source_column_index]
            cells.append(
                PdfTableCellGeometry(
                    row=row_index,
                    column=column_index,
                    text=extracted[row_index][column_index],
                    bbox=_box(bbox) if bbox is not None else None,
                )
            )
    column_edges = tuple(sorted({float(box[index]) for row in table.rows for box in row.cells if box is not None
                                 for index in (0, 2)}))
    row_edges = tuple(sorted({float(box[index]) for row in table.rows for box in row.cells if box is not None
                              for index in (1, 3)}))
    if strategy == 'text' and cells:
        row_edges = tuple(min(cell.bbox[1] for cell in cells if cell.row == index and cell.bbox)
                          for index in range(len(row_indices))) + (max(cell.bbox[3] for cell in cells if cell.bbox),)
        cells = [replace(cell, bbox=(cell.bbox[0], row_edges[cell.row], cell.bbox[2], row_edges[cell.row + 1]))
                 if cell.bbox else cell for cell in cells]
    return PdfTableGeometry(
        rows=extracted,
        cells=tuple(cells),
        bbox=_box(table.bbox),
        number=number,
        strategy=strategy,
        column_edges=column_edges,
        row_edges=row_edges,
    )


def _table_axes(table: Any) -> tuple[list[list[str]], list[int], list[int]]:
    rows = [[str(value or "").strip() for value in row] for row in table.extract()]
    row_indices = [index for index, row in enumerate(rows) if any(row)]
    column_count = max((len(row) for row in rows), default=0)
    for row in rows:
        row.extend([""] * (column_count - len(row)))
    column_indices = [index for index in range(column_count) if any(rows[row][index] for row in row_indices)]
    return rows, row_indices, column_indices


def _text_block(block: dict[str, Any], number: int) -> PdfTextBlockGeometry:
    lines: list[PdfLineGeometry] = []
    for line in block.get("lines", []):
        spans = tuple(
            PdfSpanGeometry(
                text=str(span.get("text", "")),
                bbox=_box(span.get("bbox")),
                origin=_point(span.get("origin")),
                font=str(span.get("font", "")),
                size=float(span.get("size", 0.0)),
                flags=int(span.get("flags", 0)),
                color=int(span.get("color", 0)),
                ascender=_optional_float(span.get("ascender")),
                descender=_optional_float(span.get("descender")),
            )
            for span in line.get("spans", [])
        )
        lines.append(
            PdfLineGeometry(
                spans=spans,
                bbox=_box(line.get("bbox")),
                direction=_point(line.get("dir"), default=(1.0, 0.0)),
                writing_mode=int(line.get("wmode", 0)),
                quad=_line_quad(line),
            )
        )
    return PdfTextBlockGeometry(lines=tuple(lines), bbox=_box(block.get("bbox")), number=number)


def _line_quad(line: dict[str, Any]) -> tuple[tuple[float, float], ...]:
    if not line.get('spans') or _point(line.get('dir'), default=(1.0, 0.0)) == (1.0, 0.0):
        return ()
    import fitz

    quad = fitz.recover_line_quad(line)
    return tuple((float(point.x), float(point.y)) for point in (quad.ul, quad.ur, quad.ll, quad.lr))


def _box(value: Any) -> PdfBox:
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return tuple(float(item) for item in value)  # type: ignore[return-value]
    return (0.0, 0.0, 0.0, 0.0)


def _point(value: Any, *, default: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return float(value[0]), float(value[1])
    return default


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None


__all__ = [
    "PdfBox",
    "PdfGeometryDocument",
    "PdfImageGeometry",
    "PdfLineGeometry",
    "PdfPageGeometry",
    "PdfSpanGeometry",
    "PdfTableCellGeometry",
    "PdfTableGeometry",
    "PdfTextBlockGeometry",
    "extract_pdf_geometry",
]
