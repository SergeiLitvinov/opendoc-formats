"""Measured PDF cell edges projected onto physical native Word cell borders."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from opendoc_model import ArtifactLimitError, Border, BorderSet, ColorValue, DocumentLimits, get_borders, set_borders

from opendoc_formats.support.cancellation import checkpoint

SIDES = ('top', 'left', 'bottom', 'right')
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MAX_BORDER_COMPARISONS = 1_000_000


def plan_cell_borders(matches: list, placements: list, *, limits: DocumentLimits | None = None) -> list:
    work, plan = 0, []
    for row, column, cell in placements:
        checkpoint()
        left, top, right, bottom = cell.properties['pdf_cell_bbox']
        edges = ((left, top, right, top), (left, top, left, bottom),
                 (left, bottom, right, bottom), (right, top, right, bottom))
        styles = {}
        for side, edge in zip(SIDES, edges):
            vertical = edge[0] == edge[2]
            axis, fixed = (1, 0) if vertical else (0, 1)
            pieces = []
            for segment, _image, _location, style, _expected in matches:
                checkpoint()
                work += 1
                if work > MAX_BORDER_COMPARISONS:
                    raise ArtifactLimitError('Flow cell-border matching work exceeded', path='table',
                                             quota='flow cell-border comparisons', maximum=MAX_BORDER_COMPARISONS)
                if ((segment[0] == segment[2]) != vertical or abs(segment[fixed]-edge[fixed]) > .0001):
                    continue
                start, end = max(edge[axis], segment[axis]), min(edge[axis+2], segment[axis+2])
                if start < end:
                    pieces.append((start, end, style))
            values = {piece[2] for piece in pieces}
            if len(values) != 1:
                raise ValueError('A logical cell side needs one complete native border style')
            cursor, discrepancy = edge[axis], 0.0
            for start, end, _style in sorted(pieces):
                checkpoint()
                discrepancy += abs(start-cursor)
                cursor = end
            if discrepancy+abs(cursor-edge[axis+2]) > .0001:
                raise ValueError('A logical cell side needs complete source stroke coverage')
            width, color = next(iter(values))
            styles[side] = {'width': width, 'color': color}
        expected = BorderSet({side: Border(kind='line', style='solid', width_pt=style['width'],
                                           color=ColorValue.from_hex(style['color'])) for side, style in styles.items()})
        declared = get_borders(cell, limits=limits)
        if declared is not None and declared != expected:
            raise ValueError('Edited cell borders need explicit source-grid reconciliation')
        set_borders(cell, expected, limits=limits)
        for offset in range(cell.row_span):
            checkpoint()
            physical = dict(styles)
            if offset:
                physical['top'] = None
            if offset+1 < cell.row_span:
                physical['bottom'] = None
            plan.append({'row': row+offset, 'column': column, 'styles': physical})
    return plan


def verify_cell_borders(table: ET.Element, plan: list) -> None:
    expected = {(cell['row'], cell['column']): cell['styles'] for cell in plan}
    actual = {}
    for row, native_row in enumerate(table.findall(W+'tr')):
        column = 0
        for cell in native_row.findall(W+'tc'):
            checkpoint()
            actual[row, column] = cell.find(W+'tcPr/'+W+'tcBorders')
            span = cell.find(W+'tcPr/'+W+'gridSpan')
            column += int(span.get(W+'val')) if span is not None else 1
    if actual.keys() != expected.keys():
        raise ValueError('Native Word cell-border topology changed')
    for key, styles in expected.items():
        checkpoint()
        borders = actual[key]
        if borders is None or len(borders) != 4 or {border.tag.removeprefix(W) for border in borders} != set(SIDES):
            raise ValueError('Native Word cell border roles changed')
        for border in borders:
            style = styles[border.tag.removeprefix(W)]
            attributes = ({W+'val': 'none'} if style is None else
                          {W+'val': 'single', W+'color': style['color'], W+'sz': str(round(style['width']*8))})
            if border.attrib != attributes:
                raise ValueError('Native Word cell border replacement changed stroke')
