"""Common Anatomy quotas and physical source retention for sfnt programs."""

import json
import struct
import sys
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, compare_snapshots, inspect_binary
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from tests.binary_fixtures import own_placement_font, zip_bytes
from tests.test_sfnt_inspection import wrapper


@pytest.mark.parametrize('source', [wrapper(), wrapper(version=b'OTTO'), own_placement_font()])
def test_original_program_and_table_ranges_survive_common_snapshot_and_capture(source):
    snapshot = inspect_binary(source, capture=True)
    assert snapshot.container == 'sfnt' and snapshot.opc is None and snapshot.epub is None
    assert not dict(snapshot.details)['assessment_complete']
    original, *tables = snapshot.items
    assert original.locator == 'sfnt:source' and original.payload == source
    for table in tables:
        details = dict(table.details)
        assert table.kind == 'sfnt-table' and table.payload == source[details['offset']:details['offset']+table.size]
    assert all(item.payload is None for item in inspect_binary(source).items)
    assert inspect_binary(source, container='sfnt').source_sha256 == snapshot.source_sha256
    assert compare_snapshots(snapshot, inspect_binary(source))['binary_identical']
    assert json.loads(json.dumps(snapshot.to_dict()))['container'] == 'sfnt'


@pytest.mark.parametrize('limits', [AnatomyLimits(max_input_bytes=51), AnatomyLimits(max_part_bytes=51),
                                   AnatomyLimits(max_items=2), AnatomyLimits(max_total_bytes=57)])
@pytest.mark.parametrize('checksums', [False, True])
def test_all_common_limits_charge_original_program_plus_declared_tables(limits, checksums):
    # 52 source bytes and two 3-byte tables, three inventory items in total.
    with pytest.raises(ResourceLimitError):
        inspect_binary(wrapper(), capture=True, sfnt_checksums=checksums, limits=limits)


def test_exact_aggregate_boundary_and_zero_remaining_table_budget():
    source = wrapper()
    assert len(source) == 52
    assert len(inspect_binary(source, limits=AnatomyLimits(max_items=3, max_part_bytes=52, max_total_bytes=58)).items) == 3
    with pytest.raises(ResourceLimitError):
        inspect_binary(source, limits=AnatomyLimits(max_total_bytes=52))
    empty = bytearray(source)
    struct.pack_into('>I', empty, 24, 0)
    struct.pack_into('>I', empty, 40, 0)
    assert len(inspect_binary(bytes(empty), limits=AnatomyLimits(max_total_bytes=52)).items) == 3
    with pytest.raises(ResourceLimitError):
        inspect_binary(source, limits=AnatomyLimits(max_items=1))


def test_changed_directory_checksum_is_storage_change_even_with_identical_table_payload():
    source = wrapper()
    changed = bytearray(source)
    struct.pack_into('>I', changed, 16, 99)
    comparison = compare_snapshots(inspect_binary(source), inspect_binary(bytes(changed)))
    assert 'sfnt:table=OWN ' in comparison['storage_changed']
    assert 'sfnt:table=OWN ' not in comparison['content_changed']
    assert 'sfnt:source' in comparison['content_changed']


def test_pdf_marker_inside_font_payload_does_not_choose_pdf_profile():
    source = bytearray(wrapper())
    source[44:49] = b'%PDF-'
    assert inspect_binary(bytes(source)).container == 'sfnt'


def test_zip_polyglot_requires_explicit_profile_and_preserves_both_physical_views():
    source = wrapper()+zip_bytes([('own.txt', b'Own ZIP view')])
    with pytest.raises(UnsupportedDocumentError, match='ambiguous'):
        inspect_binary(source)
    assert inspect_binary(source, container='sfnt', capture=True).items[0].payload == source
    assert inspect_binary(source, container='zip', capture=True).items[0].payload == b'Own ZIP view'


def test_nested_font_is_inspected_explicitly_and_cli_writes_generated_names(tmp_path, monkeypatch):
    from tools.document_anatomy import main

    source = wrapper()
    outer = inspect_binary(zip_bytes([('word/fonts/own.ttf', source)]), capture=True)
    assert inspect_binary(outer.items[0].payload).container == 'sfnt'
    path, output = tmp_path/'own.ttf', tmp_path/'anatomy'
    path.write_bytes(source)
    monkeypatch.setattr(sys, 'argv', ['document_anatomy', str(path), '--container', 'sfnt', '--output', str(output)])
    main()
    report = json.loads((output/'inventory.json').read_text(encoding='utf-8'))
    assert report['container'] == 'sfnt'
    assert (output/report['items'][0]['payload_file']).read_bytes() == source
    assert all((output/item['payload_file']).parent == output for item in report['items'])


def test_cancellation_inside_sfnt_table_parser_is_inherited_from_common_scope(monkeypatch):
    import opendoc_formats.native.sfnt as sfnt

    stop = Event()
    original = sfnt.hashlib.sha256

    def cancel(payload):
        result = original(payload)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(sfnt.hashlib, 'sha256', cancel)
        with pytest.raises(OperationCancelledError):
            inspect_binary(wrapper(), cancelled=stop.is_set)
    assert inspect_binary(wrapper()).items


@pytest.mark.parametrize('capture', [False, True])
def test_optional_checksum_audit_uses_same_snapshot_and_preserves_payloads(capture):
    from dataclasses import asdict

    from opendoc_formats.native.sfnt import inspect_sfnt_checksums

    source = own_placement_font()
    ordinary = inspect_binary(source, capture=capture)
    audited = inspect_binary(source, capture=capture, sfnt_checksums=True)
    assert audited.items == ordinary.items and audited.source_sha256 == ordinary.source_sha256
    assert 'checksums' not in dict(ordinary.details)
    checksums = dict(audited.details)['checksums']
    assert checksums == asdict(inspect_sfnt_checksums(source))
    assert checksums['adjustment_valid'] and all(table['valid'] for table in checksums['tables'])
    assert not checksums['assessment_complete'] and not dict(audited.details)['assessment_complete']
    assert json.loads(json.dumps(audited.to_dict()))['details']['checksums']['source_sha256'] == audited.source_sha256


@pytest.mark.parametrize('value', [None, 1, 'true'])
def test_checksum_flag_requires_boolean_before_source_read(value):
    with pytest.raises(TypeError, match='boolean'):
        inspect_binary('does-not-exist.ttf', sfnt_checksums=value)


def test_checksum_option_is_not_silently_ignored_for_other_containers():
    with pytest.raises(ValueError, match='requires the sfnt'):
        inspect_binary(zip_bytes([('own', b'Own')]), sfnt_checksums=True)


@pytest.mark.parametrize('capture', [False, True])
def test_cli_checksum_report_and_comparison_preserve_source_files(tmp_path, monkeypatch, capture):
    from tools.document_anatomy import main

    original = wrapper()
    changed = bytearray(original)
    struct.pack_into('>I', changed, 16, 0x4f776e00)
    source, other, output = tmp_path/'own.ttf', tmp_path/'changed.ttf', tmp_path/'anatomy'
    source.write_bytes(original)
    other.write_bytes(changed)
    args = ['document_anatomy', str(source), '--sfnt-checksums', '--compare', str(other), '--output', str(output)]
    if not capture:
        args.append('--no-payloads')
    monkeypatch.setattr(sys, 'argv', args)
    main()
    report = json.loads((output/'inventory.json').read_text(encoding='utf-8'))
    checksums = report['details']['checksums']
    assert checksums['adjustment_valid'] is None and not checksums['tables'][0]['valid']
    assert report['comparison']['container_metadata_changed']
    assert 'sfnt:table=OWN ' in report['comparison']['storage_changed']
    assert 'sfnt:table=OWN ' not in report['comparison']['content_changed']
    assert source.read_bytes() == original and other.read_bytes() == changed
    if capture:
        assert (output/report['items'][0]['payload_file']).read_bytes() == original
    else:
        assert all('payload_file' not in item for item in report['items'])
        assert [path.name for path in output.iterdir()] == ['inventory.json']


def test_cancellation_inside_optional_checksum_is_inherited_and_scope_restored(monkeypatch):
    import opendoc_formats.native.sfnt as sfnt
    from tests.test_sfnt_checksums import program

    source = program(b'Own ' * 65536)
    original = sfnt._checksum
    polls, active = [], []

    def checksum(data, cancelled):
        active.append(True)
        return original(data, cancelled)

    def cancelled():
        if active:
            polls.append(True)
        return len(polls) == 3

    with monkeypatch.context() as context:
        context.setattr(sfnt, '_checksum', checksum)
        with pytest.raises(OperationCancelledError):
            inspect_binary(source, sfnt_checksums=True, cancelled=cancelled)
    assert len(polls) == 3
    assert inspect_binary(source, sfnt_checksums=True).items
