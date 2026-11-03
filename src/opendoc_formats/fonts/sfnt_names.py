"""Native finite name-table reader; unfamiliar encodings require the established engine."""

from __future__ import annotations

import struct

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.sfnt import inspect_sfnt
from opendoc_formats.support.cancellation import cancellation_requested, checkpoint

_WINDOWS_CODECS = {0: 'utf-16-be', 1: 'utf-16-be', 2: 'shift_jis', 3: 'gb2312',
                   4: 'big5', 5: 'euc_kr', 6: 'johab', 10: 'utf-16-be'}
# Standard CJK units use Python's codecs. Macintosh extension bytes that these
# codecs cannot decode retain the existing engine recovery path; never replace them.
_MAC_CODECS = {1: 'x_mac_japanese', 2: 'x_mac_trad_chinese', 3: 'x_mac_korean',
               25: 'x_mac_simp_chinese', 6: 'mac_greek', 7: 'mac_cyrillic', 29: 'mac_latin2',
               35: 'mac_turkish', 37: 'mac_iceland'}
_ROMAN_LANGUAGES = {15: 'mac_iceland', 17: 'mac_turkish', 18: 'mac_croatian',
                    24: 'mac_latin2', 25: 'mac_latin2', 26: 'mac_latin2', 27: 'mac_latin2',
                    28: 'mac_latin2', 36: 'mac_latin2', 37: 'mac_romanian',
                    38: 'mac_latin2', 39: 'mac_latin2', 40: 'mac_latin2'}
_ISO_CODECS = {0: 'ascii', 1: 'utf-16-be', 2: 'latin1'}


def read_program_names(data: bytes, *, face_index: int | None = None) -> dict[int, str]:
    """Read IDs 1/4/6/16 with the established source-order/English selection policy."""
    inventory = inspect_sfnt(data, cancelled=cancellation_requested, face_index=face_index)
    table = next((table for table in inventory.tables if table.tag == 'name'), None)
    if table is None or table.length < 6:
        raise UnsupportedDocumentError('Font program has no complete native name table')
    start = table.offset
    version, count, storage = struct.unpack_from('>3H', data, start)
    if version not in (0, 1):
        raise UnsupportedDocumentError('Native font names require naming table version 0/1')
    end = 6+12*count
    if end > table.length:
        raise InvalidDocumentError('sfnt:name: invalid record array')
    if count > 4096:
        raise ResourceLimitError('sfnt:name: native record budget exceeded')
    languages = 0
    if version == 1:
        if end+2 > table.length:
            raise InvalidDocumentError('sfnt:name: missing language-tag count')
        languages = struct.unpack_from('>H', data, start+end)[0]
        end += 2+4*languages
        if languages > 4096:
            raise ResourceLimitError('sfnt:name: native language-tag record budget exceeded')
    if not end <= storage <= table.length:
        raise InvalidDocumentError('sfnt:name: invalid language-tag array or string storage')
    values: dict[int, str] = {}
    preferred: set[int] = set()
    decoded_bytes = 0

    def decode(length: int, offset: int, codec: str) -> str:
        nonlocal decoded_bytes
        if offset+length > table.length-storage:
            raise InvalidDocumentError('sfnt:name: string outside storage')
        decoded_bytes += length
        if decoded_bytes > 8*1024*1024:
            raise ResourceLimitError('sfnt:name: native decoded-byte work budget exceeded')
        raw = memoryview(data)[start+storage+offset:start+storage+offset+length]
        try:
            text = bytes(raw).decode(codec)
        except UnicodeDecodeError as error:
            raise UnsupportedDocumentError('Name record requires encoding recovery') from error
        if '\0' in text:
            raise UnsupportedDocumentError('Name record may require legacy double-encoding recovery')
        return text

    for index in range(languages):
        checkpoint()
        length, offset = struct.unpack_from('>2H', data, start+6+12*count+2+4*index)
        decode(length, offset, 'utf-16-be')  # Check declared tags; retain the established numeric-language policy.
    for index in range(count):
        checkpoint()
        platform, encoding, language, identifier, length, offset = struct.unpack_from('>6H', data, start+6+12*index)
        if offset+length > table.length-storage:
            raise InvalidDocumentError(f'sfnt:name: record {index} outside string storage')
        if identifier not in {1, 4, 6, 16} or identifier in preferred:
            continue
        if language >= 0x8000 and (version != 1 or language-0x8000 >= languages):
            raise UnsupportedDocumentError('Name record references an unknown language tag')
        if platform == 0 and encoding <= 6:
            codec = 'utf-16-be'
        elif platform == 3 and encoding in _WINDOWS_CODECS:
            codec = _WINDOWS_CODECS[encoding]
        elif platform == 1 and encoding == 0:
            codec = _ROMAN_LANGUAGES.get(language, 'mac_roman')
        elif platform == 1 and encoding in _MAC_CODECS:
            codec = _MAC_CODECS[encoding]
        elif platform == 2 and encoding in _ISO_CODECS:
            codec = _ISO_CODECS[encoding]
        else:
            raise UnsupportedDocumentError('Name record encoding outside native profile')
        text = decode(length, offset, codec)
        values[identifier] = text
        if (platform == 1 and language == 0) or (platform == 3 and language == 0x409):
            preferred.add(identifier)
    checkpoint()
    return values
