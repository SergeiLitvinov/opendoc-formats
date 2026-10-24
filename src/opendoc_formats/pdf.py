"""Public, bounded PDF page access without exposing the optional rendering engine."""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, fields
from typing import Any, TypeAlias

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
    max_objects: int = 100_000
    max_object_bytes: int = 32 * 1024 * 1024
    max_inspection_bytes: int = 256 * 1024 * 1024
    max_text_spans: int = 100_000
    max_text_metadata_bytes: int = 8 * 1024 * 1024

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


@dataclass(frozen=True)
class PdfGlyphInfo:
    unicode: int
    glyph_id: int
    origin: tuple[float, float]
    bbox: tuple[float, float, float, float]


PdfTextScalar: TypeAlias = str | int | float | bool | None
PdfTextValue: TypeAlias = PdfTextScalar | tuple[PdfTextScalar, ...]


@dataclass(frozen=True)
class PdfTextSpan:
    page_index: int
    span_index: int
    seqno: int
    paint_type: int
    font: str
    font_size: float
    bbox: tuple[float, float, float, float]
    direction: tuple[float, float]
    opacity: float
    glyphs: tuple[PdfGlyphInfo, ...]
    metadata: tuple[tuple[str, PdfTextValue], ...] = ()

    @property
    def text(self) -> str | None:
        """Backend Unicode sequence only; an invalid scalar leaves the sequence unknown."""
        if any(not 0 <= glyph.unicode <= 0x10ffff or 0xd800 <= glyph.unicode <= 0xdfff for glyph in self.glyphs):
            return None
        return ''.join(chr(glyph.unicode) for glyph in self.glyphs)


@dataclass(frozen=True)
class PdfObjectInfo:
    """Active xref slot: normalized dictionary and encoded stream, without decoding."""

    xref: int
    dictionary: str
    raw_stream: bytes | None


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

    @property
    def object_count(self) -> int:
        self._check_open()
        count = int(self._document.xref_length()) - 1
        if count > self._limits.max_objects:
            raise ResourceLimitError('PDF xref slots exceed max_objects')
        check_cancel(self._cancelled)
        return count

    @property
    def trailer(self) -> str:
        self._check_open()
        value = str(self._document.pdf_trailer())
        if len(value.encode('utf-8')) > self._limits.max_object_bytes:
            raise ResourceLimitError('PDF trailer exceeds max_object_bytes')
        check_cancel(self._cancelled)
        return value

    @property
    def repaired(self) -> bool:
        self._check_open()
        return bool(self._document.is_repaired)

    def iter_objects(self) -> Iterator[PdfObjectInfo]:
        """Inspect the active object table. Historical revisions/free-slot identity are not inferred."""
        total = 0
        for xref in range(1, self.object_count + 1):
            self._check_open()
            try:
                dictionary = str(self._document.xref_object(xref, compressed=False, ascii=True))
                dictionary_size = len(dictionary.encode('utf-8'))
                if dictionary_size > self._limits.max_object_bytes:
                    raise ResourceLimitError(f'PDF xref={xref} dictionary exceeds max_object_bytes')
                check_cancel(self._cancelled)
                is_stream = bool(self._document.xref_is_stream(xref))
                stream = self._document.xref_stream_raw(xref) if is_stream else None
                if is_stream and not isinstance(stream, bytes):
                    raise InvalidDocumentError(f'PDF xref={xref} returned an invalid encoded stream')
                size = dictionary_size + (len(stream) if stream is not None else 0)
                if size > self._limits.max_object_bytes:
                    raise ResourceLimitError(f'PDF xref={xref} exceeds max_object_bytes')
                total += size
                if total > self._limits.max_inspection_bytes:
                    raise ResourceLimitError(f'PDF xref={xref} exceeds max_inspection_bytes')
            except ResourceLimitError:
                raise
            except (RuntimeError, ValueError) as error:
                raise InvalidDocumentError(f'Cannot inspect PDF xref={xref}: {error}') from error
            check_cancel(self._cancelled)
            yield PdfObjectInfo(xref, dictionary, stream)

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
            with self._preserve_rotation(page):
                text = page.get_text("text")
                result = PdfPageInfo(index, float(page.rect.width), float(page.rect.height), int(page.rotation), text)
        except NativeAccessError:
            raise
        except (RuntimeError, ValueError) as error:
            raise InvalidDocumentError(f"Cannot read PDF page {index}: {error}") from error
        if len(text) > self._limits.max_text_chars:
            raise ResourceLimitError("PDF page text exceeds character limit")
        check_cancel(self._cancelled)
        return result

    def page_text_spans(self, index: int) -> tuple[PdfTextSpan, ...]:
        """Observe bounded native glyph/paint spans; never infer reading order or clipping visibility."""
        page = self._page(index)
        try:
            with self._preserve_rotation(page):
                raw = page.get_texttrace()
        except NativeAccessError:
            raise
        except (RuntimeError, ValueError) as error:
            raise InvalidDocumentError(f'Cannot inspect PDF page {index} text: {error}') from error
        check_cancel(self._cancelled)
        from opendoc_formats.native.pdf_text import text_spans

        result = text_spans(raw, index, self._limits, self._cancelled)
        check_cancel(self._cancelled)
        return result

    @contextmanager
    def _preserve_rotation(self, page: Any) -> Iterator[None]:
        # Text backends temporarily change rotation and may flatten its inheritance.
        rotation = self._document.xref_get_key(page.xref, 'Rotate')
        original = self._document.xref_object(page.xref, compressed=False, ascii=True)
        if len(original.encode('utf-8')) > self._limits.max_object_bytes:
            raise ResourceLimitError(f'PDF xref={page.xref} dictionary exceeds max_object_bytes')
        try:
            yield
        finally:
            if self._document is not None and self._document.xref_get_key(page.xref, 'Rotate') != rotation:
                # Setting "null" does not remove the key on every supported backend.
                self._document.update_object(page.xref, original)
                self._document.reload_page(page)

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


__all__ = ["PdfDocument", "PdfLimits", "PdfObjectInfo", "PdfPageInfo", "RenderedPage",
           "PdfGlyphInfo", "PdfTextSpan", "PdfTextScalar", "PdfTextValue"]
