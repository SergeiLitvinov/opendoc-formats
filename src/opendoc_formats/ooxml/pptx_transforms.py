"""Shared finite DrawingML group-coordinate math, owned by Formats."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from opendoc_model.units import ooxml_angle_to_degrees

from opendoc_formats.support.cancellation import cancellable_items


def _p(local: str) -> str:
    return "{http://schemas.openxmlformats.org/presentationml/2006/main}"+local


def _a(local: str) -> str:
    return "{http://schemas.openxmlformats.org/drawingml/2006/main}"+local


def _xml_bool(value: str | None) -> bool:
    return value in {"1", "true", "on"}


@dataclass(frozen=True)
class _Matrix:
    """2D affine matrix using the SVG/CSS ``a,b,c,d,e,f`` convention."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def then(self, child: "_Matrix") -> "_Matrix":
        """Compose this parent matrix with a child/local matrix."""

        return _Matrix(
            a=self.a * child.a + self.c * child.b,
            b=self.b * child.a + self.d * child.b,
            c=self.a * child.c + self.c * child.d,
            d=self.b * child.c + self.d * child.d,
            e=self.a * child.e + self.c * child.f + self.e,
            f=self.b * child.e + self.d * child.f + self.f,
        )

    def point(self, x: float, y: float) -> tuple[float, float]:
        return self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f



@dataclass(frozen=True)
class _Transform:
    """Mapping from a group child coordinate space to absolute slide EMU."""

    matrix: _Matrix = _Matrix()
    rotation: float = 0.0
    requires_affine: bool = False



def _apply_transform(transform: _Transform, x: float, y: float, cx: float, cy: float) -> tuple[float, float, float, float]:
    points = (
        transform.matrix.point(x, y),
        transform.matrix.point(x + cx, y),
        transform.matrix.point(x, y + cy),
        transform.matrix.point(x + cx, y + cy),
    )
    xs = [point[0] for point in cancellable_items(points)]
    ys = [point[1] for point in cancellable_items(points)]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)



def _translate(x: float, y: float) -> _Matrix:
    return _Matrix(e=x, f=y)



def _scale(x: float, y: float) -> _Matrix:
    return _Matrix(a=x, d=y)



def _rotation_flip(rotation: float, *, flip_h: bool, flip_v: bool) -> _Matrix:
    radians = math.radians(rotation)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    horizontal = -1.0 if flip_h else 1.0
    vertical = -1.0 if flip_v else 1.0
    return _Matrix(
        a=cosine * horizontal,
        b=sine * horizontal,
        c=-sine * vertical,
        d=cosine * vertical,
    )



def _around_center(
    center_x: float,
    center_y: float,
    *,
    rotation: float,
    flip_h: bool,
    flip_v: bool,
) -> _Matrix:
    return (
        _translate(center_x, center_y)
        .then(_rotation_flip(rotation, flip_h=flip_h, flip_v=flip_v))
        .then(_translate(-center_x, -center_y))
    )



def _is_uniform_axis_scale(matrix: _Matrix) -> bool:
    return (
        math.isclose(matrix.b, 0.0, abs_tol=1e-9)
        and math.isclose(matrix.c, 0.0, abs_tol=1e-9)
        and math.isclose(abs(matrix.a), abs(matrix.d), rel_tol=1e-9, abs_tol=1e-9)
    )



def _group_child_transform(group_element: Any, parent: _Transform) -> _Transform:
    """Посчитать трансформацию дочерних фигур группы.

    Дочерние координаты заданы в пространстве chOff..chExt; масштаб
    пересчитывается в размер ext группы. Если chOff/chExt отсутствуют,
    дочерние координаты считаются абсолютными в пространстве страницы.
    """
    grp_pr = group_element.find(_p("grpSpPr"))
    xfrm = grp_pr.find(_a("xfrm")) if grp_pr is not None else None
    if xfrm is None:
        return parent
    off = xfrm.find(_a("off"))
    ext = xfrm.find(_a("ext"))
    ch_off = xfrm.find(_a("chOff"))
    ch_ext = xfrm.find(_a("chExt"))
    if ch_off is None or ch_ext is None or off is None or ext is None:
        return parent
    gx = float(off.get("x", 0))
    gy = float(off.get("y", 0))
    gcx = float(ext.get("cx", 1))
    gcy = float(ext.get("cy", 1))
    cox = float(ch_off.get("x", 0))
    coy = float(ch_off.get("y", 0))
    ccx = float(ch_ext.get("cx", gcx))
    ccy = float(ch_ext.get("cy", gcy))
    sx = gcx / ccx if ccx else 1.0
    sy = gcy / ccy if ccy else 1.0
    rotation = ooxml_angle_to_degrees(float(xfrm.get("rot", 0)))
    flip_h = _xml_bool(xfrm.get("flipH"))
    flip_v = _xml_bool(xfrm.get("flipV"))
    mapping = _translate(gx, gy).then(_scale(sx, sy)).then(_translate(-cox, -coy))
    orientation = _around_center(
        gx + gcx / 2,
        gy + gcy / 2,
        rotation=rotation,
        flip_h=flip_h,
        flip_v=flip_v,
    )
    local = orientation.then(mapping)
    return _Transform(
        matrix=parent.matrix.then(local),
        rotation=parent.rotation + rotation,
        requires_affine=parent.requires_affine or bool(rotation) or flip_h or flip_v,
    )

