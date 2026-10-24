"""Bounded immutable copies of native PDF text observations; no layout or Unicode repair."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.common import Cancellation, check_cancel

if TYPE_CHECKING:
    from opendoc_formats.pdf import PdfLimits, PdfTextScalar, PdfTextSpan, PdfTextValue


def _integer(value: Any) -> int:
    if type(value) is not int:
        raise InvalidDocumentError('Invalid PDF text integer')
    return value


def _number(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise InvalidDocumentError('Non-finite PDF text coordinate/metric')
    return float(value)


def _point(value: Any) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise InvalidDocumentError('Invalid PDF glyph origin/direction')
    return _number(value[0]), _number(value[1])


def _box(value: Any) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise InvalidDocumentError('Invalid PDF text bounds')
    box = _number(value[0]), _number(value[1]), _number(value[2]), _number(value[3])
    if box[2] < box[0] or box[3] < box[1]:
        raise InvalidDocumentError('Reversed PDF text bounds')
    return box


def _scalar(value: Any, remaining: int) -> PdfTextScalar:
    if value is None or type(value) in (str, int, float, bool):
        if isinstance(value, str) and len(value) > remaining:
            raise ResourceLimitError('PDF text exceeds max_text_metadata_bytes')
        if type(value) is float and not math.isfinite(value):
            raise InvalidDocumentError('Non-finite PDF text metadata')
        return value  # type: ignore[no-any-return]
    raise UnsupportedDocumentError('PDF text metadata is outside the scalar inspection profile')


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8'))
    except (ValueError, UnicodeError) as error:
        raise InvalidDocumentError('Invalid native PDF text metadata encoding') from error


def _copy_value(value: Any, remaining: int, cancelled: Cancellation | None) -> tuple[PdfTextValue, int]:
    if isinstance(value, (list, tuple)):
        size, copied = 2, []
        for index, component in enumerate(value):
            check_cancel(cancelled)
            item = _scalar(component, max(0, remaining-size))
            size += _json_size(item) + (1 if index else 0)
            if size > remaining:
                raise ResourceLimitError('PDF text exceeds max_text_metadata_bytes')
            copied.append(item)
        result: PdfTextValue = tuple(copied)
    else:
        result = _scalar(value, remaining)
        size = _json_size(result)
    if size > remaining:
        raise ResourceLimitError('PDF text exceeds max_text_metadata_bytes')
    return result, size


def text_spans(raw: Any, page_index: int, limits: PdfLimits, cancelled: Cancellation | None) -> tuple[PdfTextSpan, ...]:
    from opendoc_formats.pdf import PdfGlyphInfo, PdfTextSpan

    if not isinstance(raw, (list, tuple)):
        raise InvalidDocumentError('Invalid native PDF text trace')
    if len(raw) > limits.max_text_spans:
        raise ResourceLimitError('PDF text exceeds max_text_spans')
    result, characters, metadata_bytes = [], 0, 0
    core = {'seqno', 'type', 'font', 'size', 'bbox', 'dir', 'opacity'}
    for ordinal, span in enumerate(raw):
        check_cancel(cancelled)
        if not isinstance(span, dict) or not core <= span.keys() or 'chars' not in span:
            raise InvalidDocumentError(f'PDF page {page_index} span {ordinal}: missing native text fields')
        chars = span['chars']
        if not isinstance(chars, (list, tuple)):
            raise InvalidDocumentError('Invalid native PDF glyph sequence')
        characters += len(chars)
        if characters > limits.max_text_chars:
            raise ResourceLimitError('PDF glyph observations exceed max_text_chars')
        values: dict[str, PdfTextValue] = {}
        metadata_bytes += 2  # compact JSON object braces, excluding chars
        for key, value in span.items():
            check_cancel(cancelled)
            if key == 'chars':
                continue
            remaining = limits.max_text_metadata_bytes - metadata_bytes
            if not isinstance(key, str):
                raise InvalidDocumentError('Invalid native PDF text metadata key')
            if len(key) > remaining:
                raise ResourceLimitError('PDF text exceeds max_text_metadata_bytes')
            key_size = _json_size(key) + 1 + (1 if values else 0)
            copied, size = _copy_value(value, remaining-key_size, cancelled)
            metadata_bytes += key_size+size
            values[key] = copied
        font = values['font']
        if not isinstance(font, str):
            raise InvalidDocumentError('Invalid native PDF font name')
        opacity = _number(values['opacity'])
        if not 0 <= opacity <= 1:
            raise InvalidDocumentError('Invalid native PDF text opacity')
        glyphs = []
        for character in chars:
            check_cancel(cancelled)
            if not isinstance(character, (list, tuple)) or len(character) != 4:
                raise InvalidDocumentError('Invalid native PDF glyph record')
            glyphs.append(PdfGlyphInfo(_integer(character[0]), _integer(character[1]), _point(character[2]), _box(character[3])))
        result.append(PdfTextSpan(
            page_index, ordinal, _integer(values['seqno']), _integer(values['type']), font, _number(values['size']),
            _box(values['bbox']), _point(values['dir']), opacity, tuple(glyphs),
            tuple(sorted((key, value) for key, value in values.items() if key not in core)),
        ))
    check_cancel(cancelled)
    return tuple(result)
