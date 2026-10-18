"""Finite page-relative Word table placement and measured native row heights."""

from __future__ import annotations

import math
from typing import Any

from opendoc_model import Box, IssueSeverity, Table, get_borders

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MARKER = 'docx_page_table'


def _top_edge_offset(table: Table) -> float:
    borders = [get_borders(cell) for cell in table.rows[0].cells] if table.rows else []
    return max((border.sides['top'].width_pt or 0 for border in borders
                if border and 'top' in border.sides and border.sides['top'].kind == 'line'), default=0) / 2


def export_table_position(source: Table, target: Any, report: Any, location: str) -> None:
    if not source.properties.get(MARKER):
        return
    try:
        box = source.box
        if box is None or box.rotation or min(box.width, box.height) <= 0:
            raise ValueError('Positioned table requires a positive unrotated Box')
        if any(not math.isfinite(value) or abs(value * 20) >= 2**31 for value in (box.x, box.y)):
            raise ValueError('Table position exceeds native coordinates')
        from docx.oxml import OxmlElement

        owner = target._tbl.tblPr
        for old in owner.findall(W + 'tblpPr'):
            owner.remove(old)
        node = OxmlElement('w:tblpPr')
        inset = source.rows[0].cells[0].properties.margins_twips.get('left', 0) if source.rows and source.rows[0].cells else 0
        for key, value in {'horzAnchor': 'page', 'vertAnchor': 'page', 'tblpX': str(round(box.x * 20) + inset),
                           'tblpY': str(round((box.y - _top_edge_offset(source)) * 20)),
                           'leftFromText': '0', 'rightFromText': '0',
                           'topFromText': '0', 'bottomFromText': '0'}.items():
            node.set(W + key, value)
        owner.insert_element_before(node, 'w:tblOverlap', 'w:tblW', 'w:jc', 'w:tblCellSpacing', 'w:tblInd')
    except (ValueError, TypeError, OverflowError) as error:
        report.add(IssueSeverity.ERROR, 'docx.table-position', str(error), location)


def import_table_position(source: Any, target: Table) -> None:
    nodes = source._tbl.xpath('./w:tblPr/w:tblpPr')
    if not nodes:
        return
    node = nodes[0]
    try:
        if len(nodes) != 1 or node.get(W + 'horzAnchor') != 'page' or node.get(W + 'vertAnchor') != 'page':
            raise ValueError('Unsupported table anchors')
        x, y = int(node.get(W + 'tblpX', '')), int(node.get(W + 'tblpY', ''))
        if target.rows and target.rows[0].cells:
            x -= target.rows[0].cells[0].properties.margins_twips.get('left', 0)
        width = sum(target.properties.grid_widths_twips)
        heights = [row.properties.get('docx_height_twips') for row in target.rows]
        if not width or not heights or any(type(value) is not int or value <= 0 for value in heights):
            raise ValueError('Positioned table height or width remains unknown')
        target.box = Box(x / 20, round((y / 20 + _top_edge_offset(target)) * 20) / 20, width / 20, sum(heights) / 20)
        target.properties[MARKER] = True
    except (ValueError, TypeError):
        target.properties['docx_table_position_unsupported'] = True
