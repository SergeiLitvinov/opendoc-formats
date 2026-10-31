"""Invert source DrawingML group frames for native Box edits; no guessed geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import opendoc_model as od
from opendoc_model.units import EMU_PER_POINT, ooxml_angle_to_degrees

from opendoc_formats.ooxml.pptx_placeholders import inherited_source_frame
from opendoc_formats.ooxml.pptx_source_xml import SourceRoots
from opendoc_formats.ooxml.pptx_transforms import _apply_transform, _group_child_transform, _Transform
from opendoc_formats.support.cancellation import cancellable_items, checkpoint

A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'


@dataclass
class GeometryBinding:
    section: int
    block: int
    part: str
    shape: Any
    xfrm: Any
    parent: _Transform
    original: od.Box
    override: bool = False


def geometry_bindings(
    document: od.DocumentModel, roots: SourceRoots | None = None, *, placeholders: bool = False,
) -> list[GeometryBinding]:
    graph = document.package
    if graph is None or graph.format != 'pptx':
        return []
    roots = SourceRoots() if roots is None else roots
    result, seen = [], set()
    for si, section in enumerate(cancellable_items(document.sections)):
        part = section.provenance.package_part if section.provenance else None
        if part not in graph.parts:
            continue
        roots.load(graph, part)
        native = {}
        for shape in cancellable_items(roots[part].iter()):
            if shape.tag not in {P+name for name in ('sp', 'pic', 'cxnSp', 'graphicFrame')}:
                continue
            identities = shape.findall('.//'+P+'cNvPr')
            if len(identities) == 1:
                native.setdefault(identities[0].get('id'), []).append(shape)
        for bi, block in enumerate(cancellable_items(section.blocks)):
            identity = block.properties.get('pptx', {}).get('object_id')
            shapes = native.get(identity, [])
            if block.box is None or len(shapes) != 1:
                continue
            shape = shapes[0]
            xfrm = shape.find(P+'xfrm') if shape.tag == P+'graphicFrame' else shape.find(P+'spPr/'+A+'xfrm')
            override = False
            if xfrm is None and placeholders:
                xfrm = inherited_source_frame(shape, part, graph, roots)
                override = xfrm is not None
            if xfrm is None or xfrm.find(A+'off') is None or xfrm.find(A+'ext') is None:
                continue
            parent, valid = _Transform(), True
            for group in reversed(list(shape.iterancestors(P+'grpSp'))):
                checkpoint()
                transform = group.find(P+'grpSpPr/'+A+'xfrm')
                if transform is None:
                    valid = False
                    break
                if any(transform.find(A+name) is None for name in ('off', 'ext', 'chOff', 'chExt')):
                    valid = False
                    break
                try:
                    sized = all(int(transform.find(A+name).get(axis, '0')) > 0
                                for name in ('ext', 'chExt') for axis in ('cx', 'cy'))
                except (TypeError, ValueError):
                    sized = False
                if not sized:
                    valid = False
                    break
                parent = _group_child_transform(group, parent)
            if not valid:
                continue
            offset, extent = xfrm.find(A+'off'), xfrm.find(A+'ext')
            try:
                x, y = int(offset.get('x')), int(offset.get('y'))
                w, h = int(extent.get('cx')), int(extent.get('cy'))
                rotation = ooxml_angle_to_degrees(int(xfrm.get('rot', '0')))
            except (TypeError, ValueError):
                continue
            if w < 0 or h < 0 or w+h == 0:
                continue
            original = od.Box(*[value/EMU_PER_POINT for value in _apply_transform(parent, x, y, w, h)],
                              rotation=parent.rotation+rotation)
            key = (part, identity)
            if key in seen:
                raise ValueError('Repeated native geometry owner')
            seen.add(key)
            result.append(GeometryBinding(si, bi, part, shape, xfrm, parent, original, override))
    return result


def project_geometry(binding: GeometryBinding, target: od.Box, *, frame_resize: bool = False) -> bool:
    """Set native off/ext/rot at native integer precision; untouched frames remain byte-equivalent."""
    original = binding.original
    fields = ('x', 'y', 'width', 'height', 'rotation')
    if all(math.isclose(getattr(target, name), getattr(original, name), abs_tol=1e-9, rel_tol=0) for name in fields):
        return False
    if binding.shape.tag == P+'cxnSp' and any(
        binding.shape.find(P+'nvCxnSpPr/'+P+'cNvCxnSpPr/'+A+name) is not None for name in ('stCxn', 'endCxn')
    ):
        raise ValueError('Connected connector geometry requires an explicit endpoint projection')
    if binding.shape.tag == P+'graphicFrame' and any(
        not math.isclose(getattr(target, name), getattr(original, name), abs_tol=1e-9, rel_tol=0)
        for name in (('rotation',) if frame_resize else ('width', 'height', 'rotation'))
    ):
        raise ValueError('GraphicFrame resizing requires native table/chart geometry projection; translation only')
    matrix = binding.parent.matrix
    a, b, c, d = matrix.a, matrix.b, matrix.c, matrix.d
    determinant = a*d-b*c
    scale = max(abs(a), abs(b), abs(c), abs(d))
    if not scale or abs(determinant) <= 1e-12*scale*scale:
        raise ValueError('Singular source group transform')
    width, height = target.width*EMU_PER_POINT, target.height*EMU_PER_POINT
    bounds_det = abs(a)*abs(d)-abs(b)*abs(c)
    if abs(bounds_det) > 1e-10*scale*scale:
        w = (width*abs(d)-height*abs(c))/bounds_det
        h = (height*abs(a)-width*abs(b))/bounds_det
    elif math.isclose(target.width, original.width, abs_tol=1e-9, rel_tol=0) and math.isclose(
        target.height, original.height, abs_tol=1e-9, rel_tol=0
    ):
        # Translation/rotation does not require guessing local aspect ratio at 45 degrees.
        extent = binding.xfrm.find(A+'ext')
        w, h = int(extent.get('cx')), int(extent.get('cy'))
    else:
        raise ValueError('Source bounds do not uniquely determine native local extents')
    if w < -1e-5 or h < -1e-5 or w+h <= 0:
        raise ValueError('Requested bounds have no nonnegative native local extents')
    cx = (target.x+target.width/2)*EMU_PER_POINT-matrix.e
    cy = (target.y+target.height/2)*EMU_PER_POINT-matrix.f
    x, y = (d*cx-c*cy)/determinant-w/2, (-b*cx+a*cy)/determinant-h/2
    values = [round(value) for value in (x, y, max(0, w), max(0, h))]
    if values[2]+values[3] == 0:
        raise ValueError('Geometry is below native coordinate resolution')
    if any(abs(value) > 2_147_483_647 for value in values):
        raise ValueError('Native geometry exceeds the accepted integer-coordinate profile')
    projected = [value/EMU_PER_POINT for value in _apply_transform(binding.parent, *values)]
    if any(abs(value-getattr(target, name)) > 1/EMU_PER_POINT+1e-9
           for value, name in zip(projected, ('x', 'y', 'width', 'height'), strict=True)):
        raise ValueError('Requested frame cannot be represented within one slide-coordinate EMU')
    offset, extent = binding.xfrm.find(A+'off'), binding.xfrm.find(A+'ext')
    for name, value in zip(('x', 'y'), values[:2], strict=True):
        offset.set(name, str(value))
    for name, value in zip(('cx', 'cy'), values[2:], strict=True):
        extent.set(name, str(value))
    if not math.isclose(target.rotation, original.rotation, abs_tol=1e-9, rel_tol=0):
        rotation = round((target.rotation-binding.parent.rotation)*60000)
        if abs(rotation) > 2_147_483_647:
            raise ValueError('Native rotation exceeds the accepted integer-angle profile')
        binding.xfrm.set('rot', str(rotation))
    if binding.override:
        binding.shape.find(P+'spPr').insert(0, binding.xfrm)
    return True
