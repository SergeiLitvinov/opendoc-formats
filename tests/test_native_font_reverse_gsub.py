"""Owned type-8 bytes: structural validation and unchanged ligature evidence."""

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


def reverse_substitution(*, coverage2=False, back=1, ahead=1, shared=False, outputs=(2, 3)):
    coverage = (struct.pack('>5H', 2, 1, 2, 3, 0) if coverage2 else struct.pack('>4H', 1, 2, 2, 3))
    context = struct.pack('>3H', 1, 1, 1)
    minimum = 10+2*(back+ahead+len(outputs))
    offsets = [minimum+len(coverage)+(0 if shared else 6*i) for i in range(back+ahead)]
    words = [1, minimum, back, *offsets[:back], ahead, *offsets[back:], len(outputs), *outputs]
    return struct.pack('>'+'H'*len(words), *words)+coverage+context*(1 if shared and offsets else len(offsets))


def test_owned_reverse_fixture_is_reproducible(tmp_path):
    fixture = Path(__file__).parent/'native/data/ligature-reverse.ttf'
    assert fixture.read_bytes() == program(tmp_path, table=mixed_gsub(reverse_substitution(), lookup_type=8))


@pytest.mark.parametrize('coverage2', [False, True])
@pytest.mark.parametrize('extension', [False, True])
@pytest.mark.parametrize('before', [False, True])
@pytest.mark.parametrize('back,ahead,shared', [(0, 0, False), (1, 0, False), (0, 2, False),
                                           (2, 3, False), (2, 3, True)])
def test_reverse_contexts_match_engine_without_import(tmp_path, monkeypatch, coverage2, extension,
                                                     before, back, ahead, shared):
    table = reverse_substitution(coverage2=coverage2, back=back, ahead=ahead, shared=shared)
    source = program(tmp_path, table=mixed_gsub(table, lookup_type=8, extension=extension, before=before))
    expected = reference(source)
    assert expected == {5: 'fi', 6: 'ti'}
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Accepted reverse chaining lookup imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert read_ligature_mapping(source) == _program_ligature_map(source) == expected


@pytest.mark.parametrize('cmap,expected', [(None, {5: 'fi', 6: 'ti'}), ({70: 'f'}, {6: 'ti'}),
                                        ({0xfb01: 'fi'}, {6: 'ti'})])
def test_reverse_outputs_do_not_infer_unicode_or_override_ambiguity(tmp_path, cmap, expected):
    table = reverse_substitution(outputs=(5, 6))
    source = program(tmp_path, table=mixed_gsub(table, lookup_type=8), cmap=cmap)
    assert read_ligature_mapping(source) == reference(source) == expected


@pytest.mark.parametrize('offset,value', [(0, 2), (2, 0), (2, 16), (2, 65535), (4, 65535),
                                        (6, 0), (6, 16), (6, 65535), (8, 65535), (10, 0),
                                        (10, 16), (10, 65535), (12, 3), (14, 7), (16, 65535),
                                        (20, 1), (22, 7), (24, 2), (28, 65535), (30, 7)])
def test_invalid_reverse_ranges_counts_and_glyphs_never_return_partial_mapping(tmp_path, offset, value):
    table = bytearray(reverse_substitution())
    struct.pack_into('>H', table, offset, value)
    source = program(tmp_path, table=mixed_gsub(bytes(table), lookup_type=8))
    with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
        read_ligature_mapping(source)


@pytest.mark.parametrize('length', range(38))
def test_truncated_reverse_subtable_refuses_partial_evidence(tmp_path, length):
    source = program(tmp_path, table=mixed_gsub(reverse_substitution()[:length], lookup_type=8))
    with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
        read_ligature_mapping(source)


def test_reverse_shared_contexts_charge_work_per_reference(tmp_path):
    table = mixed_gsub(reverse_substitution(back=512, ahead=512, shared=True), lookup_type=8)
    position = struct.unpack_from('>H', table, 8)[0]
    second = struct.unpack_from('>H', table, position+4)[0]
    lookups = table[position+6:]
    table = table[:position]+struct.pack('>2H', 1000, 2002)+struct.pack('>H', 2002+second-6)*999+lookups
    with pytest.raises(ResourceLimitError, match='work budget'):
        read_ligature_mapping(program(tmp_path, table=table))


def test_cancel_inside_reverse_coverage_does_not_enter_engine(tmp_path, monkeypatch):
    import opendoc_formats.fonts.sfnt_ligatures as native

    source = program(tmp_path, table=mixed_gsub(reverse_substitution(), lookup_type=8))
    stop, calls = Event(), []
    original, coverage = native._Gsub.reverse_table, native._Gsub.coverage

    def cancel_coverage(self, base, expected):
        calls.append(True)
        if len(calls) == 2:  # After input, inside backtrack coverage validation.
            stop.set()
        return coverage(self, base, expected)

    def reverse(self, base):
        monkeypatch.setattr(native._Gsub, 'coverage', cancel_coverage)
        return original(self, base)

    def forbidden(*args, **kwargs):
        pytest.fail('Cancelled reverse chaining entered fontTools')

    monkeypatch.setattr(native._Gsub, 'reverse_table', reverse)
    monkeypatch.setattr(TTFont, '__init__', forbidden)
    with cancellation_scope(stop.is_set, 'GSUB reverse chaining'):
        with pytest.raises(OperationCancelledError):
            _program_ligature_map(source)
        stop.clear()
    assert len(calls) == 2
