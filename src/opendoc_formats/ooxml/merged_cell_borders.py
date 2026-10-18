"""Map whole merged-cell borders onto Word's physical continuation cells."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from opendoc_model import Border, BorderSet, IssueSeverity, TableCell, get_borders, set_borders

from opendoc_formats.ooxml.borders import export_borders, import_borders
from opendoc_formats.ooxml.widths import export_width


def export_merge_borders(target: Any, placements: list, report: Any, location: str) -> None:
    from docx.oxml.ns import qn

    for row, column, source in placements:
        if source.properties.get('docx_merge_borders_unsupported'):
            report.add(IssueSeverity.ERROR, 'docx.merge-borders', 'Native border segments require explicit resolution', location)
            continue
        borders = get_borders(source)
        if source.row_span < 2 or borders is None:
            continue
        for offset in range(source.row_span):
            cursor = 0
            native = None
            for cell in target._tbl.tr_lst[row + offset].tc_lst:
                if cursor == column:
                    native = cell
                    break
                span = cell.tcPr.find(qn('w:gridSpan')) if cell.tcPr is not None else None
                cursor += int(span.get(qn('w:val'))) if span is not None else 1
            if native is None:
                raise ValueError('Native merge continuation is missing')
            sides = dict(borders.sides)
            if offset:
                sides['top'] = Border(kind='none')
            if offset + 1 < source.row_span:
                sides['bottom'] = Border(kind='none')
            projected = TableCell()
            set_borders(projected, BorderSet(sides, extra=borders.extra))
            owner = native.get_or_add_tcPr()
            export_width(source, owner, 'w:tcW')
            export_borders(projected, owner, report, f'{location}.rows[{row + offset}].column[{column}]')


def import_merge_borders(origin: TableCell, owner: Any) -> None:
    from lxml import etree

    continuation = TableCell()
    import_borders(continuation, owner)
    original, extra = get_borders(origin), get_borders(continuation)
    if original is None and extra is None:
        return
    sides = dict(original.sides) if original else {}
    following = extra.sides if extra else {}

    def same(a: Border | None, b: Border | None) -> bool:
        return (replace(a, extra={}) if a else None) == (replace(b, extra={}) if b else None)

    if (any(not same(sides.get(side), following.get(side)) for side in ('left', 'right'))
            or following.get('top', Border(kind='none')).kind == 'line'):
        origin.properties['docx_merge_borders_unsupported'] = True
        origin.properties.setdefault('docx_merge_border_segments', []).append(etree.tostring(owner, encoding='unicode'))
    if 'bottom' in following:
        sides['bottom'] = following['bottom']
    set_borders(origin, BorderSet(sides, extra=original.extra if original else {}))
