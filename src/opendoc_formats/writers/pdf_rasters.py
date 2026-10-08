"""Bounded native raster transforms and placement in PDF page and Story coordinates."""

from __future__ import annotations

import math
import re
import struct
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from opendoc_model import (
    ConversionReport,
    DocumentModel,
    Image,
    IssueSeverity,
    Paragraph,
    Resource,
    Table,
    get_anchor,
    iter_anchors,
)


@dataclass(frozen=True)
class PdfRaster:
    image: Image
    resource: Resource
    location: str
    rotation: int | None
    flow_id: str | None = None
    flow_alignment: str | None = None


def _rotation(image: Image) -> int | None:
    rotation = image.box.rotation if image.box else 0
    if not math.isfinite(rotation):
        raise ValueError("Invalid raster rotation")
    matrix = image.properties.get("pdf_image_transform")
    flipped = image.properties.get("flip_horizontal", False) or image.properties.get("flip_vertical", False)
    if matrix is None:
        if image.properties.get("placement") in ("inline", "anchor") or image.crop is not None or flipped or rotation:
            return None
        return 0
    if not isinstance(matrix, (list, tuple)) or len(matrix) != 6:
        raise ValueError("Invalid PDF raster transform")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in matrix):
        raise ValueError("Invalid PDF raster transform")
    a, b, c, d = matrix[:4]
    if max(abs(value) for value in matrix) > 1_000_000 or abs(a * d - b * c) < 1e-8:
        raise ValueError("Degenerate or excessive PDF raster transform")
    if flipped or rotation or image.crop is not None:
        return None

    def zero(value: float) -> bool:
        return abs(value) < 1e-6

    if zero(b) and zero(c):
        if a > 0 and d > 0:
            return 0
        if a < 0 and d < 0:
            return 180
    if zero(a) and zero(d):
        if b < 0 and c > 0:
            return 90
        if b > 0 and c < 0:
            return 270
    return None


def prepare_rasters(
    document: DocumentModel,
    report: ConversionReport,
    cancelled: Callable[[], bool],
) -> tuple[DocumentModel, list[list[PdfRaster]]]:
    placements = []
    sections = []
    count = 0
    anchors = {get_anchor(reference.node).id for reference in iter_anchors(document)}
    for section_index, section in enumerate(document.sections):
        rasters = []

        def image(value: Image, location: str, alignment: str | None = None) -> Image | None:
            nonlocal count
            resource = document.resources.get(value.resource_id)
            if value.box is None or resource is None or not resource.media_type.startswith("image/"):
                return value
            if cancelled():
                report.add(IssueSeverity.ERROR, "cancelled", "Raster preparation cancelled", location)
                return value
            try:
                box = value.box
                if (not all(math.isfinite(x) and abs(x) <= 1_000_000 for x in (box.x, box.y, box.width, box.height))
                        or box.width <= 0 or box.height <= 0):
                    raise ValueError("Invalid positioned raster box")
                if resource.data is None or len(resource.data) > 32 * 1024 * 1024:
                    raise ValueError("Raster data missing or exceeds 32 MiB")
                count += 1
                if count > 10000:
                    raise ValueError("Raster placement limit exceeded")
                for flag in ("flip_horizontal", "flip_vertical"):
                    if flag in value.properties and type(value.properties[flag]) is not bool:
                        raise ValueError("Raster reflection flags must be boolean")
                if resource.data.startswith(b"\x89PNG\r\n\x1a\n"):
                    if len(resource.data) < 24 or resource.data[12:16] != b"IHDR":
                        raise ValueError("Invalid PNG header")
                    width, height = struct.unpack(">II", resource.data[16:24])
                    if min(width, height) == 0 or width * height > 128_000_000 or max(width, height) > 32768:
                        raise ValueError("PNG pixel dimensions exceed limits")
                if value.crop is not None:
                    crop = value.crop
                    margins = (crop.left, crop.top, crop.right, crop.bottom)
                    if (not all(math.isfinite(item) and 0 <= item < 1 for item in margins)
                            or crop.left + crop.right > 1 - 1e-6 or crop.top + crop.bottom > 1 - 1e-6):
                        raise ValueError("Unsupported or empty raster crop")
                paragraph_anchor = (value.properties.get("placement") == "anchor"
                                    and value.properties.get("vertical_relative_from") == "paragraph"
                                    and value.properties.get("horizontal_relative_from") in ("column", "margin")
                                    and box.x == 0 and box.y == 0)
                in_flow = value.properties.get("placement") == "inline" or paragraph_anchor
                if in_flow:
                    angle = math.radians(box.rotation % 360)
                    flow_width = abs(box.width * math.cos(angle)) + abs(box.height * math.sin(angle))
                    flow_height = abs(box.width * math.sin(angle)) + abs(box.height * math.cos(angle))
                    available_width = section.page.width.pt - section.page.margin_left.pt - section.page.margin_right.pt
                    available_height = section.page.height.pt - section.page.margin_top.pt - section.page.margin_bottom.pt
                    if ".headers[" in location:
                        available_height = section.page.margin_top.pt * 0.85 - 4
                    elif ".footers[" in location:
                        available_height = section.page.margin_bottom.pt - 6
                    if flow_width > available_width or flow_height > available_height:
                        raise ValueError("Inline raster does not fit its declared page area")
                flow_id = f"opendoc-pdf-raster-{count}" if in_flow else None
                while flow_id is not None and flow_id in anchors:
                    flow_id += "-internal"
                flow_alignment = value.properties.get("horizontal_align", alignment) if paragraph_anchor else alignment
                rasters.append(PdfRaster(value, resource, location, _rotation(value), flow_id, flow_alignment))
                if paragraph_anchor:
                    report.add(IssueSeverity.LOSS, "pdf-raster-anchor-wrap",
                               "Paragraph anchor follows flow; original floating wrap and overlap rules are not reconstructed",
                               location)
                if (value.properties.get("opacity", 1) != 1 or value.properties.get("grayscale")
                        or any(value.properties.get(key) for key in ("shape_effects_xml", "line_xml", "stroke_color"))):
                    report.add(IssueSeverity.LOSS, "pdf-raster-effects", "DrawingML visual effects are not recreated", location)
            except (ValueError, TypeError) as error:
                report.add(IssueSeverity.ERROR, "pdf-raster-unsupported", str(error), location)
                return value
            if flow_id:
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
                        kept = image(item, f"{path}.content[{offset}]", block.alignment) if isinstance(item, Image) else item
                        if kept is not None:
                            content.append(kept)
                    if (any(isinstance(item, Image) and item.properties.get("placement") == "inline" for item in content)
                            and any(getattr(item, "text", "").strip() for item in content)):
                        report.add(IssueSeverity.LOSS, "pdf-inline-raster-layout",
                                   "Mixed text/image line layout follows Story rather than the original word processor", path)
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
        if any(r.flow_id is None for r in rasters) and any((prepared.blocks, prepared.headers, prepared.footers)):
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
        if raster.rotation is None:
            _draw_affine(page, raster)
            continue
        page.insert_image(
            fitz.Rect(box.x, box.y, box.x + box.width, box.y + box.height),
            stream=raster.resource.data,
            rotate=raster.rotation,
            keep_proportion=False,
        )


def _draw_affine(page: Any, raster: PdfRaster) -> None:
    """Replace only the backend's newly generated image placement stream."""
    import fitz

    box = raster.image.box
    assert box is not None
    source = raster.image.properties.get("pdf_image_transform")
    if source is not None:
        a, b, c, d, e, f = source
        xs, ys = (e, e + a, e + c, e + a + c), (f, f + b, f + d, f + b + d)
        x0, y0 = min(xs), min(ys)
        sx, sy = box.width / (max(xs) - x0), box.height / (max(ys) - y0)
        a, c, e = a * sx, c * sx, box.x + (e - x0) * sx
        b, d, f = b * sy, d * sy, box.y + (f - y0) * sy
        if box.rotation:
            angle = math.radians(box.rotation % 360)
            cosine, sine = math.cos(angle), math.sin(angle)
            center_x, center_y = box.x + box.width / 2, box.y + box.height / 2
            dx, dy = e - center_x, f - center_y
            a, b, c, d = a * cosine - b * sine, a * sine + b * cosine, c * cosine - d * sine, c * sine + d * cosine
            e, f = center_x + dx * cosine - dy * sine, center_y + dx * sine + dy * cosine
    else:
        angle = math.radians(box.rotation % 360)
        cosine, sine = math.cos(angle), math.sin(angle)
        a, b, c, d = box.width * cosine, box.width * sine, -box.height * sine, box.height * cosine
        e, f = box.x + (box.width - a - c) / 2, box.y + (box.height - b - d) / 2
    if raster.image.properties.get("flip_horizontal"):
        e, f, a, b = e + a, f + b, -a, -b
    if raster.image.properties.get("flip_vertical"):
        e, f, c, d = e + c, f + d, -c, -d
    clip = b""
    if raster.image.crop is not None:
        crop = raster.image.crop
        points = [(e, f), (e + a, f + b), (e + a + c, f + b + d), (e + c, f + d)]
        commands = [f"{_decimal(x)} {_decimal(page.rect.height - y)} {'m' if i == 0 else 'l'}"
                    for i, (x, y) in enumerate(points)]
        clip = ("\n".join(commands) + "\nh W n\n").encode("ascii")
        horizontal, vertical = 1 - crop.left - crop.right, 1 - crop.top - crop.bottom
        a, b, c, d = a / horizontal, b / horizontal, c / vertical, d / vertical
        e, f = e - a * crop.left - c * crop.top, f - b * crop.left - d * crop.top
    values = (a, -b, -c, d, e + c, page.rect.height - f - d)
    if not all(math.isfinite(value) and abs(value) <= 1_000_000 for value in values):
        raise ValueError("Excessive derived PDF raster transform")
    previous = set(page.get_contents())
    image_xref = page.insert_image(fitz.Rect(0, 0, 1, 1), stream=raster.resource.data, keep_proportion=False)
    candidates = []
    for stream in set(page.get_contents()) - previous:
        raw = page.parent.xref_stream(stream)
        names = re.findall(rb"/([A-Za-z0-9_]+)\s+Do\b", raw)
        if names:
            if len(raw) > 1024 or len(names) != 1:
                raise ValueError("Unexpected backend image placement stream")
            candidates.append((stream, names[0]))
    if len(candidates) != 1:
        raise ValueError("Cannot identify the newly generated image placement")
    stream, name = candidates[0]
    if not any(item[0] == image_xref and item[7].encode("ascii") == name for item in page.get_images()):
        raise ValueError("Backend image resource does not match placement")
    numbers = " ".join(_decimal(value) for value in values)
    page.parent.update_stream(stream, b"q\n" + clip + numbers.encode("ascii") + b" cm\n/" + name + b" Do\nQ\n")


def _decimal(value: float) -> str:
    return format(value, ".10f").rstrip("0").rstrip(".") or "0"
