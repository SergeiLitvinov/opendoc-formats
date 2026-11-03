"""Collection offsets and finite face metadata compared with the independent font engine."""

import builtins
import hashlib
import struct
from io import BytesIO
from pathlib import Path
from threading import Event

import pytest
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.fonts.resolver import _read_face
from opendoc_formats.fonts.sfnt_cmap import read_unicode_mapping
from opendoc_formats.fonts.sfnt_names import read_program_names
from opendoc_formats.native.sfnt import SfntLimits, inspect_sfnt, read_face_metrics
from tests.binary_fixtures import own_placement_font
from tests.test_native_font_face import engine_face


def collection(*, version=1, shared=True, signed=False, cff=False):
    source = (Path(__file__).parent/'native/data/own-cff.otf').read_bytes() if cff else own_placement_font()
    group = TTCollection()
    group.fonts = [TTFont(BytesIO(source), recalcTimestamp=False) for _ in range(2)]
    second = group.fonts[1]
    second['head'].unitsPerEm = 2048
    second['OS/2'].fsType = 0x100
    second['name'].setName('Own Second', 1, 3, 1, 0x409)
    second['name'].setName('Own Second', 16, 3, 1, 0x409)
    for table in second['cmap'].tables:
        if table.isUnicode():
            table.cmap.pop(65, None)
            table.cmap[67] = 'A'
    if version == 2:
        group.dsig = None
        if signed:
            group.dsig = DefaultTable('DSIG')
            group.dsig.data = b'Own opaque signature fixture; not cryptographic evidence'
    output = BytesIO()
    try:
        group.save(output, shareTables=shared)
        return output.getvalue()
    finally:
        group.close()


@pytest.mark.parametrize('version,signed', [(1, False), (2, False), (2, True)])
@pytest.mark.parametrize('shared', [False, True])
@pytest.mark.parametrize('cff', [False, True])
def test_collection_metadata_and_absolute_ranges_without_fonttools(tmp_path, monkeypatch, version, signed, shared, cff):
    data = collection(version=version, shared=shared, signed=signed, cff=cff)
    path = tmp_path/'own.ttc'
    path.write_bytes(data)
    expected_faces = [engine_face(path, face_index=index) for index in range(2)]
    expected = []
    for index in range(2):
        with TTFont(path, fontNumber=index, lazy=True) as font:
            expected.append({tag: (record.offset, record.length) for tag, record in font.reader.tables.items()})
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Accepted TTC metadata path imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    assert _read_face(path) == expected_faces[0]
    assert expected_faces[0].units_per_em == 1000 and expected_faces[1].units_per_em == 2048
    for index in range(2):
        inventory = inspect_sfnt(data, face_index=index, capture=True)
        assert inventory.face_index == index and inventory.directory_offset == struct.unpack_from('>I', data, 12+4*index)[0]
        assert inventory.source_sha256 == hashlib.sha256(data).hexdigest() and inventory.source_size == len(data)
        assert not inventory.assessment_complete
        assert {table.tag: (table.offset, table.length) for table in inventory.tables} == expected[index]
        for table in inventory.tables:
            assert table.payload == data[table.offset:table.offset+table.length]
        assert read_face_metrics(data, face_index=index).units_per_em == expected_faces[index].units_per_em
        assert frozenset(read_unicode_mapping(data, face_index=index)) == expected_faces[index].glyphs
        names = read_program_names(data, face_index=index)
        assert (names.get(16) or names[1]) == expected_faces[index].family
    assert path.read_bytes() == data


@pytest.mark.parametrize('offset,value', [(4, 0x30000), (8, 0), (12, 0), (12, 21), (16, 0xffffffff)])
def test_collection_header_damage_never_yields_partial_inventory(offset, value):
    data = bytearray(collection())
    struct.pack_into('>I', data, offset, value)
    with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
        inspect_sfnt(bytes(data), face_index=0)


@pytest.mark.parametrize('quota,limits', [('max_faces', SfntLimits(max_faces=1)),
                                         ('max_tables', SfntLimits(max_tables=1)),
                                         ('max_table_bytes', SfntLimits(max_table_bytes=1))])
def test_collection_budgets_are_enforced(quota, limits):
    with pytest.raises(ResourceLimitError, match=quota):
        inspect_sfnt(collection(), face_index=0, limits=limits)


@pytest.mark.parametrize('value', [True, -1, 0.5, '0'])
def test_collection_face_index_is_strict(value):
    with pytest.raises(ValueError):
        inspect_sfnt(collection(), face_index=value)


def test_collection_selection_is_explicit_and_range_checked():
    data = collection()
    with pytest.raises(UnsupportedDocumentError, match='explicit face_index'):
        inspect_sfnt(data)
    with pytest.raises(InvalidDocumentError, match='selected face'):
        inspect_sfnt(data, face_index=2)


@pytest.mark.parametrize('field,value', [(0, 1), (4, 0xffffffff), (8, 4)])
def test_invalid_collection_signature_declarations_are_rejected(field, value):
    data = bytearray(collection(version=2, signed=True))
    struct.pack_into('>I', data, 20+field, value)
    with pytest.raises(InvalidDocumentError, match='DSIG'):
        inspect_sfnt(bytes(data), face_index=0)


@pytest.mark.parametrize('field,value', [(8, 0), (8, 0xffffffff), (12, 0xffffffff)])
def test_collection_table_pointers_are_absolute_and_bounded(field, value):
    data = bytearray(collection())
    base = struct.unpack_from('>I', data, 12)[0]
    struct.pack_into('>I', data, base+12+field, value)
    with pytest.raises(InvalidDocumentError, match='table range'):
        inspect_sfnt(bytes(data), face_index=0)


def test_standalone_explicit_face_zero_keeps_inventory_unchanged():
    data = own_placement_font()
    assert inspect_sfnt(data, face_index=0) == inspect_sfnt(data)


def test_unconfirmed_other_face_directory_preserves_first_face_engine_recovery(tmp_path, monkeypatch):
    data = bytearray(collection())
    struct.pack_into('>I', data, 16, 0xffffffff)
    path = tmp_path/'legacy.ttc'
    path.write_bytes(data)
    expected = engine_face(path)
    original, calls = TTFont.getBestCmap, []

    def engine(self, *args, **kwargs):
        calls.append(True)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TTFont, 'getBestCmap', engine)
    assert _read_face(path) == expected and calls == [True]


def test_cancel_during_collection_directory_walk_preserves_source(tmp_path, monkeypatch):
    import opendoc_formats.native.sfnt as native

    data = collection()
    path = tmp_path/'own.ttc'
    path.write_bytes(data)
    stop = Event()
    original = native._collection_directory

    def interrupted(*args):
        result = original(*args)
        stop.set()
        return result

    monkeypatch.setattr(native, '_collection_directory', interrupted)
    with pytest.raises(OperationCancelledError):
        inspect_sfnt(path, face_index=0, cancelled=stop.is_set)
    assert path.read_bytes() == data
