"""Семантическая интерпретация геометрического слоя PDF."""

from __future__ import annotations

from collections.abc import Callable

from opendoc_formats.readers.pdf_classify import classify_text_block, repeated_margin_roles
from opendoc_formats.readers.pdf_geometry import PdfGeometryDocument, PdfTableGeometry, PdfTextBlockGeometry
from opendoc_formats.readers.pdf_layout import analyze_reading_order
from opendoc_formats.support.cancellation import check_cancelled
from opendoc_formats.support.text_diagnostics import ledger
from opendoc_formats.types import Block, BlockType, DocFormat, Table, Text


def analyze_pdf_geometry(document: PdfGeometryDocument, *, cancelled: Callable[[], bool] | None = None) -> Text:
    """Преобразовать координатные блоки в совместимый семантический ``Text``."""

    blocks: list[Block] = []
    tables: list[Table] = []
    plain_parts: list[str] = []
    check_cancelled(cancelled, 'PDF semantic analysis')
    margin_roles = repeated_margin_roles(document)
    for page in document.pages:
        check_cancelled(cancelled, 'PDF semantic page')
        text_blocks = [block for block in page.text_blocks if not _covered_by_table(block, page.tables, cancelled=cancelled)]
        layout = analyze_reading_order([*text_blocks, *page.tables], page.width)
        for reading_index, ordered_block in enumerate(layout.blocks):
            check_cancelled(cancelled, 'PDF semantic block')
            source = ordered_block.block
            text = source.text
            if not text:
                continue
            meta = {
                "bbox": list(source.bbox),
                "reading_order": reading_index,
                "column": ordered_block.column,
                "column_count": layout.column_count,
                "spanning": ordered_block.spanning,
                "gutter": list(layout.gutter) if layout.gutter is not None else None,
                "page_width": page.width,
                "page_height": page.height,
            }
            if isinstance(source, PdfTableGeometry):
                rows = [list(row) for row in source.rows]
                meta.update(
                    {
                        "rows": rows,
                        "table_index": len(tables),
                        "source_table": source.number,
                        "row_count": source.row_count,
                        "column_count_table": source.column_count,
                        "table_strategy": source.strategy,
                        "cell_bboxes": [list(cell.bbox) if cell.bbox is not None else None for cell in source.cells],
                    }
                )
                blocks.append(Block(type=BlockType.TABLE, text=text, page=page.number, meta=meta))
                tables.append(Table(rows=rows, page=page.number))
            else:
                meta["source_block"] = source.number
                classification = classify_text_block(
                    source,
                    page,
                    repeated_role=margin_roles.get((page.number, source.number)),
                )
                meta.update(
                    {
                        "semantic_role": classification.role,
                        "semantic_confidence": classification.confidence,
                        "semantic_evidence": list(classification.evidence),
                    }
                )
                if classification.role in {"header", "footer"}:
                    meta["excluded_from_plain"] = True
                blocks.append(Block(type=classification.block_type, text=text, page=page.number, meta=meta))
            if not blocks[-1].meta.get("excluded_from_plain"):
                plain_parts.append(text)
    check_cancelled(cancelled, 'PDF semantic analysis completion')
    return Text(
        blocks=blocks,
        tables=tables,
        plain="\n".join(plain_parts),
        source_format=DocFormat.PDF,
        engine=document.engine,
        pages=len(document.pages),
        warnings=list(document.warnings),
        diagnostics=ledger(tuple(document.diagnostics)) if document.diagnostics else None,
    )


def _covered_by_table(block: PdfTextBlockGeometry, tables: tuple[PdfTableGeometry, ...], *,
                      cancelled: Callable[[], bool] | None = None) -> bool:
    check_cancelled(cancelled, 'PDF semantic table matching')
    x0, y0, x1, y1 = block.bbox
    block_area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if block_area == 0:
        return False
    for table in tables:
        check_cancelled(cancelled, 'PDF semantic table matching')
        tx0, ty0, tx1, ty1 = table.bbox
        intersection = max(0.0, min(x1, tx1) - max(x0, tx0)) * max(0.0, min(y1, ty1) - max(y0, ty0))
        if intersection / block_area >= 0.5:
            return True
    return False


__all__ = ["analyze_pdf_geometry"]
