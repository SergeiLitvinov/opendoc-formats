"""OpenType baseline metrics used by the fixed-layout Word writer."""

from __future__ import annotations

import struct
from functools import lru_cache
from io import BytesIO

from opendoc_model import TextStyle

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.common import read_source
from opendoc_formats.native.sfnt import SfntLimits, inspect_sfnt
from opendoc_formats.support.cancellation import cancellation_requested, checkpoint

_CACHE_ENTRIES = 64
_CACHE_INPUT_BYTES = 1024 * 1024


def _native_metrics(data: bytes) -> tuple[float, float]:
    limits = SfntLimits()
    inventory = inspect_sfnt(data, limits=limits, cancelled=cancellation_requested)
    tables = {table.tag: table for table in inventory.tables}
    head, horizontal = tables.get('head'), tables.get('hhea')
    if head is None or horizontal is None or head.length < 54 or horizontal.length < 36:
        raise UnsupportedDocumentError('Font baseline requires complete head/hhea tables')
    if data[head.offset:head.offset+4] != b'\0\1\0\0' or data[horizontal.offset:horizontal.offset+4] != b'\0\1\0\0':
        raise UnsupportedDocumentError('Unsupported head/hhea version for native baseline metrics')
    units = struct.unpack_from('>H', data, head.offset+18)[0]
    if not 16 <= units <= 16384:
        raise UnsupportedDocumentError('Font unitsPerEm outside native baseline profile')
    ascent, descent, gap = struct.unpack_from('>hhh', data, horizontal.offset+4)
    return (ascent+gap)/units, -descent/units


def _decode_metrics(data: bytes) -> tuple[float, float]:
    try:
        result = _native_metrics(data)
        checkpoint()
        return result
    except (InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError):
        checkpoint()
    return _engine_metrics(BytesIO(data))


def _engine_metrics(source: str | BytesIO) -> tuple[float, float]:
    checkpoint()
    from fontTools.ttLib import TTFont

    with TTFont(source, lazy=True) as font:
        checkpoint()
        units = font['head'].unitsPerEm
        horizontal = font['hhea']
        result = (horizontal.ascent + horizontal.lineGap) / units, -horizontal.descent / units
        checkpoint()
    checkpoint()
    return result


# At most 64 MiB of source bytes, plus small metrics/entry overhead. Larger
# bounded snapshots still use the same decoder, without retaining their bytes.
_cached_metrics = lru_cache(maxsize=_CACHE_ENTRIES)(_decode_metrics)


def _metrics(path: str) -> tuple[float, float] | None:
    checkpoint()
    try:
        try:
            data = read_source(path, SfntLimits().max_input_bytes, cancellation_requested)
        except (InvalidDocumentError, ResourceLimitError):
            # Preserve the established lazy-file path for oversized/unreadable snapshots.
            result = _engine_metrics(path)
        else:
            result = _cached_metrics(data) if len(data) <= _CACHE_INPUT_BYTES else _decode_metrics(data)
        checkpoint()
        return result
    except OperationCancelledError:
        raise
    except Exception:  # noqa: BLE001 - unresolved font metrics must remain unknown
        checkpoint()
        return None


def word_line_ascent(style: TextStyle) -> float | None:
    resolution = style.properties.get('font_resolution')
    if not style.font_family or style.font_size is None or not isinstance(resolution, dict) or not resolution.get('path'):
        return None
    metrics = _metrics(str(resolution['path']))
    return metrics[0] * style.font_size.pt if metrics is not None else None


def word_line_descent(style: TextStyle) -> float | None:
    resolution = style.properties.get('font_resolution')
    if not style.font_family or style.font_size is None or not isinstance(resolution, dict) or not resolution.get('path'):
        return None
    metrics = _metrics(str(resolution['path']))
    return metrics[1] * style.font_size.pt if metrics is not None else None
