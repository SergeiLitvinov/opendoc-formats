"""Editable table cells, including paragraph structure and explicit cell appearance."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import opendoc_model as od
from opendoc_model.document_model import Paragraph, Table, TableCell, TableRow

from opendoc_formats.ooxml.pptx_table_grid import merge_origins
from opendoc_formats.readers.pptx_paragraph import frame_metadata, paragraph_metadata
from opendoc_formats.support.cancellation import cancellable_items, checkpoint

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def read_table(
    element: Any,
    box: od.Box | None,
    slide_part: Any,
    theme_colors: dict[str, str],
    parse_runs: Callable[..., None],
    resolve_color: Callable[..., Any],
    alignments: dict[str, str],
) -> od.Table:
    rows = []
    for row_index, row in enumerate(element.findall(A + "tr")):
        checkpoint()
        cells = []
        for column_index, cell in enumerate(row.findall(A + "tc")):
            checkpoint()
            blocks = []
            for paragraph in cell.findall(A + "txBody/" + A + "p"):
                checkpoint()
                content = []
                parse_runs(paragraph, content, slide_part, theme_colors=theme_colors)
                meta = paragraph_metadata(paragraph, alignments)
                blocks.append(
                    Paragraph(
                        content,
                        alignment=meta.get("alignment"),
                        properties={
                            "pptx": {
                                "paragraphs": [meta],
                                "text_frame": frame_metadata(cell.find(A + "txBody")),
                            }
                        },
                    )
                )
            settings = _cell_settings(cell.find(A + "tcPr"), theme_colors, resolve_color)
            settings['opendoc_formats.pptx_cell'] = {'row': row_index, 'column': column_index}
            cells.append(TableCell(blocks, int(cell.get("rowSpan", "1")), int(cell.get("gridSpan", "1")), settings))
        rows.append(TableRow(cells, {"height_pt": float(row.get("h", "0")) / 12700}))
    properties = {}
    grid = element.find(A + "tblGrid")
    if grid is not None:
        properties["column_widths_pt"] = [float(column.get("w", "0")) / 12700 for column in cancellable_items(grid)]
        if all(width > 0 for width in properties['column_widths_pt']):
            properties['grid_widths_twips'] = [max(1, round(width * 20)) for width in properties['column_widths_pt']]
    origins = merge_origins(element)
    hidden = origins is not None and any(
        (ri, ci) not in origins and any(
            not isinstance(run, od.TextRun) or run.text or run.link
            for block in cell.blocks if isinstance(block, Paragraph) for run in block.content
        ) for ri, row in enumerate(rows) for ci, cell in enumerate(row.cells)
    )
    if origins is None or hidden:
        properties['opendoc_formats.pptx_table_grid'] = {
            'version': 1, 'layout': 'physical-unverified',
            'reason': 'hidden-continuation-content' if hidden else 'unproved-merge-topology',
        }
    else:
        owners = {}
        for ri, ci in cancellable_items(sorted(origins)):
            cell = rows[ri].cells[ci]
            for y in range(ri, ri + cell.row_span):
                for x in range(ci, ci + cell.column_span):
                    checkpoint()
                    owners[y, x] = ri, ci
        continuations = []
        for ri, row in enumerate(cancellable_items(rows)):
            logical = []
            for ci, cell in enumerate(cancellable_items(row.cells)):
                if (ri, ci) in origins:
                    logical.append(cell)
                else:
                    owner = owners[ri, ci]
                    continuations.append({
                        'row': ri, 'column': ci, 'owner_row': owner[0], 'owner_column': owner[1],
                        'properties': dict(cell.properties),
                    })
            row.cells = logical
        properties['opendoc_formats.pptx_table_grid'] = {'version': 1, 'layout': 'logical-origins'}
        if continuations:
            properties['opendoc_formats.pptx_continuations'] = continuations
    return Table(rows, box=box, properties=properties)


def _cell_settings(properties: dict[str, Any], colors: dict[str, str], resolve: Callable[..., Any]) -> dict[str, Any]:
    if properties is None:
        return {}
    result = {}
    for key, side in (("marL", "left"), ("marR", "right"), ("marT", "top"), ("marB", "bottom")):
        checkpoint()
        if properties.get(key) is not None:
            result.setdefault("margins_twips", {})[side] = round(float(properties.get(key)) / 635)
    if properties.get("anchor") is not None:
        result["vertical_alignment"] = {"t": "top", "ctr": "center", "b": "bottom"}.get(properties.get("anchor"))
    fill = properties.find(A + "solidFill")
    if fill is not None:
        color, _ = resolve(fill, colors)
        if color:
            result["fill"] = color.to_hex()
            result["fill_color"] = color.to_dict()
    elif properties.find(A + "noFill") is not None:
        result["fill"] = "none"
    borders = {}
    for tag in ("lnL", "lnR", "lnT", "lnB", "lnTlToBr", "lnBlToTr"):
        checkpoint()
        line = properties.find(A + tag)
        if line is None:
            continue
        border = {"width_pt": float(line.get("w", "12700")) / 12700}
        if line.find(A + "noFill") is not None:
            border["none"] = True
        solid = line.find(A + "solidFill")
        if solid is not None:
            color, _ = resolve(solid, colors)
            if color:
                border["color"] = color.to_dict()
        dash = line.find(A + "prstDash")
        if dash is not None:
            border["dash"] = dash.get("val")
        borders[tag] = border
    if borders:
        result["pptx_borders"] = borders
    return result
