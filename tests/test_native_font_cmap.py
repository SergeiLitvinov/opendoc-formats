"""Independent cmap bytes and engine parity for declared Unicode coverage."""

import builtins
import struct
from io import BytesIO
from threading import Event

import pytest
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.fonts.resolver import _read_face
from opendoc_formats.fonts.sfnt_cmap import read_unicode_coverage, read_unicode_mapping
from opendoc_formats.support.cancellation import cancellation_scope
from tests.binary_fixtures import own_placement_font


def groups(kind, values):
    return struct.pack('>HH3I', kind, 0, 16+12*len(values), 0, len(values))+b''.join(struct.pack('>3I', *row) for row in values)


def array(kind, values, first=0):
    if kind == 0:
        return struct.pack('>3H', 0, 262, 0)+bytes(values)
    return struct.pack('>5H', 6, 10+2*len(values), 0, first, len(values))+b''.join(struct.pack('>H', value) for value in values)


def segment(*, array=False, start=65, end=67, delta=-64):
    length = 38 if array else 32
    return (struct.pack('>7H', 4, length, 0, 4, 4, 1, 0)+struct.pack('>3H', end, 0xffff, 0)
            +struct.pack('>2H2h2H', start, 0xffff, -1 if array else delta, 1, 4 if array else 0, 0)
            +(struct.pack('>3H', 2, 0, 1) if array else b''))


def font_with_cmaps(records):
    offset = 4+8*len(records)
    directory, payload = bytearray(), bytearray()
    for platform, encoding, subtable in records:
        directory.extend(struct.pack('>2HI', platform, encoding, offset+len(payload)))
        payload.extend(subtable)
    native = DefaultTable('cmap')
    native.data = struct.pack('>2H', 0, len(records))+directory+payload
    output = BytesIO()
    with TTFont(BytesIO(own_placement_font()), recalcTimestamp=False) as font:
        font['cmap'] = native
        font.save(output)
    return output.getvalue()


def high_bytes(*, shared=False, delta=0, values=(1, 0, 2), first=65):
    keys = [0]*256
    keys[0x81] = 8
    if shared:
        keys[0x82] = 8
    single = struct.pack('>2HhH', 65, 3, 0, 10)
    double = struct.pack('>2HhH', first, len(values), delta, 8)
    payload = struct.pack('>3H', 1, 0, 2)+struct.pack('>'+'H'*len(values), *values)
    return struct.pack('>3H', 2, 534+len(payload), 0)+struct.pack('>256H', *keys)+single+double+payload


@pytest.mark.parametrize('shared', [False, True])
@pytest.mark.parametrize('delta,values', [(0, (1, 0, 2)), (-1, (2, 0, 3)), (-2, (2, 0, 3)),
                                         (1, (0xffff, 1, 0)), (0, ())])
def test_high_byte_mapping_matches_engine_without_fonttools(tmp_path, monkeypatch, shared, delta, values):
    from tests.test_native_font_face import engine_face

    source = font_with_cmaps([(3, 1, high_bytes(shared=shared, delta=delta, values=values))])
    path = tmp_path/'own.ttf'
    path.write_bytes(source)
    expected_face = engine_face(path)
    with TTFont(BytesIO(source)) as font:
        expected = {code: font.getGlyphID(name) for code, name in font.getBestCmap().items()}
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Native cmap2 path imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    assert read_unicode_mapping(source) == expected
    assert read_unicode_coverage(source) == frozenset(expected)
    assert _read_face(path) == expected_face
    assert path.read_bytes() == source


@pytest.mark.parametrize('offset,value', [(6, 8), (6+0x81*2, 7), (6+0x81*2, 65528),
                                        (526, 255), (528, 257), (532, 1), (532, 0), (532, 65534)])
def test_invalid_high_byte_keys_ranges_and_offsets_never_return_partial_mapping(offset, value):
    data = bytearray(high_bytes())
    struct.pack_into('>H', data, offset, value)
    with pytest.raises((UnsupportedDocumentError, InvalidDocumentError)):
        read_unicode_mapping(font_with_cmaps([(3, 1, bytes(data))]))


def test_high_byte_work_budget_counts_shared_and_zero_entries():
    source = font_with_cmaps([(3, 1, high_bytes(shared=True, values=(0, 0, 0)))])
    assert read_unicode_mapping(source, max_codepoints=9) == {65: 1, 67: 2}
    with pytest.raises(ResourceLimitError, match='work budget'):
        read_unicode_mapping(source, max_codepoints=8)


def test_high_byte_legacy_encoding_is_not_promoted_to_unicode():
    source = font_with_cmaps([(3, 2, high_bytes())])
    with TTFont(BytesIO(source)) as font:
        assert font.getBestCmap() is None
    assert read_unicode_mapping(source) == {}


def test_high_byte_distinct_subheaders_can_share_glyph_storage():
    data = bytearray(high_bytes())
    struct.pack_into('>H', data, 4+0x83*2+2, 16)
    struct.pack_into('>H', data, 524, 18)
    struct.pack_into('>H', data, 532, 16)
    data[534:534] = struct.pack('>2HhH', 65, 3, 1, 8)
    struct.pack_into('>H', data, 2, len(data))
    source = font_with_cmaps([(3, 1, bytes(data))])
    expected = {65: 1, 67: 2, 0x8141: 1, 0x8143: 2, 0x8341: 2, 0x8343: 3}
    with TTFont(BytesIO(source)) as font:
        assert {code: font.getGlyphID(name) for code, name in font.getBestCmap().items()} == expected
    assert read_unicode_mapping(source) == expected


def test_high_byte_encoding_preference_is_unchanged():
    source = font_with_cmaps([(3, 1, high_bytes()), (3, 10, groups(12, [(0x1f600, 0x1f600, 1)]))])
    assert read_unicode_mapping(source) == {0x1f600: 1}


def test_high_byte_cancel_inside_mapping_does_not_import_engine(monkeypatch):
    import opendoc_formats.fonts.sfnt_cmap as native

    source = font_with_cmaps([(3, 1, high_bytes())])
    calls, stop = [], Event()
    original, imported = native.checkpoint, builtins.__import__

    def checkpoint():
        calls.append(True)
        if len(calls) == 72:  # Encoding record, subheaders, then single-byte mappings.
            stop.set()
        original()

    def guarded(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Cancelled cmap2 entered engine fallback')
        return imported(name, *args, **kwargs)

    monkeypatch.setattr(native, 'checkpoint', checkpoint)
    monkeypatch.setattr(builtins, '__import__', guarded)
    with cancellation_scope(stop.is_set, 'Own cmap2'):
        with pytest.raises(OperationCancelledError):
            read_unicode_mapping(source)
        stop.clear()
    assert len(calls) == 72


def test_noncanonical_high_byte_key_keeps_engine_recovery(tmp_path, monkeypatch):
    from tests.test_native_font_face import engine_face

    data = bytearray(high_bytes())
    struct.pack_into('>H', data, 6+0x81*2, 9)
    path = tmp_path/'legacy.ttf'
    path.write_bytes(font_with_cmaps([(3, 1, bytes(data))]))
    expected = engine_face(path)
    original, calls = TTFont.getBestCmap, []

    def engine(self, *args, **kwargs):
        calls.append(True)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TTFont, 'getBestCmap', engine)
    assert _read_face(path) == expected and calls == [True]


@pytest.mark.parametrize('records,expected', [
    ([(0, 0, array(0, [1]+[0]*254+[2]))], {0, 255}),
    ([(3, 1, array(0, [0]*256))], set()),
    ([(3, 1, array(6, [1, 0, 2], 65))], {65, 67}),
    ([(0, 3, array(6, [2], 0xffff))], {0xffff}),
    ([(0, 3, array(6, [], 0xffff))], set()),
    ([(3, 1, array(6, [2], 65)), (3, 10, groups(12, [(0x1f600, 0x1f600, 1)]))], {0x1f600}),
    ([(3, 1, segment())], {65, 66, 67}),
    ([(3, 1, segment(array=True))], {65}),
    ([(3, 1, segment(start=0, end=2, delta=0))], {1, 2}),
    ([(3, 10, groups(12, [(0x1f600, 0x1f602, 1)]))], {0x1f600, 0x1f601, 0x1f602}),
    ([(3, 10, groups(12, [(65, 67, 0)]))], {66, 67}),
    ([(0, 6, groups(13, [(65, 67, 2)]))], {65, 66, 67}),
    ([(0, 6, groups(13, [(65, 67, 0)]))], set()),
    ([(0, 3, segment()), (3, 10, groups(12, [(0x1f600, 0x1f600, 1)]))], {0x1f600}),
    ([(3, 10, groups(12, [(65, 65, 1)])), (3, 10, groups(12, [(66, 66, 2)]))], {65}),
    ([(1, 0, segment())], set()),
    ([(1, 0, struct.pack('>3H', 0, 262, 0)+bytes(256)), (3, 1, segment())], {65, 66, 67}),
    ([(0, 5, struct.pack('>H2I', 14, 10, 0)), (3, 1, segment())], {65, 66, 67}),
])
def test_native_coverage_matches_independent_engine_and_expected_nonzero_mappings(records, expected):
    source = font_with_cmaps(records)
    with TTFont(BytesIO(source), lazy=True) as reference:
        assert set((reference.getBestCmap() or {}).keys()) == expected
        glyph_ids = {code: reference.getGlyphID(name) for code, name in (reference.getBestCmap() or {}).items()}
    assert read_unicode_coverage(source) == frozenset(expected)
    assert read_unicode_mapping(source) == glyph_ids


@pytest.mark.parametrize('flags', [0, 2, 0x100, 0x200, 0x108])
def test_resolver_uses_native_cmap_and_preserves_all_face_metadata(tmp_path, monkeypatch, flags):
    source = font_with_cmaps([(3, 10, groups(12, [(65, 67, 1), (0x1f600, 0x1f600, 2)]))])
    path = tmp_path/'own.ttf'
    with TTFont(BytesIO(source), recalcTimestamp=False) as font:
        font['OS/2'].fsType = flags
        font.save(path)
    before = path.read_bytes()
    with TTFont(path, lazy=True) as reference:
        expected = frozenset(reference.getBestCmap())
        expected_family = reference['name'].getDebugName(16) or reference['name'].getDebugName(1)
        expected_metrics = (reference['OS/2'].usWeightClass, reference['OS/2'].usWidthClass,
                            reference['head'].unitsPerEm, float(reference['OS/2'].xAvgCharWidth or 500),
                            bool(reference['post'].italicAngle))

    def forbidden(self, *args, **kwargs):
        pytest.fail('Native resolver profile called fontTools.getBestCmap')

    monkeypatch.setattr(TTFont, 'getBestCmap', forbidden)
    face = _read_face(path)
    assert face is not None and face.glyphs == expected and face.family == expected_family
    assert (face.weight, face.width_class, face.units_per_em, face.average_width, face.italic) == expected_metrics
    assert face.embeddable == (not bool(flags & (2 | 0x200)))
    assert face.subsettable == (not bool(flags & 0x100))
    assert path.read_bytes() == before


def test_nonconforming_array_keeps_existing_engine_coverage(tmp_path, monkeypatch):
    # Declared length includes extra storage; the established engine ignores it.
    subtable = struct.pack('>8H', 6, 16, 0, 65, 2, 1, 0, 2)
    path = tmp_path/'legacy.ttf'
    path.write_bytes(font_with_cmaps([(3, 1, subtable)]))
    original = TTFont.getBestCmap
    calls = []

    def engine(self, *args, **kwargs):
        calls.append(True)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TTFont, 'getBestCmap', engine)
    face = _read_face(path)
    assert face is not None and face.glyphs == frozenset({65}) and calls == [True]


@pytest.mark.parametrize('kind', [0, 6])
def test_array_resolver_never_imports_fonttools(tmp_path, monkeypatch, kind):
    from tests.test_native_font_face import engine_face

    values = [0]*65+[1, 0, 2]+[0]*188 if kind == 0 else [1, 0, 2]
    source = font_with_cmaps([(3, 1, array(kind, values, 65))])
    path = tmp_path/'own.ttf'
    path.write_bytes(source)
    expected = engine_face(path)
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == 'fontTools' or name.startswith('fontTools.'):
            pytest.fail('Native array resolver imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    assert _read_face(path) == expected
    assert path.read_bytes() == source


@pytest.mark.parametrize('subtable,error', [
    (struct.pack('>3H', 0, 261, 0)+bytes(255), InvalidDocumentError),
    (struct.pack('>4H', 6, 8, 0, 65), InvalidDocumentError),
    (struct.pack('>5H', 6, 10, 0, 65, 1), UnsupportedDocumentError),
    (struct.pack('>5H', 6, 12, 0, 65, 0)+b'\0\1', UnsupportedDocumentError),
    (array(6, [1, 2], 0xffff), UnsupportedDocumentError),
])
def test_invalid_array_never_returns_partial_coverage(subtable, error):
    with pytest.raises(error):
        read_unicode_coverage(font_with_cmaps([(3, 1, subtable)]))


@pytest.mark.parametrize('kind,maximum', [(0, 255), (6, 2)])
def test_array_work_budget_includes_zero_mappings(kind, maximum):
    values = [0]*256 if kind == 0 else [0]*3
    source = font_with_cmaps([(3, 1, array(kind, values))])
    with pytest.raises(ResourceLimitError, match='work budget'):
        read_unicode_coverage(source, max_codepoints=maximum)


@pytest.mark.parametrize('kind', [0, 6])
def test_cancellation_inside_array_walk(kind, monkeypatch):
    import opendoc_formats.fonts.sfnt_cmap as native

    values = [1]*256 if kind == 0 else [1]*10
    source = font_with_cmaps([(3, 1, array(kind, values))])
    calls, stop = [], Event()
    original = native.checkpoint

    def checkpoint():
        calls.append(True)
        if len(calls) == 4:  # Encoding record, then three glyph-array iterations.
            stop.set()
        original()

    monkeypatch.setattr(native, 'checkpoint', checkpoint)
    with cancellation_scope(stop.is_set, 'Own cmap array'):
        with pytest.raises(OperationCancelledError):
            read_unicode_coverage(source)
        stop.clear()
    assert len(calls) == 4


@pytest.mark.parametrize('container', ['woff', 'ttc'])
def test_snapshot_keeps_compressed_and_first_collection_face_behavior(tmp_path, container):
    path = tmp_path/f'own.{container}'
    if container == 'woff':
        with TTFont(BytesIO(own_placement_font()), recalcTimestamp=False) as font:
            font.flavor = 'woff'
            font.save(path)
    else:
        collection = TTCollection()
        collection.fonts = [TTFont(BytesIO(own_placement_font())), TTFont(BytesIO(own_placement_font()))]
        try:
            collection.fonts[1]['head'].unitsPerEm = 2048
            collection.save(path)
        finally:
            collection.close()
    before = path.read_bytes()
    with TTFont(path, lazy=True, fontNumber=0) as reference:
        expected = frozenset(reference.getBestCmap())
        units = reference['head'].unitsPerEm
    face = _read_face(path)
    assert face is not None and face.glyphs == expected and face.units_per_em == units == 1000
    assert path.read_bytes() == before


@pytest.mark.parametrize('subtable,error', [
    (groups(12, [(66, 65, 1)]), UnsupportedDocumentError),
    (groups(12, [(65, 67, 1), (67, 68, 1)]), UnsupportedDocumentError),
    (groups(13, [(0, 0x110000, 1)]), UnsupportedDocumentError),
    (groups(12, [(65, 67, 0xffffffff)]), UnsupportedDocumentError),
    (groups(12, [(65, 67, 1)])[:-1], InvalidDocumentError),
])
def test_out_of_profile_groups_never_return_partial_coverage(subtable, error):
    source = font_with_cmaps([(3, 10, subtable)])
    with pytest.raises(error):
        read_unicode_coverage(source)


def test_array_offsets_and_work_budget_are_checked_before_unbounded_expansion():
    source = font_with_cmaps([(3, 1, segment())])
    with pytest.raises(ResourceLimitError, match='work budget'):
        read_unicode_coverage(source, max_codepoints=2)
    bad = bytearray(segment(array=True))
    struct.pack_into('>H', bad, 28, 0xfffe)
    with pytest.raises(InvalidDocumentError, match='glyph array'):
        read_unicode_coverage(font_with_cmaps([(3, 1, bytes(bad))]))
    huge = font_with_cmaps([(0, 6, groups(13, [(0, 0x10ffff, 1)]))])
    with pytest.raises(ResourceLimitError, match='work budget'):
        read_unicode_coverage(huge)


def test_cancel_during_cmap_walk_does_not_start_engine_and_closes_font(tmp_path, monkeypatch):
    import opendoc_formats.fonts.resolver as resolver
    import opendoc_formats.fonts.sfnt_cmap as native

    path = tmp_path/'own.ttf'
    path.write_bytes(font_with_cmaps([(3, 10, groups(12, [(65, 67, 1)]))]))
    stop, calls, closed = Event(), [], []
    original_checkpoint, original_close = native.checkpoint, TTFont.close

    def checkpoint():
        calls.append(True)
        if len(calls) == 3:
            stop.set()
        original_checkpoint()

    def close(self):
        closed.append(True)
        return original_close(self)

    def forbidden(self, *args, **kwargs):
        pytest.fail('Cancellation started cmap fallback')

    def engine_metadata(data, **kwargs):
        raise UnsupportedDocumentError('Exercise the established metadata reader context')

    monkeypatch.setattr(resolver, 'read_face_metrics', engine_metadata)
    monkeypatch.setattr(native, 'checkpoint', checkpoint)
    monkeypatch.setattr(TTFont, 'close', close)
    monkeypatch.setattr(TTFont, 'getBestCmap', forbidden)
    with cancellation_scope(stop.is_set, 'Own cmap'):
        with pytest.raises(OperationCancelledError):
            _read_face(path)
        stop.clear()
    assert closed == [True]
