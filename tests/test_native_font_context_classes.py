"""Owned class-based GSUB bytes, without class-to-Unicode inference or shaping."""

import builtins
import struct
from pathlib import Path
from threading import Event

import pytest
from fontTools.ttLib import TTFont

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.fonts.sfnt_ligatures import read_ligature_mapping
from opendoc_formats.support.cancellation import cancellation_scope
from opendoc_formats.writers.pdf_unicode import _program_ligature_map
from tests.test_native_font_ligatures import mixed_gsub, program, reference


def class_definition(kind=1, labels=(1, 2, 1)):
    if kind == 1:
        return struct.pack('>3H', 1, 2, len(labels))+struct.pack('>'+'H'*len(labels), *labels)
    return struct.pack('>2H', 2, len(labels))+b''.join(
        struct.pack('>3H', 2+i, 2+i, label) for i, label in enumerate(labels))


def context_classes(kind=5, *, definition=1, coverage2=False, shared=False, zero=False,
                    repeated=1, actions=((0, 0),), rest=(2,), back=(0,), ahead=(0,)):
    coverage = struct.pack('>8H', 2, 2, 2, 2, 0, 4, 4, 1) if coverage2 else struct.pack('>4H', 1, 2, 2, 4)
    classes = class_definition(definition, (0 if zero else 1, 2, 0 if zero else 1))
    words = ([1+len(rest), len(actions), *rest] if kind == 5 else
             [len(back), *back, 1+len(rest), *rest, len(ahead), *ahead, len(actions)])
    words.extend(value for record in actions for value in record)
    rule = struct.pack('>'+'H'*len(words), *words)
    group = struct.pack('>H', repeated)+struct.pack('>H', 2+2*repeated)*repeated+rule
    header = 14 if kind == 5 else 18  # Three class RuleSets, including NULL entries.
    start = header+len(coverage)
    defs = [start+(0 if shared else i*len(classes)) for i in range(1 if kind == 5 else 3)]
    first_group = start+len(classes)*(1 if shared or kind == 5 else 3)
    sets = [first_group if zero else 0, 0 if zero else first_group, 0]
    words = [2, header, *defs, 3, *sets]
    return struct.pack('>'+'H'*len(words), *words)+coverage+classes*(1 if shared or kind == 5 else 3)+group


@pytest.mark.parametrize('kind', [5, 6])
@pytest.mark.parametrize('definition', [1, 2])
@pytest.mark.parametrize('coverage2', [False, True])
@pytest.mark.parametrize('extension', [False, True])
@pytest.mark.parametrize('before', [False, True])
@pytest.mark.parametrize('profile', ['ordinary', 'shared', 'zero'])
def test_class_context_matches_engine_without_import(tmp_path, monkeypatch, kind, definition, coverage2,
                                                    extension, before, profile):
    table = context_classes(kind, definition=definition, coverage2=coverage2,
                            shared=profile == 'shared', zero=profile == 'zero')
    source = program(tmp_path, table=mixed_gsub(table, lookup_type=kind, extension=extension, before=before))
    expected = reference(source)
    assert expected == {5: 'fi', 6: 'ti'}
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Accepted class-based GSUB imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert read_ligature_mapping(source) == _program_ligature_map(source) == expected


@pytest.mark.parametrize('kind', [5, 6])
def test_class_labels_are_not_bounded_as_glyph_ids(tmp_path, kind):
    table = context_classes(kind, rest=(65535,), back=(65534,), ahead=(65533,))
    source = program(tmp_path, table=mixed_gsub(table, lookup_type=kind))
    assert read_ligature_mapping(source) == reference(source) == {5: 'fi', 6: 'ti'}


@pytest.mark.parametrize('kind', [5, 6])
@pytest.mark.parametrize('definition', [1, 2])
def test_implicit_class_zero_uses_undefined_glyphs(tmp_path, kind, definition):
    table = bytearray(context_classes(kind, definition=definition, zero=True))
    header = 14 if kind == 5 else 18
    struct.pack_into('>2H', table, header+4, 0, 1)  # Not explicitly assigned by ClassDef.
    source = program(tmp_path, table=mixed_gsub(bytes(table), lookup_type=kind))
    assert read_ligature_mapping(source) == reference(source) == {5: 'fi', 6: 'ti'}


@pytest.mark.parametrize('kind', [5, 6])
@pytest.mark.parametrize('definition', [1, 2])
@pytest.mark.parametrize('problem', ['def-offset', 'def-format', 'glyph', 'def-count', 'group-offset',
                                    'rule-offset', 'empty', 'lookup', 'first-class'])
def test_damaged_class_context_never_returns_partial_evidence(tmp_path, kind, definition, problem):
    table = bytearray(context_classes(kind, definition=definition))
    header = 14 if kind == 5 else 18
    input_def = struct.unpack_from('>H', table, 4 if kind == 5 else 6)[0]
    group = struct.unpack_from('>H', table, header-4)[0]
    rule = group+struct.unpack_from('>H', table, group+2)[0]
    position, value = {
        'def-offset': (4, header-2), 'def-format': (input_def, 3),
        'glyph': (input_def+2 if definition == 1 else input_def+4, 65535),
        'def-count': (input_def+4 if definition == 1 else input_def+2, 65535),
        'group-offset': (header-4, header-2), 'rule-offset': (group+2, 2),
        'empty': (rule if kind == 5 else rule+4, 0),
        'lookup': (rule+8 if kind == 5 else rule+16, 2),
        'first-class': (input_def+6 if definition == 1 else input_def+8, 3),
    }[problem]
    struct.pack_into('>H', table, position, value)
    with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
        read_ligature_mapping(program(tmp_path, table=mixed_gsub(bytes(table), lookup_type=kind)))


@pytest.mark.parametrize('kind', [5, 6])
def test_overlapping_or_reversed_class_ranges_are_rejected(tmp_path, kind):
    for position, value in ((10, 2), (4, 3)):
        table = bytearray(context_classes(kind, definition=2))
        base = struct.unpack_from('>H', table, 4 if kind == 5 else 6)[0]
        struct.pack_into('>H', table, base+position, value)
        with pytest.raises(InvalidDocumentError, match='class ranges'):
            read_ligature_mapping(program(tmp_path, table=mixed_gsub(bytes(table), lookup_type=kind)))


@pytest.mark.parametrize('kind', [5, 6])
@pytest.mark.parametrize('definition', [1, 2])
def test_every_class_table_truncation_refuses_partial_evidence(tmp_path, kind, definition):
    table = context_classes(kind, definition=definition)
    for length in range(len(table)):
        with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
            read_ligature_mapping(program(tmp_path, table=mixed_gsub(table[:length], lookup_type=kind)))


@pytest.mark.parametrize('kind', [5, 6])
def test_changed_class_sequence_preserves_engine_fallback(tmp_path, monkeypatch, kind):
    source = program(tmp_path, table=mixed_gsub(context_classes(kind, actions=((0, 0), (2, 0))), lookup_type=kind))
    expected, original, calls = reference(source), TTFont.__init__, []

    def engine(self, *args, **kwargs):
        calls.append(True)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TTFont, '__init__', engine)
    with pytest.raises(UnsupportedDocumentError, match='changed input context'):
        read_ligature_mapping(source)
    assert _program_ligature_map(source) == expected and calls == [True]


@pytest.mark.parametrize('kind', [5, 6])
def test_shared_class_rules_consume_work_per_reference(tmp_path, kind):
    table = mixed_gsub(context_classes(kind, shared=True, repeated=64), lookup_type=kind)
    position = struct.unpack_from('>H', table, 8)[0]
    second = struct.unpack_from('>H', table, position+4)[0]
    table = (table[:position]+struct.pack('>2H', 1000, 2002)
             +struct.pack('>H', 2002+second-6)*999+table[position+6:])
    with pytest.raises(ResourceLimitError, match='work budget'):
        read_ligature_mapping(program(tmp_path, table=table))


@pytest.mark.parametrize('kind', [5, 6])
@pytest.mark.parametrize('definition', [1, 2])
def test_cancel_inside_class_definition_never_enters_engine(tmp_path, monkeypatch, kind, definition):
    import opendoc_formats.fonts.sfnt_ligatures as native

    source = program(tmp_path, table=mixed_gsub(context_classes(kind, definition=definition), lookup_type=kind))
    stop, calls = Event(), []
    original, spend = native._Gsub.class_definition, native._Gsub.spend

    def cancel_spend(self, count=1):
        calls.append(True)
        if len(calls) == 6:  # Inside the class value array / first expanded range.
            stop.set()
        return spend(self, count)

    def cancel(self, base):
        monkeypatch.setattr(native._Gsub, 'spend', cancel_spend)
        return original(self, base)

    def forbidden(*args, **kwargs):
        pytest.fail('Cancelled ClassDef entered fontTools')

    monkeypatch.setattr(native._Gsub, 'class_definition', cancel)
    monkeypatch.setattr(TTFont, '__init__', forbidden)
    with cancellation_scope(stop.is_set, 'GSUB classes'):
        with pytest.raises(OperationCancelledError):
            _program_ligature_map(source)
        stop.clear()
    assert len(calls) == 6


@pytest.mark.parametrize('kind', [5, 6])
def test_owned_class_fixture_is_reproducible(tmp_path, kind):
    fixture = Path(__file__).parent/f'native/data/ligature-classes{kind}.ttf'
    assert fixture.read_bytes() == program(tmp_path, table=mixed_gsub(context_classes(kind), lookup_type=kind))
