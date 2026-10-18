"""Extract raster images and vector drawings from PDF pages.

Provides:
- ``ExtractedPdfImage`` — actual pixel data from PDF page resources.
- ``PdfVectorDrawing`` — vector path commands (fills, strokes, clipping).
- ``extract_pdf_images()`` — per-page list of extracted images.
- ``extract_pdf_vector_drawings()`` — per-page list of vector drawings.
- ``enrich_geometry_with_images()`` — merge extracted data into a
  ``PdfGeometryDocument`` for downstream consumers (OCR merge, PDF→DOCX).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opendoc_model import ArtifactLimitError, ImageCrop
from opendoc_model.color import ColorValue

from opendoc_formats.readers.pdf_geometry import (
    PdfBox,
    PdfGeometryDocument,
    PdfPageGeometry,
)


@dataclass(frozen=True)
class ExtractedPdfImage:
    """Raster image with actual pixel data extracted from PDF."""

    bbox: PdfBox
    number: int
    width: int
    height: int
    extension: str
    colorspace: str
    data: bytes
    xref: int
    page: int
    smask_xref: int = 0
    transform: tuple[float, ...] = ()
    crop: ImageCrop | None = None
    paint_seq: int | None = None
    graphics_state_unknown: bool = False

    @property
    def media_type(self) -> str:
        ext = self.extension.lower()
        if ext in ("jpg", "jpeg"):
            return "image/jpeg"
        if ext == "png":
            return "image/png"
        if ext in ("tif", "tiff"):
            return "image/tiff"
        if ext == "gif":
            return "image/gif"
        if ext == "bmp":
            return "image/bmp"
        if ext == "jp2":
            return "image/jp2"
        return f"image/{ext}"


@dataclass(frozen=True)
class PdfVectorDrawing:
    """One vector drawing element from a PDF page.

    Each drawing corresponds to a group in PyMuPDF's ``page.get_drawings()``.
    The ``items`` tuple stores path operators and JSON-compatible coordinate tuples.
    """

    bbox: PdfBox
    number: int
    page: int
    items: tuple[tuple[Any, ...], ...] = ()
    fill: ColorValue | None = None
    stroke: ColorValue | None = None
    width: float = 0.0
    fill_opacity: float = 1.0
    stroke_opacity: float = 1.0
    even_odd: bool = False
    close_path: bool = True
    dashes: str = ""
    line_join: int = 0
    line_cap: int = 0
    clip_rects: tuple[PdfBox, ...] = ()
    graphics_state_unsupported: bool = False
    paint_seq: int | None = None
    neutral_page_group_only: bool = False

    @property
    def is_path(self) -> bool:
        return bool(self.items)


def _to_int(value: object) -> int:
    """Convert value to int, handling PyMuPDF tuples like (0, 0, 0)."""
    if value is None:
        return 0
    if isinstance(value, (list, tuple)):
        return int(value[0]) if value else 0
    return int(value)  # type: ignore[arg-type]


def _pdf_drawing_color(value: object, *, alpha: float) -> ColorValue | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        return ColorValue.from_srgb_components(*(float(component) for component in value), alpha=alpha)
    except (TypeError, ValueError):
        return None


def extract_pdf_images(path: str | Path) -> tuple[list[ExtractedPdfImage], list[str]]:
    """Extract all raster image pixel data from a PDF.

    Uses PyMuPDF's ``page.get_images()`` + ``document.extract_image()`` to
    retrieve the actual bytes of every image embedded in the PDF.  Returns
    a flat list of ``ExtractedPdfImage`` sorted by (page, number).

    Every painted occurrence is retained, including repeated xrefs and inline images.
    """
    import fitz

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)

    images: list[ExtractedPdfImage] = []
    warnings: list[str] = []

    with fitz.open(str(source)) as document:
        for page_number, page in enumerate(document, start=1):
            # Match get_image_info's TextPage flags: whitespace filtering can renumber blocks.
            page_dict = page.get_text("dict", sort=False, flags=fitz.TEXT_PRESERVE_IMAGES,
                                      clip=fitz.INFINITE_RECT()) or {}
            image_blocks = [block for block in page_dict.get("blocks", []) if block.get("type") == 1]
            infos = {item["number"]: item for item in page.get_image_info(xrefs=True)}
            from opendoc_formats.readers.pdf_image_clips import clipped_image_placement, image_clip_profiles

            clips = image_clip_profiles(page)
            graphics = page.get_drawings(extended=True)
            clip_count = sum(draw.get('type') == 'clip' for draw in graphics)
            unknown_group = any(draw.get('type') == 'group' and not _neutral_page_group(page, draw)
                                for draw in graphics)
            masks = {int(item[0]): int(item[1]) for item in page.get_images(full=True)}
            paint_images = [(index, box) for index, (kind, box) in enumerate(page.get_bboxlog()) if kind == 'fill-image']
            for block_index, block in enumerate(image_blocks):
                from opendoc_formats.errors import ResourceLimitError

                width, height = int(block.get("width", 0)), int(block.get("height", 0))
                if width * height > 128_000_000 or max(width, height) > 32768 or len(images) >= 10000:
                    raise ResourceLimitError("PDF raster exceeds pixel or placement limits")
                block_number = int(block.get("number", block_index))
                info = infos.get(block_number, {})
                original_box = info.get('bbox', block.get('bbox', ()))
                matches = [(index, box) for index, box in paint_images
                           if len(original_box) == 4 and max(abs(a - b) for a, b in zip(original_box, box)) < .02]
                paint_seq = matches[0][0] if matches else None
                if matches:
                    paint_images.remove(matches[0])
                clipped = clipped_image_placement(info, clips)
                xref = int(info.get("xref", 0)) or -(block_number + 1)
                data = block.get("image", b"")
                if len(data) > 32 * 1024 * 1024:
                    raise ResourceLimitError("PDF raster exceeds 32 MiB")
                if not data:
                    warnings.append(f"page {page_number} image {block_number}: missing image bytes")
                    continue
                extension = str(block.get("ext", "png"))
                if block.get("mask"):
                    from opendoc_formats.readers.pdf_image_alpha import straight_alpha_png

                    data = straight_alpha_png(data, block['mask'])
                    extension = "png"
                if len(data) > 32 * 1024 * 1024:
                    raise ResourceLimitError("PDF raster with mask exceeds 32 MiB")
                images.append(ExtractedPdfImage(
                    bbox=clipped[0] if clipped else info.get("bbox", block.get("bbox", (0.0, 0.0, 0.0, 0.0))),
                    number=block_number,
                    width=int(block.get("width", 0)), height=int(block.get("height", 0)),
                    extension=extension, colorspace=str(block.get("colorspace", "")),
                    data=data, xref=xref, page=page_number, smask_xref=masks.get(xref, 0),
                    transform=clipped[1] if clipped else tuple(block.get("transform", ())),
                    crop=clipped[2] if clipped else None,
                    paint_seq=paint_seq,
                    graphics_state_unknown=unknown_group or bool(clip_count and not (clipped and clip_count == 1)),
                ))

    images.sort(key=lambda img: (img.page, img.number))
    return images, warnings


def extract_pdf_vector_drawings(path: str | Path) -> tuple[list[PdfVectorDrawing], list[str]]:
    """Extract vector drawing commands from a PDF.

    Uses PyMuPDF's ``page.get_drawings()`` to retrieve vector paths,
    fills, strokes, and clipping regions.  Returns a flat list of
    ``PdfVectorDrawing`` sorted by (page, number).
    """
    from opendoc_formats.readers.pdf_content import content_only_pdf

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)

    drawings: list[PdfVectorDrawing] = []
    warnings: list[str] = []

    with content_only_pdf(source) as document:
        for page_number, page in enumerate(document, start=1):
            try:
                raw = page.get_drawings(extended=True)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"page {page_number} get_drawings: {type(exc).__name__}: {exc}")
                continue

            states = []
            draw_index = 0
            for draw in raw:
                level = draw.get("level", 0)
                while states and states[-1][0] >= level:
                    states.pop()
                if draw.get("type") in {"clip", "group"}:
                    commands = draw.get("items", [])
                    rectangle = (
                        tuple(float(value) for value in commands[0][1])
                        if draw["type"] == "clip" and len(commands) == 1 and commands[0][0] == "re" else None
                    )
                    root_group = not states and _neutral_page_group(page, draw)
                    states.append((level, rectangle, rectangle is None and not root_group))
                    if len(states) > 64:
                        raise ArtifactLimitError(f"PDF graphics state nesting exceeds 64 on page {page_number}")
                    continue
                draw_index += 1
                rect = draw.get("rect")
                bbox = (
                    (
                        float(rect.x0),
                        float(rect.y0),
                        float(rect.x1),
                        float(rect.y1),
                    )
                    if rect
                    else (0.0, 0.0, 0.0, 0.0)
                )

                items = tuple(_drawing_value(command) for command in draw.get("items", []))
                fill_opacity = float(1.0 if draw.get("fill_opacity") is None else draw["fill_opacity"])
                stroke_opacity = float(1.0 if draw.get("stroke_opacity") is None else draw["stroke_opacity"])
                fill_color = _pdf_drawing_color(draw.get("fill"), alpha=fill_opacity)
                stroke_color = _pdf_drawing_color(draw.get("stroke") or draw.get("color"), alpha=stroke_opacity)

                drawings.append(
                    PdfVectorDrawing(
                        bbox=bbox,
                        number=draw_index,
                        page=page_number,
                        items=items,
                        fill=fill_color,
                        stroke=stroke_color,
                        width=float(draw.get("width", 0.0) or 0.0),
                        fill_opacity=fill_opacity,
                        stroke_opacity=stroke_opacity,
                        even_odd=bool(draw.get("even_odd", False)),
                        close_path=bool(draw.get("closePath", True)),
                        dashes=str(draw.get("dashes") or "[] 0"),
                        line_join=_to_int(draw.get("lineJoin", 0)),
                        line_cap=_to_int(draw.get("lineCap", 0)),
                        clip_rects=tuple(rectangle for _, rectangle, _ in states if rectangle is not None),
                        graphics_state_unsupported=any(rectangle is None for _, rectangle, _ in states),
                        neutral_page_group_only=(any(rectangle is None for _, rectangle, _ in states)
                                                 and not any(unsupported for _, _, unsupported in states)),
                        paint_seq=draw.get('seqno'),
                    )
                )

    return drawings, warnings


def _neutral_page_group(page: Any, draw: dict) -> bool:
    return bool(draw.get('type') == 'group' and draw.get('level') == 0
                and draw.get('isolated') is True and not draw.get('knockout')
                and draw.get('blendmode') == 'Normal' and draw.get('opacity') == 1
                and draw.get('rect') is not None
                and max(abs(a - b) for a, b in zip(draw['rect'],
                                                  (0, 0, page.cropbox.width, page.cropbox.height))) < .001)


def _drawing_value(value: Any) -> Any:
    """Keep path operators and coordinates independent of PyMuPDF objects."""
    import fitz

    if isinstance(value, (list, tuple, fitz.Point, fitz.Rect, fitz.Quad)):
        return tuple(_drawing_value(part) for part in value)
    return value


def enrich_geometry_with_images(
    geometry: PdfGeometryDocument,
    images: list[ExtractedPdfImage] | None = None,
    vector_drawings: list[PdfVectorDrawing] | None = None,
) -> PdfGeometryDocument:
    """Merge extracted images and vector drawings into a geometry document.

    This is a convenience function that enriches each ``PdfPageGeometry``
    in the document with the supplied extracted images and vector drawings,
    grouped by page number.
    """
    if not images and not vector_drawings:
        return geometry

    images_by_page: dict[int, list[ExtractedPdfImage]] = {}
    if images:
        for img in images:
            images_by_page.setdefault(img.page, []).append(img)

    vectors_by_page: dict[int, list[PdfVectorDrawing]] = {}
    if vector_drawings:
        for v in vector_drawings:
            vectors_by_page.setdefault(v.page, []).append(v)

    enriched_pages: list[PdfPageGeometry] = []
    for page in geometry.pages:
        pn = page.number
        page_images = tuple(images_by_page.get(pn, []))
        page_vectors = tuple(vectors_by_page.get(pn, []))
        enriched_pages.append(
            PdfPageGeometry(
                number=page.number,
                width=page.width,
                height=page.height,
                rotation=page.rotation,
                text_blocks=page.text_blocks,
                image_blocks=page.image_blocks,
                tables=page.tables,
                extracted_images=page_images,
                vector_drawings=page_vectors,
            )
        )

    return PdfGeometryDocument(
        pages=enriched_pages,
        metadata=geometry.metadata,
        engine=geometry.engine,
        warnings=geometry.warnings,
    )


__all__ = [
    "ExtractedPdfImage",
    "PdfVectorDrawing",
    "enrich_geometry_with_images",
    "extract_pdf_images",
    "extract_pdf_vector_drawings",
]
