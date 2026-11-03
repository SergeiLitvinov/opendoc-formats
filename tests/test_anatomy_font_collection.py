"""Selected collection faces in the shared physical inspection API and CLI."""

import json
import struct
import sys
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, compare_snapshots, inspect_binary
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.sfnt import inspect_sfnt
from tests.binary_fixtures import own_placement_font, zip_bytes
from tests.test_native_font_collection import collection


@pytest.mark.parametrize('face_index', [0, 1])
@pytest.mark.parametrize('version,signed', [(1, False), (2, False), (2, True)])
@pytest.mark.parametrize('capture', [False, True])
def test_common_snapshot_retains_collection_and_selected_absolute_payloads(face_index, version, signed, capture):
    source = collection(version=version, signed=signed)
    snapshot = inspect_binary(source, sfnt_face_index=face_index, capture=capture)
    native = inspect_sfnt(source, face_index=face_index, capture=capture)
    assert snapshot.container == 'sfnt' and snapshot.source_sha256 == native.source_sha256
    assert snapshot.items[0].locator == 'sfnt:source' and snapshot.items[0].size == len(source)
    assert snapshot.items[0].payload == (source if capture else None)
    assert dict(snapshot.details)['face_index'] == face_index
    assert dict(snapshot.details)['directory_offset'] == native.directory_offset
    assert not dict(snapshot.details)['assessment_complete']
    for item, table in zip(snapshot.items[1:], native.tables, strict=True):
        assert item.locator == f'sfnt:face={face_index}:table={table.tag}'
        assert item.payload == table.payload and item.sha256 == table.sha256
        assert dict(item.details)['offset'] == table.offset
    assert json.loads(json.dumps(snapshot.to_dict()))['details']['face_index'] == face_index


def test_different_face_views_are_not_the_same_literal_table_addresses():
    source = collection()
    before = inspect_binary(source, sfnt_face_index=0)
    after = inspect_binary(source, sfnt_face_index=1)
    comparison = compare_snapshots(before, after)
    assert comparison['binary_identical'] and comparison['container_metadata_changed']
    assert comparison['added'] and comparison['removed']
    assert not comparison['content_changed']


@pytest.mark.parametrize('limits', [AnatomyLimits(max_part_bytes=1), AnatomyLimits(max_total_bytes=1),
                                   AnatomyLimits(max_items=1)])
def test_collection_source_and_tables_charge_common_budgets(limits):
    with pytest.raises(ResourceLimitError):
        inspect_binary(collection(), sfnt_face_index=0, limits=limits)


def test_exact_source_plus_selected_table_budget_and_face_array_budget():
    source = collection()
    inventory = inspect_sfnt(source, face_index=0)
    total = len(source)+sum(table.length for table in inventory.tables)
    limits = AnatomyLimits(max_total_bytes=total, max_part_bytes=len(source), max_items=1+len(inventory.tables))
    assert inspect_binary(source, sfnt_face_index=0, limits=limits).items
    with pytest.raises(ResourceLimitError):
        inspect_binary(source, sfnt_face_index=0, limits=AnatomyLimits(max_total_bytes=total-1))
    repeated = struct.pack('>4s2I', b'ttcf', 0x10000, 100)
    with pytest.raises(ResourceLimitError, match='max_faces'):
        inspect_binary(repeated, sfnt_face_index=0, limits=AnatomyLimits(max_items=4))


@pytest.mark.parametrize('value', [True, -1, '0', 0.5])
def test_face_index_is_checked_before_source_read(value):
    with pytest.raises(ValueError):
        inspect_binary('missing.ttc', sfnt_face_index=value)


def test_scope_and_checksum_options_are_not_silently_ignored():
    with pytest.raises(ValueError, match='requires the sfnt'):
        inspect_binary(zip_bytes([('own', b'Own')]), sfnt_face_index=0)
    with pytest.raises(UnsupportedDocumentError, match='explicit face_index'):
        inspect_binary(collection())
    with pytest.raises(UnsupportedDocumentError, match='standalone'):
        inspect_binary(collection(), sfnt_face_index=0, sfnt_checksums=True)
    assert inspect_binary(own_placement_font(), sfnt_face_index=0) == inspect_binary(own_placement_font())


def test_collection_zip_polyglot_requires_an_explicit_container_profile():
    source = collection()+zip_bytes([('own', b'Own ZIP view')])
    with pytest.raises(UnsupportedDocumentError, match='ambiguous'):
        inspect_binary(source, sfnt_face_index=0)
    assert inspect_binary(source, container='sfnt', sfnt_face_index=0, capture=True).items[0].payload == source
    assert inspect_binary(source, container='zip', capture=True).items[0].payload == b'Own ZIP view'


def test_pdf_marker_inside_collection_is_not_a_second_container():
    source = collection()+b'%PDF-'
    assert inspect_binary(source, sfnt_face_index=0).container == 'sfnt'


@pytest.mark.parametrize('capture', [False, True])
def test_cli_selects_same_face_for_comparison_and_uses_safe_payload_names(tmp_path, monkeypatch, capture):
    from tools.document_anatomy import main

    source = collection(version=2, signed=True)
    path, other, output = tmp_path/'own.ttc', tmp_path/'other.ttc', tmp_path/'dissection'
    path.write_bytes(source)
    other.write_bytes(source)
    args = ['document_anatomy', str(path), '--sfnt-face-index', '1', '--compare', str(other), '--output', str(output)]
    if not capture:
        args.append('--no-payloads')
    monkeypatch.setattr(sys, 'argv', args)
    main()
    report = json.loads((output/'inventory.json').read_text(encoding='utf-8'))
    assert report['details']['face_index'] == 1 and report['comparison']['binary_identical']
    if capture:
        assert (output/report['items'][0]['payload_file']).read_bytes() == source
        assert all((output/item['payload_file']).parent == output for item in report['items'])
    else:
        assert all('payload_file' not in item for item in report['items'])
    assert path.read_bytes() == other.read_bytes() == source


def test_common_cancellation_after_collection_header_does_not_return_partial_view(monkeypatch):
    import opendoc_formats.native.sfnt as native

    source = collection()
    original, stop = native._collection_directory, Event()

    def interrupted(*args):
        result = original(*args)
        stop.set()
        return result

    monkeypatch.setattr(native, '_collection_directory', interrupted)
    with pytest.raises(OperationCancelledError):
        inspect_binary(source, sfnt_face_index=1, cancelled=stop.is_set)
