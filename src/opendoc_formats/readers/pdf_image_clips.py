"""Read a bounded single-image quadrilateral clip profile, without executing content."""

from __future__ import annotations

import math
import re
import zlib
from typing import Any

from opendoc_model import ImageCrop

_NUMBER = rb"([+-]?[0-9]+(?:\.[0-9]+)?)"
_POINT = _NUMBER + rb"\s+" + _NUMBER
_CLIP = re.compile(
    rb"q\s+" + _POINT + rb"\s+m\s+" + _POINT + rb"\s+l\s+" + _POINT + rb"\s+l\s+"
    + _POINT + rb"\s+l\s+h\s+W\s+n\s+" + rb"\s+".join([_NUMBER] * 6)
    + rb"\s+cm\s+/([A-Za-z0-9_]+)\s+Do\s+Q",
)


def image_clip_profiles(page: Any) -> list[tuple[int, tuple[float, ...], tuple[float, ...], ImageCrop]]:
    """Recognize isolated native image clips; other graphics states remain outside this profile."""
    resources = {item[7]: item[0] for item in page.get_images(full=True) if item[-1] == 0}
    result = []
    ta, tb, tc, td, te, tf = page.transformation_matrix

    def convert(x: float, y: float) -> tuple[float, float]:
        return x * ta + y * tc + te, x * tb + y * td + tf

    for stream in page.get_contents():
        encoded = page.parent.xref_stream_raw(stream)
        if encoded is None or len(encoded) > 16384:
            continue
        kind, value = page.parent.xref_get_key(stream, "Filter")
        if kind == "null":
            raw = encoded
        elif (kind == "name" and value == "/FlateDecode") or (
            kind == "array" and re.fullmatch(r"\[\s*/FlateDecode\s*\]", value)
        ):
            if page.parent.xref_get_key(stream, "DecodeParms")[0] != "null":
                continue
            inflater = zlib.decompressobj()
            try:
                raw = inflater.decompress(encoded, 16385)
            except zlib.error:
                continue
            if len(raw) > 16384 or not inflater.eof or inflater.unconsumed_tail or inflater.unused_data:
                continue
        else:
            continue
        match = _CLIP.fullmatch(raw.strip())
        if match is None:
            continue
        numbers = [float(item) for item in match.groups()[:-1]]
        if any(not math.isfinite(value) or abs(value) > 1_000_000 for value in numbers):
            continue
        points = list(zip(numbers[:8:2], numbers[1:8:2], strict=True))
        a, b, c, d, e, f = numbers[8:]
        determinant = a * d - b * c
        if abs(determinant) < 1e-8:
            continue
        coordinates = [((d * (x-e) - c * (y-f)) / determinant,
                        1 - (-b * (x-e) + a * (y-f)) / determinant) for x, y in points]
        left, top = coordinates[0]
        right, bottom = coordinates[2]
        if not (math.isclose(coordinates[1][0], right, abs_tol=1e-7)
                and math.isclose(coordinates[1][1], top, abs_tol=1e-7)
                and math.isclose(coordinates[3][0], left, abs_tol=1e-7)
                and math.isclose(coordinates[3][1], bottom, abs_tol=1e-7)):
            continue
        margins = [round(left, 9), round(top, 9), round(1-right, 9), round(1-bottom, 9)]
        if any(value < 0 or value >= 1 for value in margins) or right-left <= 1e-6 or bottom-top <= 1e-6:
            continue
        crop = ImageCrop(*margins)
        native_top = convert(e+c, f+d)
        native_right = convert(e+c+a, f+d+b)
        native_bottom = convert(e, f)
        raw_transform = (native_right[0]-native_top[0], native_right[1]-native_top[1],
                         native_bottom[0]-native_top[0], native_bottom[1]-native_top[1], *native_top)
        frame = [convert(x, y) for x, y in points]
        frame_transform = (frame[1][0]-frame[0][0], frame[1][1]-frame[0][1],
                           frame[3][0]-frame[0][0], frame[3][1]-frame[0][1], *frame[0])
        name = match.groups()[-1].decode("ascii")
        if name in resources:
            result.append((resources[name], raw_transform, frame_transform, crop))
    return result


def clipped_image_placement(
    info: dict[str, Any], profiles: list[tuple[int, tuple[float, ...], tuple[float, ...], ImageCrop]],
) -> tuple[tuple[float, ...], tuple[float, ...], ImageCrop] | None:
    matrix = info.get("transform", ())
    for xref, original, frame, crop in profiles:
        if xref != info.get("xref") or len(matrix) != 6:
            continue
        if not all(math.isclose(a, b, abs_tol=0.001, rel_tol=1e-7) for a, b in zip(matrix, original, strict=True)):
            continue
        a, b, c, d, e, f = frame
        xs, ys = (e, e+a, e+c, e+a+c), (f, f+b, f+d, f+b+d)
        return (min(xs), min(ys), max(xs), max(ys)), frame, crop
    return None
