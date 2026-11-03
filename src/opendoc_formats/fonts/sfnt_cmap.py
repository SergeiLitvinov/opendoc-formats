"""Finite Unicode cmap declarations, without glyph-name decoding or shaping."""

from __future__ import annotations

import struct
from collections.abc import Iterator

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.common import positive_int
from opendoc_formats.native.sfnt import inspect_sfnt
from opendoc_formats.support.cancellation import cancellation_requested, checkpoint

_PREFERENCES = ((3, 10), (0, 6), (0, 4), (3, 1), (0, 3), (0, 2), (0, 1), (0, 0))


def read_unicode_coverage(data: bytes, *, max_codepoints: int = 131072, face_index: int | None = None) -> frozenset[int]:
    """Return nonzero declared mappings from the same preferred Unicode subtable as before."""
    return frozenset(code for code, _ in _unicode_pairs(data, max_codepoints, face_index))


def read_unicode_mapping(data: bytes, *, max_codepoints: int = 131072, face_index: int | None = None) -> dict[int, int]:
    """Return declared codepoint → numeric glyph ID; no glyph-name or shaping inference."""
    return dict(_unicode_pairs(data, max_codepoints, face_index))


def _unicode_pairs(data: bytes, max_codepoints: int, face_index: int | None) -> Iterator[tuple[int, int]]:
    positive_int(max_codepoints, 'max_codepoints')
    inventory = inspect_sfnt(data, cancelled=cancellation_requested, face_index=face_index)
    table = next((table for table in inventory.tables if table.tag == 'cmap'), None)
    if table is None or table.length < 4:
        raise UnsupportedDocumentError('sfnt:cmap: missing or truncated table')
    cmap = memoryview(data)[table.offset:table.offset+table.length]
    version, count = struct.unpack_from('>2H', cmap)
    if version != 0 or count > 4096:
        raise UnsupportedDocumentError('sfnt:cmap: version/record count outside native profile')
    if 4+8*count > len(cmap):
        raise InvalidDocumentError('sfnt:cmap: truncated encoding records')
    records: dict[tuple[int, int], memoryview] = {}
    for index in range(count):
        checkpoint()
        platform, encoding, offset = struct.unpack_from('>2HI', cmap, 4+8*index)
        if offset < 4+8*count or offset+4 > len(cmap):
            raise InvalidDocumentError('sfnt:cmap: subtable offset outside data area')
        kind = struct.unpack_from('>H', cmap, offset)[0]
        if kind in (0, 2, 4, 6):
            length = struct.unpack_from('>H', cmap, offset+2)[0]
            minimum = 16 if kind == 4 else 6
        elif kind in (12, 13):
            if offset+16 > len(cmap):
                raise InvalidDocumentError('sfnt:cmap: truncated group header')
            reserved, length, _, groups = struct.unpack_from('>H3I', cmap, offset+2)
            if reserved or length != 16+12*groups:
                raise UnsupportedDocumentError('sfnt:cmap: group header outside native profile')
            minimum = 16
        elif kind == 14:
            if offset+10 > len(cmap):
                raise InvalidDocumentError('sfnt:cmap: truncated variation header')
            length = struct.unpack_from('>I', cmap, offset+2)[0]
            minimum = 10
        else:
            raise UnsupportedDocumentError('sfnt:cmap: subtable format outside native 0/2/4/6/12/13 profile')
        if length < minimum or offset+length > len(cmap):
            raise InvalidDocumentError('sfnt:cmap: subtable length outside source')
        records.setdefault((platform, encoding), cmap[offset:offset+length])
    selected = next((records[key] for key in _PREFERENCES if key in records), None)
    if selected is None:
        checkpoint()
        return
    kind = struct.unpack_from('>H', selected)[0]
    if kind in (0, 6):
        yield from _array(selected, kind, max_codepoints)
    elif kind == 2:
        yield from _high_bytes(selected, max_codepoints)
    elif kind == 4:
        yield from _segments(selected, max_codepoints)
    elif kind in (12, 13):
        yield from _groups(selected, kind, max_codepoints)
    else:
        raise UnsupportedDocumentError('sfnt:cmap: selected subtable outside native 0/2/4/6/12/13 profile')
    checkpoint()


def _high_bytes(data: memoryview, maximum: int) -> Iterator[tuple[int, int]]:
    if len(data) < 526 or len(data) % 2:
        raise InvalidDocumentError('sfnt:cmap2: truncated keys/subheaders or odd length')
    keys = struct.unpack_from('>256H', data, 6)
    if keys[0] or any(key % 8 for key in keys):
        raise UnsupportedDocumentError('sfnt:cmap2: noncanonical subheader keys')
    count = max(keys)//8+1
    arrays = 518+8*count
    if arrays > len(data):
        raise InvalidDocumentError('sfnt:cmap2: subheader array outside source')
    headers = []
    for index in range(count):
        checkpoint()
        position = 518+8*index
        first, size, delta, offset = struct.unpack_from('>2HhH', data, position)
        if first > 255 or first+size > 256 or offset % 2:
            raise UnsupportedDocumentError('sfnt:cmap2: byte range or glyph offset outside native profile')
        address = position+6+offset
        if size and (address < arrays or address+2*size > len(data)):
            raise InvalidDocumentError('sfnt:cmap2: glyph array address outside source')
        headers.append((first, size, delta, address))
    work = 0
    for high, key in enumerate(keys):
        checkpoint()
        first, size, delta, address = headers[key//8]
        if key:
            indices = range(size)
        elif first <= high < first+size:
            indices = range(high-first, high-first+1)
        else:
            continue
        for index in indices:
            checkpoint()
            work += 1
            if work > maximum:
                raise ResourceLimitError('sfnt:cmap: codepoint work budget exceeded')
            raw = struct.unpack_from('>H', data, address+2*index)[0]
            glyph = (raw+delta) & 0xffff if raw else 0
            if glyph:
                yield (high*256+first+index if key else high), glyph


def _array(data: memoryview, kind: int, maximum: int) -> Iterator[tuple[int, int]]:
    if kind == 0:
        if len(data) != 262:
            raise InvalidDocumentError('sfnt:cmap0: expected 256 glyph entries')
        first, count, offset, width = 0, 256, 6, 1
    else:
        if len(data) < 10:
            raise InvalidDocumentError('sfnt:cmap6: truncated array header')
        first, count = struct.unpack_from('>2H', data, 6)
        if len(data) != 10+2*count or first+count > 0x10000:
            # The engine can recover some nonconforming arrays. Keep that policy there.
            raise UnsupportedDocumentError('sfnt:cmap6: array outside native BMP profile')
        offset, width = 10, 2
    if count > maximum:
        raise ResourceLimitError('sfnt:cmap: codepoint work budget exceeded')
    for index in range(count):
        checkpoint()
        glyph = data[offset+index] if width == 1 else struct.unpack_from('>H', data, offset+2*index)[0]
        if glyph:
            yield first+index, glyph


def _segments(data: memoryview, maximum: int) -> Iterator[tuple[int, int]]:
    twice = struct.unpack_from('>H', data, 6)[0]
    count = twice//2
    if not twice or twice % 2 or len(data) % 2 or 16+8*count > len(data):
        raise InvalidDocumentError('sfnt:cmap4: invalid segment arrays')
    if struct.unpack_from('>H', data, 14+2*count)[0]:
        raise UnsupportedDocumentError('sfnt:cmap4: nonzero reserved pad')
    previous = -1
    work = 0
    for index in range(count):
        checkpoint()
        end = struct.unpack_from('>H', data, 14+2*index)[0]
        start = struct.unpack_from('>H', data, 16+2*count+2*index)[0]
        delta = struct.unpack_from('>h', data, 16+4*count+2*index)[0]
        word = 16+6*count+2*index
        offset = struct.unpack_from('>H', data, word)[0]
        if start > end or start <= previous or offset % 2:
            raise UnsupportedDocumentError('sfnt:cmap4: unordered/overlapping segment or odd glyph offset')
        previous = end
        if index == count-1:
            if start != 0xffff or end != 0xffff:
                raise UnsupportedDocumentError('sfnt:cmap4: missing terminal segment')
            break
        work += end-start+1
        if work > maximum:
            raise ResourceLimitError('sfnt:cmap: codepoint work budget exceeded')
        for codepoint in range(start, end+1):
            checkpoint()
            if offset:
                address = word+offset+2*(codepoint-start)
                if address < 16+8*count or address+2 > len(data):
                    raise InvalidDocumentError('sfnt:cmap4: glyph array address outside source')
                raw = struct.unpack_from('>H', data, address)[0]
                glyph = (raw+delta) & 0xffff if raw else 0
            else:
                glyph = (codepoint+delta) & 0xffff
            if glyph:
                yield codepoint, glyph


def _groups(data: memoryview, kind: int, maximum: int) -> Iterator[tuple[int, int]]:
    count = struct.unpack_from('>I', data, 12)[0]
    previous = -1
    work = 0
    for index in range(count):
        checkpoint()
        start, end, glyph = struct.unpack_from('>3I', data, 16+12*index)
        if start > end or end > 0x10ffff or start <= previous:
            raise UnsupportedDocumentError('sfnt:cmap: group order/range outside native profile')
        previous = end
        work += end-start+1
        if work > maximum:
            raise ResourceLimitError('sfnt:cmap: codepoint work budget exceeded')
        if kind == 12 and glyph+end-start > 0xffffffff:
            raise UnsupportedDocumentError('sfnt:cmap12: glyph range overflows uint32')
        for codepoint in range(start, end+1):
            checkpoint()
            if glyph or (kind == 12 and codepoint > start):
                yield codepoint, glyph+codepoint-start if kind == 12 else glyph
