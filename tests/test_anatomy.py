"""Independent original bytes establish the native baseline for compatibility work."""

import hashlib
import json
import struct
import zipfile
import zlib
from dataclasses import replace
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, compare_snapshots, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from tests.binary_fixtures import PR, RGB, W, own_docx, own_pdf, own_png, zip_bytes
from tools.document_anatomy import save_dissection


def test_zip_native_members_xml_relationships_and_opaque_bytes_are_recovered_exactly(tmp_path):
    source = tmp_path/'own.docx'
    original = own_docx()
    source.write_bytes(original)
    snapshot = inspect_binary(source, capture=True)
    assert snapshot.source_sha256 == hashlib.sha256(original).hexdigest()
    assert snapshot.container == 'zip' and len(snapshot.items) == 6
    items = {item.locator: item for item in snapshot.items}
    assert items['zip:/word/media/own.png'].payload == own_png()
    assert items['zip:/word/embeddings/unknown.bin'].payload == b'Own opaque binary\x00\xff\x01'
    document = items['zip:/word/document.xml']
    assert [(node.path, node.tag) for node in document.xml_nodes if node.path in ('0/0/0', '0/0/1', '0/0/2')] == [
        ('0/0/0', '{'+W+'}p'), ('0/0/1', '{'+W+'}tbl'), ('0/0/2', '{'+W+'}p'),
    ]
    relationships = items['zip:/word/_rels/document.xml.rels'].xml_nodes
    external = next(node for node in relationships if dict(node.attributes).get('TargetMode') == 'External')
    assert external.tag == '{'+PR+'}Relationship'
    assert dict(external.attributes)['Target'] == 'https://example.invalid/own'
    assert source.read_bytes() == original
    json.dumps(snapshot.to_dict())


def test_storage_difference_does_not_masquerade_as_member_content_loss():
    entries = [('own.xml', b'<own><value>One</value></own>'), ('own.bin', bytes(range(200)))]
    stored = inspect_binary(zip_bytes(entries, compression=zipfile.ZIP_STORED))
    deflated = inspect_binary(zip_bytes(entries))
    difference = compare_snapshots(stored, deflated)
    assert not difference['binary_identical'] and not difference['assessment_complete']
    assert difference['content_changed'] == difference['added'] == difference['removed'] == []
    assert difference['storage_changed'] == ['zip:/own.bin', 'zip:/own.xml']


def test_added_removed_and_changed_native_members_are_distinguished():
    before = inspect_binary(zip_bytes([('change.xml', b'<own>A</own>'), ('gone.bin', b'Gone')]))
    after = inspect_binary(zip_bytes([('change.xml', b'<own>B</own>'), ('new.bin', b'New')]))
    difference = compare_snapshots(before, after)
    assert difference['content_changed'] == ['zip:/change.xml']
    assert difference['added'] == ['zip:/new.bin'] and difference['removed'] == ['zip:/gone.bin']


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16'])
def test_dtd_is_rejected_before_entity_expansion_but_opaque_inspection_retains_exact_bytes(encoding):
    xml = '<?xml version="1.0" encoding="'+encoding+'"?><!DOCTYPE own [<!ENTITY x "expanded">]><own>&x;</own>'
    source = zip_bytes([('own.xml', xml.encode(encoding))])
    with pytest.raises(UnsupportedDocumentError, match='DTD'):
        inspect_binary(source)
    item = inspect_binary(source, parse_xml=False, capture=True).items[0]
    assert item.payload == xml.encode(encoding) and not item.xml_nodes


@pytest.mark.parametrize('limits', [
    AnatomyLimits(max_input_bytes=10), AnatomyLimits(max_items=1), AnatomyLimits(max_part_bytes=10),
    AnatomyLimits(max_total_bytes=10), AnatomyLimits(max_xml_nodes=1), AnatomyLimits(max_xml_depth=1),
    AnatomyLimits(max_xml_characters=2), AnatomyLimits(max_xml_name_chars=2),
])
def test_selected_native_limits_abort_without_a_partial_snapshot(limits):
    source = zip_bytes([('own.xml', b'<root own="attribute"><child>Text</child></root>'), ('own.bin', b'Own')])
    with pytest.raises(ResourceLimitError):
        inspect_binary(source, limits=limits)


@pytest.mark.parametrize('name', ['../own.xml', '/own.xml', 'C:/own.xml', 'dir/../own.xml'])
def test_unsafe_member_addresses_are_rejected_even_when_dump_names_are_generated(name):
    with pytest.raises(InvalidDocumentError):
        inspect_binary(zip_bytes([(name, b'<own/>')]))


def test_duplicate_member_and_crc_corruption_are_not_silently_accepted():
    with pytest.warns(UserWarning, match='Duplicate'):
        duplicate = zip_bytes([('own.bin', b'Own'), ('own.bin', b'Other')])
    with pytest.raises(InvalidDocumentError):
        inspect_binary(duplicate)
    original = bytearray(zip_bytes([('own.bin', b'Own')], compression=zipfile.ZIP_STORED))
    header = struct.unpack_from('<4s5H3I2H', original)
    original[30+header[-2]+header[-1]] ^= 1
    with pytest.raises(InvalidDocumentError):
        inspect_binary(bytes(original))


def test_cancel_during_xml_walk_preserves_source_and_restores_scope(tmp_path, monkeypatch):
    import opendoc_formats.anatomy as anatomy

    source = tmp_path/'own.docx'
    source.write_bytes(own_docx())
    original = source.read_bytes()
    stop = Event()
    method = anatomy._Budget.characters_used

    def used(self, *args):
        method(self, *args)
        stop.set()

    with monkeypatch.context() as context:
        context.setattr(anatomy._Budget, 'characters_used', used)
        with pytest.raises(OperationCancelledError):
            inspect_binary(source, cancelled=stop.is_set)
    assert source.read_bytes() == original
    assert inspect_binary(source).to_dict() == inspect_binary(source, cancelled=lambda: False).to_dict()


def test_dissection_uses_flat_generated_names_and_never_replaces_a_directory(tmp_path):
    snapshot = inspect_binary(own_docx(), capture=True)
    output = tmp_path/'dissected'
    save_dissection(snapshot, output)
    manifest = json.loads((output/'inventory.json').read_text(encoding='utf-8'))
    for entry, item in zip(manifest['items'], snapshot.items, strict=True):
        assert (output/entry['payload_file']).read_bytes() == item.payload
        assert '/' not in entry['payload_file'] and '\\' not in entry['payload_file']
    with pytest.raises(FileExistsError):
        save_dissection(snapshot, output)


def test_pdf_active_objects_keep_encoded_streams_and_original_pixels_without_own_pdf_parser():
    pytest.importorskip('pymupdf')
    source, commands = own_pdf()
    snapshot = inspect_binary(source, capture=True)
    assert snapshot.container == 'pdf' and len(snapshot.items) == 6
    items = {item.locator: item for item in snapshot.items}
    assert zlib.decompress(items['pdf:xref=5'].payload) == commands
    assert items['pdf:xref=6'].payload == zlib.compress(RGB)
    assert '/Subtype /Image' in dict(items['pdf:xref=6'].details)['dictionary']
    assert compare_snapshots(snapshot, inspect_binary(source))['binary_identical']


def test_pdf_native_slots_stream_limits_and_context_lifetime():
    pytest.importorskip('pymupdf')
    from opendoc_formats.errors import DocumentClosedError
    from opendoc_formats.pdf import PdfDocument, PdfLimits

    source, _ = own_pdf()
    for limits in (PdfLimits(max_objects=1), PdfLimits(max_object_bytes=10), PdfLimits(max_inspection_bytes=10)):
        with PdfDocument(source, limits=limits) as document:
            with pytest.raises(ResourceLimitError):
                list(document.iter_objects())
    with PdfDocument(source) as document:
        iterator = document.iter_objects()
        assert next(iterator).xref == 1
    with pytest.raises(DocumentClosedError):
        next(iterator)


def test_pdf_cancellation_after_a_native_object_does_not_advance_or_change_source(monkeypatch):
    engine = pytest.importorskip('pymupdf')
    source, _ = own_pdf()
    stop, calls = Event(), []
    original = engine.Document.xref_object

    def first(self, xref, *args, **kwargs):
        if xref < 0:
            return original(self, xref, *args, **kwargs)
        assert not calls, 'Another xref was read after cancellation'
        calls.append(xref)
        result = original(self, xref, *args, **kwargs)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(engine.Document, 'xref_object', first)
        with pytest.raises(OperationCancelledError):
            inspect_binary(source, cancelled=stop.is_set)
    assert calls == [1] and inspect_binary(source).source_sha256 == hashlib.sha256(source).hexdigest()


def test_raw_zip_inspection_does_not_import_any_document_decoder(monkeypatch):
    import opendoc_formats.native.common as common

    def forbidden(*args, **kwargs):
        pytest.fail('ZIP inspection imported an optional decoder')

    monkeypatch.setattr(common, 'backend', forbidden)
    assert inspect_binary(own_docx()).container == 'zip'


def test_pdf_marker_inside_a_zip_member_is_not_mistaken_for_the_outer_container():
    source, _ = own_pdf()
    assert inspect_binary(zip_bytes([('own.pdf', source)], compression=zipfile.ZIP_STORED)).container == 'zip'


def test_pdf_backend_repair_is_exposed_instead_of_being_mistaken_for_original_wire_structure():
    pytest.importorskip('pymupdf')
    source, _ = own_pdf()
    damaged = source[:source.rfind(b'startxref\n')]+b'startxref\n0\n%%EOF\n'
    snapshot = inspect_binary(damaged)
    assert dict(snapshot.details)['repaired']
    assert snapshot.source_sha256 == hashlib.sha256(damaged).hexdigest()


def test_malformed_xml_is_located_and_opaque_profile_still_recovers_its_bytes():
    source = zip_bytes([('bad.xml', b'<own>')])
    with pytest.raises(InvalidDocumentError, match='zip:/bad.xml'):
        inspect_binary(source)
    assert inspect_binary(source, parse_xml=False, capture=True).items[0].payload == b'<own>'


@pytest.mark.parametrize('kwargs', [{'capture': 1}, {'parse_xml': 1}, {'limits': None}, {'container': 'docx'}])
def test_invalid_profiles_fail_before_reading_source(kwargs):
    with pytest.raises((TypeError, ValueError)):
        inspect_binary('own-nonexistent-file', **kwargs)


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16'])
def test_xml_offsets_refer_to_original_member_bytes_including_utf16(encoding):
    xml = '<?xml version="1.0" encoding="'+encoding+'"?><root><child>Own</child><empty/></root>'
    payload = xml.encode(encoding)
    item = inspect_binary(zip_bytes([('own.xml', payload)])).items[0]
    child = next(node for node in item.xml_nodes if node.tag == 'child')
    empty = next(node for node in item.xml_nodes if node.tag == 'empty')
    unit = 'utf-16-le' if encoding == 'utf-16' else encoding
    assert payload[child.start_byte:].startswith('<child>'.encode(unit))
    assert payload[child.end_event_byte:].startswith('</child>'.encode(unit))
    assert payload[empty.end_event_byte:].startswith('</root>'.encode(unit))


def test_duplicate_snapshot_locators_cannot_create_a_false_correspondence():
    snapshot = inspect_binary(zip_bytes([('own.bin', b'Own')]))
    with pytest.raises(ValueError, match='unique native locators'):
        compare_snapshots(replace(snapshot, items=snapshot.items*2), snapshot)
