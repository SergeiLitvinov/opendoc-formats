"""Bounded, inert table inventories for standalone OpenType and explicitly selected collection faces."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Callable
from dataclasses import dataclass, field, fields

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.common import Source, check_cancel, positive_int, read_source


@dataclass(frozen=True)
class SfntLimits:
    max_input_bytes: int = 32 * 1024 * 1024
    max_tables: int = 4096
    max_table_bytes: int = 32 * 1024 * 1024
    max_total_table_bytes: int = 64 * 1024 * 1024
    max_faces: int = 256
    max_findings: int = 4096

    def __post_init__(self) -> None:
        for item in fields(self):
            positive_int(getattr(self, item.name), item.name, zero=item.name != 'max_input_bytes')


@dataclass(frozen=True)
class SfntTable:
    tag: str
    directory_offset: int
    offset: int
    length: int
    declared_checksum: int
    sha256: str
    payload: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True)
class SfntInventory:
    source_sha256: str
    source_size: int
    sfnt_version: str
    header_hex: str
    tables: tuple[SfntTable, ...]
    variation_tables: tuple[str, ...]
    assessment_complete: bool = field(default=False, init=False)
    face_index: int | None = None
    directory_offset: int = 0


@dataclass(frozen=True)
class SfntFaceMetrics:
    weight: int
    width_class: int
    units_per_em: int
    average_width: int
    fs_type: int
    italic: bool


@dataclass(frozen=True)
class SfntTableChecksum:
    tag: str
    declared: int
    computed: int
    valid: bool


@dataclass(frozen=True)
class SfntChecksumReport:
    source_sha256: str
    tables: tuple[SfntTableChecksum, ...]
    whole_checksum: int
    declared_adjustment: int | None
    expected_adjustment: int | None
    adjustment_valid: bool | None
    assessment_complete: bool = field(default=False, init=False)


@dataclass(frozen=True)
class SfntFinding:
    code: str
    offset: int
    tag: str | None
    message: str


@dataclass(frozen=True)
class SfntStructureReport:
    source_sha256: str
    face_index: int | None
    directory_offset: int
    findings: tuple[SfntFinding, ...]
    assessment_complete: bool = field(default=False, init=False)


def inspect_sfnt_structure(source: Source, *, limits: SfntLimits = SfntLimits(),
                           face_index: int | None = None,
                           cancelled: Callable[[], bool] | None = None) -> SfntStructureReport:
    """Observe directory/padding defects without repair; one representative partner per overlapping table."""
    if not isinstance(limits, SfntLimits):
        raise ValueError('limits must be SfntLimits')
    data = read_source(source, limits.max_input_bytes, cancelled)
    inventory = inspect_sfnt(data, limits=limits, face_index=face_index, cancelled=cancelled)
    findings: list[SfntFinding] = []

    def add(code: str, offset: int, tag: str | None, message: str) -> None:
        check_cancel(cancelled)
        if len(findings) >= limits.max_findings:
            raise ResourceLimitError('sfnt:structure: max_findings exceeded')
        findings.append(SfntFinding(code, offset, tag, message))

    base = inventory.directory_offset
    tags = [table.tag for table in inventory.tables]
    if tags != sorted(tags):
        add('sfnt.directory.order', base+12, None, 'Table records are not sorted by tag')
    selector = len(tags).bit_length()-1
    expected = 16*(1 << selector), selector, 16*len(tags)-16*(1 << selector)
    observed = struct.unpack_from('>3H', data, base+6)
    if observed != expected:
        add('sfnt.directory.search', base+6, None, f'Search parameters {observed} differ from derived {expected}')
    for table in inventory.tables:
        check_cancel(cancelled)
        trimmed = table.tag.rstrip(' ')
        if not trimmed or ' ' in trimmed:
            add('sfnt.directory.tag-spaces', table.directory_offset, table.tag, 'Tag spaces are not trailing padding')
        end = table.offset+table.length
        padded = (end+3)//4*4
        if padded > len(data):
            add('sfnt.padding.truncated', end, table.tag, 'Table padding to the next four-byte boundary is missing')
        elif any(data[end:padded]):
            add('sfnt.padding.nonzero', end, table.tag, 'Table padding contains nonzero bytes')
    active: SfntTable | None = None
    for table in sorted(inventory.tables, key=lambda value: (value.offset, value.tag)):
        check_cancel(cancelled)
        if not table.length:
            continue
        if active is not None and table.offset < active.offset+active.length:
            add('sfnt.table.overlap', table.offset, table.tag, f'Payload intersects table {active.tag!r}')
        if active is None or table.offset+table.length > active.offset+active.length:
            active = table
    check_cancel(cancelled)
    return SfntStructureReport(inventory.source_sha256, inventory.face_index, base, tuple(findings))


def inspect_sfnt_checksums(source: Source, *, limits: SfntLimits = SfntLimits(),
                           cancelled: Callable[[], bool] | None = None) -> SfntChecksumReport:
    """Observe table checksums and standalone head adjustment without repairing source bytes.

    The table checksum treats head.checkSumAdjustment as zero. The whole-file sum
    includes actual padding/trailing bytes; validity is unknown without a head table.
    Matching sums do not prove structural, glyph or rendering validity.
    """
    if not isinstance(limits, SfntLimits):
        raise ValueError('limits must be SfntLimits')
    data = read_source(source, limits.max_input_bytes, cancelled)
    inventory = inspect_sfnt(data, limits=limits, cancelled=cancelled)
    checks = []
    adjustment = None
    for table in inventory.tables:
        check_cancel(cancelled)
        payload = memoryview(data)[table.offset:table.offset+table.length]
        computed = _checksum(payload, cancelled)
        if table.tag == 'head':
            if table.length < 12:
                raise InvalidDocumentError('sfnt:head: checksum adjustment field is truncated')
            adjustment = struct.unpack_from('>I', payload, 8)[0]
            computed = (computed-adjustment) & 0xffffffff
        checks.append(SfntTableChecksum(table.tag, table.declared_checksum, computed, table.declared_checksum == computed))
    whole = _checksum(memoryview(data), cancelled)
    expected = None if adjustment is None else (0xb1b0afba-whole+adjustment) & 0xffffffff
    check_cancel(cancelled)
    return SfntChecksumReport(inventory.source_sha256, tuple(checks), whole, adjustment, expected,
                              None if adjustment is None else adjustment == expected)


def _checksum(data: memoryview, cancelled: Callable[[], bool] | None) -> int:
    result = 0
    # Fixed-size chunks bound temporary work and cancellation latency independently of the font size.
    for start in range(0, len(data), 65536):
        check_cancel(cancelled)
        chunk = data[start:start+65536]
        aligned = len(chunk)//4*4
        result += sum(word[0] for word in struct.iter_unpack('>I', chunk[:aligned]))
        if aligned != len(chunk):
            result += int.from_bytes(chunk[aligned:], 'big') << (8*(4-len(chunk)+aligned))
        result &= 0xffffffff
    check_cancel(cancelled)
    return result


def _collection_directory(data: bytes, face_index: int, limits: SfntLimits,
                          cancelled: Callable[[], bool] | None) -> tuple[int, int]:
    if len(data) < 12:
        raise InvalidDocumentError('sfnt:collection: truncated header')
    version, count = struct.unpack_from('>2I', data, 4)
    if version not in (0x10000, 0x20000):
        raise UnsupportedDocumentError('sfnt:collection: unsupported TTC version')
    if count > limits.max_faces:
        raise ResourceLimitError('sfnt:collection: max_faces exceeded')
    end = 12+4*count+(12 if version == 0x20000 else 0)
    if not count or end > len(data) or face_index >= count:
        raise InvalidDocumentError('sfnt:collection: invalid face array or selected face')
    selected = 0
    for index in range(count):
        check_cancel(cancelled)
        offset = struct.unpack_from('>I', data, 12+4*index)[0]
        if offset < end or offset % 4 or offset+12 > len(data):
            raise InvalidDocumentError('sfnt:collection: directory offset outside data area')
        if index == face_index:
            selected = offset
    if version == 0x20000:
        tag, length, offset = struct.unpack_from('>3I', data, end-12)
        if (tag, length, offset) != (0, 0, 0):
            if tag != 0x44534947 or not length or offset < end or offset+length > len(data):
                raise InvalidDocumentError('sfnt:collection: invalid DSIG declaration')
    return selected, end


def inspect_sfnt(source: Source, *, capture: bool = False, limits: SfntLimits = SfntLimits(),
                 face_index: int | None = None,
                 cancelled: Callable[[], bool] | None = None) -> SfntInventory:
    """Inventory table ranges; collection selection must be explicit, with original absolute offsets."""
    if type(capture) is not bool or not isinstance(limits, SfntLimits):
        raise ValueError('capture must be bool and limits must be SfntLimits')
    data = read_source(source, limits.max_input_bytes, cancelled)
    if face_index is not None:
        positive_int(face_index, 'face_index', zero=True)
    if len(data) < 4:
        raise InvalidDocumentError('sfnt:header: truncated signature')
    base, minimum = 0, 0
    collection = data[:4] == b'ttcf'
    if collection:
        if face_index is None:
            raise UnsupportedDocumentError('sfnt:collection: standalone default requires an explicit face_index for TTC')
        base, minimum = _collection_directory(data, face_index, limits, cancelled)
    elif face_index not in (None, 0):
        raise UnsupportedDocumentError('sfnt:header: standalone font has only face zero')
    version = data[base:base+4]
    if version not in (b'\x00\x01\x00\x00', b'OTTO'):
        raise UnsupportedDocumentError('sfnt:header: only standalone TrueType/OpenType wrappers are supported')
    if base+12 > len(data):
        raise InvalidDocumentError('sfnt:header: truncated table directory header')
    count = struct.unpack_from('>H', data, base+4)[0]
    if count > limits.max_tables:
        raise ResourceLimitError('sfnt:header: max_tables exceeded')
    directory_end = base+12+16*count
    if not count or directory_end > len(data):
        raise InvalidDocumentError('sfnt:header: empty or truncated table directory')
    total = 0
    tables = []
    seen: set[bytes] = set()
    for index in range(count):
        check_cancel(cancelled)
        location = base+12+16*index
        tag, checksum, offset, length = struct.unpack_from('>4sIII', data, location)
        if tag in seen or any(value < 32 or value > 126 for value in tag):
            raise InvalidDocumentError(f'sfnt:table={index}: duplicate or non-printable table tag')
        seen.add(tag)
        lower = minimum if collection else directory_end
        if (offset < lower or offset > len(data) or length > len(data)-offset
                or (length and offset < directory_end and offset+length > base)):
            raise InvalidDocumentError(f'sfnt:table={index}: table range outside data area')
        if offset % 4:
            raise UnsupportedDocumentError(f'sfnt:table={index}: unaligned table offset outside supported profile')
        total += length
        if length > limits.max_table_bytes or total > limits.max_total_table_bytes:
            raise ResourceLimitError(f'sfnt:table={index}: max_table_bytes/max_total_table_bytes exceeded')
        payload = memoryview(data)[offset:offset+length]
        tables.append(SfntTable(tag.decode('ascii'), location, offset, length, checksum,
                                hashlib.sha256(payload).hexdigest(), bytes(payload) if capture else None))
    check_cancel(cancelled)
    variations = {'fvar', 'gvar', 'avar', 'CFF2', 'HVAR', 'VVAR', 'MVAR'}
    source_digest = hashlib.sha256(data).hexdigest()
    check_cancel(cancelled)
    return SfntInventory(source_digest, len(data), version.hex(), data[base:base+12].hex(), tuple(tables),
                         tuple(table.tag for table in tables if table.tag in variations),
                         face_index=face_index if collection else None, directory_offset=base)


def read_face_metrics(data: bytes, *, cancelled: Callable[[], bool] | None = None,
                      default_variations: bool = False, face_index: int | None = None) -> SfntFaceMetrics:
    """Read base head/OS2/post fields, optionally validating fvar; never select a variation instance."""
    if type(default_variations) is not bool:
        raise ValueError('default_variations must be bool')
    inventory = inspect_sfnt(data, cancelled=cancelled, face_index=face_index)
    tables = {table.tag: table for table in inventory.tables}
    if inventory.variation_tables:
        if not default_variations or 'fvar' not in tables or 'CFF2' in tables:
            raise UnsupportedDocumentError('sfnt:face: variation metadata requires the established reader')
        from opendoc_formats.native.fvar import inspect_fvar_table

        variation = tables['fvar']
        inspect_fvar_table(memoryview(data)[variation.offset:variation.offset+variation.length], cancelled=cancelled)

    def required(tag: str, minimum: int) -> SfntTable:
        check_cancel(cancelled)
        table = tables.get(tag)
        if table is None or table.length < minimum:
            raise UnsupportedDocumentError(f'sfnt:{tag}: missing/short face metadata table')
        return table

    head, os2, post, maximum = required('head', 54), required('OS/2', 78), required('post', 32), required('maxp', 6)
    if (struct.unpack_from('>I', data, head.offset)[0] != 0x10000
            or struct.unpack_from('>I', data, head.offset+12)[0] != 0x5f0f3cf5):
        raise UnsupportedDocumentError('sfnt:head: version/magic outside native face profile')
    units = struct.unpack_from('>H', data, head.offset+18)[0]
    if not 16 <= units <= 16384:
        raise UnsupportedDocumentError('sfnt:head: unitsPerEm outside native face profile')
    version = struct.unpack_from('>H', data, os2.offset)[0]
    size = {0: 78, 1: 86, 2: 96, 3: 96, 4: 96, 5: 100}.get(version)
    if size is None or os2.length < size:
        raise UnsupportedDocumentError('sfnt:OS/2: version/size outside native face profile')
    average, weight, width, fs_type = struct.unpack_from('>h3H', data, os2.offset+2)
    max_version, glyph_count = struct.unpack_from('>IH', data, maximum.offset)
    if max_version not in (0x5000, 0x10000) or (max_version == 0x10000 and maximum.length < 32) or not glyph_count:
        raise UnsupportedDocumentError('sfnt:maxp: version/size/count outside native face profile')
    _post_profile(data, post, glyph_count, cancelled)
    angle = struct.unpack_from('>i', data, post.offset+4)[0]
    check_cancel(cancelled)
    return SfntFaceMetrics(weight, width, units, average, fs_type, bool(angle))


def _post_profile(data: bytes, table: SfntTable, glyph_count: int, cancelled: Callable[[], bool] | None) -> None:
    version = struct.unpack_from('>I', data, table.offset)[0]
    if version == 0x30000 or (version == 0x10000 and glyph_count <= 258):
        return
    if version == 0x40000:
        # Apple format 4 stores exactly one opaque uint16 character code per glyph.
        # These printer codes are not Unicode coverage and never replace cmap.
        if table.length != 32+2*glyph_count:
            raise UnsupportedDocumentError('sfnt:post: format 4 character-code array outside native face profile')
        check_cancel(cancelled)
        return
    if version != 0x20000 or table.length < 34:
        raise UnsupportedDocumentError('sfnt:post: version outside native face profile')
    count = struct.unpack_from('>H', data, table.offset+32)[0]
    if count != glyph_count or 34+2*count > table.length:
        raise UnsupportedDocumentError('sfnt:post: glyph-name array outside native face profile')
    maximum = 0
    for index in range(count):
        check_cancel(cancelled)
        maximum = max(maximum, struct.unpack_from('>H', data, table.offset+34+2*index)[0])
    position, end = table.offset+34+2*count, table.offset+table.length
    for _ in range(max(0, maximum-257)):
        check_cancel(cancelled)
        if position >= end or position+1+data[position] > end:
            raise UnsupportedDocumentError('sfnt:post: truncated Pascal glyph-name storage')
        position += 1+data[position]
