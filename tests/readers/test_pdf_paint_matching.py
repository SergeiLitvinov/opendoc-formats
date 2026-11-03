"""Canonical paint hints require one exact native observation and never keep stale claims."""

from dataclasses import replace

import pymupdf
import pytest
from opendoc_model import (
    ArtifactLimitError,
    DocumentLimits,
    DocumentModel,
    Paragraph,
    Section,
    TextRun,
    TextStyle,
    document_from_json,
    document_to_json,
)

from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.pdf import PdfGlyphInfo, PdfTextSpan
from opendoc_formats.readers.pdf_paint import _evidence, _text_spans, attach_text_paint
from tests.binary_fixtures import own_pdf


def trace(text='AB', *, seqno=7, kind=0):
    return PdfTextSpan(0, 0, seqno, kind, 'Own font', 12, (10, 20, 30, 32), (1, 0), 1,
                       tuple(PdfGlyphInfo(ord(char), index+1, (10+index*10, 30), (10+index*10, 20, 20+index*10, 32))
                             for index, char in enumerate(text)))


def test_unique_native_match_and_font_program_binding_are_preserved():
    span = trace()
    index = {(10, 30): [(span, 0)]}
    programs = {((10, 30), ord('A')): {'font-own'}, ((20, 30), ord('B')): {'font-own'}}
    assert _evidence('AB', 'Own font', (10, 30), index, programs) == {
        'pdf_paint_seq': 7, 'pdf_paint_type': 0, 'pdf_paint_opacity': 1, 'pdf_font_resource': 'font-own',
    }
    programs[((20, 30), ord('B'))] = {'other-font'}
    assert 'pdf_font_resource' not in _evidence('AB', 'Own font', (10, 30), index, programs)


@pytest.mark.parametrize('code', [-1, 0xd800, 0x110000, 0xfffd])
def test_unmapped_unicode_never_crashes_or_silently_establishes_a_known_match(code):
    native = trace()
    unknown = replace(native, glyphs=(replace(native.glyphs[0], unicode=code), native.glyphs[1]))
    for candidates in ([(unknown, 0)], [(native, 0), (unknown, 0)]):
        assert _evidence('AB', 'Own font', (10, 30), {(10, 30): candidates}, {}) == {
            'pdf_paint_unknown': True, 'pdf_paint_unknown_reason': 'unmapped-native-unicode',
        }


def test_duplicate_fill_stroke_events_are_not_deduplicated_into_false_certainty():
    index = {(10, 30): [(trace(kind=0), 0), (trace(kind=1), 0)]}
    result = _evidence('AB', 'Own font', (10, 30), index, {})
    assert result == {'pdf_paint_unknown': True, 'pdf_paint_unknown_reason': 'ambiguous-native-match'}


def test_font_mismatch_short_prefix_and_empty_semantics_remain_unknown():
    index = {(10, 30): [(trace(), 0)]}
    for text, font in [('AB', 'Other font'), ('ABC', 'Own font'), ('AC', 'Own font')]:
        assert _evidence(text, font, (10, 30), index, {})['pdf_paint_unknown_reason'] == 'no-exact-native-match'
    assert _evidence('', 'Own font', (10, 30), index, {})['pdf_paint_unknown_reason'] == 'empty-semantic-text'


def test_ligature_continuation_is_a_unicode_observation_not_a_second_font_guess():
    native = trace('fi')
    native = replace(native, glyphs=(native.glyphs[0], replace(native.glyphs[1], glyph_id=-1, bbox=(20, 20, 20, 32))))
    assert _evidence('fi', 'Own font', (10, 30), {(10, 30): [(native, 0)]}, {})['pdf_paint_seq'] == 7


def test_matching_checks_cancellation_inside_the_unicode_walk():
    polls = 0

    def stopped():
        nonlocal polls
        polls += 1
        return polls >= 3

    with pytest.raises(OperationCancelledError):
        _evidence('AB', 'Own font', (10, 30), {(10, 30): [(trace(), 0)]}, {}, cancelled=stopped)
    assert polls == 3


@pytest.mark.parametrize('limits,quota,maximum', [
    (DocumentLimits(max_nodes=1), 'nodes', 1), (DocumentLimits(max_bytes=1), 'bytes', 1),
    (DocumentLimits(max_bytes=0), 'bytes', 0),
])
def test_native_snapshot_work_honors_selected_import_budgets(limits, quota, maximum):
    source, _ = own_pdf()
    with pymupdf.open(stream=source, filetype='pdf') as native:
        with pytest.raises(ArtifactLimitError) as captured:
            _text_spans(native[0], limits, None)
    assert captured.value.path == '$.sections[0].pdf_text_paint'
    assert captured.value.quota == quota and captured.value.maximum == maximum


def test_reattachment_clears_only_owned_stale_hints_and_preserves_unknown_through_json(tmp_path):
    source = tmp_path/'own.pdf'
    original, _ = own_pdf(commands=b'BT /F1 12 Tf 30 350 Td (Before) Tj ET\n')
    source.write_bytes(original)
    run = TextRun('Before', TextStyle(font_family='Helvetica'), properties={
        'pdf_origin': [30, 50], 'own': 'keep', 'pdf_paint_unknown': True,
        'pdf_paint_unknown_reason': 'old', 'pdf_paint_seq': 99, 'pdf_paint_type': 3, 'pdf_paint_opacity': 0,
    })
    document = DocumentModel(sections=[Section(blocks=[Paragraph(content=[run])])], source_format='pdf')
    attach_text_paint(document, source, limits=None)
    assert run.properties['pdf_paint_seq'] == 0 and run.properties['pdf_paint_type'] == 0
    assert not any(key in run.properties for key in ('pdf_paint_unknown', 'pdf_paint_unknown_reason'))
    run.text = 'Changed'
    attach_text_paint(document, source, limits=None)
    assert run.properties['pdf_paint_unknown_reason'] == 'no-exact-native-match'
    assert not any(key in run.properties for key in ('pdf_paint_seq', 'pdf_paint_type', 'pdf_paint_opacity'))
    restored = document
    for _ in range(2):
        restored = document_from_json(document_to_json(restored))
    preserved = restored.sections[0].blocks[0].content[0].properties
    assert preserved['pdf_paint_unknown_reason'] == 'no-exact-native-match' and preserved['own'] == 'keep'
    assert source.read_bytes() == original
