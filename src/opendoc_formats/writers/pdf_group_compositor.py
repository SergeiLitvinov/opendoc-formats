"""Exact planar RGB rectangle composition; no bitmap or SVG filter fallback.

ISO 32000-1 11.3/11.4 and W3C Compositing Level 1 define the equations.
The deliberately finite profile rejects curves, strokes, masks and interleaved
text/images requiring a different backdrop. Typed source scopes remain intact.
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import replace
from xml.etree import ElementTree as ET

from opendoc_model import Box, DocumentLimits, DocumentModel, Image, Section, walk_model

from opendoc_formats.pdf_graphics import axis_rectangle, paint_clips, rectangle_points
from opendoc_formats.writers.pdf_docx_graphics import SVG, install_svg


def _blend(backdrop: float, source: float, mode: int) -> float:
    if mode == 0:
        return source
    if mode == 1:
        return backdrop * source
    if mode == 2:
        return backdrop + source - backdrop * source
    if mode == 3:
        return _blend(source, backdrop, 8)
    if mode == 4:
        return min(backdrop, source)
    if mode == 5:
        return max(backdrop, source)
    if mode == 6:
        return 0. if backdrop == 0 else 1. if source == 1 else min(1., backdrop / (1-source))
    if mode == 7:
        return 1. if backdrop == 1 else 0. if source == 0 else 1-min(1., (1-backdrop)/source)
    if mode == 8:
        return 2*backdrop*source if source <= .5 else 1-2*(1-backdrop)*(1-source)
    if mode == 9:
        if source <= .5:
            return backdrop-(1-2*source)*backdrop*(1-backdrop)
        curve = ((16*backdrop-12)*backdrop+4)*backdrop if backdrop <= .25 else math.sqrt(backdrop)
        return backdrop+(2*source-1)*(curve-backdrop)
    if mode == 10:
        return abs(backdrop-source)
    if mode == 11:
        return backdrop+source-2*backdrop*source
    raise ValueError('Nonseparable blend needs a separately verified color-space projection')


def _over(backdrop: tuple, source: tuple, mode: int) -> tuple:
    ab, alpha = backdrop[3], source[3]
    cb = [v/ab if ab else 0. for v in backdrop[:3]]
    cs = [v/alpha if alpha else 0. for v in source[:3]]
    rgb = [(1-alpha)*backdrop[i] + alpha*((1-ab)*cs[i] + ab*_blend(cb[i], cs[i], mode)) for i in range(3)]
    return (*rgb, alpha+ab*(1-alpha))


def project_rectangular_groups(document: DocumentModel, section: Section, evidence: dict,
                               *, limits: DocumentLimits | None) -> dict:
    if not evidence.get('typed_complete'):
        raise ValueError('Complex group requires complete typed paint occurrence coverage')
    if any(group['knockout'] for group in evidence['groups']):
        raise ValueError('Knockout group projection is unverified across independent PDF renderers')
    if any(group['colorspace'] not in (None, 'DeviceRGB') for group in evidence['groups']):
        raise ValueError('Non-RGB group blending space requires an explicit color-space projection')
    budget = limits or DocumentLimits()
    vectors = {}
    for ref in walk_model(section, limits=limits):
        image = ref.node
        if isinstance(image, Image) and document.resources[image.resource_id].media_type == 'application/pdf+vector':
            vectors[image.properties['pdf_paint_seq']] = image
    if not vectors:
        raise ValueError('No verified vector group content')
    rectangles = {}
    for sequence, image in vectors.items():
        paint, clips = paint_clips(evidence, sequence, {'fill-path'}, compositing=True)
        resource = document.resources[image.resource_id]
        props = resource.properties
        from opendoc_formats.writers.pdf_vectors import _validate

        _validate(image, replace(resource, properties={**props, 'graphics_state_unsupported': False, 'clip_rects': []}))
        items = props.get('items', [])
        color = props.get('fill')
        if (props.get('stroke') is not None or len(items) != 1 or items[0][0] != 're'
                or not isinstance(color, dict) or color.get('space') != 'srgb' or color.get('icc_profile') is not None):
            raise ValueError('Group compositor requires constant RGB filled rectangles without strokes')
        if image.box is None or image.box.rotation or list(items[0][1]) != props.get('bbox'):
            raise ValueError('Rectangle placement/geometry needs a verified axis-aligned frame')
        bounds = [image.box.x, image.box.y, image.box.x+image.box.width, image.box.y+image.box.height]
        for clip in clips:
            points = rectangle_points(clip)
            region = axis_rectangle(points) if points else None
            if region is None:
                raise ValueError('Group compositor requires rectangular clips')
            bounds = [max(bounds[0], region[0]), max(bounds[1], region[1]),
                      min(bounds[2], region[2]), min(bounds[3], region[3])]
        alpha = props.get('fill_opacity', 1.)
        rectangles[sequence] = (bounds, (*[c*alpha for c in color['components']], alpha))
        for key in paint['groups']:
            if evidence['groups'][key]['blendmode'] > 11:
                raise ValueError('Nonseparable group blend is outside the verified RGB rectangle profile')
    first = min(vectors)
    order = evidence.get('paint_order', list(range(len(evidence['paints']))))
    ranks = {sequence: index for index, sequence in enumerate(order)}
    for sequence, paint in enumerate(evidence['paints']):
        if sequence in vectors:
            continue
        if any(g['opacity'] != 1 or g['knockout'] or g['blendmode']
               for key in paint['groups'] if (g := evidence['groups'][key])):
            raise ValueError('Mixed text/image compositing group needs a verified native target representation')
        for vector_seq, (box, _) in rectangles.items():
            b = paint['bbox']
            if ((ranks[sequence] < ranks[vector_seq] or sequence < first)
                    and box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3]):
                raise ValueError('Group backdrop interleaves text or raster content')
    children = {None: []}
    for sequence in order:
        paint = evidence['paints'][sequence]
        if sequence not in vectors:
            continue
        parent = None
        for key in paint['groups']:
            group = ('g', key)
            if group not in children:
                children[group] = []
                children[parent].append(group)
            parent = group
        children[parent].append(('p', sequence))

    def evaluate(key: tuple, backdrop: tuple, x: float, y: float) -> tuple[tuple, float, bool]:
        if key[0] == 'p':
            box, color = rectangles[key[1]]
            if not (box[0] <= x < box[2] and box[1] <= y < box[3]):
                return backdrop, 0., False
            return _over(backdrop, color, 0), color[3], True
        state = evidence['groups'][key[1]]
        initial = (0., 0., 0., 0.) if state['isolated'] else backdrop
        current, alpha, shape = initial, 0., False
        for child in children[key]:
            result, child_alpha, child_shape = evaluate(child, current, x, y)
            if child_shape:
                current = result
                alpha = child_alpha+alpha*(1-child_alpha)
                shape = True
        source = (*[(current[i]-(1-alpha)*initial[i])*state['opacity'] for i in range(3)],
                  alpha*state['opacity'])
        return _over(backdrop, source, state['blendmode']), source[3], shape

    xs = sorted({v for box, _ in rectangles.values() for v in (box[0], box[2])})
    ys = sorted({v for box, _ in rectangles.values() for v in (box[1], box[3])})
    if (len(xs)-1)*(len(ys)-1)*max(1, len(evidence['groups'])+len(vectors)) > min(1_000_000, budget.max_nodes*10):
        raise ValueError('Planar group composition exceeds selected work budget')
    frame = Box(xs[0]-1, ys[0]-1, xs[-1]-xs[0]+2, ys[-1]-ys[0]+2)
    root = ET.Element(f'{{{SVG}}}svg', {'width': f'{frame.width}pt', 'height': f'{frame.height}pt',
                                     'viewBox': f'0 0 {frame.width} {frame.height}'})
    for top, bottom in zip(ys, ys[1:]):
        for left, right in zip(xs, xs[1:]):
            color = (0., 0., 0., 0.)
            for child in children[None]:
                color, _, _ = evaluate(child, color, (left+right)/2, (top+bottom)/2)
            if color[3] == 0:
                continue
            rgb = [min(255, int(min(1., max(0., c/color[3]))*255 + .50001)) for c in color[:3]]
            ET.SubElement(root, f'{{{SVG}}}rect', {'x': f'{left-frame.x:.12g}', 'y': f'{top-frame.y:.12g}',
                          'width': f'{right-left:.12g}', 'height': f'{bottom-top:.12g}',
                          'fill': '#' + ''.join(f'{c:02x}' for c in rgb),
                          'fill-opacity': f'{color[3]:.12g}'})
    image = vectors[first]
    install_svg(document, image, document.resources[image.resource_id], root, frame)
    document.metadata.setdefault('pdf_docx_group_projection', []).append({
        'source_vector_occurrences': len(vectors), 'target_vector_images': 1, 'native_group_editing': False,
    })
    removed = {id(value) for key, value in vectors.items() if key != first}

    def prune(blocks: list) -> None:
        for block in blocks:
            if hasattr(block, 'content'):
                block.content[:] = [node for node in block.content if id(node) not in removed]
            if hasattr(block, 'blocks'):
                prune(block.blocks)
        blocks[:] = [block for block in blocks if not hasattr(block, 'content') or block.content]

    prune(section.blocks)
    result = deepcopy(evidence)
    for paint in result['paints']:
        paint['groups'] = []
    result['paints'][first]['kind'] = 'fill-image'
    result['paints'][first]['clips'] = []
    result['paints'][first]['alpha'] = 1.
    return result
