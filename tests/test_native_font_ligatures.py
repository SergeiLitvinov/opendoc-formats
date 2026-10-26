"""Native GSUB evidence compared with the established engine and independent PDF pixels."""

import builtins
import struct
from io import BytesIO
from pathlib import Path
from threading import Event

import pytest
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from opendoc_model import ConversionReport

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.fonts.sfnt_ligatures import read_ligature_mapping
from opendoc_formats.native.sfnt import inspect_sfnt
from opendoc_formats.support.cancellation import cancellation_scope
from opendoc_formats.writers.pdf_unicode import _ligature_map, _program_ligature_map, restore_ligature_unicode
from tests.binary_fixtures import own_placement_font
from tests.writers.test_pdf_unicode import _font


def gsub(rules=((2, 5, (3,)), (4, 6, (3,))), *, coverage2=False, extension=False, flags=0, repeated=1, version=0x10000):
    groups = {}
    for first, target, rest in rules:
        groups.setdefault(first, []).append(struct.pack('>2H', target, len(rest)+1)+struct.pack('>'+'H'*len(rest), *rest))
    sets = []
    for first in sorted(groups):
        records = groups[first]
        offset = 2+2*len(records)
        offsets = []
        for record in records:
            offsets.append(offset)
            offset += len(record)
        sets.append(struct.pack('>H', len(records))+struct.pack('>'+'H'*len(offsets), *offsets)+b''.join(records))
    offset = 6+2*len(sets)
    offsets = []
    for group in sets:
        offsets.append(offset)
        offset += len(group)
    coverage = (struct.pack('>2H', 2, len(groups))+b''.join(struct.pack('>3H', first, first, i)
                for i, first in enumerate(sorted(groups)))) if coverage2 else (
                    struct.pack('>2H', 1, len(groups))+struct.pack('>'+'H'*len(groups), *sorted(groups)))
    ligatures = (struct.pack('>3H', 1, offset, len(sets))+struct.pack('>'+'H'*len(offsets), *offsets)
                 +b''.join(sets)+coverage)
    table = struct.pack('>2HI', 1, 4, 8)+ligatures if extension else ligatures
    subtables = 16 if repeated > 1 else 1
    lookup = struct.pack('>3H', 7 if extension else 4, flags, subtables)+struct.pack('>H', 6+2*subtables)*subtables+table
    lookups = struct.pack('>H', repeated)+struct.pack('>H', 2+2*repeated)*repeated+lookup
    scripts = struct.pack('>H4s7H', 1, b'DFLT', 8, 4, 0, 0, 0xffff, 1, 0)
    features = struct.pack('>H4s4H', 1, b'liga', 8, 0, 1, 0)
    header_size = 14 if version == 0x10001 else 10
    return (struct.pack('>I3H', version, header_size, header_size+len(scripts), header_size+len(scripts)+len(features))
            +(bytes(4) if version == 0x10001 else b'')+scripts+features+lookups)


def program(tmp_path, *, table=None, post3=True, cmap=None):
    path = tmp_path/'own.ttf'
    _font(path)
    with TTFont(path, recalcTimestamp=False) as font:
        font['head'].created = font['head'].modified = 3400000000
        font['name'].setName('Copyright 2026 Sergei Litvinov', 0, 3, 1, 0x409)
        font['name'].setName('MIT License', 13, 3, 1, 0x409)
        if post3:
            font['post'].formatType = 3.0
        if cmap:
            for entry in font['cmap'].tables:
                if entry.isUnicode():
                    entry.cmap.update(cmap)
        if table is not None:
            font['GSUB'] = DefaultTable('GSUB')
            font['GSUB'].data = table
        output = BytesIO()
        font.save(output)
    return output.getvalue()


def reference(source):
    with TTFont(BytesIO(source), lazy=False) as font:
        return _ligature_map(font)


def post4_program(source, codes=(0xffff, 32, 102, 105, 116, 0xfb01, 0xfb02)):
    output = BytesIO()
    with TTFont(BytesIO(source), recalcTimestamp=False) as font:
        font.getGlyphOrder()
        header = bytearray(font.getTableData('post')[:32])
        struct.pack_into('>I', header, 0, 0x40000)
        font['post'] = DefaultTable('post')
        font['post'].data = bytes(header)+struct.pack('>'+'H'*len(codes), *codes)
        font.save(output)
    return output.getvalue()


@pytest.mark.parametrize('codes', [(0xffff, 32, 102, 105, 116, 0xfb01, 0xfb02),
                                  (0,)*7, (0xffff,)*7, (0xd800, 65, 65, 65, 65, 0xfffe, 0xffff)])
@pytest.mark.parametrize('extension', [False, True])
@pytest.mark.parametrize('rules,expected', [
    (((2, 5, (3,)), (4, 6, (3,))), {5: 'fi', 6: 'ti'}),
    (((2, 5, (3,)), (4, 5, (3,))), {}),
    (((2, 5, (3,)), (4, 5, (6,))), {}),
])
def test_post4_printer_codes_do_not_change_numeric_ligature_evidence(tmp_path, monkeypatch, codes,
                                                                  extension, rules, expected):
    source = post4_program(program(tmp_path, table=gsub(rules, extension=extension)), codes)
    assert reference(source) == expected
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Supported post 4 GSUB imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert read_ligature_mapping(source) == _program_ligature_map(source) == expected


@pytest.mark.parametrize('codes', [(), (0xffff,), (0xffff,)*8])
def test_post4_recovered_size_keeps_previous_ligature_engine(tmp_path, monkeypatch, codes):
    source = post4_program(program(tmp_path, table=gsub()), codes)
    expected, original, calls = reference(source), TTFont.__init__, []

    def engine(self, *args, **kwargs):
        calls.append(True)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TTFont, '__init__', engine)
    with pytest.raises(UnsupportedDocumentError, match='post'):
        read_ligature_mapping(source)
    assert _program_ligature_map(source) == expected and calls == [True]


def test_owned_post4_fixture_is_reproducible(tmp_path):
    fixture = Path(__file__).parent/'native/data/ligature-post4.ttf'
    assert fixture.read_bytes() == post4_program(program(tmp_path, table=gsub()))


def mixed_gsub(single, *, extension=False, before=False, coverage2=False, version=0x10000, lookup_type=1):
    """Append an independently encoded lookup while preserving the original offsets."""
    original = gsub(coverage2=coverage2, version=version)
    position = struct.unpack_from('>H', original, 8)[0]
    ligature = original[position+4:]
    table = struct.pack('>2HI', 1, lookup_type, 8)+single if extension else single
    lookup = struct.pack('>4H', 7 if extension else lookup_type, 0, 1, 8)+table
    first, second = (lookup, ligature) if before else (ligature, lookup)
    return original[:position]+struct.pack('>3H', 2, 6, 6+len(first))+first+second


def single_substitution(kind=1, *, coverage2=False, delta=1):
    coverage = struct.pack('>5H', 2, 1, 2, 3, 0) if coverage2 else struct.pack('>4H', 1, 2, 2, 3)
    if kind == 1:
        return struct.pack('>3H', 1, 6, delta % 65536)+coverage
    return struct.pack('>5H', 2, 10, 2, 3, 4)+coverage


def sequence_substitution(*, coverage2=False, outputs=(3, 2), shared=False):
    coverage = struct.pack('>5H', 2, 1, 2, 3, 0) if coverage2 else struct.pack('>4H', 1, 2, 2, 3)
    sequence = struct.pack('>H', len(outputs))+struct.pack('>'+'H'*len(outputs), *outputs)
    return struct.pack('>5H', 1, 10, 2, 10+len(coverage),
                       10+len(coverage)+(0 if shared else len(sequence)))+coverage+sequence*(1 if shared else 2)


@pytest.mark.parametrize('kind', [2, 3])
@pytest.mark.parametrize('coverage2', [False, True])
@pytest.mark.parametrize('extension', [False, True])
@pytest.mark.parametrize('before', [False, True])
@pytest.mark.parametrize('shared', [False, True])
def test_adjacent_sequences_preserve_engine_mapping_without_import(tmp_path, monkeypatch, kind,
                                                                coverage2, extension, before, shared):
    source = program(tmp_path, table=mixed_gsub(sequence_substitution(coverage2=coverage2, shared=shared),
                     lookup_type=kind, extension=extension, before=before, coverage2=coverage2))
    expected = reference(source)
    assert expected == {5: 'fi', 6: 'ti'}
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Accepted Multiple/AlternateSubst entered fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert read_ligature_mapping(source) == _program_ligature_map(source) == expected


@pytest.mark.parametrize('kind', [2, 3])
@pytest.mark.parametrize('offset,value', [(0, 2), (2, 4), (2, 65535), (4, 3), (6, 4), (8, 65535),
                                        (12, 3), (14, 3), (18, 65535), (20, 7)])
def test_damaged_adjacent_sequence_never_returns_partial_mapping(tmp_path, kind, offset, value):
    table = bytearray(sequence_substitution())
    struct.pack_into('>H', table, offset, value)
    source = program(tmp_path, table=mixed_gsub(bytes(table), lookup_type=kind))
    with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
        read_ligature_mapping(source)


@pytest.mark.parametrize('kind', [2, 3])
def test_shared_sequence_storage_is_charged_for_every_lookup(tmp_path, kind):
    table = mixed_gsub(sequence_substitution(outputs=(2,)*512, shared=True), lookup_type=kind)
    position = struct.unpack_from('>H', table, 8)[0]
    second = struct.unpack_from('>H', table, position+4)[0]
    lookups = table[position+6:]
    table = (table[:position]+struct.pack('>2H', 1000, 2002)
             +struct.pack('>H', 2002+second-6)*999+lookups)
    source = program(tmp_path, table=table)
    with pytest.raises(ResourceLimitError, match='word/coverage work budget'):
        read_ligature_mapping(source)


@pytest.mark.parametrize('kind', [2, 3])
def test_cancellation_inside_adjacent_sequences_does_not_enter_engine(tmp_path, monkeypatch, kind):
    import opendoc_formats.fonts.sfnt_ligatures as native

    source = program(tmp_path, table=mixed_gsub(sequence_substitution(), lookup_type=kind))
    stop, calls = Event(), []
    original = native._Gsub.sequence_table
    glyph = native._Gsub.glyph

    def cancel_glyph(self, position):
        calls.append(True)
        if len(calls) == 4:  # Two covered inputs, then inside the output sequence.
            stop.set()
        return glyph(self, position)

    def sequence(self, base, lookup_kind):
        monkeypatch.setattr(native._Gsub, 'glyph', cancel_glyph)
        return original(self, base, lookup_kind)

    def forbidden(*args, **kwargs):
        pytest.fail('Cancelled sequence entered fontTools fallback')

    monkeypatch.setattr(native._Gsub, 'sequence_table', sequence)
    monkeypatch.setattr(TTFont, '__init__', forbidden)
    with cancellation_scope(stop.is_set, 'GSUB sequences'):
        with pytest.raises(OperationCancelledError):
            _program_ligature_map(source)
        stop.clear()
    assert len(calls) == 4


def test_multiple_deletion_keeps_engine_fallback(tmp_path, monkeypatch):
    source = program(tmp_path, table=mixed_gsub(sequence_substitution(outputs=()), lookup_type=2))
    expected, original, calls = reference(source), TTFont.__init__, []

    def engine(self, *args, **kwargs):
        calls.append(True)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TTFont, '__init__', engine)
    with pytest.raises(UnsupportedDocumentError, match='deletion'):
        read_ligature_mapping(source)
    assert _program_ligature_map(source) == expected and calls == [True]


@pytest.mark.parametrize('kind', [1, 2])
@pytest.mark.parametrize('coverage2', [False, True])
@pytest.mark.parametrize('extension', [False, True])
@pytest.mark.parametrize('before', [False, True])
def test_single_substitutions_alongside_ligatures_need_no_engine(tmp_path, monkeypatch,
                                                               kind, coverage2, extension, before):
    source = program(tmp_path, table=mixed_gsub(single_substitution(kind, coverage2=coverage2),
                                              extension=extension, before=before, coverage2=coverage2))
    expected = reference(source)
    assert expected == {5: 'fi', 6: 'ti'}
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Accepted mixed GSUB imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert read_ligature_mapping(source) == _program_ligature_map(source) == expected


@pytest.mark.parametrize('delta', [-2, -1, 0, 1, 3])
def test_single_substitution_delta_uses_modulo_65536_without_changing_unicode_policy(tmp_path, delta):
    source = program(tmp_path, table=mixed_gsub(single_substitution(delta=delta)))
    assert read_ligature_mapping(source) == reference(source) == {5: 'fi', 6: 'ti'}


def test_owned_mixed_gsub_fixture_is_reproducible(tmp_path):
    fixture = Path(__file__).parent/'native/data/ligature-mixed.ttf'
    assert fixture.read_bytes() == program(tmp_path, table=mixed_gsub(single_substitution(delta=0)))


@pytest.mark.parametrize('offset,value', [(0, 3), (2, 4), (2, 65535), (4, 65530), (10, 7), (12, 2)])
def test_damaged_adjacent_single_lookup_cannot_return_partial_native_mapping(tmp_path, offset, value):
    single = bytearray(single_substitution())
    struct.pack_into('>H', single, offset, value)
    source = program(tmp_path, table=mixed_gsub(bytes(single)))
    with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
        read_ligature_mapping(source)


@pytest.mark.parametrize('problem', ['count', 'target', 'unordered', 'truncated'])
def test_damaged_single_format2_never_yields_partial_ligatures(tmp_path, problem):
    single = bytearray(single_substitution(2))
    if problem == 'truncated':
        single = single[:-1]
    else:
        position, value = {'count': (4, 3), 'target': (6, 7), 'unordered': (16, 2)}[problem]
        struct.pack_into('>H', single, position, value)
    source = program(tmp_path, table=mixed_gsub(bytes(single), extension=True))
    with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
        read_ligature_mapping(source)


def test_one_extension_lookup_cannot_mix_single_and_ligature_types(tmp_path):
    original = gsub()
    position = struct.unpack_from('>H', original, 8)[0]
    single = struct.pack('>2HI', 1, 1, 8)+single_substitution()
    ligature = struct.pack('>2HI', 1, 4, 8)+original[position+12:]
    lookup = struct.pack('>5H', 7, 0, 2, 10, 10+len(single))+single+ligature
    table = original[:position]+struct.pack('>2H', 1, 4)+lookup
    with pytest.raises(InvalidDocumentError, match='inconsistent extension'):
        read_ligature_mapping(program(tmp_path, table=table))


def post1_program(source):
    """Keep numeric cmap/GSUB/outlines; use standard Macintosh glyph names."""
    output = BytesIO()
    with TTFont(BytesIO(source), recalcTimestamp=False) as font:
        font.getGlyphOrder()
        header = bytearray(font.getTableData('post')[:32])
        struct.pack_into('>I', header, 0, 0x10000)
        font['post'] = DefaultTable('post')
        font['post'].data = bytes(header)
        font.save(output)
    return output.getvalue()


@pytest.mark.parametrize('coverage2', [False, True])
@pytest.mark.parametrize('extension', [False, True])
@pytest.mark.parametrize('version', [0x10000, 0x10001])
@pytest.mark.parametrize('rules,expected', [
    (((2, 5, (3,)), (4, 6, (3,))), {5: 'fi', 6: 'ti'}),
    (((2, 5, (3,)), (4, 5, (3,))), {}),
    (((2, 5, (3,)), (4, 5, (6,))), {}),
])
def test_post1_numeric_identity_matches_engine_without_import(tmp_path, monkeypatch, coverage2, extension,
                                                            version, rules, expected):
    source = post1_program(program(tmp_path, table=gsub(rules, coverage2=coverage2,
                                                     extension=extension, version=version)))
    assert reference(source) == expected
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Post-1 ligature mapping imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert read_ligature_mapping(source) == _program_ligature_map(source) == expected


@pytest.mark.parametrize('problem', ['too-many-glyphs', 'short-header'])
def test_post1_incomplete_identity_never_returns_native_mapping(tmp_path, problem):
    source = bytearray(post1_program(program(tmp_path, table=gsub())))
    tables = {table.tag: table for table in inspect_sfnt(bytes(source)).tables}
    if problem == 'too-many-glyphs':
        struct.pack_into('>H', source, tables['maxp'].offset+4, 259)
    else:
        table_count = struct.unpack_from('>H', source, 4)[0]
        for index in range(table_count):
            position = 12+16*index
            if source[position:position+4] == b'post':
                struct.pack_into('>I', source, position+12, 31)
                break
    with pytest.raises(UnsupportedDocumentError, match='post'):
        read_ligature_mapping(bytes(source))


def test_owned_post2_fixture_is_reproducible(tmp_path):
    fixture = Path(__file__).parent/'native/data/ligature-post2.ttf'
    assert fixture.read_bytes() == program(tmp_path, post3=False)


def raw_post2(source, indices, names=(), *, count=None, truncate=0):
    output = BytesIO()
    with TTFont(BytesIO(source), recalcTimestamp=False) as font:
        font.getGlyphOrder()  # Other tables retain their original numeric glyph IDs on save.
        header = bytearray(font.getTableData('post')[:32])
        struct.pack_into('>I', header, 0, 0x20000)
        data = (bytes(header)+struct.pack('>H', len(indices) if count is None else count)
                +struct.pack('>'+'H'*len(indices), *indices)
                +b''.join(bytes([len(name)])+name for name in names))
        table = DefaultTable('post')
        table.data = data[:-truncate] if truncate else data
        font['post'] = table
        font.save(output)
    return output.getvalue()


@pytest.mark.parametrize('indices,names', [
    ([0, 3, 73, 76, 87, 258, 259], [b'fi', b'ti']),
    ([0]*7, []),
    ([258]*7, [b'alias']),
    ([258, 259, 260, 261, 0, 258, 259], [b'.notdef', b'.notdef.1', b'alias', b'alias.1']),
    ([258, 259, 260, 261, 262, 263, 264], [b'', b'glyph00000', b'f', b'i', b't', b'fi', b'ti']),
])
@pytest.mark.parametrize('rules,expected', [
    (((2, 5, (3,)), (4, 6, (3,))), {5: 'fi', 6: 'ti'}),
    (((2, 5, (3,)), (4, 5, (3,))), {}),
    (((2, 5, (3,)), (4, 5, (6,))), {}),
])
def test_post2_aliases_and_recovery_names_keep_numeric_identity_without_engine(tmp_path, monkeypatch,
                                                                             indices, names, rules, expected):
    source = raw_post2(program(tmp_path, table=gsub(rules), post3=False), indices, names)
    assert reference(source) == expected
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Post-2 numeric identity imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert read_ligature_mapping(source) == _program_ligature_map(source) == expected


def test_nonconforming_post2_count_keeps_engine_recovery(tmp_path, monkeypatch):
    import opendoc_formats.writers.pdf_unicode as writer

    source = raw_post2(program(tmp_path, table=gsub(), post3=False), [0, 3, 73, 76, 87, 258, 259],
                       [b'fi', b'ti'], count=8)
    assert reference(source) == {5: 'fi', 6: 'ti'}
    with pytest.raises(UnsupportedDocumentError, match='glyph-name array'):
        read_ligature_mapping(source)
    calls, original = [], writer._ligature_map

    def observed(font):
        calls.append(True)
        return original(font)

    monkeypatch.setattr(writer, '_ligature_map', observed)
    assert _program_ligature_map(source) == {5: 'fi', 6: 'ti'} and calls == [True]


def test_truncated_post2_name_storage_never_gives_partial_native_mapping(tmp_path):
    source = raw_post2(program(tmp_path, table=gsub(), post3=False), [0, 3, 73, 76, 87, 258, 259],
                       [b'fi', b'ti'], truncate=1)
    with pytest.raises(UnsupportedDocumentError, match='Pascal'):
        read_ligature_mapping(source)


@pytest.mark.parametrize('coverage2', [False, True])
@pytest.mark.parametrize('extension', [False, True])
@pytest.mark.parametrize('version', [0x10000, 0x10001])
@pytest.mark.parametrize('post3', [False, True])
@pytest.mark.parametrize('rules,expected', [
    (((2, 5, (3,)), (4, 6, (3,))), {5: 'fi', 6: 'ti'}),
    (((2, 5, (3,)), (2, 5, (3,))), {5: 'fi'}),
    (((2, 5, (3,)), (2, 5, (4,))), {}),
    (((2, 5, (3,)), (2, 5, (6,))), {}),
])
def test_native_mapping_matches_independent_engine_without_imports(tmp_path, monkeypatch, coverage2, extension,
                                                                 version, post3, rules, expected):
    source = program(tmp_path, table=gsub(rules, coverage2=coverage2, extension=extension, version=version), post3=post3)
    assert reference(source) == expected
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Supported GSUB profile imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert read_ligature_mapping(source) == _program_ligature_map(source) == expected


@pytest.mark.parametrize('cmap,expected', [({70: 'f'}, {6: 'ti'}), ({0xfb01: 'fi'}, {6: 'ti'}),
                                          ({0xd800: 'f'}, {5: 'fi', 6: 'ti'})])
@pytest.mark.parametrize('post3', [False, True])
def test_aliases_encoded_ligatures_and_surrogates_keep_established_policy(tmp_path, cmap, expected, post3):
    source = program(tmp_path, table=gsub(), cmap=cmap, post3=post3)
    assert read_ligature_mapping(source) == reference(source) == expected


@pytest.mark.parametrize('post3,flags,version', [(False, 1, 0x10000), (True, 1, 0x10000)])
def test_lookup_flags_keep_engine_fallback(tmp_path, monkeypatch, post3, flags, version):
    import opendoc_formats.writers.pdf_unicode as writer

    source = program(tmp_path, table=gsub(flags=flags, version=version), post3=post3)
    expected = reference(source)
    with pytest.raises(UnsupportedDocumentError):
        read_ligature_mapping(source)
    calls, original = [], writer._ligature_map

    def observed(font):
        calls.append(True)
        return original(font)

    monkeypatch.setattr(writer, '_ligature_map', observed)
    assert _program_ligature_map(source) == expected and calls == [True]


@pytest.mark.parametrize('version', [0x10002, 0x20000])
def test_unknown_versions_are_not_treated_as_version_11(tmp_path, version):
    with pytest.raises(UnsupportedDocumentError, match='version 1.0/1.1'):
        read_ligature_mapping(program(tmp_path, table=gsub(version=version)))


@pytest.mark.parametrize('offset,value', [(4, 10), (6, 12), (8, 13)])
def test_version_11_offsets_cannot_point_into_extended_header(tmp_path, offset, value):
    table = bytearray(gsub(version=0x10001))
    struct.pack_into('>H', table, offset, value)
    with pytest.raises(InvalidDocumentError, match='parent header'):
        read_ligature_mapping(program(tmp_path, table=bytes(table)))


@pytest.mark.parametrize('length', [10, 11, 12, 13])
def test_version_11_requires_complete_extended_header(tmp_path, length):
    with pytest.raises(InvalidDocumentError, match='range outside table'):
        read_ligature_mapping(program(tmp_path, table=gsub(version=0x10001)[:length]))


def test_version_11_feature_variations_keep_engine_fallback(tmp_path, monkeypatch):
    import opendoc_formats.writers.pdf_unicode as writer

    table = bytearray(gsub(version=0x10001))
    struct.pack_into('>I', table, 10, len(table))
    table.extend(struct.pack('>2HI', 1, 0, 0))
    source = program(tmp_path, table=bytes(table))
    expected = reference(source)
    with pytest.raises(UnsupportedDocumentError, match='feature variations'):
        read_ligature_mapping(source)
    calls, original = [], writer._ligature_map

    def observed(font):
        calls.append(True)
        return original(font)

    monkeypatch.setattr(writer, '_ligature_map', observed)
    assert _program_ligature_map(source) == expected and calls == [True]


@pytest.mark.parametrize('offset,value', [(4, 0), (8, 0xffff), (10, 0xffff), (38, 7), (56, 0), (64, 0xffff),
                                        (28, 7), (42, 7), (70, 0xffff), (72, 1), (74, 0xffff), (90, 4)])
def test_malformed_offsets_counts_and_glyphs_never_return_partial_mapping(tmp_path, offset, value):
    table = bytearray(gsub())
    struct.pack_into('>H', table, offset, value)
    source = program(tmp_path, table=bytes(table))
    with pytest.raises((InvalidDocumentError, UnsupportedDocumentError, ResourceLimitError)):
        read_ligature_mapping(source)


def test_repeated_shared_tables_charge_work_budget(tmp_path):
    source = program(tmp_path, table=gsub(repeated=1000))
    with pytest.raises(ResourceLimitError, match='work budget'):
        read_ligature_mapping(source)


@pytest.mark.parametrize('budget', ['lookups', 'bytes'])
def test_declared_table_and_lookup_budgets_are_checked_before_walk(tmp_path, budget):
    table = bytearray(gsub())
    if budget == 'lookups':
        struct.pack_into('>H', table, 44, 1001)
    else:
        table.extend(bytes(8*1024*1024))
    with pytest.raises(ResourceLimitError, match='budget'):
        read_ligature_mapping(program(tmp_path, table=bytes(table)))


@pytest.mark.parametrize('pipeline', [False, True])
def test_cancel_inside_gsub_does_not_enter_engine_fallback(tmp_path, monkeypatch, pipeline):
    import opendoc_formats.fonts.sfnt_ligatures as native

    source = program(tmp_path, table=gsub())
    stop, calls = Event(), []
    original = native._Gsub.word

    def word(self, position):
        calls.append(True)
        if len(calls) == 10:
            stop.set()
        return original(self, position)

    def forbidden(*args, **kwargs):
        pytest.fail('Cancellation entered fontTools fallback')

    monkeypatch.setattr(native._Gsub, 'word', word)
    monkeypatch.setattr(TTFont, '__init__', forbidden)

    class Pdf:
        def __iter__(self):
            return iter([self])

        def get_fonts(self, **kwargs):
            return [(1,)]

        def xref_get_key(self, xref, key):
            return {'Encoding': ('name', '/Identity-H'), 'ToUnicode': ('xref', '2 0 R'),
                    'DescendantFonts': ('array', '[3 0 R]'), 'Subtype': ('name', '/CIDFontType2'),
                    'CIDToGIDMap': ('name', '/Identity')}[key]

        def extract_font(self, xref):
            return '', '', '', source

    with cancellation_scope(stop.is_set, 'Own GSUB'):
        with pytest.raises(OperationCancelledError):
            if pipeline:
                restore_ligature_unicode(Pdf(), ConversionReport(None), 'own-page')
            else:
                _program_ligature_map(source)
        stop.clear()
    assert len(calls) == 10


def test_font_without_gsub_needs_no_engine(monkeypatch):
    source = own_placement_font()

    def forbidden(*args, **kwargs):
        pytest.fail('Font without GSUB started the legacy reader')

    monkeypatch.setattr(TTFont, '__init__', forbidden)
    assert read_ligature_mapping(source) == _program_ligature_map(source) == {}


@pytest.mark.parametrize('version', [0x10000, 0x10001])
@pytest.mark.parametrize('post', [1, 2, 3, 4])
@pytest.mark.parametrize('mixed', [False, True, 2, 3, 5, 6, 8, 'rules5', 'rules6', 'classes5', 'classes6'])
def test_real_pdf_ligature_unicode_repair_without_fonttools_keeps_pixels(tmp_path, monkeypatch, version, post, mixed):
    import pymupdf as fitz

    if mixed in ('classes5', 'classes6'):
        from tests.test_native_font_context_classes import context_classes

        kind = int(mixed[-1])
        table = mixed_gsub(context_classes(kind), lookup_type=kind, version=version)
    elif mixed in ('rules5', 'rules6'):
        from tests.test_native_font_context_rules import context_rules

        kind = int(mixed[-1])
        table = mixed_gsub(context_rules(kind), lookup_type=kind, version=version)
    elif mixed in (5, 6):
        from tests.test_native_font_context_gsub import context_substitution

        table = mixed_gsub(context_substitution(mixed), lookup_type=mixed, version=version)
    elif mixed == 8:
        from tests.test_native_font_reverse_gsub import reverse_substitution

        table = mixed_gsub(reverse_substitution(), lookup_type=8, version=version)
    elif mixed in (2, 3):
        table = mixed_gsub(sequence_substitution(), lookup_type=mixed, version=version)
    else:
        table = mixed_gsub(single_substitution(delta=0), version=version) if mixed else gsub(version=version)
    source = program(tmp_path, table=table, post3=post == 3)
    if post == 1:
        source = post1_program(source)
    elif post == 4:
        source = post4_program(source)
    (tmp_path/'own.ttf').write_bytes(source)
    story = fitz.Story(html='<p>fi ti fi</p>', user_css=(
        '@font-face {font-family:Own;src:url(own.ttf);} p {font-family:Own;font-size:20pt;}'
    ), archive=fitz.Archive(str(tmp_path)))
    pdf = story.write_with_links(lambda *_: (fitz.Rect(0, 0, 240, 200), fitz.Rect(20, 20, 220, 180), fitz.Identity))
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Native ToUnicode repair imported fontTools')
        return original(name, *args, **kwargs)

    try:
        before = pdf[0].get_pixmap().samples
        if post == 4:
            embedded = [pdf.extract_font(font[0])[3] for font in pdf[0].get_fonts(full=True)]
            assert any(struct.unpack_from('>I', data, table.offset)[0] == 0x40000
                       for data in embedded for table in inspect_sfnt(data).tables if table.tag == 'post')
        assert ''.join(pdf[0].get_text().split()) != 'fitifi'
        monkeypatch.setattr(builtins, '__import__', forbidden)
        report = ConversionReport(None)
        restore_ligature_unicode(pdf, report, 'own-page')
        with fitz.open(stream=pdf.tobytes(), filetype='pdf') as restored:
            assert ''.join(restored[0].get_text().split()) == 'fitifi'
            assert restored[0].get_pixmap().samples == before
        assert report.metrics['pdf_ligature_unicode_mappings'] == 2
    finally:
        pdf.close()
