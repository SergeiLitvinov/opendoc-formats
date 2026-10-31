"""Read SVG companions and cropping without flattening vector resources."""

from __future__ import annotations

from typing import Any

import opendoc_model as od
from opendoc_model.document_model import Image

from opendoc_formats.ooxml.pptx_crop import contained_crop, read_crop

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
SVG = "{http://schemas.microsoft.com/office/drawing/2016/SVG/main}"


def read_picture(element: Any, slide_part: Any, state: Any, box: od.Box | None) -> od.Image | None:
    fill = element.find(P + "blipFill")
    blip = fill.find(A + "blip") if fill is not None else None
    if blip is None:
        return None

    def resource(rid: str | None) -> str | None:
        if not rid:
            return None
        try:
            part = slide_part.related_part(rid)
        except (KeyError, ValueError):
            return None
        return state.add_image_resource(
            media_type=part.content_type, data=part.blob, filename=str(part.partname).rsplit("/", 1)[-1], object_id=rid
        )

    primary = resource(blip.get(R + "embed"))
    svg = blip.find(".//" + SVG + "svgBlip")
    vector = resource(svg.get(R + "embed")) if svg is not None else None
    if not (vector or primary):
        return None
    properties = {"fallback_resource_id": primary} if vector and primary else {}
    crop = fill.find(A + "srcRect")
    cropping = read_crop(crop)
    if not contained_crop(cropping):
        properties['opendoc_formats.pptx_source_rectangle'] = {'state': 'opaque', 'attributes': dict(crop.attrib)}
        if state.diagnostics:
            state.diagnostics.record(
                'pptx.image-crop', 'unrepresentable-source-rectangle',
                'Signed/outside source rectangle retained as native data; ImageCrop cannot represent it',
                element, state=od.PreservationState.OPAQUE,
            )
        cropping = None
    info = element.find(P + "nvPicPr/" + P + "cNvPr")
    return Image(
        resource_id=vector or primary,
        alt_text=info.get("descr", "") if info is not None else "",
        box=box,
        crop=cropping,
        properties=properties,
        provenance=state.origin(object_id=info.get("id") if info is not None else None),
    )
