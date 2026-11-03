"""Native picture viewport edits, preserving media, SVG companions and effects."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import opendoc_model as od
from lxml import etree

from opendoc_formats.ooxml.pptx_source_geometry import A, GeometryBinding, P
from opendoc_formats.support.cancellation import cancellable_items, checkpoint

R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
SVG = '{http://schemas.microsoft.com/office/drawing/2016/SVG/main}'
SIDES = ('left', 'top', 'right', 'bottom')


def read_crop(rectangle: Any) -> od.ImageCrop | None:
    if rectangle is None:
        return None
    values = []
    for side in ('l', 't', 'r', 'b'):
        value = rectangle.get(side, '0')
        if len(value) > 64 or re.fullmatch(r'[+-]?(?:[0-9]+|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)%)', value) is None:
            raise ValueError('Invalid DrawingML crop percentage')
        values.append(float(value[:-1])/100 if value.endswith('%') else int(value)/100000)
    return od.ImageCrop(*values)


def contained_crop(crop: od.ImageCrop | None) -> bool:
    return crop is None or (all(0 <= getattr(crop, side) <= 1 for side in SIDES)
                            and crop.left+crop.right < 1 and crop.top+crop.bottom < 1)


@dataclass
class CropBinding:
    geometry: GeometryBinding
    model: od.Image
    fill: Any
    rectangle: Any
    original: od.ImageCrop | None

    def mask(self) -> None:
        self.model.crop = deepcopy(self.original)


def bind_image_crop(native: GeometryBinding, model: od.Block, document: od.DocumentModel) -> CropBinding | None:
    if not isinstance(model, od.Image) or native.shape.tag != P+'pic':
        return None
    fills = native.shape.findall(P+'blipFill')
    if len(fills) != 1:
        return None
    fill = fills[0]
    blips, rectangles, stretches = (fill.findall(A+name) for name in ('blip', 'srcRect', 'stretch'))
    if len(blips) != 1 or len(rectangles) > 1 or len(stretches) != 1 or fill.find(A+'tile') is not None:
        return None
    fill_rectangles = stretches[0].findall(A+'fillRect')
    if len(stretches[0]) != 1 or len(fill_rectangles) != 1 or len(fill_rectangles[0]):
        return None
    fill_rectangle = fill_rectangles[0]
    if set(fill_rectangle.attrib)-{'l', 't', 'r', 'b'}:
        return None
    try:
        destination = read_crop(fill_rectangle)
        if any(getattr(destination, side) != 0 for side in SIDES):
            return None
    except ValueError:
        return None
    blip = blips[0]
    if blip.get(R+'link') is not None:
        return None
    companions = blip.findall('.//'+SVG+'svgBlip')
    if len(companions) > 1:
        return None
    graph = document.package
    if graph is None:
        return None
    for node in (blip, *companions):
        if node.get(R+'link') is not None:
            return None
        identity = node.get(R+'embed')
        if not identity:
            return None
        edges = [edge for edge in cancellable_items(graph.relationships) if edge.source == native.part and edge.id == identity]
        if len(edges) != 1 or edges[0].external or edges[0].relationship_type != R[1:-1]+'/image':
            return None
        part = graph.parts.get(edges[0].target)
        if part is None or not part.media_type.startswith('image/'):
            return None
    rectangle = rectangles[0] if rectangles else None
    if rectangle is not None and (len(rectangle) or set(rectangle.attrib)-{'l', 't', 'r', 'b'}):
        return None
    try:
        original = read_crop(rectangle)
    except ValueError:
        return None
    if not contained_crop(original):
        return None
    return CropBinding(native, model, fill, rectangle, original)


def project_image_crop(binding: CropBinding) -> bool:
    target = binding.model.crop
    if target == binding.original:
        return False
    checkpoint()
    if target is None:
        binding.fill.remove(binding.rectangle)
        return True
    values = [getattr(target, side) for side in SIDES]
    if any(type(value) not in (int, float) or not 0 <= value <= 1 for value in values):
        raise ValueError('Crop must use finite fractions between zero and one')
    units = [round(value * 100000) for value in values]
    if units[0]+units[2] >= 100000 or units[1]+units[3] >= 100000:
        raise ValueError('Rounded native crop removes the entire image')
    rectangle = binding.rectangle
    if rectangle is None:
        rectangle = etree.Element(A+'srcRect')
        binding.fill.insert(list(binding.fill).index(binding.fill.find(A+'blip'))+1, rectangle)
    for side, value in zip(('l', 't', 'r', 'b'), units, strict=True):
        rectangle.set(side, str(value))
    return True
