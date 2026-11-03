"""Physical PNG chunks and finite IHDR/critical-order audit, without pixel decoding."""

from __future__ import annotations

import hashlib
import struct
import zlib
from typing import TYPE_CHECKING, Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.png_metadata import inspect_metadata
from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import AnatomyLimits, BinaryItem

SIGNATURE = b'\x89PNG\r\n\x1a\n'
DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}


def inspect_png(data: bytes, limits: AnatomyLimits, capture: bool) -> tuple[tuple[BinaryItem, ...], dict[str, Any]]:
    """Keep complete original chunk bytes; CRC/core structure do not prove valid pixels or color metadata."""
    from opendoc_formats.anatomy import BinaryItem

    checkpoint()
    if not data.startswith(SIGNATURE):
        raise InvalidDocumentError('png:signature: missing PNG signature')
    if len(data) > limits.max_total_bytes or limits.max_part_bytes < 8:
        raise ResourceLimitError('png:signature: max_total_bytes/max_part_bytes exceeded')
    items = [BinaryItem('png:signature', 'png-signature', 8, hashlib.sha256(SIGNATURE).hexdigest(),
                        payload=SIGNATURE if capture else None)]
    offset = 8
    header: dict[str, Any] = {}
    palette = idat = idat_closed = False
    unknown_critical: list[str] = []
    ancillary: list[str] = []
    while offset < len(data):
        checkpoint()
        location = f'png:chunk={len(items) - 1}'
        if len(items) >= limits.max_items:
            raise ResourceLimitError(f'{location}: max_items exceeded')
        if len(data) - offset < 12:
            raise InvalidDocumentError(f'{location}: truncated chunk header/data/CRC')
        length, kind = struct.unpack_from('>I4s', data, offset)
        if length > 0x7fffffff or any(not (65 <= value <= 90 or 97 <= value <= 122) for value in kind):
            raise InvalidDocumentError(f'{location}: invalid chunk length/type')
        size = length + 12
        if size > limits.max_part_bytes:
            raise ResourceLimitError(f'{location}: max_part_bytes exceeded')
        stop = offset + size
        if stop > len(data):
            raise InvalidDocumentError(f'{location}: chunk extends beyond source')
        declared = struct.unpack_from('>I', data, stop - 4)[0]
        actual = zlib.crc32(memoryview(data)[offset + 4:stop - 4])
        checkpoint()
        if actual != declared:
            raise InvalidDocumentError(f'{location}: CRC mismatch')
        name = kind.decode('ascii')
        if not header and kind != b'IHDR':
            raise InvalidDocumentError(f'{location}: IHDR must be first')
        if kind == b'IHDR':
            if header or length != 13:
                raise InvalidDocumentError(f'{location}: duplicate or invalid IHDR')
            width, height, depth, color, compression, filtering, interlace = struct.unpack_from('>IIBBBBB', data, offset + 8)
            if not (0 < width <= 0x7fffffff and 0 < height <= 0x7fffffff) or depth not in DEPTHS.get(color, ()):
                raise InvalidDocumentError(f'{location}: invalid dimensions or depth/color combination')
            if compression != 0 or filtering != 0 or interlace not in (0, 1):
                raise UnsupportedDocumentError(f'{location}: unsupported compression/filter/interlace profile')
            header = {'width': width, 'height': height, 'bit_depth': depth, 'color_type': color,
                      'compression': compression, 'filter': filtering, 'interlace': interlace}
        elif kind == b'PLTE':
            entries = length // 3
            if (palette or idat or not length or length % 3 or entries > 256
                    or header['color_type'] in (0, 4)
                    or header['color_type'] == 3 and entries > 2 ** header['bit_depth']):
                raise InvalidDocumentError(f'{location}: invalid PLTE size/order/color profile')
            palette = True
        elif kind == b'IDAT':
            if idat_closed or header['color_type'] == 3 and not palette:
                raise InvalidDocumentError(f'{location}: IDAT order or required palette is invalid')
            idat = True
        elif kind == b'IEND':
            if length or not idat or stop != len(data):
                raise InvalidDocumentError(f'{location}: invalid IEND or trailing bytes')
        if kind != b'IDAT' and idat:
            idat_closed = True
        if kind[0] & 32:
            ancillary.append(name)
        elif kind not in (b'IHDR', b'PLTE', b'IDAT', b'IEND'):
            unknown_critical.append(name)
        chunk = memoryview(data)[offset:stop]
        items.append(BinaryItem(location + ':' + name, 'png-chunk', size, hashlib.sha256(chunk).hexdigest(),
                                details=(('chunk_type', name), ('offset', offset), ('data_offset', offset + 8),
                                         ('data_length', length), ('crc32', declared), ('crc_verified', True),
                                         ('ancillary', bool(kind[0] & 32)), ('private', bool(kind[1] & 32)),
                                         ('reserved_bit_set', bool(kind[2] & 32)), ('safe_to_copy', bool(kind[3] & 32))),
                                payload=bytes(chunk) if capture else None))
        offset = stop
        if kind == b'IEND':
            checkpoint()
            return tuple(items), {**header, 'core_chunk_order_assessed': True, 'crc_verified': True,
                                  'unknown_critical_chunks': tuple(unknown_critical), 'ancillary_chunks': tuple(ancillary),
                                  **inspect_metadata(data, items, header),
                                  'image_data_assessed': False, 'ancillary_semantics_assessed': False,
                                  'assessment_complete': False}
    raise InvalidDocumentError('png:end: missing IEND')


__all__ = ['SIGNATURE', 'inspect_png']
