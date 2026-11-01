"""Bounded Flate stream decoding shared by physical PDF inventories."""

from __future__ import annotations

import zlib

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError
from opendoc_formats.support.cancellation import checkpoint


def inflate(raw: memoryview, maximum: int, location: str, *, expected: int | None = None) -> bytearray:
    decoder = zlib.decompressobj()
    output = bytearray()
    limit = min(maximum, expected) if expected is not None else maximum
    if limit < 0:
        raise ResourceLimitError(location+'no remaining decoded byte budget')
    try:
        for offset in range(0, len(raw), 65536):
            checkpoint()
            chunk: bytes | memoryview = raw[offset:offset+65536]
            while chunk:
                checkpoint()
                output.extend(decoder.decompress(chunk, min(65536, limit-len(output)+1)))
                if len(output) > limit:
                    if expected is not None and limit == expected:
                        raise InvalidDocumentError(location+'decoded stream exceeds declared record length')
                    raise ResourceLimitError(location+'decoded stream exceeds byte budget')
                if decoder.unused_data:
                    raise InvalidDocumentError(location+'trailing bytes after zlib stream')
                chunk = decoder.unconsumed_tail
    except zlib.error as error:
        raise InvalidDocumentError(location+'invalid FlateDecode data') from error
    if not decoder.eof or (expected is not None and len(output) != expected):
        raise InvalidDocumentError(location+'truncated FlateDecode data or wrong decoded length')
    return output
