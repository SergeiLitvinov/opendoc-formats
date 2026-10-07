"""Bounded native PDF paths, separated from raster HTML resources."""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, replace
from typing import Any, Callable

from opendoc_model import Box, DocumentModel, Image, Paragraph, Provenance, ProvenanceEvent, Resource, Table
from opendoc_model.color import ColorValue
from opendoc_model.diagnostics import ConversionReport, IssueSeverity

MAX_VECTOR_COMMANDS = 50_000
_DASH_NUMBER = r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"


@dataclass(frozen=True)
class PdfVector:
    image: Image
    resource: Resource
    location: str


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1_000_000:
        raise ValueError("invalid or excessive vector coordinate")
    return float(value)


def _validate(image: Image, resource: Resource) -> None:
    if image.box is None or image.box.width < 0 or image.box.height < 0:
        raise ValueError("native vector requires a nonnegative placement Box")
    for value in (image.box.x, image.box.y, image.box.width, image.box.height):
        _number(value)
    props = resource.properties
    items = props.get("items")
    if not isinstance(items, (list, tuple)) or not items or len(items) > MAX_VECTOR_COMMANDS:
        raise ValueError("invalid or excessive vector command count")
    for command in items:
        if not isinstance(command, (list, tuple)) or not command:
            raise ValueError("invalid vector command")
        operator = command[0]
        lengths = {"l": 3, "c": 5, "re": 3, "qu": 2}
        if operator not in lengths or len(command) != lengths[operator]:
            raise ValueError(f"unsupported vector command: {operator!r}")
        if operator == "re":
            if len(command[1]) != 4 or command[2] not in (-1, 1):
                raise ValueError("invalid rectangle command")
            for number in command[1]:
                _number(number)
        else:
            points = command[1] if operator == "qu" else command[1:]
            if operator == "qu" and len(points) != 4:
                raise ValueError("invalid quad command")
            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) != 2:
                    raise ValueError("invalid vector point")
                for number in point:
                    _number(number)
    for name in ("fill_opacity", "stroke_opacity"):
        if not 0 <= _number(props.get(name, 1)) <= 1:
            raise ValueError("invalid vector opacity")
    if _number(props.get("width", 1)) < 0:
        raise ValueError("negative vector stroke width")
    for name in ("line_cap", "line_join"):
        if props.get(name, 0) not in (0, 1, 2):
            raise ValueError(f"invalid vector {name}")
    for name in ("even_odd", "close_path"):
        if type(props.get(name, False)) is not bool:
            raise ValueError(f"invalid vector {name}")
    dashes = props.get("dashes", "[] 0")
    if not isinstance(dashes, str) or len(dashes) > 8192:
        raise ValueError("excessive vector dash pattern")
    if not re.fullmatch(rf"\[(?:\s*{_DASH_NUMBER}\s*)*\]\s+{_DASH_NUMBER}", dashes):
        raise ValueError("unsupported vector dash pattern")
    dash_values = re.findall(_DASH_NUMBER, dashes)
    if len(dash_values) > 257:
        raise ValueError("excessive vector dash entries")
    for value in dash_values:
        _number(float(value))
    for name in ("fill", "stroke"):
        if props.get(name) is not None:
            color = ColorValue.from_dict(props[name])
            if color.blend_mode != "normal" or color.icc_profile is not None:
                raise ValueError("vector blend modes and ICC paint require a visual surrogate")
            color.to_srgb()
    if any(props.get(name) is not None for name in ("clip", "clip_path", "mask", "transform")):
        raise ValueError("vector clipping, masks and transforms require a visual surrogate")
    if "bbox" in props:
        bounds = props["bbox"]
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
            raise ValueError("invalid source vector bbox")
        x0, y0, x1, y1 = map(_number, bounds)
        if x1 < x0 or y1 < y0:
            raise ValueError("invalid source vector dimensions")
        scales = [target / source for target, source in ((image.box.width, x1 - x0), (image.box.height, y1 - y0)) if source]
        if ((x1 == x0 and image.box.width != 0) or (y1 == y0 and image.box.height != 0)
                or (len(scales) == 2 and not math.isclose(*scales, rel_tol=1e-6))):
            raise ValueError("nonuniform vector scaling requires a visual surrogate")


def prepare_vectors(
    document: DocumentModel, report: ConversionReport, cancelled: Callable[[], bool],
) -> tuple[DocumentModel, list[list[PdfVector]]]:
    """Remove supported fixed vectors from HTML, retaining the untouched source model."""
    count = 0
    all_vectors = []
    sections = []
    for section_index, section in enumerate(document.sections):
        vectors: list[PdfVector] = []

        def inline(image: Image, location: str) -> Image | None:
            nonlocal count
            resource = document.resources.get(image.resource_id)
            if resource is None or resource.media_type != "application/pdf+vector":
                return image
            if cancelled():
                report.add(IssueSeverity.ERROR, "cancelled", "PDF vector preparation cancelled", location)
                return image
            try:
                _validate(image, resource)
                count += len(resource.properties["items"])
                if count > MAX_VECTOR_COMMANDS:
                    raise ValueError("document vector command limit exceeded")
            except (ValueError, TypeError, KeyError) as error:
                surrogate = image.visual_surrogate
                replacement = document.resources.get(surrogate.resource_id) if surrogate else None
                raw = replacement.data if replacement is not None else None
                if replacement is not None and replacement.media_type == "image/png" and raw is not None:
                    if len(raw) < 24 or len(raw) > 32 * 1024 * 1024 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
                        report.add(IssueSeverity.ERROR, "pdf-vector-surrogate", "invalid PNG surrogate", location)
                        return image
                    width, height = struct.unpack(">II", raw[16:24])
                    if not width or not height or width > 8192 or height > 8192 or width * height > 16_000_000:
                        report.add(IssueSeverity.ERROR, "pdf-vector-surrogate", "PNG surrogate exceeds pixel limits", location)
                        return image
                    report.add(IssueSeverity.LOSS, "pdf-vector-surrogate", str(error), location)
                    provenance = image.provenance or Provenance(source_format=document.source_format or "pdf")
                    provenance = replace(provenance, events=[*provenance.events, ProvenanceEvent(
                        "export.pdf.vector-surrogate", detail=f"used {replacement.id}", fallback_reason=str(error),
                    )])
                    return replace(image, resource_id=replacement.id, provenance=provenance)
                report.add(IssueSeverity.ERROR, "pdf-vector-unsupported", str(error), location)
                return image
            vectors.append(PdfVector(image, resource, location))
            if any(name not in resource.properties for name in ("bbox", "width", "dashes", "line_cap", "line_join")):
                report.add(IssueSeverity.LOSS, "pdf-vector-style", "missing source bbox or stroke style; defaults used", location)
            return None

        def blocks(values: list, location: str) -> list:
            result = []
            for index, block in enumerate(values):
                path = f"{location}[{index}]"
                if isinstance(block, Image):
                    value = inline(block, path)
                    if value is not None:
                        result.append(value)
                elif isinstance(block, Paragraph):
                    content = []
                    for offset, item in enumerate(block.content):
                        value = inline(item, f"{path}.content[{offset}]") if isinstance(item, Image) else item
                        if value is not None:
                            content.append(value)
                    if content or not block.content:
                        result.append(replace(block, content=content))
                elif isinstance(block, Table):
                    rows = [replace(row, cells=[replace(cell, blocks=blocks(cell.blocks, f"{path}.rows[{r}].cells[{c}].blocks"))
                                                for c, cell in enumerate(row.cells)]) for r, row in enumerate(block.rows)]
                    result.append(replace(block, rows=rows))
                else:
                    result.append(block)
            return result

        sections.append(replace(section, **{name: blocks(getattr(section, name), f"sections[{section_index}].{name}")
                                            for name in ("blocks", "headers", "footers")}))
        all_vectors.append(vectors)
    report.metrics["pdf_vectors"] = {"native": sum(map(len, all_vectors)), "commands": count}
    return replace(document, sections=sections), all_vectors


def draw_vectors(page: Any, vectors: list[PdfVector], cancelled: Callable[[], bool]) -> None:
    import fitz

    for vector in vectors:
        props, box = vector.resource.properties, vector.image.box
        assert box is not None
        bounds = props.get("bbox", (box.x, box.y, box.x + box.width, box.y + box.height))
        source = Box(bounds[0], bounds[1], bounds[2] - bounds[0], bounds[3] - bounds[1])
        scale = box.width / source.width if source.width else box.height / source.height if source.height else 1

        def point(raw: Any) -> Any:
            return fitz.Point(box.x + (raw[0] - source.x) * scale, box.y + (raw[1] - source.y) * scale)

        shape = page.new_shape()
        for command in props["items"]:
            if cancelled():
                raise ValueError("PDF vector rendering cancelled")
            operator = command[0]
            if operator == "l":
                shape.draw_line(point(command[1]), point(command[2]))
            elif operator == "c":
                shape.draw_bezier(*(point(p) for p in command[1:]))
            elif operator == "qu":
                shape.draw_quad(fitz.Quad(*(point(p) for p in command[1])))
            else:
                x0, y0, x1, y1 = command[1]
                if command[2] == 1:
                    shape.draw_rect(fitz.Rect(point((x0, y0)), point((x1, y1))))
                    continue
                corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
                if command[2] == -1:
                    corners.reverse()
                shape.draw_polyline([point(p) for p in corners])
        colors = {name: tuple(ColorValue.from_dict(props[name]).to_srgb().components) if props.get(name) else None
                  for name in ("fill", "stroke")}
        shape.finish(color=colors["stroke"], fill=colors["fill"], width=props.get("width", 1) * scale,
                     fill_opacity=props.get("fill_opacity", 1), stroke_opacity=props.get("stroke_opacity", 1),
                     even_odd=props.get("even_odd", False), closePath=props.get("close_path", True),
                     dashes=re.sub(_DASH_NUMBER, lambda m: f"{float(m[0]) * scale:g}", props.get("dashes", "[] 0")),
                     lineCap=props.get("line_cap", 0), lineJoin=props.get("line_join", 0))
        shape.commit()
