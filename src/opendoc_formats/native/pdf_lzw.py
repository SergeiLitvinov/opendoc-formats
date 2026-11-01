"""Bounded PDF LZWDecode with a fixed prefix table; no PDF/image dependencies."""

from __future__ import annotations

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError
from opendoc_formats.support.cancellation import checkpoint


def unpack(raw: memoryview, maximum: int, location: str, *, expected: int | None = None,
           early_change: int = 1) -> tuple[bytearray, int]:
    """Return bytes and the byte containing EOD; retain padding/trailing source bytes."""
    if type(early_change) is not int or early_change not in (0, 1):
        raise InvalidDocumentError(location+'LZW EarlyChange must be 0 or 1')
    limit = min(maximum, expected) if expected is not None else maximum
    if limit < 0:
        raise ResourceLimitError(location+'no remaining LZW decoded byte budget')
    checkpoint()
    # Store prefix links, never an expanding copy of every dictionary phrase.
    prefix = [0]*4096
    suffix = bytearray(4096)
    first = bytearray(4096)
    lengths = [0]*4096
    for code in range(256):
        suffix[code] = first[code] = code
        lengths[code] = 1
    output = bytearray()
    cursor = bits = buffer = 0
    width, next_code, previous = 9, 258, -1
    while True:
        checkpoint()
        while bits < width:
            if cursor >= len(raw):
                raise InvalidDocumentError(location+'truncated LZW code or missing EOD')
            buffer = (buffer << 8) | raw[cursor]
            cursor += 1
            bits += 8
        bits -= width
        code = (buffer >> bits) & ((1 << width)-1)
        buffer &= (1 << bits)-1
        if code == 256:
            width, next_code, previous = 9, 258, -1
            continue
        if code == 257:
            if expected is not None and len(output) != expected:
                raise InvalidDocumentError(location+'LZW EOD disagrees with decoded length')
            return output, cursor
        if next_code == 4096:
            raise InvalidDocumentError(location+'full LZW table requires clear-table or EOD')
        special = code == next_code and previous >= 0
        if code > next_code or (code == next_code and not special) or (previous < 0 and code > 255):
            raise InvalidDocumentError(location+'invalid forward LZW dictionary reference')
        root = previous if special else code
        count = lengths[root]+int(special)
        if len(output)+count > limit:
            if expected is not None and limit == expected:
                raise InvalidDocumentError(location+'LZW exceeds declared record length')
            raise ResourceLimitError(location+'LZW exceeds decoded byte budget')
        head = first[root]
        stack = bytearray()
        link = root
        while link >= 258:
            if len(stack) % 1024 == 0:
                checkpoint()
            stack.append(suffix[link])
            link = prefix[link]
        stack.append(link)
        output.extend(reversed(stack))
        if special:
            output.append(head)
        if previous >= 0:
            prefix[next_code] = previous
            suffix[next_code] = head
            first[next_code] = first[previous]
            lengths[next_code] = lengths[previous]+1
            next_code += 1
            if width < 12 and next_code == (1 << width)-early_change:
                width += 1
        previous = code
