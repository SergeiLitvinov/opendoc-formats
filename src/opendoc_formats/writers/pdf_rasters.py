"""Place bounded raster images in page coordinates, without HTML flow layout."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from opendoc_model import ConversionReport, DocumentModel, Image, IssueSeverity, Paragraph, Resource, Table


@dataclass(frozen=True)
class PdfRaster:
    image: Image
    resource: Resource
    location: str
    rotation: int


def _rotation(image: Image) -> int:
    rotation = image.box.rotation if image.box else 0
    if not math.isfinite(rotation) or rotation % 90:
        raise ValueError("Only quarter-turn raster rotations are supported")
    rotation = int(rotation) % 360
    matrix = image.properties.get("pdf_image_transform")
    if matrix is None:
        return rotation
    if not isinstance(matrix, (list, tuple)) or len(matrix) != 6:
        raise ValueError("Invalid PDF raster transform")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in matrix):
        raise ValueError("Invalid PDF raster transform")
    a, b, c, d = matrix[:4]

    def zero(value: float) -> bool:
        return abs(value) < 1e-6

    if zero(b) and zero(c):
        if a > 0 and d > 0:
            return rotation
        if a < 0 and d < 0:
            return (180 + rotation) % 360
    if zero(a) and zero(d):
        if b < 0 and c > 0:
            return (90 + rotation) % 360
        if b > 0 and c < 0:
            return (270 + rotation) % 360
    raise ValueError("Raster shear/reflection/arbitrary rotation requires a separate profile")


def prepare_rasters(
    document: DocumentModel,
    report: ConversionReport,
    cancelled: Callable[[], bool],
) -> tuple[DocumentModel, list[list[PdfRaster]]]:
    placements = []
    sections = []
    count = 0
    for section_index, section in enumerate(document.sections):
        rasters = []

        def image(value: Image, location: str) -> Image | None:
            nonlocal count
            resource = document.resources.get(value.resource_id)
            if value.box is None or resource is None or not resource.media_type.startswith("image/"):
                return value
            if cancelled():
                report.add(IssueSeverity.ERROR, "cancelled", "Raster preparation cancelled", location)
                return value
            try:
                box = value.box
                if not all(math.isfinite(x) for x in (box.x, box.y, box.width, box.height)) or box.width <= 0 or box.height <= 0:
                    raise ValueError("Invalid positioned raster box")
                if resource.data is None or len(resource.data) > 32 * 1024 * 1024:
                    raise ValueError("Raster data missing or exceeds 32 MiB")
                count += 1
                if count > 10000:
                    raise ValueError("Raster placement limit exceeded")
                rasters.append(PdfRaster(value, resource, location, _rotation(value)))
            except (ValueError, TypeError) as error:
                report.add(IssueSeverity.ERROR, "pdf-raster-unsupported", str(error), location)
                return value
            return None

        def blocks(values: list, location: str) -> list:
            result = []
            for index, block in enumerate(values):
                path = f"{location}[{index}]"
                if isinstance(block, Image):
                    item = image(block, path)
                    if item is not None:
                        result.append(item)
                elif isinstance(block, Paragraph):
                    content = []
                    for offset, item in enumerate(block.content):
                        kept = image(item, f"{path}.content[{offset}]") if isinstance(item, Image) else item
                        if kept is not None:
                            content.append(kept)
                    if content or not block.content:
                        result.append(replace(block, content=content))
                elif isinstance(block, Table):
                    rows = [
                        replace(
                            row,
                            cells=[
                                replace(
                                    cell,
                                    blocks=blocks(
                                        cell.blocks,
                                        f"{path}.rows[{r}].cells[{c}].blocks",
                                    ),
                                )
                                for c, cell in enumerate(row.cells)
                            ],
                        )
                        for r, row in enumerate(block.rows)
                    ]
                    result.append(replace(block, rows=rows))
                else:
                    result.append(block)
            return result

        prepared = replace(
            section,
            **{
                name: blocks(getattr(section, name), f"sections[{section_index}].{name}")
                for name in ("blocks", "headers", "footers")
            },
        )
        if rasters and any((prepared.blocks, prepared.headers, prepared.footers)):
            report.add(
                IssueSeverity.LOSS,
                "pdf-raster-compositing",
                "Rasters overlay flow content; source paint order is not reconstructed",
                f"sections[{section_index}]",
            )
        placements.append(rasters)
        sections.append(prepared)
    report.metrics["pdf_rasters"] = {"native": count}
    return replace(document, sections=sections), placements


def draw_rasters(page: Any, rasters: list[PdfRaster], cancelled: Callable[[], bool]) -> None:
    import fitz

    for raster in rasters:
        if cancelled():
            raise ValueError("PDF raster rendering cancelled")
        box = raster.image.box
        assert box is not None
        page.insert_image(
            fitz.Rect(box.x, box.y, box.x + box.width, box.y + box.height),
            stream=raster.resource.data,
            rotate=raster.rotation,
            keep_proportion=False,
        )
