"""Independent format-3 contextual GSUB bytes; validation without lookup execution."""

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


def context_substitution(kind=5, *, coverage2=False, back=1, ahead=1, inputs=2,
                         actions=((0, 0),), shared=False):
    coverage = struct.pack('>5H', 2, 1, 2, 3, 0) if coverage2 else struct.pack('>4H', 1, 2, 2, 3)
    total = inputs if kind == 5 else back+inputs+ahead
    minimum = (6 if kind == 5 else 10)+2*total+4*len(actions)
    offsets = [minimum+(0 if shared else len(coverage)*i) for i in range(total)]
    words = ([3, inputs, len(actions), *offsets] if kind == 5 else
             [3, back, *offsets[:back], inputs, *offsets[back:back+inputs],
              ahead, *offsets[back+inputs:], len(actions)])
    words.extend(value for record in actions for value in record)
    return struct.pack('>'+'H'*len(words), *words)+coverage*(1 if shared and total else total)


@pytest.mark.parametrize('kind', [5, 6])
@pytest.mark.parametrize('coverage2', [False, True])
@pytest.mark.parametrize('extension', [False, True])
@pytest.mark.parametrize('before', [False, True])
@pytest.mark.parametrize('shared', [False, True])
def test_context_mapping_matches_engine_without_import(tmp_path, monkeypatch, kind, coverage2,
                                                      extension, before, shared):
    table = context_substitution(kind, coverage2=coverage2, shared=shared)
    source = program(tmp_path, table=mixed_gsub(table, lookup_type=kind, extension=extension, before=before))
    expected = reference(source)
    assert expected == {5: 'fi', 6: 'ti'}
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Accepted context format 3 imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert read_ligature_mapping(source) == _program_ligature_map(source) == expected


@pytest.mark.parametrize('kind', [5, 6])
@pytest.mark.parametrize('actions', [(), ((1, 0),), ((1, 0), (0, 0)), ((0, 1),), ((0, 1), (1, 0))])
def test_context_actions_remain_ordered_and_unexecuted(tmp_path, kind, actions):
    table = context_substitution(kind, back=0, ahead=0, actions=actions)
    source = program(tmp_path, table=mixed_gsub(table, lookup_type=kind))
    assert read_ligature_mapping(source) == reference(source) == {5: 'fi', 6: 'ti'}


@pytest.mark.parametrize('kind', [5, 6])
@pytest.mark.parametrize('problem', ['format', 'empty', 'lookup', 'offset', 'glyph', 'order', 'count'])
def test_invalid_context_never_returns_partial_mapping(tmp_path, kind, problem):
    table = bytearray(context_substitution(kind))
    header = 14 if kind == 5 else 22
    offset_position, input_position = (6, 2) if kind == 5 else (4, 6)
    position, value = {
        'format': (0, 2), 'empty': (input_position, 0), 'lookup': (header-2, 2),
        'offset': (offset_position, header-2), 'glyph': (header+4, 7),
        'order': (header+6, 2), 'count': (header+2, 65535),
    }[problem]
    struct.pack_into('>H', table, position, value)
    with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
        read_ligature_mapping(program(tmp_path, table=mixed_gsub(bytes(table), lookup_type=kind)))


@pytest.mark.parametrize('kind', [5, 6])
def test_every_truncated_context_rejects_partial_evidence(tmp_path, kind):
    table = context_substitution(kind)
    for length in range(len(table)):
        with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
            read_ligature_mapping(program(tmp_path, table=mixed_gsub(table[:length], lookup_type=kind)))


@pytest.mark.parametrize('kind', [5, 6])
def test_expanded_sequence_index_keeps_engine_fallback(tmp_path, monkeypatch, kind):
    table = context_substitution(kind, actions=((0, 0), (2, 0)))
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
def test_shared_context_coverage_is_charged_per_reference(tmp_path, kind):
    table = mixed_gsub(context_substitution(kind, inputs=1024, shared=True), lookup_type=kind)
    position = struct.unpack_from('>H', table, 8)[0]
    second = struct.unpack_from('>H', table, position+4)[0]
    table = (table[:position]+struct.pack('>2H', 1000, 2002)
             +struct.pack('>H', 2002+second-6)*999+table[position+6:])
    with pytest.raises(ResourceLimitError, match='work budget'):
        read_ligature_mapping(program(tmp_path, table=table))


@pytest.mark.parametrize('kind', [5, 6])
def test_cancellation_in_context_coverage_never_enters_engine(tmp_path, monkeypatch, kind):
    import opendoc_formats.fonts.sfnt_ligatures as native

    source = program(tmp_path, table=mixed_gsub(context_substitution(kind), lookup_type=kind))
    stop, calls = Event(), []
    original, coverage = native._Gsub.context_table, native._Gsub.coverage

    def cancel_coverage(self, base, expected):
        calls.append(True)
        if len(calls) == 2:
            stop.set()
        return coverage(self, base, expected)

    def context(self, base, lookup_kind, lookups):
        monkeypatch.setattr(native._Gsub, 'coverage', cancel_coverage)
        return original(self, base, lookup_kind, lookups)

    def forbidden(*args, **kwargs):
        pytest.fail('Cancelled context entered fontTools')

    monkeypatch.setattr(native._Gsub, 'context_table', context)
    monkeypatch.setattr(TTFont, '__init__', forbidden)
    with cancellation_scope(stop.is_set, 'GSUB context'):
        with pytest.raises(OperationCancelledError):
            _program_ligature_map(source)
        stop.clear()
    assert len(calls) == 2


@pytest.mark.parametrize('kind', [5, 6])
def test_owned_context_fixture_is_reproducible(tmp_path, kind):
    fixture = Path(__file__).parent/f'native/data/ligature-context{kind}.ttf'
    assert fixture.read_bytes() == program(tmp_path, table=mixed_gsub(context_substitution(kind), lookup_type=kind))
