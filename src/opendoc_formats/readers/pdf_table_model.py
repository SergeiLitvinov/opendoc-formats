"""Retain native PDF cell geometry and text styling in reconstructed Model tables."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from opendoc_model import DiagnosticIssue, IssueSeverity, Paragraph, PreservationRecord, Provenance, TableCell, TableRow, TextRun

from opendoc_formats.readers.pdf_diagnostics import append_pdf_warning
from opendoc_formats.readers.pdf_geometry import PdfPageGeometry, PdfTextBlockGeometry
from opendoc_formats.support.cancellation import check_cancelled


def pdf_table_rows(
    page: PdfPageGeometry, meta: dict[str, Any], run_builder: Callable[[Any, str, dict[str, Any]], list[TextRun]],
    warnings: list[str],
    *, diagnostics: list[PreservationRecord] | None = None, source_path: str = '', location: str = 'pdf.table',
    cancelled: Callable[[], bool] | None = None,
) -> list[TableRow]:
    table = next((table for table in page.tables if table.number == meta.get('source_table')), None)
    result = []
    column_count = max((len(row) for row in meta.get('rows', [])), default=0)
    rectangles = [cell.bbox for cell in table.cells if cell.bbox is not None] if table else []
    for row_index, values in enumerate(meta.get('rows', [])):
        check_cancelled(cancelled, 'PDF table row reconstruction')
        cells = []
        for column_index, value in enumerate(values):
            check_cancelled(cancelled, 'PDF table cell reconstruction')
            offset = row_index * column_count + column_index
            geometry = table.cells[offset] if table is not None and offset < len(table.cells) else None
            box = geometry.bbox if geometry is not None else None
            if box is None and table and table.column_edges and table.row_edges:
                x = (table.column_edges[column_index] + table.column_edges[column_index + 1]) / 2
                y = (table.row_edges[row_index] + table.row_edges[row_index + 1]) / 2
                if any(rect[0] < x < rect[2] and rect[1] < y < rect[3] for rect in rectangles):
                    continue  # Covered by a measured cell spanning this logical slot.
            lines = []
            if box is not None:
                x0, y0, x1, y1 = box
                for block in page.text_blocks:
                    check_cancelled(cancelled, 'PDF table text matching')
                    for line in block.lines:
                        spans = tuple(span for span in line.spans if x0 <= (span.bbox[0] + span.bbox[2]) / 2 <= x1
                                      and y0 <= (span.bbox[1] + span.bbox[3]) / 2 <= y1)
                        if spans:
                            lines.append(replace(line, spans=spans))
            lines.sort(key=lambda line: (line.bbox[1], line.bbox[0]))
            actual = '\n'.join(line.text for line in lines)
            properties: dict[str, Any] = {}
            if box is not None:
                properties['pdf_cell_bbox'] = list(box)
            if lines and actual.split() == str(value).split():
                properties['pdf_cell_rotated_text'] = any(line.direction != (1.0, 0.0) or line.writing_mode for line in lines)
                paragraphs = [Paragraph(content=run_builder(PdfTextBlockGeometry((line,), line.bbox, 0), line.text, {}),
                                        properties={'pdf_cell_native_line': True}) for line in lines]
                spans = [span for line in lines for span in line.spans]
                properties['pdf_text_bbox'] = [min(span.bbox[0] for span in spans), min(span.bbox[1] for span in spans),
                                               max(span.bbox[2] for span in spans), max(span.bbox[3] for span in spans)]
                properties['pdf_text_origin'] = list(spans[0].origin)
            else:
                paragraphs = [Paragraph(content=[TextRun(str(value))])]
                if str(value).strip():
                    properties['pdf_cell_layout_uncertain'] = True
                    append_pdf_warning(warnings, diagnostics, DiagnosticIssue(
                        'pdf.cell-layout-unresolved', IssueSeverity.LOSS,
                        f'PDF table cell layout unresolved: page {page.number}, row {row_index}, cell {column_index}',
                        f'{location}.rows[{row_index}].cells[{len(cells)}]',
                        {'source_table': meta.get('source_table'), 'source_row': row_index, 'source_column': column_index},
                        'pdf-cell-layout-unmeasured',
                    ), Provenance('pdf', source_path or None, page=page.number,
                                  object_id=f'table-{meta.get("source_table", "unknown")}-row-{row_index}-cell-{column_index}'))
            row_span = column_span = 1
            if box is not None and table and table.column_edges and table.row_edges:
                column_span = _edge_index(table.column_edges, box[2]) - _edge_index(table.column_edges, box[0])
                row_span = _edge_index(table.row_edges, box[3]) - _edge_index(table.row_edges, box[1])
            cells.append(TableCell(blocks=paragraphs, properties=properties,
                                   row_span=row_span, column_span=column_span))
        result.append(TableRow(cells=cells))
    return result


def _edge_index(edges: tuple[float, ...], value: float) -> int:
    for index, edge in enumerate(edges):
        if abs(edge - value) < .01:
            return index
    raise ValueError('PDF table cell does not align with measured table axes')
