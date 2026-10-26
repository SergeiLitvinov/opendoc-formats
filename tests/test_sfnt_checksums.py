"""Independent checksum oracle, damaged-byte observations and bounded cancellation."""

import builtins
import hashlib
import struct

import pytest
from fontTools.ttLib.sfnt import calcChecksum

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.sfnt import SfntLimits, inspect_sfnt, inspect_sfnt_checksums
from tests.binary_fixtures import own_placement_font


def program(payload, *, head=True, version=b'\0\1\0\0'):
    tables = [(b'OWN ', payload)]
    if head:
        tables.append((b'head', struct.pack('>3I', 0x10000, 0, 0)))
    directory, storage = bytearray(), bytearray()
    for tag, data in tables:
        offset = 12+16*len(tables)+len(storage)
        directory.extend(struct.pack('>4sIII', tag, calcChecksum(data), offset, len(data)))
        storage.extend(data)
        storage.extend(bytes(-len(storage) % 4))
    result = bytearray(struct.pack('>4s4H', version, len(tables), 0, 0, 0)+directory+storage)
    if head:
        offset = struct.unpack_from('>I', directory, 16+8)[0]
        struct.pack_into('>I', result, offset+8, (0xb1b0afba-calcChecksum(result)) & 0xffffffff)
    return bytes(result)


@pytest.mark.parametrize('version', [b'\0\1\0\0', b'OTTO'])
@pytest.mark.parametrize('length', [0, 1, 2, 3, 4, 7, 65535, 65536, 65537])
def test_checksums_match_independent_oracle_across_padding_and_chunk_boundaries(version, length):
    payload = (b'\xff\x80\x01\x02'*(length//4+1))[:length]
    source = program(payload, version=version)
    report = inspect_sfnt_checksums(source)
    assert report.source_sha256 == hashlib.sha256(source).hexdigest()
    assert report.whole_checksum == calcChecksum(source) == 0xb1b0afba
    assert report.adjustment_valid and report.declared_adjustment == report.expected_adjustment
    assert all(item.valid for item in report.tables) and not report.assessment_complete
    assert report.tables[0].computed == calcChecksum(payload)


def test_real_owned_font_checksums_match_directory_without_importing_engine(monkeypatch):
    source = own_placement_font()
    inventory = inspect_sfnt(source)
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Checksum audit imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    report = inspect_sfnt_checksums(source)
    assert all(item.valid for item in report.tables) and report.adjustment_valid
    assert [(item.tag, item.declared) for item in report.tables] == [
        (table.tag, table.declared_checksum) for table in inventory.tables
    ]


@pytest.mark.parametrize('damage', ['payload', 'directory-checksum', 'adjustment', 'padding', 'trailing'])
def test_damage_is_reported_without_repairing_or_discarding_source(tmp_path, damage):
    source = bytearray(program(b'Own'))
    inventory = inspect_sfnt(bytes(source))
    own, head = inventory.tables
    if damage == 'payload':
        source[own.offset] ^= 1
    elif damage == 'directory-checksum':
        source[own.directory_offset+4] ^= 1
    elif damage == 'adjustment':
        source[head.offset+8] ^= 1
    elif damage == 'padding':
        source[own.offset+own.length] = 1
    else:
        source.extend(b'\x01')
    path = tmp_path/'original.ttf'
    path.write_bytes(source)
    report = inspect_sfnt_checksums(path)
    assert not report.adjustment_valid
    assert report.tables[0].valid == (damage not in ('payload', 'directory-checksum'))
    assert report.tables[1].valid  # head checksum excludes the adjustment field.
    assert path.read_bytes() == source
    assert report.whole_checksum == calcChecksum(source)


def test_no_head_reports_unknown_adjustment_and_truncated_head_is_explicit():
    source = program(b'Own', head=False)
    report = inspect_sfnt_checksums(source)
    assert report.tables[0].valid
    assert report.declared_adjustment is report.expected_adjustment is report.adjustment_valid is None
    short = bytearray(program(b'Own'))
    struct.pack_into('>I', short, 12+16+12, 8)
    with pytest.raises(InvalidDocumentError, match='adjustment field'):
        inspect_sfnt_checksums(bytes(short))


def test_existing_size_and_table_work_limits_apply():
    source = program(b'Own')
    for limits in (SfntLimits(max_input_bytes=len(source)-1), SfntLimits(max_tables=1),
                   SfntLimits(max_table_bytes=2), SfntLimits(max_total_table_bytes=14)):
        with pytest.raises(ResourceLimitError):
            inspect_sfnt_checksums(source, limits=limits)
    with pytest.raises(UnsupportedDocumentError):
        inspect_sfnt_checksums(b'wOFF'+bytes(100))


def test_cancel_inside_large_table_checksum_preserves_original(tmp_path, monkeypatch):
    import opendoc_formats.native.sfnt as native

    source = program(b'Own ' * 65536)
    path = tmp_path/'own.ttf'
    path.write_bytes(source)
    original = native._checksum
    polls, active = [], []

    def checksum(data, cancelled):
        active.append(True)
        return original(data, cancelled)

    def cancelled():
        if active:
            polls.append(True)
        return len(polls) == 3

    monkeypatch.setattr(native, '_checksum', checksum)
    with pytest.raises(OperationCancelledError):
        inspect_sfnt_checksums(path, cancelled=cancelled)
    assert len(polls) == 3 and path.read_bytes() == source
