"""Bounded physical fvar records; fixed values stay exact and no instance is selected."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Callable
from dataclasses import dataclass, field

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.common import check_cancel, positive_int


@dataclass(frozen=True)
class FvarAxis:
    tag: str
    minimum: int
    default: int
    maximum: int
    flags: int
    name_id: int


@dataclass(frozen=True)
class FvarInstance:
    name_id: int
    coordinates: tuple[int, ...]
    postscript_name_id: int | None


@dataclass(frozen=True)
class FvarInventory:
    table_sha256: str
    table_size: int
    axes_offset: int
    axis_size: int
    instance_size: int
    axes: tuple[FvarAxis, ...]
    instances: tuple[FvarInstance, ...]
    assessment_complete: bool = field(default=False, init=False)


def inspect_fvar_table(data: bytes | memoryview, *, max_bytes: int = 8*1024*1024, max_axes: int = 64,
                       max_instances: int = 4096, max_coordinates: int = 262144,
                       cancelled: Callable[[], bool] | None = None) -> FvarInventory:
    """Inspect one table payload; name IDs are not resolved and variation programs are not run."""
    for name, value in (('max_bytes', max_bytes), ('max_axes', max_axes),
                        ('max_instances', max_instances), ('max_coordinates', max_coordinates)):
        positive_int(value, name, zero=name != 'max_bytes')
    check_cancel(cancelled)
    if not isinstance(data, (bytes, memoryview)):
        raise TypeError('fvar data must be bytes or memoryview')
    view = memoryview(data)
    if view.nbytes > max_bytes:
        raise ResourceLimitError('sfnt:fvar: table byte budget exceeded')
    payload = bytes(view)
    if len(payload) < 16:
        raise InvalidDocumentError('sfnt:fvar: truncated header')
    major, minor, offset, reserved, axes, axis_size, instances, instance_size = struct.unpack_from('>8H', payload)
    if (major, minor, reserved, axis_size) != (1, 0, 2, 20) or instance_size not in (4+4*axes, 6+4*axes):
        raise UnsupportedDocumentError('sfnt:fvar: version/record profile unsupported')
    if axes > max_axes or instances > max_instances or axes*instances > max_coordinates:
        raise ResourceLimitError('sfnt:fvar: axis/instance/coordinate budget exceeded')
    instance_offset = offset+axes*axis_size
    if offset < 16 or instance_offset+instances*instance_size > len(payload):
        raise InvalidDocumentError('sfnt:fvar: arrays outside table')
    axis_records: list[FvarAxis] = []
    seen: set[bytes] = set()
    for index in range(axes):
        check_cancel(cancelled)
        tag, minimum, default, maximum, flags, name_id = struct.unpack_from('>4s3i2H', payload, offset+index*axis_size)
        if tag in seen or any(value < 32 or value > 126 for value in tag) or not minimum <= default <= maximum:
            raise InvalidDocumentError('sfnt:fvar: duplicate/invalid axis tag or range')
        if flags & ~1:
            raise UnsupportedDocumentError('sfnt:fvar: unknown axis flags')
        seen.add(tag)
        axis_records.append(FvarAxis(tag.decode('ascii'), minimum, default, maximum, flags, name_id))
    instance_records = []
    for index in range(instances):
        check_cancel(cancelled)
        start = instance_offset+index*instance_size
        name_id, flags = struct.unpack_from('>2H', payload, start)
        if flags:
            raise UnsupportedDocumentError('sfnt:fvar: unknown instance flags')
        coordinates = []
        for number, axis in enumerate(axis_records):
            check_cancel(cancelled)
            coordinate = struct.unpack_from('>i', payload, start+4+4*number)[0]
            if not axis.minimum <= coordinate <= axis.maximum:
                raise UnsupportedDocumentError('sfnt:fvar: instance coordinate outside axis range')
            coordinates.append(coordinate)
        postscript = struct.unpack_from('>H', payload, start+4+4*axes)[0] if instance_size == 6+4*axes else 0xffff
        instance_records.append(FvarInstance(name_id, tuple(coordinates), None if postscript == 0xffff else postscript))
    digest = hashlib.sha256(payload).hexdigest()
    check_cancel(cancelled)
    return FvarInventory(digest, len(payload), offset, axis_size, instance_size, tuple(axis_records), tuple(instance_records))
