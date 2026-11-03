"""Strict MS-OLEDS 2.3.6 envelope; application-specific NativeData stays inert."""

from __future__ import annotations

import hashlib
import struct
from typing import TYPE_CHECKING, Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError
from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import AnatomyLimits, BinaryItem


def inspect_ole_native(data: bytes, limits: AnatomyLimits, capture: bool) -> tuple[tuple[BinaryItem, ...], dict[str, Any]]:
    """Inventory the exact size-prefixed stream, never search for a signature inside NativeData."""
    from opendoc_formats.anatomy import BinaryItem

    checkpoint()
    if len(data) > limits.max_part_bytes or len(data) > limits.max_total_bytes or limits.max_items < 2:
        raise ResourceLimitError('ole-native:source: max_part_bytes/max_total_bytes/max_items exceeded')
    if len(data) < 4:
        raise InvalidDocumentError('ole-native:header: truncated NativeDataSize')
    size = struct.unpack_from('<I', data)[0]
    if size != len(data) - 4:
        raise InvalidDocumentError('ole-native:header: NativeDataSize does not match the complete stream')
    items = []
    for locator, kind, start, length in (
        ('ole-native:header', 'ole-native-header', 0, 4),
        ('ole-native:data', 'ole-native-data', 4, size),
    ):
        checkpoint()
        chunk = memoryview(data)[start:start + length]
        items.append(BinaryItem(locator, kind, length, hashlib.sha256(chunk).hexdigest(),
                                details=(('offset', start), ('length', length)), payload=bytes(chunk) if capture else None))
    checkpoint()
    return tuple(items), {'native_data_size': size, 'assessment_complete': False, 'application_data_assessed': False}


__all__ = ['inspect_ole_native']
