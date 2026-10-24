"""Original compound sector chains, without producing them through an inspected parser."""

import hashlib
import json
import random
import struct
import sys
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, compare_snapshots, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from tests.binary_fixtures import own_cfbf, zip_bytes


@pytest.mark.parametrize('version', [3, 4])
def test_original_sector_and_stream_payloads_offsets_and_slack_are_exact(version):
    source, small, big = own_cfbf(version=version)
    snapshot = inspect_binary(source, capture=True)
    assert snapshot.container == 'cfbf' and snapshot.opc is None and snapshot.epub is None
    assert not dict(snapshot.details)['assessment_complete']
    assert not dict(snapshot.details)['directory_tree_assessed']
    physical = [item for item in snapshot.items if item.kind == 'cfbf-physical-sector']
    assert b''.join(item.payload for item in physical) == source
    assert physical[-1].payload.startswith(b'Own unclaimed allocated bytes\x00\xff')
    assert dict(physical[-1].details)['role'] == 'unclaimed'
    streams = {dict(item.details)['name']: item for item in snapshot.items if item.kind != 'cfbf-physical-sector'}
    for name, expected in [('Small', small), ('Large', big)]:
        item = streams[name]
        assert item.payload == expected and item.size == len(expected)
        assert item.sha256 == hashlib.sha256(expected).hexdigest()
        details = dict(item.details)
        assert b''.join(source[offset:offset+size] for offset, size in details['data_ranges']) == expected
        assert bytes.fromhex(details['entry_hex']) == source[details['entry_offset']:details['entry_offset']+128]
    assert dict(streams['Small'].details)['chain'] == (0, 2, 1)
    assert dict(streams['Small'].details)['allocation'] == 'mini-fat'
    assert streams['Folder'].payload == b''
    assert json.loads(json.dumps(snapshot.to_dict()))['container'] == 'cfbf'
    assert all(item.payload is None for item in inspect_binary(source).items)
    assert compare_snapshots(snapshot, inspect_binary(source))['binary_identical']


def test_extended_difat_is_followed_and_every_physical_fat_sector_is_accounted():
    source, small, big = own_cfbf(difat=True)
    snapshot = inspect_binary(source, capture=True)
    assert len(dict(snapshot.details)['fat_sectors']) == 110
    assert any(dict(item.details).get('role') == 'difat' for item in snapshot.items)
    assert next(item for item in snapshot.items if item.locator == 'cfbf:directory=1').payload == small
    assert next(item for item in snapshot.items if item.locator == 'cfbf:directory=2').payload == big


def test_old_version_three_high_dword_is_preserved_without_forging_a_huge_size():
    source, small, big = own_cfbf(high_size_bits=0x12345678)
    snapshot = inspect_binary(source, capture=True)
    item = next(item for item in snapshot.items if item.locator == 'cfbf:directory=2')
    assert item.payload == big and item.size == 4096
    assert dict(item.details)['stream_size_raw'] == (0x12345678 << 32) | 4096


def changed(offset, value, *, data=None, fmt='<I'):
    source = bytearray(data if data is not None else own_cfbf()[0])
    struct.pack_into(fmt, source, offset, value)
    return bytes(source)


@pytest.mark.parametrize('offset,value,error', [
    (26, 7, UnsupportedDocumentError), (28, 0xfeff, UnsupportedDocumentError),
    (30, 12, UnsupportedDocumentError), (32, 5, UnsupportedDocumentError),
    (56, 8192, UnsupportedDocumentError), (40, 1, InvalidDocumentError),
    (44, 999, InvalidDocumentError), (68, 0, InvalidDocumentError),
    (72, 999, InvalidDocumentError), (60, 0, InvalidDocumentError),
])
def test_unsupported_header_profiles_and_inconsistent_control_chains_are_explicit(offset, value, error):
    with pytest.raises(error, match='cfbf:'):
        inspect_binary(changed(offset, value, fmt='<H' if offset < 34 else '<I'))


@pytest.mark.parametrize('offset,value', [
    (512+1*4, 1),  # directory cycle
    (512+4*4, 4),  # large-stream cycle
    (512+4*4, 1000),  # out-of-file FAT target
    (512+4*4, 0xfffffffe),  # too-short large stream
    (512+0*4, 0xfffffffe),  # incorrect FAT sector marker
    (1536, 0),  # mini chain cycle
    (1536, 3),  # mini index beyond the root's declared mini stream
    (1536, 0xfffffffe),  # too-short mini chain
    (1024+2*128+116, 3),  # stream sharing its root mini stream's physical sector
    (1024+2*128+120, 4608),  # declared normal size longer than the chain
    (512+11*4, 12),  # extra allocation after the declared large-stream length
    (64, 2),  # mini FAT chain shorter than its header count
])
def test_cycles_crosslinks_invalid_addresses_and_declared_sizes_do_not_yield_partial_success(offset, value):
    with pytest.raises(InvalidDocumentError, match='cfbf:'):
        inspect_binary(changed(offset, value), capture=True)


@pytest.mark.parametrize('payload', [own_cfbf()[0][:-1], own_cfbf()[0][:512], b'bad signature'])
def test_truncated_or_forced_invalid_sources_are_rejected(payload):
    with pytest.raises(InvalidDocumentError, match='cfbf:'):
        inspect_binary(payload, container='cfbf')


@pytest.mark.parametrize('offset,value,fmt', [(1024+128+64, 3, '<H'), (1024+128+64, 66, '<H'),
                                            (1024+128, 0xd800, '<H'), (1024+66, 2, '<B'),
                                            (1024+66, 0, '<B')])
def test_invalid_directory_root_types_and_utf16_names_are_explicit(offset, value, fmt):
    with pytest.raises(InvalidDocumentError, match='cfbf:directory'):
        inspect_binary(changed(offset, value, fmt=fmt))


def test_two_small_streams_cannot_claim_the_same_mini_sectors():
    source = changed(1024+2*128+120, 145)
    source = changed(1024+2*128+116, 0, data=source)
    with pytest.raises(InvalidDocumentError, match='cross-linked'):
        inspect_binary(source)


def test_difat_cycles_and_invalid_markers_are_bounded():
    source = own_cfbf(difat=True)[0]
    sector = struct.unpack_from('<I', source, 68)[0]
    loop = changed((sector+2)*512-4, sector, data=source)
    loop = changed(72, 2, data=loop)
    with pytest.raises(InvalidDocumentError, match='cycle or cross-linked'):
        inspect_binary(loop)
    marker = changed(512+sector*4, 0xffffffff, data=source)
    with pytest.raises(InvalidDocumentError, match='allocation marker'):
        inspect_binary(marker)


def test_controlled_wire_mutations_never_escape_as_index_or_decoder_errors():
    original = own_cfbf()[0]
    randomizer = random.Random(721)
    for _ in range(100):
        source = bytearray(original)
        for _ in range(randomizer.randint(1, 4)):
            offset = randomizer.randrange(len(source))
            source[offset] ^= randomizer.randrange(1, 256)
        immutable = bytes(source)
        try:
            result = inspect_binary(immutable, container='cfbf', capture=True)
        except (InvalidDocumentError, UnsupportedDocumentError, ResourceLimitError):
            continue
        assert b''.join(item.payload for item in result.items if item.kind == 'cfbf-physical-sector') == immutable
        assert not dict(result.details)['assessment_complete']


def test_directory_links_are_raw_observations_without_a_tree_validity_claim():
    source = changed(1024+76, 0)  # root points to itself: do not recurse or claim a valid storage hierarchy
    snapshot = inspect_binary(source)
    root = next(item for item in snapshot.items if item.locator == 'cfbf:directory=0')
    assert dict(root.details)['child'] == 0
    assert not dict(snapshot.details)['directory_tree_assessed']
    assert not dict(snapshot.details)['assessment_complete']


def test_polyglot_requires_explicit_container_and_each_physical_view_remains_available():
    source = own_cfbf()[0]+zip_bytes([('own.txt', b'Own ZIP bytes')])
    source += bytes(-len(source) % 512)
    with pytest.raises(UnsupportedDocumentError, match='ambiguous'):
        inspect_binary(source)
    assert inspect_binary(source, container='zip', capture=True).items[0].payload == b'Own ZIP bytes'
    compound = inspect_binary(source, container='cfbf', capture=True)
    assert b''.join(item.payload for item in compound.items if item.kind == 'cfbf-physical-sector') == source


@pytest.mark.parametrize('version', [3, 4])
def test_selected_budgets_cover_physical_and_logical_data_before_return(version):
    source, small, big = own_cfbf(version=version)
    required = len(source)+192+len(small)+len(big)
    snapshot = inspect_binary(source, limits=AnatomyLimits(max_total_bytes=required))
    assert snapshot.items
    for limits, quota in [(AnatomyLimits(max_input_bytes=len(source)-1), 'Input exceeds'),
                          (AnatomyLimits(max_total_bytes=required-1), 'max_total_bytes'),
                          (AnatomyLimits(max_part_bytes=4095), 'max_part_bytes'),
                          (AnatomyLimits(max_items=2), 'max_items')]:
        with pytest.raises(ResourceLimitError, match=quota):
            inspect_binary(source, limits=limits)


def test_cancellation_inside_mini_chain_restores_context_and_original_file(tmp_path, monkeypatch):
    from opendoc_formats.native.cfbf import _Reader

    source, _, _ = own_cfbf()
    path = tmp_path/'own.bin'
    path.write_bytes(source)
    stop = Event()
    read_table = _Reader.table

    def table(self, sectors, index, owner):
        result = read_table(self, sectors, index, owner)
        if owner == 'directory=1':
            stop.set()
        return result

    monkeypatch.setattr(_Reader, 'table', table)
    with pytest.raises(OperationCancelledError):
        inspect_binary(path, cancelled=stop.is_set)
    assert path.read_bytes() == source
    assert inspect_binary(source).items


def test_embedded_container_is_inspected_explicitly_and_cli_uses_owned_payload_names(tmp_path, monkeypatch):
    from tools.document_anatomy import main

    source, small, _ = own_cfbf()
    outer = inspect_binary(zip_bytes([('word/embeddings/own.bin', source)]), capture=True)
    assert len(outer.items) == 1 and not outer.items[0].xml_nodes
    assert inspect_binary(outer.items[0].payload).container == 'cfbf'
    path, output = tmp_path/'own.bin', tmp_path/'dissection'
    path.write_bytes(source)
    monkeypatch.setattr(sys, 'argv', ['document_anatomy', str(path), '--output', str(output), '--compare', str(path)])
    main()
    report = json.loads((output/'inventory.json').read_text(encoding='utf-8'))
    assert report['container'] == 'cfbf' and report['comparison']['binary_identical']
    item = next(item for item in report['items'] if item['locator'] == 'cfbf:directory=1')
    assert (output/item['payload_file']).read_bytes() == small
    assert all((output/item['payload_file']).parent == output for item in report['items'])
