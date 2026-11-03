"""Bounded parameterless PDF byte filters, without PDF/image backends or input rewriting."""

from __future__ import annotations

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError
from opendoc_formats.native.pdf_runlength import unpack
from opendoc_formats.native.pdf_syntax import SPACE
from opendoc_formats.support.cancellation import checkpoint


class _Output:
    def __init__(self, maximum: int, expected: int | None, location: str) -> None:
        self.limit = min(maximum, expected) if expected is not None else maximum
        self.expected = expected
        self.location = location
        if self.limit < 0:
            raise ResourceLimitError(location+'no remaining ASCII decoded byte budget')
        self.data = bytearray()

    def put(self, value: bytes) -> None:
        if len(self.data)+len(value) > self.limit:
            if self.expected is not None and self.limit == self.expected:
                raise InvalidDocumentError(self.location+'ASCII data exceeds declared record length')
            raise ResourceLimitError(self.location+'ASCII data exceeds decoded byte budget')
        self.data.extend(value)

    def finish(self, consumed: int) -> tuple[bytearray, int]:
        checkpoint()
        if self.expected is not None and len(self.data) != self.expected:
            raise InvalidDocumentError(self.location+'ASCII EOD disagrees with decoded length')
        return self.data, consumed


def ascii_hex(raw: memoryview, maximum: int, location: str, *, expected: int | None = None) -> tuple[bytearray, int]:
    """Decode pairs and the optional final high nibble, returning the physical EOD end."""
    output = _Output(maximum, expected, location)
    high = -1
    for cursor, value in enumerate(raw):
        if cursor % 4096 == 0:
            checkpoint()
        if value in SPACE:
            continue
        if value == 62:
            if high >= 0:
                output.put(bytes([high << 4]))
            return output.finish(cursor+1)
        if 48 <= value <= 57:
            nibble = value-48
        elif 65 <= value <= 70:
            nibble = value-55
        elif 97 <= value <= 102:
            nibble = value-87
        else:
            raise InvalidDocumentError(location+'invalid ASCIIHexDecode digit')
        if high < 0:
            high = nibble
        else:
            output.put(bytes([(high << 4)+nibble]))
            high = -1
    raise InvalidDocumentError(location+'missing ASCIIHexDecode EOD')


def ascii85(raw: memoryview, maximum: int, location: str, *, expected: int | None = None) -> tuple[bytearray, int]:
    """Decode complete/partial base-85 groups and standalone z; require the PDF ~> end."""
    output = _Output(maximum, expected, location)
    cursor, number, count = 0, 0, 0
    while cursor < len(raw):
        if cursor % 4096 == 0:
            checkpoint()
        value = raw[cursor]
        cursor += 1
        if value in SPACE:
            continue
        if value == 126:
            if cursor >= len(raw) or raw[cursor] != 62:
                raise InvalidDocumentError(location+'invalid ASCII85Decode EOD')
            cursor += 1
            if count == 1:
                raise InvalidDocumentError(location+'single-digit final ASCII85Decode group')
            if count:
                amount = count-1
                for _ in range(5-count):
                    number = number*85+84
                if number > 0xffffffff:
                    raise InvalidDocumentError(location+'ASCII85Decode group exceeds uint32')
                output.put(number.to_bytes(4, 'big')[:amount])
            return output.finish(cursor)
        if value == 122:
            if count:
                raise InvalidDocumentError(location+'ASCII85Decode z inside a group')
            output.put(b'\0\0\0\0')
        elif 33 <= value <= 117:
            number = number*85+value-33
            count += 1
            if count == 5:
                if number > 0xffffffff:
                    raise InvalidDocumentError(location+'ASCII85Decode group exceeds uint32')
                output.put(number.to_bytes(4, 'big'))
                number, count = 0, 0
        else:
            raise InvalidDocumentError(location+'invalid ASCII85Decode digit')
    raise InvalidDocumentError(location+'missing ASCII85Decode EOD')


BYTE_DECODERS = {'RunLengthDecode': unpack, 'ASCIIHexDecode': ascii_hex, 'ASCII85Decode': ascii85}
