"""Represent orthogonal native PDF image matrices using editable Word pictures."""

from __future__ import annotations

import math

from opendoc_model import Box, Image


def prepare_image_transform(image: Image) -> None:
    if image.properties.get('pdf_graphics_state_unknown'):
        raise ValueError('PDF image clipping or graphics group is outside the measured native Word profile')
    matrix = image.properties.get('pdf_image_transform')
    if not matrix:
        return
    if (not isinstance(matrix, list) or len(matrix) != 6
            or any(type(value) not in {int, float} or not math.isfinite(value) for value in matrix)):
        raise ValueError('Invalid native PDF image transform')
    a, b, c, d, e, f = matrix
    width, height = math.hypot(a, b), math.hypot(c, d)
    if min(width, height) <= 0 or max(width, height, abs(e), abs(f)) > 1_000_000:
        raise ValueError('Degenerate or excessive PDF image transform')
    if abs(a * c + b * d) > width * height * 1e-6:
        raise ValueError('Sheared PDF image requires a verified non-rasterizing Word representation')
    x, y = e + (a + c) / 2, f + (b + d) / 2
    image.box = Box(x - width / 2, y - height / 2, width, height,
                    rotation=math.degrees(math.atan2(b, a)) % 360)
    image.properties['flip_vertical'] = a * d - b * c < 0
