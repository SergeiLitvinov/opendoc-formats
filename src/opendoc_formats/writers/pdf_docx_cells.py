"""Measured native PDF cell baselines after Word font resolution."""

from __future__ import annotations

from opendoc_model import (
    Box,
    DocumentLimits,
    DocumentModel,
    Paragraph,
    Table,
    TableCell,
    TextRun,
    WidthMeasure,
    get_borders,
    set_preferred_width,
    walk_model,
)

from opendoc_formats.fonts.word_metrics import word_line_ascent, word_line_descent


def prepare_cell_baselines(cell: TableCell) -> None:
    paragraphs = [block for block in cell.blocks if isinstance(block, Paragraph)
                  and block.properties.get('pdf_cell_native_line')]
    if not paragraphs:
        return
    metrics = []
    for paragraph in paragraphs:
        runs = [run for run in paragraph.content if isinstance(run, TextRun) and run.text]
        values = [(word_line_ascent(run.style), word_line_descent(run.style),
                   run.style.properties.get('docx_run_position_pt', 0)) for run in runs]
        if not values or any(ascent is None or descent is None for ascent, descent, _ in values):
            raise ValueError('PDF cell baseline has unresolved Word font metrics')
        metrics.append((max(ascent + shift for ascent, _, shift in values),
                        max(descent - shift for _, descent, shift in values)))
    box = cell.properties['pdf_cell_bbox']
    origins = [paragraph.properties['pdf_text_origin'] for paragraph in paragraphs]
    top, left = origins[0][1] - box[1] - metrics[0][0], origins[0][0] - box[0]
    borders = get_borders(cell)
    if borders and 'top' in borders.sides and borders.sides['top'].kind == 'line':
        top -= (borders.sides['top'].width_pt or 0) / 2
    if min(top, left) < -.025:
        raise ValueError('PDF text extends beyond the supported native cell inset')
    cell.properties['margins_twips'] = {**cell.properties.margins_twips, 'top': max(0, round(top * 20)),
                                       'left': max(0, round(left * 20))}
    for index, paragraph in enumerate(paragraphs):
        paragraph.properties['left_indent_pt'] = round((origins[index][0] - origins[0][0]) * 20) / 20
        if index + 1 < len(paragraphs):
            gap = origins[index + 1][1] - origins[index][1] - metrics[index][1] - metrics[index + 1][0]
            if gap < -.025:
                raise ValueError('PDF cell lines overlap outside the measured native Word flow profile')
            paragraph.properties['space_after_pt'] = max(0, round(gap * 20) / 20)


def fit_virtual_tables(document: DocumentModel, *, limits: DocumentLimits | None) -> None:
    """Virtual PDF text bands have no visible edges; fit their native text metrics."""
    if document.source_format != 'pdf':
        return
    for reference in walk_model(document, limits=limits):
        table = reference.node
        if (not isinstance(table, Table) or table.properties.get('pdf', {}).get('table_strategy') != 'text'
                or table.box is None):
            continue
        cells = [cell for row in table.rows for cell in row.cells]
        offsets, sizes = [], []
        for cell in cells:
            runs = [run for paragraph in cell.blocks if isinstance(paragraph, Paragraph)
                    for run in paragraph.content if isinstance(run, TextRun) and run.text]
            if not runs or not cell.properties.get('pdf_text_origin'):
                continue
            ascent = max(word_line_ascent(run.style) or 0 for run in runs)
            if not ascent:
                raise ValueError('Virtual PDF cell has unresolved Word font metrics')
            offsets.append(cell.properties['pdf_text_origin'][1] - cell.properties['pdf_cell_bbox'][1] - ascent)
            sizes.extend(run.style.font_size.pt for run in runs if run.style.font_size)
        shift = min([0, *offsets])
        padding = 2 * max(sizes, default=0)
        for cell in cells:
            box = cell.properties.get('pdf_cell_bbox')
            if box:
                cell.properties['pdf_cell_bbox'] = [box[0], box[1] + shift, box[2], box[3] + shift]
        for row in table.rows:
            if row.cells:
                cell = row.cells[-1]
                box = cell.properties['pdf_cell_bbox']
                box[2] += padding
                set_preferred_width(cell, WidthMeasure('absolute', box[2] - box[0], 'pt'))
        grid = list(table.properties.grid_widths_twips)
        if grid:
            grid[-1] += round(padding * 20)
            table.properties['grid_widths_twips'] = grid
        extra = 0
        for cell in table.rows[-1].cells:
            prepare_cell_baselines(cell)
            lines = [paragraph for paragraph in cell.blocks if isinstance(paragraph, Paragraph)
                     and paragraph.properties.get('pdf_text_origin')]
            if lines:
                runs = [run for run in lines[-1].content if isinstance(run, TextRun) and run.text]
                required = (lines[-1].properties['pdf_text_origin'][1] - cell.properties['pdf_cell_bbox'][1]
                            + max(word_line_descent(run.style) or 0 for run in runs))
                extra = max(extra, required - table.rows[-1].properties['docx_height_twips'] / 20)
        extra = max(0, round(extra * 20) / 20)
        table.rows[-1].properties['docx_height_twips'] += round(extra * 20)
        box = table.box
        table.box = Box(box.x, box.y + shift, box.width + padding, box.height + extra)
        set_preferred_width(table, WidthMeasure('absolute', table.box.width, 'pt'))
