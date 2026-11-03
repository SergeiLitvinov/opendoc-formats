"""Bounded projection of sparse Model spans onto a native Word table grid."""

from __future__ import annotations

from bisect import bisect_left

from opendoc_model import ArtifactLimitError, DocumentLimits, Table, TableCell

from opendoc_formats.support.cancellation import cancellable_items, checkpoint


def native_grid(table: Table, *, limits: DocumentLimits | None = None) -> tuple[int, list[tuple[int, int, TableCell]]]:
    budget = limits or DocumentLimits()
    active: dict[int, int] = {}
    result = []
    width = len(table.properties.grid_widths_twips)
    height = max(len(table.rows), 1)
    if max(width, 1) * height > budget.max_nodes:
        raise ArtifactLimitError('Native table grid exceeds selected node budget',
                                 path='table', quota='native table grid', maximum=budget.max_nodes)
    for row_index, row in enumerate(table.rows):
        checkpoint()
        active = {column: until for column, until in cancellable_items(active.items()) if until > row_index}
        blocked = sorted(active)
        column = 0
        for cell in row.cells:
            checkpoint()
            if row_index + cell.row_span > len(table.rows):
                raise ValueError('Native table row span exceeds the table')
            while True:
                checkpoint()
                end = column + cell.column_span
                if max(width, end) * height > budget.max_nodes:
                    raise ArtifactLimitError('Native table grid exceeds selected node budget',
                                             path='table', quota='native table grid', maximum=budget.max_nodes)
                index = bisect_left(blocked, column)
                if index == len(blocked) or blocked[index] >= end:
                    break
                column = blocked[index] + 1
            result.append((row_index, column, cell))
            if cell.row_span > 1:
                for index in range(column, end):
                    checkpoint()
                    active[index] = row_index + cell.row_span
            width = max(width, end)
            column = end
    return max(width, 1), result
