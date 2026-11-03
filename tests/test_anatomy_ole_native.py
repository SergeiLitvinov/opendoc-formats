"""Independent MS-OLEDS envelope bytes; application-specific Package stays opaque."""

import builtins
import hashlib
import json
import struct
import sys
from dataclasses import replace
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.anatomy_tree import inspect_container_tree
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from tests.binary_fixtures import own_cfbf, zip_bytes
from tools.container_anatomy import main as tree_main
from tools.document_anatomy import main


def envelope(payload):
    return struct.pack('<I', len(payload)) + payload


def named_stream(payload, name='\x01Ole10Native'):
    """Patch the known mini-chain of our independent wire CFBF, not inspector output."""
    assert 0 < len(payload) <= 192
    source = bytearray(own_cfbf()[0])
    entry = 2 * 512 + 128
    encoded = (name + '\x00').encode('utf-16-le')
    assert len(encoded) <= 64
    source[entry:entry + 64] = encoded.ljust(64, b'\x00')
    struct.pack_into('<H', source, entry + 64, len(encoded))
    struct.pack_into('<Q', source, entry + 120, len(payload))
    chain = (0, 2, 1)[:(len(payload) + 63) // 64]
    for index in (0, 1, 2):
        struct.pack_into('<I', source, 3 * 512 + 4 * index, 0xffffffff)
    for index, sector in enumerate(chain):
        struct.pack_into('<I', source, 3 * 512 + 4 * sector,
                         chain[index + 1] if index + 1 < len(chain) else 0xfffffffe)
        chunk = payload[index * 64:(index + 1) * 64]
        offset = 4 * 512 + sector * 64
        source[offset:offset + len(chunk)] = chunk
    return bytes(source)


@pytest.mark.parametrize('payload', [b'', b'Own UTF-8 \xd0\x94\x00\xff', zip_bytes([('own.txt', b'Own bytes')])])
def test_explicit_envelope_inventory_recovers_all_bytes_and_offsets(payload):
    source = envelope(payload)
    snapshot = inspect_binary(source, container='ole-native', capture=True)
    assert snapshot.container == 'ole-native' and snapshot.opc is snapshot.epub is None
    assert b''.join(item.payload for item in snapshot.items) == source
    assert [item.locator for item in snapshot.items] == ['ole-native:header', 'ole-native:data']
    assert dict(snapshot.items[1].details) == {'offset': 4, 'length': len(payload)}
    assert snapshot.items[1].sha256 == hashlib.sha256(payload).hexdigest()
    assert dict(snapshot.details) == {'native_data_size': len(payload), 'assessment_complete': False,
                                     'application_data_assessed': False}
    uncaptured = inspect_binary(source, container='ole-native')
    assert all(item.payload is None for item in uncaptured.items)
    assert uncaptured.to_dict() == snapshot.to_dict()
    assert json.loads(json.dumps(snapshot.to_dict()))['source_size'] == len(source)


@pytest.mark.parametrize('source', [b'', b'\x01', b'\x01\x00\x00', struct.pack('<I', 0xffffffff),
                                   envelope(b'abc')[:-1], envelope(b'abc') + b'padding'])
def test_truncated_huge_or_trailing_size_refuses_without_repair(source):
    with pytest.raises(InvalidDocumentError, match='ole-native:header'):
        inspect_binary(source, container='ole-native')


@pytest.mark.parametrize('quota,bound', [('max_items', 2), ('max_part_bytes', 9), ('max_total_bytes', 9),
                                       ('max_input_bytes', 9)])
def test_each_selected_envelope_quota_has_exact_boundary(quota, bound):
    source = envelope(b'bytes')
    assert inspect_binary(source, container='ole-native', limits=replace(AnatomyLimits(), **{quota: bound})).items
    with pytest.raises(ResourceLimitError):
        inspect_binary(source, container='ole-native', limits=replace(AnatomyLimits(), **{quota: bound - 1}))


def test_named_cfbf_native_data_reaches_nested_zip_with_exact_original_ranges():
    inner = zip_bytes([('own', b'Own embedded file')])
    compound = named_stream(envelope(inner))
    source = zip_bytes([('word/embeddings/own.bin', compound)])
    tree = inspect_container_tree(source, capture=True)
    assert [entry.snapshot.container for entry in tree.occurrences] == ['zip', 'cfbf', 'ole-native', 'zip']
    assert tree.occurrences[-1].location == ('zip:/word/embeddings/own.bin', 'cfbf:directory=1', 'ole-native:data')
    wrapper = tree.occurrences[2].snapshot
    assert b''.join(item.payload for item in wrapper.items) == envelope(inner)
    assert tree.occurrences[-1].snapshot.items[0].payload == b'Own embedded file'
    physical = tree.occurrences[1].snapshot
    assert b''.join(item.payload for item in physical.items if item.kind == 'cfbf-physical-sector') == compound
    assert inspect_container_tree(source).to_dict() == tree.to_dict()


def test_name_is_authoritative_and_application_specific_data_is_not_signature_scanned():
    inner = zip_bytes([])
    compound = named_stream(envelope(inner), name='NotOle10Native')
    assert len(inspect_container_tree(compound).occurrences) == 1
    package = b'Own application metadata\x00' + inner
    tree = inspect_container_tree(named_stream(envelope(package)), capture=True)
    assert [entry.snapshot.container for entry in tree.occurrences] == ['cfbf', 'ole-native']
    assert tree.occurrences[-1].snapshot.items[1].payload == package
    assert not dict(tree.occurrences[-1].snapshot.details)['application_data_assessed']
    # General auto detection can still see an SFX ZIP; it does not infer an OLE envelope.
    assert inspect_binary(envelope(inner)).container == 'zip'
    with pytest.raises(UnsupportedDocumentError):
        inspect_binary(envelope(b'Unknown application bytes'))


@pytest.mark.parametrize('quota', ['max_items', 'max_total_bytes'])
def test_wrapper_and_native_data_use_the_same_tree_budget(quota):
    source = named_stream(envelope(zip_bytes([])))
    tree = inspect_container_tree(source)
    boundary = tree.charged_items if quota == 'max_items' else tree.charged_bytes
    assert inspect_container_tree(source, limits=replace(AnatomyLimits(), **{quota: boundary})) == tree
    with pytest.raises(ResourceLimitError):
        inspect_container_tree(source, limits=replace(AnatomyLimits(), **{quota: boundary - 1}))
    assert len(inspect_container_tree(source, max_depth=2, max_containers=3).occurrences) == 3
    with pytest.raises(ResourceLimitError, match='max_depth'):
        inspect_container_tree(source, max_depth=1)
    with pytest.raises(ResourceLimitError, match='max_containers'):
        inspect_container_tree(source, max_containers=2)


def test_two_identical_native_streams_keep_distinct_occurrences():
    compound = named_stream(envelope(zip_bytes([])))
    tree = inspect_container_tree(zip_bytes([('first', compound), ('second', compound)]))
    wrappers = [entry for entry in tree.occurrences if entry.snapshot.container == 'ole-native']
    assert len(wrappers) == 2 and wrappers[0].location != wrappers[1].location
    assert wrappers[0].snapshot.source_sha256 == wrappers[1].snapshot.source_sha256


def test_corrupt_named_stream_is_located_and_cli_never_creates_partial_output(tmp_path, monkeypatch):
    source = named_stream(envelope(b'abc')[:-1])
    path, output = tmp_path / 'own.bin', tmp_path / 'output'
    path.write_bytes(source)
    monkeypatch.setattr(sys, 'argv', ['container_anatomy', str(path), '--output', str(output)])
    with pytest.raises(InvalidDocumentError, match='cfbf:directory=1.*ole-native:header'):
        tree_main()
    assert path.read_bytes() == source and not output.exists()


def test_explicit_cli_generated_names_recover_header_and_native_data(tmp_path, monkeypatch):
    source, output = tmp_path / 'own.native', tmp_path / 'output'
    source.write_bytes(envelope(b'Own arbitrary data'))
    monkeypatch.setattr(sys, 'argv', ['document_anatomy', str(source), '--container', 'ole-native',
                                     '--output', str(output), '--compare', str(source)])
    main()
    report = json.loads((output / 'inventory.json').read_text(encoding='utf-8'))
    assert report['comparison']['binary_identical']
    assert b''.join((output / item['payload_file']).read_bytes() for item in report['items']) == source.read_bytes()


def test_no_optional_backend_is_imported(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in {'olefile', 'oletools', 'docx', 'pptx', 'PIL', 'lxml', 'fitz', 'pypdf'}:
            raise AssertionError(f'Unnecessary backend: {name}')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    assert len(inspect_container_tree(named_stream(envelope(zip_bytes([])))).occurrences) == 3


def test_late_native_envelope_cancellation_keeps_source_and_scope_reusable(tmp_path, monkeypatch):
    import opendoc_formats.native.ole_native as implementation
    source = envelope(b'Own bytes')
    path = tmp_path / 'own.native'
    path.write_bytes(source)
    stop = Event()
    original = implementation.inspect_ole_native
    def cancelled_after_inspection(data, limits, capture):
        value = original(data, limits, capture)
        stop.set()
        return value

    with monkeypatch.context() as context:
        context.setattr(implementation, 'inspect_ole_native', cancelled_after_inspection)
        with pytest.raises(OperationCancelledError):
            inspect_binary(path, container='ole-native', cancelled=stop.is_set)
    assert path.read_bytes() == source
    assert inspect_binary(source, container='ole-native').items
