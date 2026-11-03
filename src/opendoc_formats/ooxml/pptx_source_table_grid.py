"""Formats-owned source table dimensions, synchronized with native local extents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import opendoc_model as od

from opendoc_formats.ooxml.pptx_source_geometry import A, GeometryBinding, P
from opendoc_formats.ooxml.pptx_table_grid import merge_origins
from opendoc_formats.support.cancellation import cancellable_items, checkpoint


@dataclass
class TableGridBinding:
    geometry: GeometryBinding
    model: od.Table
    columns: list[Any]
    rows: list[Any]
    widths: list[int]
    heights: list[int]

    def mask(self) -> None:
        self.model.properties['column_widths_pt'] = [value / 12700 for value in self.widths]
        self.model.properties['grid_widths_twips'] = [max(1, round(value / 635)) for value in self.widths]
        for row, height in zip(self.model.rows, self.heights, strict=True):
            checkpoint()
            row.properties['height_pt'] = height / 12700


def bind_table_grid(geometry: GeometryBinding, model: od.Block) -> TableGridBinding | None:
    if not isinstance(model, od.Table) or geometry.shape.tag != P+'graphicFrame':
        return None
    if model.properties.get('opendoc_formats.pptx_table_grid', {}).get('layout') != 'logical-origins':
        return None
    data = geometry.shape.find(A+'graphic/'+A+'graphicData')
    if data is None or data.get('uri') != 'http://schemas.openxmlformats.org/drawingml/2006/table':
        return None
    table = data.find(A+'tbl')
    if table is None or merge_origins(table) is None:
        return None
    columns, rows = list(table.find(A+'tblGrid')), table.findall(A+'tr')
    if len(rows) != len(model.rows):
        return None
    if any(not isinstance(model.properties.get(key), list) or len(model.properties[key]) != len(columns)
           for key in ('column_widths_pt', 'grid_widths_twips')):
        return None
    if any('height_pt' not in row.properties for row in model.rows):
        return None
    extent = geometry.xfrm.find(A+'ext')
    try:
        widths = [int(column.get('w')) for column in cancellable_items(columns)]
        heights = [int(row.get('h')) for row in cancellable_items(rows)]
        if (any(value <= 0 for value in widths+heights) or sum(widths) != int(extent.get('cx'))
                or sum(heights) != int(extent.get('cy'))):
            return None
    except (TypeError, ValueError):
        return None
    return TableGridBinding(geometry, model, columns, rows, widths, heights)


def _values(values: list[Any], multiplier: int) -> list[int]:
    result = []
    for value in cancellable_items(values):
        if type(value) not in (int, float) or not 1 / multiplier <= value <= 2_147_483_647 / multiplier:
            raise ValueError('Table dimensions must be finite positive numbers within native resolution/profile')
        native = round(value * multiplier)
        if not 1 <= native <= 2_147_483_647:
            raise ValueError('Table dimensions exceed native integer resolution/profile')
        result.append(native)
    return result


def _dimension(original: list[int], requested: list[int], total: int) -> list[int]:
    if requested != original:
        if sum(requested) != total:
            raise ValueError('Explicit table dimensions must sum to the requested native local extent')
        return requested
    # Round cumulative boundaries so the final grid exactly equals the frame;
    # do not accumulate per-column errors or change the original proportions.
    cumulative, previous, result = 0, 0, []
    original_total = sum(original)
    for size in cancellable_items(original):
        cumulative += size
        boundary = (2 * cumulative * total + original_total) // (2 * original_total)
        result.append(boundary - previous)
        previous = boundary
    if any(value < 1 for value in result):
        raise ValueError('Scaled table dimensions are below native resolution')
    return result


def project_table_grid(binding: TableGridBinding) -> bool:
    """Apply explicit dimensions or proportional Box resizing without altering cell topology."""
    columns_pt = binding.model.properties['column_widths_pt']
    points = _values(columns_pt, 12700)
    twips_values = binding.model.properties['grid_widths_twips']
    twips = _values(twips_values, 635)
    if any(type(value) is not int for value in twips_values):
        raise ValueError('General table widths must use integer twips')
    source_twips = [max(1, round(value / 635)) for value in binding.widths]
    if twips_values != source_twips:
        if points != binding.widths and [max(1, round(value * 20)) for value in columns_pt] != twips_values:
            raise ValueError('Point and twip table dimensions disagree')
        if points == binding.widths:
            points = twips
    heights = _values([row.properties['height_pt'] for row in binding.model.rows], 12700)
    extent = binding.geometry.xfrm.find(A+'ext')
    widths = _dimension(binding.widths, points, int(extent.get('cx')))
    heights = _dimension(binding.heights, heights, int(extent.get('cy')))
    changed = widths != binding.widths or heights != binding.heights
    for column, value in zip(binding.columns, widths, strict=True):
        checkpoint()
        if int(column.get('w')) != value:
            column.set('w', str(value))
    for row, value in zip(binding.rows, heights, strict=True):
        checkpoint()
        if int(row.get('h')) != value:
            row.set('h', str(value))
    return changed
