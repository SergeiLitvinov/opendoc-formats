"""Bounded visual projection of common table borders to static CSS."""

from __future__ import annotations

from opendoc_model import Border, ConversionReport, IssueSeverity, Table, get_borders


def _css(border: Border, report: ConversionReport, location: str) -> str:
    if border.kind in {'none', 'nil'}:
        return '0 none'
    style = border.style
    if style not in {'solid', 'dashed', 'dotted', 'double'}:
        report.add(IssueSeverity.LOSS, 'html-border-style', 'Unknown or compound dash style uses a dashed fallback', location)
        style = 'dashed'
    width = border.width_pt
    if width is None:
        report.add(IssueSeverity.LOSS, 'html-border-width', 'Unknown width uses the CSS medium default', location)
        size = 'medium'
    elif width > 10_000:
        report.add(IssueSeverity.ERROR, 'html-border-width', 'Border width exceeds the CSS profile', location)
        size = '0'
    else:
        size = f'{width:g}pt'
    color = border.color
    if color is None:
        report.add(IssueSeverity.LOSS, 'html-border-color', 'Unknown border color uses currentColor', location)
        paint = 'currentColor'
    else:
        paint = color.to_css()
        if color.icc_profile or color.blend_mode != 'normal':
            report.add(IssueSeverity.LOSS, 'html-border-color', 'Border color effects are flattened to sRGB', location)
    if border.offset_pt:
        report.add(IssueSeverity.LOSS, 'html-border-offset', 'Per-side native offsets have no CSS border equivalent', location)
    return f'{size} {style} {paint}'


def table_border_styles(table: Table, report: ConversionReport, location: str) -> tuple[list[str], dict[int, list[str]]]:
    """Place separators at logical cell starts; direct cell declarations override them."""
    record = get_borders(table)
    if record is None and not any(get_borders(cell) for row in table.rows for cell in row.cells):
        return [], {}
    styles = ['border:0', 'border-collapse:separate', 'border-spacing:0']
    outer = {'top', 'right', 'bottom', 'left'}
    if record is not None:
        for side, border in record.sides.items():
            if side in outer:
                styles.append(f'border-{side}:{_css(border, report, location + ".borders." + side)}')
    cells = {}
    occupied: list[tuple[int, int, int]] = []
    work = 0
    for row_index, row in enumerate(table.rows):
        occupied = [interval for interval in occupied if interval[2] > row_index]
        column = 0
        for cell_index, cell in enumerate(row.cells):
            cell_location = f'{location}.rows[{row_index}].cells[{cell_index}]'
            while True:
                blocking = None
                for first, last, _ in occupied:
                    work += 1
                    if work > 100_000:
                        report.add(IssueSeverity.ERROR, 'html-border-grid', 'Table grid work exceeds 100000', cell_location)
                        return styles, cells
                    if first < column + cell.column_span and column < last:
                        blocking = last
                        break
                if blocking is None:
                    break
                column = blocking
            end = column + cell.column_span
            if end > 10_000 or row_index + cell.row_span > len(table.rows):
                report.add(IssueSeverity.ERROR, 'html-border-grid', 'Table spans exceed the CSS grid profile', cell_location)
                return styles, cells
            direct = get_borders(cell)
            declarations: dict[str, Border] = {}
            if record is not None:
                if row_index and 'inside-horizontal' in record.sides:
                    declarations['top'] = record.sides['inside-horizontal']
                if column and 'inside-vertical' in record.sides:
                    declarations['left'] = record.sides['inside-vertical']
            if direct is not None:
                for side, border in direct.sides.items():
                    if side in outer:
                        declarations[side] = border
                    else:
                        report.add(IssueSeverity.LOSS, 'html-border-diagonal',
                                   'Diagonal cell borders are outside the CSS profile',
                                   cell_location + '.borders.' + side)
            if record is not None or direct is not None:
                cells[id(cell)] = ['border:0', *(f'border-{side}:{_css(border, report, cell_location + ".borders." + side)}'
                                               for side, border in declarations.items())]
            occupied.append((column, end, row_index + cell.row_span))
            column = end
    return styles, cells
