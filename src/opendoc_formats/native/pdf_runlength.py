"""Bounded PDF RunLengthDecode; no image/PDF backend and no input rewriting."""

from __future__ import annotations

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError
from opendoc_formats.support.cancellation import checkpoint


def unpack(raw: memoryview, maximum: int, location: str, *, expected: int | None = None) -> tuple[bytearray, int]:
    """Return decoded bytes and input consumed through EOD; charge before every append."""
    limit = min(maximum, expected) if expected is not None else maximum
    if limit < 0:
        raise ResourceLimitError(location+'no remaining decoded byte budget')
    output = bytearray()
    cursor = 0
    while cursor < len(raw):
        checkpoint()
        tag = raw[cursor]
        cursor += 1
        if tag == 128:
            if expected is not None and len(output) != expected:
                raise InvalidDocumentError(location+'RunLengthDecode EOD disagrees with decoded length')
            return output, cursor
        count = tag+1 if tag < 128 else 257-tag
        consumed = count if tag < 128 else 1
        if cursor+consumed > len(raw):
            raise InvalidDocumentError(location+'truncated RunLengthDecode run')
        if len(output)+count > limit:
            if expected is not None and limit == expected:
                raise InvalidDocumentError(location+'RunLengthDecode exceeds declared record length')
            raise ResourceLimitError(location+'RunLengthDecode exceeds decoded byte budget')
        output.extend(raw[cursor:cursor+count] if tag < 128 else bytes([raw[cursor]])*count)
        cursor += consumed
    raise InvalidDocumentError(location+'missing RunLengthDecode EOD')
