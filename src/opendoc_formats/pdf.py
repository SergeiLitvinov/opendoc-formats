"""Public, bounded PDF page access without exposing the optional rendering engine."""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass, fields
from typing import Any

from opendoc_formats.errors import (
    DocumentClosedError,
    EncryptedDocumentError,
    InvalidDocumentError,
    NativeAccessError,
    PageIndexError,
    ResourceLimitError,
)
from opendoc_formats.native.common import Cancellation, Source, backend, check_cancel, positive_int, positive_number, read_source


@dataclass(frozen=True)
class PdfLimits:
    max_input_bytes: int = 128 * 1024 * 1024
    max_pages: int = 10_000
    max_dimension: int = 8192
    max_pixels: int = 16_000_000
    max_png_bytes: int = 32 * 1024 * 1024
    max_text_chars: int = 4_000_000
    cache_bytes: int = 32 * 1024 * 1024
    cache_pages: int = 8

    def __post_init__(self) -> None:
        for item in fields(self):
            positive_int(getattr(self, item.name), item.name, zero=item.name == "cache_bytes")


@dataclass(frozen=True)
class PdfPageInfo:
    index: int
    width: float
    height: float
    rotation: int
    text: str


@dataclass(frozen=True)
class RenderedPage:
    index: int
    png: bytes
    width: int
    height: int
    effective_scale: float


class PdfDocument:
    """An owned PDF context. Native calls are cancellable only at their boundaries."""

    def __init__(self, source: Source, *, limits: PdfLimits = PdfLimits(), cancelled: Cancellation | None = None) -> None:
        if not isinstance(limits, PdfLimits):
            raise TypeError("limits must be PdfLimits")
        if cancelled is not None and not callable(cancelled):
            raise TypeError("cancelled must be callable")
        self._limits = limits
        self._cancelled = cancelled
        self._document: Any = None
        self._cache: OrderedDict[tuple[int, float, float], RenderedPage] = OrderedDict()
        self._cached_bytes = 0
        data = read_source(source, limits.max_input_bytes, cancelled)
        self._engine = backend("pymupdf", "pdf")
        try:
            self._document = self._engine.open(stream=data, filetype="pdf")
            if not self._document.is_pdf:
                raise InvalidDocumentError("Expected a PDF document")
            if self._document.needs_pass or self._document.is_encrypted:
                raise EncryptedDocumentError("Password-protected PDF is not accepted")
            if not 0 < self._document.page_count <= limits.max_pages:
                if self._document.page_count > limits.max_pages:
                    raise ResourceLimitError(f"PDF exceeds {limits.max_pages} pages")
                raise InvalidDocumentError("PDF contains no pages")
            check_cancel(cancelled)
        except Exception as error:  # noqa: BLE001 - release the native document on every constructor failure
            self.close()
            if isinstance(error, (InvalidDocumentError, ResourceLimitError)):
                raise
            from opendoc_formats.errors import OperationCancelledError

            if isinstance(error, OperationCancelledError):
                raise
            raise InvalidDocumentError(f"Cannot open PDF: {error}") from error

    def __enter__(self) -> PdfDocument:
        self._check_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        document, self._document = self._document, None
        self._cache.clear()
        self._cached_bytes = 0
        if document is not None:
            document.close()

    @property
    def closed(self) -> bool:
        return self._document is None

    def _check_open(self) -> None:
        if self.closed:
            raise DocumentClosedError("PDF context is closed")
        check_cancel(self._cancelled)

    @property
    def page_count(self) -> int:
        self._check_open()
        return int(self._document.page_count)

    def _page(self, index: int) -> Any:
        self._check_open()
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError("page index must be an integer")
        if not 0 <= index < self.page_count:
            raise PageIndexError(f"PDF page index {index} is out of range")
        try:
            return self._document.load_page(index)
        except (RuntimeError, ValueError) as error:
            raise InvalidDocumentError(f"Cannot load PDF page {index}: {error}") from error

    def page_info(self, index: int) -> PdfPageInfo:
        page = self._page(index)
        try:
            text = page.get_text("text")
            result = PdfPageInfo(index, float(page.rect.width), float(page.rect.height), int(page.rotation), text)
        except (RuntimeError, ValueError) as error:
            raise InvalidDocumentError(f"Cannot read PDF page {index}: {error}") from error
        if len(text) > self._limits.max_text_chars:
            raise ResourceLimitError("PDF page text exceeds character limit")
        check_cancel(self._cancelled)
        return result

    def render_page(
        self,
        index: int,
        *,
        dpi: float | None = None,
        scale: float | None = None,
        max_dimension: int | None = None,
        rotation: float = 0,
    ) -> RenderedPage:
        if dpi is not None and scale is not None:
            raise ValueError("dpi and scale are mutually exclusive")
        factor = positive_number(scale, "scale") if scale is not None else positive_number(dpi or 96, "dpi") / 72
        if dpi is not None:
            positive_number(dpi, "dpi")
        if isinstance(rotation, bool) or not isinstance(rotation, (float, int)) or not math.isfinite(rotation):
            raise ValueError("rotation must be finite degrees")
        rotation = float(rotation) % 360
        maximum = self._limits.max_dimension
        if max_dimension is not None:
            positive_int(max_dimension, "max_dimension")
            maximum = min(maximum, max_dimension)
        page = self._page(index)
        rotated = page.rect * self._engine.Matrix(1, 1).prerotate(rotation)
        if not all(math.isfinite(value) and value > 0 for value in (rotated.width, rotated.height)):
            raise InvalidDocumentError("PDF page has invalid dimensions")
        factor = min(factor, maximum / max(rotated.width, rotated.height))
        factor = min(factor, math.sqrt(self._limits.max_pixels / (rotated.width * rotated.height)))
        for _ in range(12):
            matrix = self._engine.Matrix(factor, factor).prerotate(rotation)
            bounds = (page.rect * matrix).irect
            width, height = bounds.width, bounds.height
            if 0 < width <= maximum and 0 < height <= maximum and width * height <= self._limits.max_pixels:
                break
            factor *= 0.99
        else:
            raise ResourceLimitError("Cannot fit PDF raster within dimensions/pixel limit")
        key = (index, factor, rotation)
        if key in self._cache:
            self._cache.move_to_end(key)
            check_cancel(self._cancelled)
            return self._cache[key]
        check_cancel(self._cancelled)
        try:
            pixmap = page.get_pixmap(matrix=matrix, colorspace=self._engine.csRGB, alpha=False)
            if pixmap.width > maximum or pixmap.height > maximum or pixmap.width * pixmap.height > self._limits.max_pixels:
                raise ResourceLimitError("Rendered PDF raster exceeds limits")
            pixmap.set_dpi(max(1, round(factor * 72)), max(1, round(factor * 72)))
            png = pixmap.tobytes("png")
            result = RenderedPage(index, png, pixmap.width, pixmap.height, factor)
        except NativeAccessError:
            raise
        except (RuntimeError, ValueError) as error:
            raise InvalidDocumentError(f"Cannot render PDF page {index}: {error}") from error
        if len(png) > self._limits.max_png_bytes:
            raise ResourceLimitError("PDF PNG exceeds output limit")
        check_cancel(self._cancelled)
        if len(png) <= self._limits.cache_bytes:
            while self._cache and (
                self._cached_bytes + len(png) > self._limits.cache_bytes or len(self._cache) >= self._limits.cache_pages
            ):
                _, removed = self._cache.popitem(last=False)
                self._cached_bytes -= len(removed.png)
            self._cache[key] = result
            self._cached_bytes += len(png)
        return result


__all__ = ["PdfDocument", "PdfLimits", "PdfPageInfo", "RenderedPage"]
