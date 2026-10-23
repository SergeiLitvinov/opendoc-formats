"""Finite editable DrawingML rectangle groups, using official Model scene types."""

from __future__ import annotations

import math
from xml.etree import ElementTree as ET

from opendoc_model import AffineTransform, Box, ColorSpace, VectorPath, VectorScene

from opendoc_formats.support.cancellation import cancellable_items, checkpoint

SVG = 'http://www.w3.org/2000/svg'


def axis_transform(value: AffineTransform) -> tuple[float, float, float, float]:
    if value.b or value.c or value.a <= 0 or value.d <= 0:
        raise ValueError('Native group requires a positive axis-aligned transform')
    return value.a, value.d, value.e, value.f


def paint_style(path: VectorPath) -> tuple[str, float]:
    paint = path.fill
    if paint is None or path.stroke is not None:
        raise ValueError('Native group profile requires filled rectangles without strokes')
    color = paint.color
    if color.space is not ColorSpace.SRGB or color.icc_profile is not None or color.blend_mode != 'normal':
        raise ValueError('Native shape color needs a verified RGB declaration without a profile/blend')
    rgb = [round(c*255) for c in color.components]
    alpha = color.alpha*paint.opacity
    if (any(abs(c*255-i) > .00001 for c, i in zip(color.components, rgb, strict=True))
            or abs(alpha*100_000-round(alpha*100_000)) > .00001):
        raise ValueError('Native shape color/alpha would require quantization')
    return ''.join(f'{c:02X}' for c in rgb), alpha


def rectangle(path: VectorPath) -> Box:
    commands = path.commands
    if ([c.operation for c in commands] != ['move', 'line', 'line', 'line', 'close']
            or path.clip_id is not None or path.mask_resource_id is not None):
        raise ValueError('Native group profile requires unclipped rectangle paths')
    points = [c.values for c in commands[:-1]]
    x0, x1 = min(p[0] for p in points), max(p[0] for p in points)
    y0, y1 = min(p[1] for p in points), max(p[1] for p in points)
    if (x0 >= x1 or y0 >= y1 or set(points) != {(x0, y0), (x0, y1), (x1, y0), (x1, y1)}
            or any(a[0] != b[0] and a[1] != b[1] for a, b in zip(points, points[1:]+points[:1]))):
        raise ValueError('Native group path is not an axis-aligned rectangle')
    if path.transform != AffineTransform():
        raise ValueError('Edited path transform requires an explicit geometry projection')
    return Box(x0, y0, x1-x0, y1-y0)


def scene_profile(scene: VectorScene) -> dict[str, Box]:
    if scene.scope_version != 1 or scene.occurrences or scene.clips:
        raise ValueError('Native group profile requires a bound vector-only scope without clips/masks')
    paths = {p.id: p for p in cancellable_items(scene.paths)}
    groups = {g.id: g for g in cancellable_items(scene.groups)}
    boxes = {}
    backgrounds = [p for p in cancellable_items(scene.paths) if p.extra.get('docx_canvas_background')]
    if len(backgrounds) > 1 or (backgrounds and (
        not scene.roots or scene.roots[0] != backgrounds[0].id
        or rectangle(backgrounds[0]) != Box(0, 0, scene.width, scene.height)
    )):
        raise ValueError('Native canvas background requires its full viewport and first paint position')

    def visit(key: str) -> Box:
        checkpoint()
        if key in boxes:
            return boxes[key]
        if key in paths:
            paint_style(paths[key])
            box = rectangle(paths[key])
        else:
            group = groups[key]
            if any(child in groups for child in cancellable_items(group.children)):
                raise ValueError('Nested native groups require independent Word editing acceptance, not only XML retention')
            value = group.compositing
            if group.clip_id is not None or group.mask_resource_id is not None:
                raise ValueError('Native Word group has no verified editable clip/mask')
            if (value is None or value.opacity != 1 or value.isolated is not False
                    or value.knockout is not False or value.blend_mode != 'normal'):
                raise ValueError('Native Word group opacity/isolation/blend needs a verified vector output; effects rasterize')
            space = value.color_space
            if space is None or space.space != 'rgb' or space.profile_resource_id is not None:
                raise ValueError('Native Word group requires the explicit RGB composition profile')
            if not group.children:
                raise ValueError('Empty editable native groups are outside the verified profile')
            children = [visit(child) for child in cancellable_items(group.children)]
            x0, y0 = min(b.x for b in children), min(b.y for b in children)
            x1, y1 = max(b.x+b.width for b in children), max(b.y+b.height for b in children)
            sx, sy, tx, ty = axis_transform(group.transform)
            box = Box(x0*sx+tx, y0*sy+ty, (x1-x0)*sx, (y1-y0)*sy)
        boxes[key] = box
        return box

    for key in scene.roots:
        checkpoint()
        box = visit(key)
        if box.x < -.0001 or box.y < -.0001 or box.x+box.width > scene.width+.0001 or box.y+box.height > scene.height+.0001:
            raise ValueError('Native group paint extends outside its explicitly bound viewport')
    if not scene.roots:
        raise ValueError('An empty scene cannot resurrect its old SVG preview')
    # All emitted coordinates use Word EMUs; reject rounding rather than hiding it.
    for box in boxes.values():
        checkpoint()
        if any(not math.isfinite(v) or abs(v*12700-round(v*12700)) > .00001
               for v in (box.x, box.y, box.width, box.height)):
            raise ValueError('Native group geometry cannot be represented exactly in Word EMUs')
    return boxes


def preview_svg(scene: VectorScene) -> bytes:
    """Derived preview only: native export always consumes the bound scene."""
    scene_profile(scene)
    paths = {p.id: p for p in cancellable_items(scene.paths)}
    groups = {g.id: g for g in cancellable_items(scene.groups)}
    root = ET.Element(f'{{{SVG}}}svg', width=f'{scene.width}pt', height=f'{scene.height}pt',
                      viewBox=f'0 0 {scene.width} {scene.height}')

    def emit(key: str, parent: ET.Element) -> None:
        checkpoint()
        if key in groups:
            group = groups[key]
            a, d, e, f = axis_transform(group.transform)
            target = ET.SubElement(parent, f'{{{SVG}}}g', transform=f'matrix({a} 0 0 {d} {e} {f})')
            for child in group.children:
                checkpoint()
                emit(child, target)
        else:
            box = rectangle(paths[key])
            color, alpha = paint_style(paths[key])
            ET.SubElement(parent, f'{{{SVG}}}rect', x=str(box.x), y=str(box.y), width=str(box.width),
                          height=str(box.height), fill='#'+color, **{'fill-opacity': str(alpha)})

    for key in scene.roots:
        checkpoint()
        emit(key, root)
    return ET.tostring(root, encoding='utf-8')
