"""Immutable MuPDF text-device observations, with actual affine glyph matrices."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError
from opendoc_formats.native.common import check_cancel
from opendoc_formats.pdf import PdfLimits, PdfPlacedGlyph, PdfTextPlacement


@dataclass
class _PlacementBudget:
    limits: PdfLimits
    spans: int = 0
    glyphs: int = 0
    metadata_bytes: int = 0
    font_bytes: int = 0
    fonts: dict[int, tuple[Any, str | None]] = field(default_factory=dict)
    owner: Any = None
    closed: bool = False


@contextmanager
def placement_budget(limits: PdfLimits) -> Iterator[_PlacementBudget]:
    """Share bounded observation work within one open PDF; release native fonts before closing it."""
    state = _PlacementBudget(limits)
    try:
        yield state
    finally:
        state.fonts.clear()
        state.owner = None
        state.closed = True


def text_placements(page: Any, page_index: int, limits: PdfLimits,
                    cancelled: Callable[[], bool] | None, *, include_bounds: bool = True,
                    _budget: _PlacementBudget | None = None) -> tuple[PdfTextPlacement, ...]:
    if type(include_bounds) is not bool:
        raise ValueError('include_bounds must be boolean')
    state = _budget if _budget is not None else _PlacementBudget(limits)
    if state.closed:
        raise ValueError('Shared PDF placement budget is closed')
    if state.limits != limits:
        raise ValueError('Shared PDF placement budget requires unchanged limits')
    if state.owner is None:
        state.owner = page.parent
    elif state.owner is not page.parent:
        raise ValueError('Shared PDF placement budget belongs to another document')

    import pymupdf

    mupdf = pymupdf.mupdf
    result: list[PdfTextPlacement] = []
    font_cache = state.fonts

    def charge(value: Any) -> None:
        state.metadata_bytes += len(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))
        if state.metadata_bytes > limits.max_text_metadata_bytes:
            raise ResourceLimitError('PDF placements exceed max_text_metadata_bytes')

    class Device(mupdf.FzDevice2):  # type: ignore[misc,name-defined]  # Native virtual base has no static stub.
        def __init__(self) -> None:
            super().__init__()
            self.error: Exception | None = None
            for name in ('fill_text', 'stroke_text', 'ignore_text', 'clip_text', 'clip_stroke_text'):
                getattr(self, 'use_virtual_'+name)()

        def emit(self, operation: str, text: Any, matrix: Any, opacity: float | None) -> None:
            if self.error is not None:
                return
            try:
                check_cancel(cancelled)
                span = text.head
                while span:
                    check_cancel(cancelled)
                    if state.spans >= limits.max_text_spans:
                        raise ResourceLimitError('PDF placements exceed max_text_spans')
                    state.spans += 1
                    count = int(span.len)
                    if count < 0:
                        raise InvalidDocumentError('Negative native PDF glyph count')
                    state.glyphs += count
                    if state.glyphs > limits.max_text_chars:
                        raise ResourceLimitError('PDF placements exceed max_text_chars (glyph records)')
                    native = mupdf.FzTextSpan(span)
                    font = native.font()
                    buffer = font.m_internal.buffer
                    key = int(buffer.this) if buffer else 0
                    name = str(font.fz_font_name())
                    if opacity is not None and not math.isfinite(opacity):
                        raise InvalidDocumentError('Non-finite native PDF text opacity')
                    charge([page_index, len(result), operation, name, '0'*64 if buffer else None, opacity])
                    if key not in font_cache:
                        digest = None
                        if buffer:
                            size = int(buffer.len)
                            if size > limits.max_object_bytes:
                                raise ResourceLimitError('PDF placement font exceeds max_object_bytes')
                            state.font_bytes += size
                            if state.font_bytes > limits.max_inspection_bytes:
                                raise ResourceLimitError('PDF placement font digests exceed max_inspection_bytes')
                            # Borrowed buffer: copy bytes, never wrap it in an owning native FzBuffer.
                            data = mupdf.ll_fz_buffer_extract_copy(buffer)
                            if len(data) != size:
                                raise InvalidDocumentError('PDF placement font changed while copied')
                            check_cancel(cancelled)
                            digest = hashlib.sha256(data).hexdigest()
                        # Retain the class-aware FONT wrapper so an allocator cannot reuse a cached buffer address.
                        font_cache[key] = (font, digest)
                    glyphs = []
                    for index in range(span.len):
                        check_cancel(cancelled)
                        item = native.items(index)
                        local = mupdf.FzMatrix(span.trm)
                        local.e, local.f = item.x, item.y
                        placed = mupdf.fz_concat(local, mupdf.FzMatrix(matrix))
                        values = tuple(float(getattr(placed, key)) for key in ('a', 'b', 'c', 'd', 'e', 'f'))
                        a, b, c, d, e, f = values
                        if any(not math.isfinite(value) for value in values):
                            raise InvalidDocumentError('Non-finite PDF placement coordinates')
                        bbox = None
                        if item.gid >= 0 and include_bounds:
                            box = mupdf.fz_bound_glyph(font, item.gid, placed)
                            bbox = (float(box.x0), float(box.y0), float(box.x1), float(box.y1))
                        if any(not math.isfinite(value) for value in (bbox or ())):
                            raise InvalidDocumentError('Non-finite PDF placement coordinates')
                        code, identifier = int(item.ucs), int(item.gid)
                        charge([code, identifier, list(values), list(bbox) if bbox is not None else None])
                        glyphs.append(PdfPlacedGlyph(code, identifier, (a, b, c, d, e, f), bbox))
                    result.append(PdfTextPlacement(page_index, len(result), operation, name, font_cache[key][1],
                                                   opacity, tuple(glyphs)))
                    span = span.next
            except Exception as error:  # noqa: BLE001 - rethrown after the C callback boundary, never swallowed.
                # A callback traceback would retain borrowed native span/item wrappers past their lifetime.
                self.error = error.with_traceback(None)

        def fill_text(self, ctx: Any, text: Any, matrix: Any, colorspace: Any, color: Any,
                      alpha: float, params: Any) -> None:
            self.emit('fill', text, matrix, float(alpha))

        def stroke_text(self, ctx: Any, text: Any, stroke: Any, matrix: Any, colorspace: Any,
                        color: Any, alpha: float, params: Any) -> None:
            self.emit('stroke', text, matrix, float(alpha))

        def ignore_text(self, ctx: Any, text: Any, matrix: Any) -> None:
            self.emit('ignore', text, matrix, None)

        def clip_text(self, ctx: Any, text: Any, matrix: Any, scissor: Any) -> None:
            self.emit('clip', text, matrix, None)

        def clip_stroke_text(self, ctx: Any, text: Any, stroke: Any, matrix: Any, scissor: Any) -> None:
            self.emit('clip-stroke', text, matrix, None)

    check_cancel(cancelled)
    device = Device()
    failure = None
    try:
        mupdf.fz_run_page_contents(page.this, device, mupdf.FzMatrix(), mupdf.FzCookie())
    except (AttributeError, TypeError, RuntimeError, ValueError) as error:
        failure = error.with_traceback(None)
    finally:
        try:
            mupdf.fz_close_device(device)
        except (AttributeError, TypeError, RuntimeError, ValueError) as error:
            if failure is None:
                failure = error.with_traceback(None)
    callback_error = device.error
    device.error = None
    del device
    if _budget is None:
        font_cache.clear()
        state.owner = None
    if callback_error is not None:
        raise callback_error
    if failure is not None:
        raise failure
    check_cancel(cancelled)
    return tuple(result)
