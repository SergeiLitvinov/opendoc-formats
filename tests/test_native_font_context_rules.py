"""Owned GSUB format-1 rules, numeric identities and conservative engine parity."""

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


def context_rules(kind=5, *, coverage2=False, null=False, shared=False, repeated=1,
                  rest=(3,), back=(1,), ahead=(1,), actions=((0, 0),)):
    coverage = (struct.pack('>8H', 2, 2, 2, 2, 0, 4, 4, 1) if coverage2 else struct.pack('>4H', 1, 2, 2, 4))
    words = ([1+len(rest), len(actions), *rest] if kind == 5 else
             [len(back), *back, 1+len(rest), *rest, len(ahead), *ahead, len(actions)])
    words.extend(value for record in actions for value in record)
    rule = struct.pack('>'+'H'*len(words), *words)
    group = struct.pack('>H', repeated)+struct.pack('>H', 2+2*repeated)*repeated+rule
    first = 10+len(coverage)
    return (struct.pack('>5H', 1, 10, 2, first, 0 if null else first+(0 if shared else len(group)))
            +coverage+group*(1 if null or shared else 2))


@pytest.mark.parametrize('kind', [5, 6])
@pytest.mark.parametrize('coverage2', [False, True])
@pytest.mark.parametrize('extension', [False, True])
@pytest.mark.parametrize('before', [False, True])
@pytest.mark.parametrize('profile', ['ordinary', 'null', 'shared', 'repeated'])
def test_numeric_rules_match_engine_without_import(tmp_path, monkeypatch, kind, coverage2,
                                                 extension, before, profile):
    table = context_rules(kind, coverage2=coverage2, null=profile == 'null',
                          shared=profile == 'shared', repeated=3 if profile == 'repeated' else 1)
    source = program(tmp_path, table=mixed_gsub(table, lookup_type=kind, extension=extension, before=before))
    expected = reference(source)
    assert expected == {5: 'fi', 6: 'ti'}
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Accepted context format 1 imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert read_ligature_mapping(source) == _program_ligature_map(source) == expected


@pytest.mark.parametrize('kind', [5, 6])
@pytest.mark.parametrize('rest,back,ahead,actions', [
    ((), (), (), ()), ((3, 4), (), (), ((1, 0), (0, 0))),
    ((3,), (1, 4), (), ((0, 1),)), ((3,), (), (1, 4), ((0, 0),)),
])
def test_rule_sequence_lengths_and_action_order_are_not_executed(tmp_path, kind, rest, back, ahead, actions):
    table = context_rules(kind, rest=rest, back=back, ahead=ahead, actions=actions)
    source = program(tmp_path, table=mixed_gsub(table, lookup_type=kind))
    assert read_ligature_mapping(source) == reference(source) == {5: 'fi', 6: 'ti'}


@pytest.mark.parametrize('kind', [5, 6])
@pytest.mark.parametrize('problem', ['coverage-count', 'group-offset', 'rule-offset', 'empty', 'glyph', 'lookup'])
def test_damaged_context_rule_never_returns_partial_evidence(tmp_path, kind, problem):
    table = bytearray(context_rules(kind))
    group = struct.unpack_from('>H', table, 6)[0]
    rule = group+struct.unpack_from('>H', table, group+2)[0]
    inputs, glyph, lookup = ((rule, rule+4, rule+8) if kind == 5 else (rule+4, rule+6, rule+16))
    position, value = {'coverage-count': (4, 3), 'group-offset': (6, 8),
                       'rule-offset': (group+2, 2), 'empty': (inputs, 0),
                       'glyph': (glyph, 7), 'lookup': (lookup, 2)}[problem]
    struct.pack_into('>H', table, position, value)
    with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
        read_ligature_mapping(program(tmp_path, table=mixed_gsub(bytes(table), lookup_type=kind)))


@pytest.mark.parametrize('kind', [5, 6])
def test_every_truncated_rule_table_refuses_partial_mapping(tmp_path, kind):
    table = context_rules(kind)
    for length in range(len(table)):
        with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
            read_ligature_mapping(program(tmp_path, table=mixed_gsub(table[:length], lookup_type=kind)))


@pytest.mark.parametrize('kind', [5, 6])
def test_changed_input_sequence_keeps_previous_fallback(tmp_path, monkeypatch, kind):
    table = context_rules(kind, actions=((0, 0), (2, 0)))
    source = program(tmp_path, table=mixed_gsub(table, lookup_type=kind))
    expected, original, calls = reference(source), TTFont.__init__, []

    def engine(self, *args, **kwargs):
        calls.append(True)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TTFont, '__init__', engine)
    with pytest.raises(UnsupportedDocumentError, match='changed input context'):
        read_ligature_mapping(source)
    assert _program_ligature_map(source) == expected and calls == [True]


@pytest.mark.parametrize('kind', [5, 6])
def test_repeated_shared_rules_consume_work_budget(tmp_path, kind):
    table = mixed_gsub(context_rules(kind, shared=True, repeated=32), lookup_type=kind)
    position = struct.unpack_from('>H', table, 8)[0]
    second = struct.unpack_from('>H', table, position+4)[0]
    table = (table[:position]+struct.pack('>2H', 1000, 2002)
             +struct.pack('>H', 2002+second-6)*999+table[position+6:])
    with pytest.raises(ResourceLimitError, match='work budget'):
        read_ligature_mapping(program(tmp_path, table=table))


@pytest.mark.parametrize('kind', [5, 6])
def test_cancellation_inside_rule_glyph_array_does_not_enter_engine(tmp_path, monkeypatch, kind):
    import opendoc_formats.fonts.sfnt_ligatures as native

    source = program(tmp_path, table=mixed_gsub(context_rules(kind), lookup_type=kind))
    stop, calls = Event(), []
    original, glyph = native._Gsub.context_rule, native._Gsub.glyph

    def cancel_glyph(self, position):
        calls.append(True)
        stop.set()
        return glyph(self, position)

    def rule(self, base, lookup_kind, lookups):
        monkeypatch.setattr(native._Gsub, 'glyph', cancel_glyph)
        return original(self, base, lookup_kind, lookups)

    def forbidden(*args, **kwargs):
        pytest.fail('Cancelled context rule entered fontTools')

    monkeypatch.setattr(native._Gsub, 'context_rule', rule)
    monkeypatch.setattr(TTFont, '__init__', forbidden)
    with cancellation_scope(stop.is_set, 'GSUB context rules'):
        with pytest.raises(OperationCancelledError):
            _program_ligature_map(source)
        stop.clear()
    assert calls == [True]


@pytest.mark.parametrize('kind', [5, 6])
def test_owned_rule_fixture_is_reproducible(tmp_path, kind):
    fixture = Path(__file__).parent/f'native/data/ligature-rules{kind}.ttf'
    assert fixture.read_bytes() == program(tmp_path, table=mixed_gsub(context_rules(kind), lookup_type=kind))
