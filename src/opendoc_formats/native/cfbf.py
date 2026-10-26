"""Bounded physical CFBF observations, without OLE interpretation or execution."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import AnatomyLimits, BinaryItem

SIGNATURE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
FREE, END, FAT, DIFAT = 0xffffffff, 0xfffffffe, 0xfffffffd, 0xfffffffc


def _invalid(location: str, message: str) -> NoReturn:
    raise InvalidDocumentError(f'cfbf:{location}: {message}')


@dataclass(frozen=True)
class _Entry:
    index: int
    kind: int
    start: int
    size: int
    details: tuple[tuple[str, Any], ...]


class _Reader:
    def __init__(self, data: bytes, limits: AnatomyLimits, capture: bool) -> None:
        self.data, self.limits, self.capture = memoryview(data), limits, capture
        if len(data) < 512 or data[:8] != SIGNATURE:
            _invalid('header', 'missing/truncated compound file signature')
        self.version, endian, shift, mini_shift = (int(value) for value in struct.unpack_from('<4H', data, 26))
        if self.version not in (3, 4) or endian != 0xfffe or shift != {3: 9, 4: 12}.get(self.version) or mini_shift != 6:
            raise UnsupportedDocumentError('cfbf:header: unsupported version, byte order or sector profile')
        self.sector_size = 1 << shift
        if len(data) < self.sector_size or len(data) % self.sector_size:
            _invalid('header', 'truncated or unaligned sectors')
        self.count = len(data)//self.sector_size-1
        self.words = self.sector_size//4
        self.total = len(data)
        if self.count+1 > limits.max_items:
            raise ResourceLimitError('cfbf:header: max_items exceeded by physical sectors')
        if self.sector_size > limits.max_part_bytes or self.total > limits.max_total_bytes:
            raise ResourceLimitError('cfbf:header: max_part_bytes/max_total_bytes exceeded by physical inventory')
        self.used: dict[int, str] = {}
        self.mini_used: dict[int, str] = {}
        self.fat: list[int] = []
        self.mini_fat: list[int] = []
        self.root_chain: list[int] = []
        self.root_size = 0
        self.directory_slots = 0

    def u32(self, offset: int) -> int:
        return int(struct.unpack_from('<I', self.data, offset)[0])

    def offset(self, sector: int) -> int:
        if not 0 <= sector < self.count:
            _invalid(f'sector={sector}', 'sector address outside the file')
        return (sector+1)*self.sector_size

    def claim(self, sector: int, owner: str, *, mini: bool = False) -> None:
        checkpoint()
        maximum = self.root_size//64 if mini else self.count
        if not 0 <= sector < maximum:
            _invalid(owner, 'sector address outside the mini stream' if mini else 'sector address outside the file')
        used = self.mini_used if mini else self.used
        if sector in used:
            _invalid(owner, f'cycle or cross-linked sector {sector}; already owned by {used[sector]}')
        used[sector] = owner

    def table(self, sectors: list[int], index: int, owner: str) -> int:
        block, slot = divmod(index, self.words)
        if index < 0 or block >= len(sectors):
            _invalid(owner, 'allocation table address outside the available table')
        return self.u32(self.offset(sectors[block])+4*slot)

    def chain(self, start: int, owner: str, *, expected: int | None = None, mini: bool = False) -> list[int]:
        sectors = []
        while start != END:
            self.claim(start, owner, mini=mini)
            sectors.append(start)
            if expected is not None and len(sectors) > expected:
                _invalid(owner, 'chain longer than declared size/count')
            start = self.table(self.mini_fat if mini else self.fat, start, owner)
        if expected is not None and len(sectors) != expected:
            _invalid(owner, 'chain shorter than declared size/count')
        return sectors

    def allocation(self) -> None:
        fat_count, first_difat, difat_count = self.u32(44), self.u32(68), self.u32(72)
        if fat_count > self.count or difat_count > self.count:
            _invalid('header', 'allocation sector count exceeds the file')

        def fat_entry(value: int) -> None:
            checkpoint()
            if value != FREE:
                if len(self.fat) >= fat_count:
                    _invalid('difat', 'more FAT sectors than declared')
                self.offset(value)
                self.fat.append(value)

        for offset in range(76, 512, 4):
            fat_entry(self.u32(offset))
        difat_sectors = []
        for _ in range(difat_count):
            self.claim(first_difat, 'difat')
            difat_sectors.append(first_difat)
            offset = self.offset(first_difat)
            for slot in range(self.words-1):
                fat_entry(self.u32(offset+4*slot))
            first_difat = self.u32(offset+self.sector_size-4)
        if first_difat != END or len(self.fat) != fat_count or fat_count*self.words < self.count:
            _invalid('difat', 'incomplete/inconsistent FAT or DIFAT coverage')
        for sector in self.fat:
            self.claim(sector, 'fat')
        for sector in self.fat+difat_sectors:
            required = FAT if self.used[sector] == 'fat' else DIFAT
            if self.table(self.fat, sector, 'fat') != required:
                _invalid(f'sector={sector}', 'wrong FAT/DIFAT allocation marker')
        if self.u32(56) != 4096:
            raise UnsupportedDocumentError('cfbf:header: unsupported mini stream cutoff')
        self.mini_fat = self.chain(self.u32(60), 'mini-fat', expected=self.u32(64))

    def entries(self) -> tuple[_Entry, ...]:
        count = self.u32(40)
        if self.version == 3 and count != 0:
            _invalid('header', 'version 3 directory sector count must be zero')
        directory = self.chain(self.u32(48), 'directory', expected=count if self.version == 4 else None)
        entries = []
        index = 0
        for sector in directory:
            for relative in range(0, self.sector_size, 128):
                checkpoint()
                if index >= self.limits.max_items:
                    raise ResourceLimitError('cfbf:directory: max_items exceeded by directory slots')
                offset = self.offset(sector)+relative
                raw = self.data[offset:offset+128]
                kind, length = raw[66], struct.unpack_from('<H', raw, 64)[0]
                if kind:
                    if kind not in (1, 2, 5) or (kind == 5) != (index == 0):
                        _invalid(f'directory={index}', 'invalid directory object type/root position')
                    if not 2 <= length <= 64 or length % 2 or bytes(raw[length-2:length]) != b'\x00\x00':
                        _invalid(f'directory={index}', 'invalid UTF-16 name length/terminator')
                    try:
                        name = bytes(raw[:length-2]).decode('utf-16-le')
                    except UnicodeDecodeError as error:
                        _invalid(f'directory={index}', f'invalid UTF-16 name: {error}')
                    size = struct.unpack_from('<Q', raw, 120)[0]
                    start = struct.unpack_from('<I', raw, 116)[0]
                    details = {
                        'directory_index': index, 'entry_offset': offset, 'entry_hex': bytes(raw).hex(),
                        'name': name, 'object_type': kind, 'color': raw[67],
                        'left_sibling': struct.unpack_from('<I', raw, 68)[0],
                        'right_sibling': struct.unpack_from('<I', raw, 72)[0],
                        'child': struct.unpack_from('<I', raw, 76)[0], 'clsid_hex': bytes(raw[80:96]).hex(),
                        'state_bits': struct.unpack_from('<I', raw, 96)[0],
                        'creation_time_raw': struct.unpack_from('<Q', raw, 100)[0],
                        'modified_time_raw': struct.unpack_from('<Q', raw, 108)[0],
                        'starting_sector': start, 'stream_size_raw': size,
                    }
                    # Old version-3 producers left this high DWORD uninitialized (MS-CFB 2.6.3).
                    entries.append(_Entry(index, kind, start, size & 0xffffffff if self.version == 3 else size,
                                          tuple(details.items())))
                index += 1
        self.directory_slots = index
        if not entries or entries[0].index != 0 or entries[0].kind != 5:
            _invalid('directory', 'missing root storage entry')
        if self.count+1+len(entries) > self.limits.max_items:
            raise ResourceLimitError('cfbf:directory: max_items exceeded by physical sectors and directory objects')
        return tuple(entries)

    def stream(self, entry: _Entry) -> BinaryItem:
        from opendoc_formats.anatomy import BinaryItem

        owner = f'directory={entry.index}'
        size = entry.size if entry.kind in (2, 5) else 0
        if size > self.limits.max_part_bytes:
            raise ResourceLimitError(f'cfbf:{owner}: max_part_bytes exceeded by stream')
        self.total += size
        if self.total > self.limits.max_total_bytes:
            raise ResourceLimitError(f'cfbf:{owner}: max_total_bytes exceeded by physical and logical inventory')
        mini = entry.kind == 2 and 0 < size < 4096
        unit = 64 if mini else self.sector_size
        chain = self.chain(entry.start, owner, expected=(size+unit-1)//unit, mini=mini) if entry.kind != 1 else []
        if entry.kind == 5:
            self.root_chain, self.root_size = chain, size
        digest, ranges, chunks = hashlib.sha256(), [], []
        remaining = size
        for sector in chain:
            checkpoint()
            if mini:
                root_sector, relative = divmod(sector*64, self.sector_size)
                offset = self.offset(self.root_chain[root_sector])+relative
            else:
                offset = self.offset(sector)
            length = min(unit, remaining)
            chunk = self.data[offset:offset+length]
            digest.update(chunk)
            ranges.append((offset, length))
            if self.capture:
                chunks.append(chunk)
            remaining -= length
        details = dict(entry.details)
        details.update({'allocation': 'mini-fat' if mini else 'fat' if entry.kind != 1 else None,
                        'chain': tuple(chain), 'data_ranges': tuple(ranges)})
        return BinaryItem('cfbf:'+owner, 'cfbf-storage' if entry.kind == 1 else 'cfbf-root-mini-stream'
                          if entry.kind == 5 else 'cfbf-stream', size, digest.hexdigest(),
                          details=tuple(details.items()), payload=b''.join(chunks) if self.capture else None)

    def directory_links(self, entries: tuple[_Entry, ...]) -> dict[str, Any]:
        """Audit physical directory pointers, including disconnected components, without recursion."""
        active = {entry.index: entry for entry in entries}
        edges: dict[int, list[tuple[str, int]]] = {index: [] for index in active}
        incoming: dict[int, tuple[int, str]] = {}
        findings: list[dict[str, Any]] = []

        def finding(code: str, index: int, field: str, target: int) -> None:
            findings.append({'code': code, 'location': f'cfbf:directory={index}/{field}', 'target': target})

        for entry in entries:
            checkpoint()
            details = dict(entry.details)
            for field in ('left_sibling', 'right_sibling', 'child'):
                checkpoint()
                target = details[field]
                if target == FREE:
                    continue
                permitted = True
                if entry.index == 0 and field != 'child':
                    finding('root-sibling', entry.index, field, target)
                    permitted = False
                if entry.kind == 2 and field == 'child':
                    finding('stream-child', entry.index, field, target)
                    permitted = False
                if target not in active:
                    finding('inactive-target' if target < self.directory_slots else 'out-of-range-target',
                            entry.index, field, target)
                    continue
                if target == 0:
                    finding('root-target', entry.index, field, target)
                    permitted = False
                # Invalid-role links stay in raw metadata but do not establish containment.
                if not permitted:
                    continue
                edges[entry.index].append((field, target))
                if target in incoming:
                    finding('multiple-references', entry.index, field, target)
                else:
                    incoming[target] = (entry.index, field)

        # Colour marks are traversal state, independent of the CFBF red/black flags.
        state: dict[int, int] = {}
        for seed in active:
            checkpoint()
            if seed in state:
                continue
            state[seed] = 1
            stack = [(seed, 0)]
            while stack:
                checkpoint()
                index, position = stack[-1]
                if position == len(edges[index]):
                    state[index] = 2
                    stack.pop()
                    continue
                stack[-1] = (index, position+1)
                field, target = edges[index][position]
                if state.get(target) == 1:
                    finding('cycle', index, field, target)
                elif target not in state:
                    state[target] = 1
                    stack.append((target, 0))

        reached = {0}
        pending = [0]
        while pending:
            checkpoint()
            for _, target in edges[pending.pop()]:
                if target not in reached:
                    reached.add(target)
                    pending.append(target)
        unreached = tuple(index for index in active if index not in reached)
        for index in unreached:
            checkpoint()
            findings.append({'code': 'unreached-entry', 'location': f'cfbf:directory={index}', 'target': None})
        return {'directory_links_assessed': True, 'directory_links_valid': not findings,
                'directory_link_findings': tuple(findings),
                'directory_reached_entries': tuple(index for index in active if index in reached),
                'directory_unreached_entries': unreached}

    def inspect(self) -> tuple[tuple[BinaryItem, ...], dict[str, Any]]:
        from opendoc_formats.anatomy import BinaryItem

        self.allocation()
        entries = self.entries()
        links = self.directory_links(entries)
        logical = [self.stream(entry) for entry in entries]
        physical = []
        for sector in range(-1, self.count):
            checkpoint()
            offset = 0 if sector == -1 else self.offset(sector)
            chunk = self.data[offset:offset+self.sector_size]
            value = None if sector == -1 else self.table(self.fat, sector, 'fat')
            role = 'header' if sector == -1 else self.used.get(sector, 'free' if value == FREE else 'unclaimed')
            physical.append(BinaryItem(f'cfbf:sector={sector}', 'cfbf-physical-sector', len(chunk),
                                       hashlib.sha256(chunk).hexdigest(), details=(('offset', offset), ('role', role),
                                       ('allocation_value', value)), payload=bytes(chunk) if self.capture else None))
        return tuple(physical+logical), {
            'major_version': self.version, 'minor_version': struct.unpack_from('<H', self.data, 24)[0],
            'sector_size': self.sector_size, 'mini_sector_size': 64, 'physical_sectors': self.count,
            'fat_sectors': tuple(self.fat), 'mini_fat_sectors': tuple(self.mini_fat),
            'directory_objects': len(entries), 'directory_slots': self.directory_slots,
            'directory_tree_assessed': False, 'assessment_complete': False,
            **links,
        }


def inspect_cfbf(data: bytes, limits: AnatomyLimits, capture: bool) -> tuple[tuple[BinaryItem, ...], dict[str, Any]]:
    return _Reader(data, limits, capture).inspect()
