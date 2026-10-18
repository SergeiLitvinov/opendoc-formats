"""Bind painted glyph origins to actual native font bytes, never family guesses."""

from __future__ import annotations

import hashlib
from typing import Any

from opendoc_model import Resource, ResourceKind


def painted_font_programs(page: Any, resources: dict[str, Resource],
                          origins: set[tuple[float, float]]) -> dict:
    """Finite MuPDF device profile; unsupported backend APIs leave bindings unknown."""
    import pymupdf

    mupdf = pymupdf.mupdf
    by_digest = {}
    sizes = set()
    for resource in resources.values():
        if resource.kind is ResourceKind.FONT and resource.data:
            by_digest.setdefault(hashlib.sha256(resource.data).digest(), []).append(resource.id)
            sizes.add(len(resource.data))
    result = {}
    if not by_digest:
        return result

    class FontDevice(mupdf.FzDevice2):
        def __init__(self) -> None:
            super().__init__()
            self.use_virtual_fill_text()
            self.cache = {}

        def fill_text(self, ctx: Any, text: Any, ctm: Any, colorspace: Any, color: Any,
                      alpha: float, color_params: Any) -> None:
            span = text.head
            while span:
                native = mupdf.FzTextSpan(span)
                buffer = native.font().m_internal.buffer
                key = int(buffer.this) if buffer else 0
                if key not in self.cache:
                    data = mupdf.fz_buffer_extract_copy(mupdf.FzBuffer(buffer)) if buffer and buffer.len in sizes else b''
                    ids = by_digest.get(hashlib.sha256(data).digest(), [])
                    self.cache[key] = ids[0] if len(ids) == 1 else None
                identifier = self.cache[key]
                for offset in range(span.len):
                    item = native.items(offset)
                    point = mupdf.fz_transform_point(mupdf.FzPoint(item.x, item.y), mupdf.FzMatrix(ctm))
                    origin = (round(point.x, 3), round(point.y, 3))
                    if origin in origins:
                        result.setdefault((origin, item.ucs), set()).add(identifier)
                span = span.next

    rotation = page.rotation
    device = None
    try:
        page.set_rotation(0)
        device = FontDevice()
        mupdf.fz_run_page_contents(page.this, device, mupdf.FzMatrix(), mupdf.FzCookie())
        mupdf.fz_close_device(device)
    except (AttributeError, TypeError, RuntimeError):
        # No name-based fallback: an ambiguous program remains explicitly unbound.
        return {}
    finally:
        page.set_rotation(rotation)
    return result
