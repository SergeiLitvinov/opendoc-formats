"""Reserve inline image space and capture its actual Story page position."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from opendoc_model import ConversionReport, DocumentModel, Image, IssueSeverity, Paragraph, get_anchor
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
        return super()._paragraph(paragraph, location)

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
