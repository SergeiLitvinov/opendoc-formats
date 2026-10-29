"""Validate physical DrawingML table merge ownership before semantic projection."""

from __future__ import annotations

from typing import Any

from opendoc_formats.support.cancellation import cancellable_items, checkpoint

A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'


def merge_origins(table: Any) -> set[tuple[int, int]] | None:
    rows = [row.findall(A+'tc') for row in table.findall(A+'tr')]
    grid = table.find(A+'tblGrid')
    if grid is None or not rows or not len(grid) or any(len(row) != len(grid) for row in rows):
        return None
    owners: dict[tuple[int, int], tuple[int, int]] = {}
    origins = set()
    for ri, row in enumerate(cancellable_items(rows)):
        for ci, cell in enumerate(cancellable_items(row)):
            flags = [cell.get(name, '0') for name in ('hMerge', 'vMerge')]
            if any(flag not in {'0', '1', 'false', 'true'} for flag in flags):
                return None
            if any(flag in {'1', 'true'} for flag in flags):
                continue
            try:
                height, width = int(cell.get('rowSpan', '1')), int(cell.get('gridSpan', '1'))
            except ValueError:
                return None
            if height < 1 or width < 1 or ri+height > len(rows) or ci+width > len(grid):
                return None
            origins.add((ri, ci))
            for y in range(ri, ri+height):
                for x in range(ci, ci+width):
                    checkpoint()
                    if (y, x) in owners:
                        return None
                    owners[y, x] = ri, ci
    for ri, row in enumerate(cancellable_items(rows)):
        for ci, cell in enumerate(cancellable_items(row)):
            owner = owners.get((ri, ci))
            if owner is None:
                return None
            if ((cell.get('hMerge', '0') in {'1', 'true'}) != (ci > owner[1])
                    or (cell.get('vMerge', '0') in {'1', 'true'}) != (ri > owner[0])):
                return None
    return origins

