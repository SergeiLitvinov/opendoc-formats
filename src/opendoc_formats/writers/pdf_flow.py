"""Reserve inline image space and capture its actual Story page position."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from opendoc_model import ConversionReport, DocumentModel, Image, IssueSeverity, Paragraph, Table, get_anchor
from opendoc_model.limits import DocumentLimits

from opendoc_formats.writers.html_writer import _HtmlRenderer


class PdfFlowRenderer(_HtmlRenderer):
    def __init__(
        self, document: DocumentModel, report: ConversionReport, flow_ids: dict[str, str], mapping: Any = None,
        *, limits: DocumentLimits | None = None,
    ) -> None:
        super().__init__(document, report, limits=limits)
        self.flow_ids = flow_ids
        self.mapping = mapping
        self.limits = limits
        self.table_grids: dict[int, dict[int, float]] = {}
        self.flow_paragraphs: dict[str, list[str]] = {}
        self.flow_tables: dict[str, list[str]] = {}
        for location, token in flow_ids.items():
            if '.rows[' in location:
                self.flow_tables.setdefault(location.split('.rows[', 1)[0], []).append(token)
            elif '.content[' in location:
                self.flow_paragraphs.setdefault(location.rsplit('.content[', 1)[0], []).append(token)

    def _table(self, table: Table, location: str, *, caption: str | None = None) -> str:
        rendered = super()._table(table, location, caption=caption)
        if location in self.flow_tables:
            self.report.add(IssueSeverity.LOSS, 'pdf-table-flow-layout',
                            'Raster sizes and source column proportions guide flow; native table row splitting '
                            'and exact source pagination are not reproduced', location)
        # A cell cannot be moved independently of its row/span topology. Retry
        # only at the containing outer table, including nested table images.
        return ''.join(f'<!--{token}-break-->' for token in self.flow_tables.get(location, ())) + rendered

    def _table_cell_styles(self, table: Table, row: int, cell: int) -> list[str]:
        if id(table) not in self.table_grids:
            from opendoc_formats.ooxml.table_grid import native_grid

            widths = list(table.properties.grid_widths_twips)
            columns, placements = native_grid(table, limits=self.limits)
            valid = len(widths) == columns and all(type(width) is int and width > 0 for width in widths)
            self.table_grids[id(table)] = ({id(value): 100*sum(widths[column:column+value.column_span])/sum(widths)
                                            for _row, column, value in placements} if valid else {})
        width = self.table_grids[id(table)].get(id(table.rows[row].cells[cell]))
        return [f'width:{width:.10f}%'] if width is not None else []

    def _paragraph(self, paragraph: Paragraph, location: str) -> str:
        if paragraph.box is not None and paragraph.provenance is not None and paragraph.provenance.source_format == 'pdf':
            # Extracted glyph bounds are observations, not a layout constraint for a substituted font.
            paragraph = replace(paragraph, box=None)
            self.report.add(
                IssueSeverity.LOSS,
                'pdf-text-layout', 'Source PDF text is reflowed; original glyph bounds are not reproduced', location,
            )
        anchor = get_anchor(paragraph)
        if anchor is not None:
            paragraph = replace(paragraph, properties={**paragraph.properties, "anchor_id": anchor.id})
        rendered = super()._paragraph(paragraph, location)
        return ''.join(f'<!--{token}-break-->' for token in self.flow_paragraphs.get(location, ())) + rendered

    def _image(self, image: Image, location: str, *, block_level: bool) -> str:
        token = self.flow_ids.get(location)
        if not token:
            rendered = super()._image(image, location, block_level=block_level)
            resource = self.document.resources.get(image.resource_id)
            if self.mapping is not None and resource is not None:
                from opendoc_formats.writers.html_resources import image_data_uri

                temporary = self.mapping.story_resource(image, location, resource)
                if temporary is not resource:
                    rendered = rendered.replace(f'src="{image_data_uri(resource)}"',
                                                f'src="{image_data_uri(temporary)}"', 1)
            return rendered
        box = image.box
        assert box is not None
        angle = math.radians(box.rotation % 360)
        width = abs(box.width * math.cos(angle)) + abs(box.height * math.sin(angle))
        height = abs(box.width * math.sin(angle)) + abs(box.height * math.cos(angle))
        return (
            f'<span id="{token}-frame" style="display:inline-block;line-height:0;font-size:0;width:100%;height:{height:.10f}pt">'
            f'<span id="{token}" style="display:inline-block;line-height:0;font-size:0;'
            f'width:{width:.10f}pt;height:{height:.10f}pt"> </span></span>'
        )


def record_position(positions: dict[tuple[str, int], tuple[float, ...]], position: Any) -> None:
    token = position.id
    if not token or not token.startswith("opendoc-pdf-raster-") or not position.open_close & 2:
        return
    key = token, position.page_num - 1
    current = tuple(position.rect)
    if key in positions and positions[key] != current:
        raise ValueError("Inline raster placeholder spans multiple pages")
    positions[key] = current


def next_flow_break(
    html: str, positions: dict[tuple[str, int], tuple[float, ...]], bottom: float,
    forced: set[str],
) -> tuple[str, str] | None:
    """Move the first overflowing raster's body paragraph/table, never resize its frame.

    Story can report completion with an inline-block below its placement rectangle.
    Only private markers before complete body paragraphs/tables permit a bounded
    retry. A cell is never detached; running content retains its rejection policy.
    """
    candidates = []
    for (token, _page), rectangle in positions.items():
        if token.endswith('-frame') or rectangle[3] <= bottom + .01:
            continue
        marker = f'<!--{token}-break-->'
        offset = html.find(marker)
        if offset >= 0:
            candidates.append((offset, token, marker))
    if not candidates:
        return None
    _, token, marker = min(candidates)
    if token in forced:
        raise ValueError('Inline raster paragraph/table still overflows after a page break')
    return html.replace(marker, marker + '<div style="page-break-before:always"></div>', 1), token
