"""Project verified native PDF clip scopes into Word pictures without page rasterization."""

from __future__ import annotations

import base64
import math
from dataclasses import replace
from xml.etree import ElementTree as ET

from opendoc_model import (
    Box,
    DocumentLimits,
    DocumentModel,
    Formula,
    Image,
    ImageCrop,
    Resource,
    ResourceKind,
    Section,
    TextRun,
    walk_model,
)

from opendoc_formats.pdf_graphics import axis_rectangle, contains, finite_number, paint_clips, rectangle_points

SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'


def prepare_section_graphics(document: DocumentModel, section: Section, *, limits: DocumentLimits | None) -> None:
    from opendoc_formats.writers.pdf_scope_projection import project_scopes

    evidence = project_scopes(document, section, limits=limits)
    if evidence is None:
        return  # Legacy Model transport retains the earlier conservative refusal.
    order = evidence.get('paint_order', [])
    if (any(group['opacity'] != 1 or group['knockout'] or group['blendmode']
            or group['colorspace'] not in (None, 'DeviceRGB') for group in evidence.get('groups', []))
            or order != sorted(order)):
        from opendoc_formats.writers.pdf_group_compositor import project_rectangular_groups

        evidence = project_rectangular_groups(document, section, evidence, limits=limits)
    supported = {'fill-path', 'stroke-path', 'fill-image', 'fill-text', 'stroke-text', 'ignore-text'}
    for sequence, paint in enumerate(evidence.get('paints', [])):
        paint_clips(evidence, sequence, supported)
        if paint['kind'] in {'fill-image', 'fill-text'} and finite_number(paint.get('alpha')) != 1:
            raise ValueError('PDF per-operation transparency requires a verified target representation')
    if evidence.get('unknown'):
        raise ValueError('Native PDF graphics state could not be measured')
    for location in walk_model(section, limits=limits):
        image = location.node
        if isinstance(image, TextRun) and image.properties.get('pdf_origin'):
            verify_text_clip(image.properties, evidence)
        elif isinstance(image, Formula):
            for line in image.properties.get('pdf_native_lines', []):
                for span in line:
                    verify_text_clip(span['paint'], evidence)
        if not isinstance(image, Image):
            continue
        resource = document.resources.get(image.resource_id)
        if resource is None:
            continue
        vector = resource.media_type == 'application/pdf+vector'
        paint, clips = paint_clips(evidence, image.properties.get('pdf_paint_seq'),
                                   {'fill-path', 'stroke-path'} if vector else {'fill-image'})
        image.properties['pdf_graphics_state_unknown'] = False
        if vector:
            # Target-local clearance; the public source and native PDF writer remain conservative.
            active = []
            for clip in clips:
                points = rectangle_points(clip)
                bounds = axis_rectangle(points) if points else None
                if bounds is None or not contains(bounds, paint['bbox']):
                    active.append(clip)
            image.properties['pdf_docx_clip_paths'] = active
            image.properties['pdf_docx_clip_limit'] = min(50_000, (limits or DocumentLimits()).max_nodes)
            image.properties['pdf_docx_graphics_measured'] = True
            if not active:
                resource.properties['graphics_state_unsupported'] = False
                resource.properties['clip_rects'] = []
        elif clips:
            _clip_raster(document, image, resource, clips, limits=limits)


def verify_text_clip(properties: dict, evidence: dict) -> None:
    paint, clips = paint_clips(evidence, properties.get('pdf_paint_seq'), {'fill-text', 'stroke-text', 'ignore-text'})
    for clip in clips:
        points = rectangle_points(clip)
        bounds = axis_rectangle(points) if points else None
        if bounds is None or not contains(bounds, paint.get('ink_bbox', paint['bbox'])):
            raise ValueError('Typed text clip intersects glyphs; native editable Word clipping is not verified')
    properties['pdf_graphics_state_unknown'] = False


def _clip_raster(document: DocumentModel, image: Image, resource: Resource, clips: list[dict],
                 *, limits: DocumentLimits | None) -> None:
    matrix = image.properties.get('pdf_source_image_transform')
    if not isinstance(matrix, list) or len(matrix) != 6:
        raise ValueError('Clipped PDF image requires its original native transform')
    a, b, c, d, e, f = map(finite_number, matrix)
    determinant = a * d - b * c
    if abs(determinant) < 1e-8:
        raise ValueError('Degenerate clipped PDF image transform')
    # Keep the existing verified shear refusal even when a clip is present.
    if abs(a*c + b*d) > math.hypot(a, b) * math.hypot(c, d) * 1e-6:
        raise ValueError('Clipped sheared PDF image needs a verified Word profile')
    left, top, right, bottom = 0., 0., 1., 1.
    rectangular = True
    for clip in clips:
        points = rectangle_points(clip)
        unit = [((d*(x-e) - c*(y-f))/determinant, (-b*(x-e) + a*(y-f))/determinant)
                for x, y in points] if points else None
        bounds = axis_rectangle(unit, tolerance=1e-5) if unit else None
        if bounds is None:
            rectangular = False
            break
        left, top, right, bottom = max(left, bounds[0]), max(top, bounds[1]), min(right, bounds[2]), min(bottom, bounds[3])
    if rectangular:
        if right <= left or bottom <= top:
            raise ValueError('Fully hidden PDF image requires an explicit visibility projection')
        left, top, right, bottom = [min(1., max(0., v)) for v in (left, top, right, bottom)]
        image.crop = ImageCrop(left, top, 1-right, 1-bottom)
        frame = [a*(right-left), b*(right-left), c*(bottom-top), d*(bottom-top),
                 e+a*left+c*top, f+b*left+d*top]
        image.properties['pdf_image_transform'] = frame
        x, y = frame[4], frame[5]
        xs, ys = (x, x+frame[0], x+frame[2], x+frame[0]+frame[2]), (y, y+frame[1], y+frame[3], y+frame[1]+frame[3])
        image.box = Box(min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys))
        return
    xs, ys = (e, e+a, e+c, e+a+c), (f, f+b, f+d, f+b+d)
    # Keep a transparent guard at the SVG viewport edge, without changing samples.
    padding = 1.
    box = Box(min(xs)-padding, min(ys)-padding, max(xs)-min(xs)+2*padding, max(ys)-min(ys)+2*padding)
    root = ET.Element(f'{{{SVG}}}svg', {'width': f'{box.width:.12g}pt', 'height': f'{box.height:.12g}pt',
                                     'viewBox': f'0 0 {box.width:.12g} {box.height:.12g}'})
    if resource.data is None or resource.media_type not in {'image/png', 'image/jpeg'}:
        raise ValueError('Clipped SVG raster profile requires retained PNG/JPEG samples')
    ET.SubElement(root, f'{{{SVG}}}image', {'width': '1', 'height': '1', 'preserveAspectRatio': 'none',
                  f'{{{XLINK}}}href': f'data:{resource.media_type};base64,' + base64.b64encode(resource.data).decode('ascii'),
                  'transform': f'matrix({a:.12g} {b:.12g} {c:.12g} {d:.12g} {e-box.x:.12g} {f-box.y:.12g})'})
    clip_svg(root, clips, box, max_commands=min(50_000, (limits or DocumentLimits()).max_nodes))
    install_svg(document, image, resource, root, box)
    image.properties.pop('pdf_image_transform', None)
    image.crop = None


def clip_svg(root: ET.Element, clips: list[dict], box: Box, *, max_commands: int = 50_000) -> None:
    if not clips:
        return
    # Each clip intersects the previous clip. Disjoint subpaths retain their winding rule.
    children = list(root)
    for child in children:
        root.remove(child)
    definitions = ET.SubElement(root, f'{{{SVG}}}defs')
    parent = root
    existing = {element.get('id') for child in children for element in child.iter() if element.get('id')}
    command_count = 0
    for index, clip in enumerate(clips):
        identifier = f'odf-native-clip-{index}'
        while identifier in existing:
            identifier += '-clip'
        existing.add(identifier)
        path = []
        for command in _word_clip_commands(clip['commands'], max_commands):
            command_count += 1
            if command_count > max_commands:
                raise ValueError('Word SVG clip representation exceeds command budget')
            numbers = [value - (box.x if offset % 2 == 0 else box.y) for offset, value in enumerate(command[1:])]
            path.append(command[0] + ' '.join(f'{v:.12g}' for v in numbers))
        element = ET.SubElement(definitions, f'{{{SVG}}}clipPath', {'id': identifier, 'clipPathUnits': 'userSpaceOnUse'})
        ET.SubElement(element, f'{{{SVG}}}path', {'d': ' '.join(path), 'clip-rule': 'evenodd' if clip['even_odd'] else 'nonzero'})
        parent = ET.SubElement(parent, f'{{{SVG}}}g', {'clip-path': f'url(#{identifier})'})
    parent.extend(children)


def _word_clip_commands(commands: list[list], maximum: int) -> list[list]:
    # Office can replace a long clip Bezier near its extrema by a chord.
    # Exact de Casteljau subdivision retains the same cubic geometry, while
    # bounding even that renderer's chord error to 0.01 point. No raster mask.
    output = []
    current = start = None

    def cubic(points: list[tuple[float, float]], depth: int = 0) -> None:
        if len(output) >= maximum:
            raise ValueError('Word SVG clip representation exceeds command budget')
        p0, p1, p2, p3 = points
        dx, dy = p3[0]-p0[0], p3[1]-p0[1]
        length = math.hypot(dx, dy)
        # Distance to the finite chord, not just its line (also handles loops).
        def distance(point: tuple[float, float]) -> float:
            t = max(0., min(1., ((point[0]-p0[0])*dx + (point[1]-p0[1])*dy) / length**2)) if length else 0.
            return math.hypot(point[0]-p0[0]-t*dx, point[1]-p0[1]-t*dy)
        if max(distance(p1), distance(p2)) <= .01:
            output.append(['C', *p1, *p2, *p3])
            return
        if depth >= 16:
            raise ValueError('Word SVG clip curve exceeds subdivision depth')
        def midpoint(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
            return ((a[0]+b[0])/2, (a[1]+b[1])/2)
        a, b, c = midpoint(p0, p1), midpoint(p1, p2), midpoint(p2, p3)
        d, e = midpoint(a, b), midpoint(b, c)
        middle = midpoint(d, e)
        cubic([p0, a, d, middle], depth+1)
        cubic([middle, e, c, p3], depth+1)

    for command in commands:
        if command[0] == 'C':
            if current is None:
                raise ValueError('Clip curve has no starting point')
            cubic([current, tuple(command[1:3]), tuple(command[3:5]), tuple(command[5:7])])
            current = tuple(command[5:7])
        else:
            output.append(command)
            if command[0] == 'M':
                current = start = tuple(command[1:])
            elif command[0] == 'L':
                current = tuple(command[1:])
            elif command[0] == 'Z':
                current = start
    return output


def install_svg(document: DocumentModel, image: Image, source: Resource, root: ET.Element, box: Box) -> None:
    identifier = source.id + '-word-clip'
    while identifier in document.resources:
        identifier += '-derived'
    document.resources[identifier] = replace(source, id=identifier, kind=ResourceKind.VECTOR_IMAGE,
                                              media_type='image/svg+xml', data=word_svg_bytes(root),
                                              filename=identifier + '.svg',
                                              properties={'pdf_source_resource': source.id})
    image.resource_id, image.box = identifier, box


def word_svg_bytes(root: ET.Element) -> bytes:
    # Office quantizes imported SVG coordinates in its intrinsic physical size.
    # A finer intrinsic scale avoids shrinking the visible contour by ~0.5 pt.
    # viewBox and the DrawingML frame retain their original geometry and size.
    width = float(root.get('width', '').removesuffix('pt'))
    height = float(root.get('height', '').removesuffix('pt'))
    if min(width, height) <= 0 or not all(math.isfinite(v) for v in (width, height)):
        raise ValueError('Invalid derived SVG dimensions')
    scale = max(1., min(16., 24_000 / max(width, height)))
    root.set('width', f'{width*scale:.12g}pt')
    root.set('height', f'{height*scale:.12g}pt')
    return ET.tostring(root, encoding='utf-8')
