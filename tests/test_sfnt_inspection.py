"""Source-byte font tables, without running a font interpreter in the inspector."""

import builtins
import hashlib
import struct
from threading import Event

import pytest

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.sfnt import SfntLimits, inspect_sfnt
from tests.binary_fixtures import own_placement_font


def wrapper(*, version=b'\x00\x01\x00\x00', tags=(b'OWN ', b'fvar')):
    data = bytearray(struct.pack('>4s4H', version, len(tags), 0, 0, 0))
    offset = 12+16*len(tags)
    for index, tag in enumerate(tags):
        data.extend(struct.pack('>4sIII', tag, index+1, offset+4*index, 3))
    data.extend(b'Own\0'*len(tags))
    return bytes(data)


@pytest.mark.parametrize('version', [b'\x00\x01\x00\x00', b'OTTO'])
def test_native_table_ranges_unknown_payload_and_header_are_preserved(version):
    source = wrapper(version=version)
    result = inspect_sfnt(source, capture=True)
    assert result.source_sha256 == hashlib.sha256(source).hexdigest()
    assert result.source_size == len(source) and result.header_hex == source[:12].hex()
    assert result.sfnt_version == version.hex() and not result.assessment_complete
    assert result.variation_tables == ('fvar',)
    for index, table in enumerate(result.tables):
        assert table.payload == source[table.offset:table.offset+table.length] == b'Own'
        assert table.sha256 == hashlib.sha256(table.payload).hexdigest()
        assert table.declared_checksum == index+1  # Observed, not asserted to be correct.
        assert table.directory_offset == 12+16*index
    assert all(table.payload is None for table in inspect_sfnt(source).tables)


def test_own_real_single_face_font_agrees_with_independent_fonttools_directory():
    from io import BytesIO

    from fontTools.ttLib import TTFont

    source = own_placement_font()
    result = inspect_sfnt(source, capture=True)
    with TTFont(BytesIO(source), lazy=True) as reference:
        assert {table.tag for table in result.tables} == set(reference.reader.tables)
        for table in result.tables:
            expected = reference.reader.tables[table.tag]
            assert (table.offset, table.length, table.declared_checksum) == (expected.offset, expected.length, expected.checkSum)
            assert table.payload == reference.reader[table.tag]
    assert result.variation_tables == ()


@pytest.mark.parametrize('source', [b'', b'\0\1\0', b'\0\1\0\0', b'\0\1\0\0'+bytes(8), wrapper()[:30]])
def test_truncated_and_empty_directories_do_not_return_partial_inventories(source):
    with pytest.raises(InvalidDocumentError, match='sfnt:header'):
        inspect_sfnt(source)


@pytest.mark.parametrize('version', [b'ttcf', b'wOFF', b'wOF2', b'true', b'typ1', b'junk'])
def test_collections_compressed_and_legacy_profiles_are_explicitly_unsupported(version):
    with pytest.raises(UnsupportedDocumentError, match='standalone'):
        inspect_sfnt(wrapper(version=version))


@pytest.mark.parametrize('offset,value', [(20, 0), (20, 999), (24, 0xffffffff)])
def test_table_ranges_cannot_point_into_directory_or_outside_input(offset, value):
    source = bytearray(wrapper())
    struct.pack_into('>I', source, offset, value)
    with pytest.raises(InvalidDocumentError, match='sfnt:table=0'):
        inspect_sfnt(bytes(source), capture=True)


@pytest.mark.parametrize('tags', [(b'name', b'name'), (b'bad\0', b'good')])
def test_duplicate_or_binary_tags_are_rejected(tags):
    with pytest.raises(InvalidDocumentError, match='table='):
        inspect_sfnt(wrapper(tags=tags))


def test_unaligned_offsets_do_not_look_like_accepted_opentype_profile():
    source = bytearray(wrapper())
    struct.pack_into('>I', source, 20, 45)
    with pytest.raises(UnsupportedDocumentError, match='unaligned'):
        inspect_sfnt(bytes(source))


@pytest.mark.parametrize('limits', [SfntLimits(max_input_bytes=1), SfntLimits(max_tables=1),
                                   SfntLimits(max_table_bytes=2), SfntLimits(max_total_table_bytes=5)])
def test_limits_cover_input_table_count_individual_and_aggregate_payload(limits):
    with pytest.raises(ResourceLimitError):
        inspect_sfnt(wrapper(), capture=True, limits=limits)


def test_cancellation_inside_table_walk_preserves_file_and_releases_scope(tmp_path, monkeypatch):
    import opendoc_formats.native.sfnt as sfnt

    path = tmp_path/'own.otf'
    source = wrapper()
    path.write_bytes(source)
    stop = Event()
    digest = sfnt.hashlib.sha256

    def cancel_after_first_table(payload):
        result = digest(payload)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(sfnt.hashlib, 'sha256', cancel_after_first_table)
        with pytest.raises(OperationCancelledError):
            inspect_sfnt(path, cancelled=stop.is_set)
    assert path.read_bytes() == source and inspect_sfnt(path).tables


def test_inspector_never_imports_optional_font_engine(monkeypatch):
    original = builtins.__import__

    def restricted(name, *args, **kwargs):
        if name.startswith(('fontTools', 'fitz', 'pymupdf', 'PIL')):
            pytest.fail('An optional decoder was imported by raw sfnt inspection')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', restricted)
    assert inspect_sfnt(wrapper()).tables
