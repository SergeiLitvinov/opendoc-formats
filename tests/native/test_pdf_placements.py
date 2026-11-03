"""Real device matrices retain native occurrences without inferring shape from text bboxes."""

import hashlib
import json
from dataclasses import FrozenInstanceError, asdict
from threading import Event

import pymupdf
import pytest

from opendoc_formats.errors import (
    DocumentClosedError,
    InvalidDocumentError,
    OperationCancelledError,
    PageIndexError,
    ResourceLimitError,
    UnsupportedDocumentError,
)
from opendoc_formats.pdf import PdfDocument, PdfLimits
from tests.binary_fixtures import own_pdf, own_placement_font


def own_source(*, rotation=b'', font=None):
    return own_pdf(font_program=font, parent_extra=rotation,
                   commands=b'BT /F1 12 Tf 1 .25 .5 1 60 300 Tm (ABC) Tj ET\n')[0]


@pytest.mark.parametrize('rotation', [b'', b'/Rotate 90 '])
def test_native_matrices_own_font_ligature_and_original_objects_survive_inspection(rotation):
    font = own_placement_font()
    source = own_source(rotation=rotation, font=font)
    with PdfDocument(source, limits=PdfLimits(cache_bytes=0)) as pdf:
        objects = tuple(pdf.iter_objects())
        before = pdf.render_page(0, dpi=108).png
        placements = pdf.page_text_placements(0)
        assert len(placements) == 1
        span = placements[0]
        assert span.page_index == 0 and span.occurrence_index == 0 and span.operation == 'fill'
        assert span.font_program_sha256 == hashlib.sha256(font).hexdigest()
        assert [(g.unicode, g.glyph_id) for g in span.glyphs] == [(65, 1), (66, 2), (102, 3), (105, -1)]
        assert span.glyphs[0].transform == (12, -3, 6, -12, 60, 100)
        assert span.glyphs[-1].glyph_bbox is None
        assert span.glyphs[-1].transform == span.glyphs[-2].transform
        for index, glyph in enumerate(span.glyphs[:3], 1):
            a, b, c, d, e, f = glyph.transform
            corners = [(a*x+c*y+e, b*x+d*y+f) for x in (.05, (.45+index*.05)) for y in (0, .7)]
            expected = (min(x for x, _ in corners), min(y for _, y in corners),
                        max(x for x, _ in corners), max(y for _, y in corners))
            assert glyph.glyph_bbox == pytest.approx(expected, abs=0.0001)
        assert pdf.render_page(0, dpi=108).png == before
        assert tuple(pdf.iter_objects()) == objects
        assert json.loads(json.dumps(asdict(span)))['glyphs'][-1]['glyph_id'] == -1
    with pytest.raises(FrozenInstanceError):
        span.glyphs[0].unicode = 999
    assert span.glyphs[0].unicode == 65


def test_all_pdf_text_modes_keep_separate_fill_stroke_ignore_and_clip_occurrences():
    commands = b''.join(b'q BT /F1 12 Tf '+str(mode).encode()+b' Tr 30 '+str(350-mode*30).encode()+
                        b' Td (AB) Tj ET Q\n' for mode in range(8))
    source = own_pdf(commands=commands)[0]
    with PdfDocument(source) as pdf:
        spans = pdf.page_text_placements(0)
    assert [span.operation for span in spans] == [
        'fill', 'stroke', 'fill', 'stroke', 'ignore', 'fill', 'clip', 'stroke', 'clip', 'fill', 'stroke', 'clip', 'clip',
    ]
    assert [span.occurrence_index for span in spans] == list(range(13))
    assert spans[2].glyphs == spans[3].glyphs and spans[2] != spans[3]


def metadata_size(spans):
    values = []
    for span in spans:
        values.append([span.page_index, span.occurrence_index, span.operation, span.font,
                       span.font_program_sha256, span.opacity])
        values.extend([glyph.unicode, glyph.glyph_id, list(glyph.transform),
                       list(glyph.glyph_bbox) if glyph.glyph_bbox is not None else None] for glyph in span.glyphs)
    return sum(len(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()) for value in values)


def test_exact_compact_metadata_budget_includes_glyph_rows_and_survives_a_failed_attempt():
    source = own_source()
    with PdfDocument(source) as pdf:
        exact = metadata_size(pdf.page_text_placements(0))
    with PdfDocument(source, limits=PdfLimits(max_text_metadata_bytes=exact)) as pdf:
        assert pdf.page_text_placements(0)
    with PdfDocument(source, limits=PdfLimits(max_text_metadata_bytes=exact-1)) as pdf:
        with pytest.raises(ResourceLimitError, match='max_text_metadata_bytes'):
            pdf.page_text_placements(0)


@pytest.mark.parametrize('limit', [PdfLimits(max_text_chars=1), PdfLimits(max_text_metadata_bytes=1)])
def test_glyph_and_metadata_limits_fail_before_copying_font_programs(limit, monkeypatch):
    def forbidden(*args):
        pytest.fail('Font program copied after the selected small budget was exhausted')

    monkeypatch.setattr(pymupdf.mupdf, 'll_fz_buffer_extract_copy', forbidden)
    with PdfDocument(own_source(), limits=limit) as pdf:
        with pytest.raises(ResourceLimitError):
            pdf.page_text_placements(0)


def test_distinct_font_bytes_are_bounded_but_repeated_occurrences_are_only_hashed_once(monkeypatch):
    font = own_placement_font()
    source = own_pdf(font_program=font, commands=b'BT /F1 12 Tf 2 Tr 30 300 Td (ABC) Tj ET\n')[0]
    reads = []
    copy_buffer = pymupdf.mupdf.ll_fz_buffer_extract_copy

    def copied(buffer):
        reads.append(int(buffer.len))
        return copy_buffer(buffer)

    monkeypatch.setattr(pymupdf.mupdf, 'll_fz_buffer_extract_copy', copied)
    with PdfDocument(source, limits=PdfLimits(max_inspection_bytes=len(font))) as pdf:
        assert len(pdf.page_text_placements(0)) == 2
    assert reads == [len(font)]
    for limits, quota in [(PdfLimits(max_inspection_bytes=len(font)-1), 'max_inspection_bytes'),
                          (PdfLimits(max_object_bytes=len(font)-1), 'max_object_bytes')]:
        with PdfDocument(source, limits=limits) as pdf:
            with pytest.raises(ResourceLimitError, match=quota):
                pdf.page_text_placements(0)


def test_callback_cancellation_returns_no_partial_snapshot_and_restores_inherited_rotate(monkeypatch):
    import opendoc_formats.native.pdf_placements as native

    stop = Event()
    construct = native.PdfPlacedGlyph
    copies = []

    def first(*args):
        assert not copies, 'Another glyph was copied after cancellation'
        value = construct(*args)
        copies.append(value)
        stop.set()
        return value

    source = own_source(rotation=b'/Rotate 90 ')
    with PdfDocument(source, cancelled=stop.is_set, limits=PdfLimits(cache_bytes=0)) as pdf:
        before = tuple(pdf.iter_objects())
        raster = pdf.render_page(0, dpi=72).png
        with monkeypatch.context() as context:
            context.setattr(native, 'PdfPlacedGlyph', first)
            with pytest.raises(OperationCancelledError):
                pdf.page_text_placements(0)
        stop.clear()
        assert tuple(pdf.iter_objects()) == before and pdf.render_page(0, dpi=72).png == raster
        assert pdf.page_text_placements(0)
    assert len(copies) == 1


def test_span_budget_and_native_page_state_are_validated_before_returns():
    source = own_pdf(commands=b'BT /F1 12 Tf 2 Tr 30 300 Td (ABC) Tj ET\n')[0]
    with PdfDocument(source, limits=PdfLimits(max_text_spans=1)) as pdf:
        with pytest.raises(ResourceLimitError, match='max_text_spans'):
            pdf.page_text_placements(0)
        with pytest.raises(PageIndexError):
            pdf.page_text_placements(1)
        with pytest.raises(TypeError):
            pdf.page_text_placements(True)
    with pytest.raises(DocumentClosedError):
        pdf.page_text_placements(0)


def test_form_matrix_text_matrix_and_page_ctm_are_composed_from_source_operators():
    font = own_placement_font()
    source, _ = own_pdf(font_program=font, commands=b'q 2 0 0 3 20 30 cm /Fm1 Do Q\n',
                        form_commands=b'BT /F1 12 Tf 1 .25 .5 1 10 20 Tm (ABC) Tj ET\n',
                        form_matrix=b'1 .1 .2 1 5 6')
    with PdfDocument(source) as pdf:
        placement, = pdf.page_text_placements(0)
    assert placement.font_program_sha256 == hashlib.sha256(font).hexdigest()
    assert placement.glyphs[0].transform == pytest.approx((25.2, -12.6, 16.8, -37.8, 58, 289), abs=.0001)


def test_image_only_content_has_no_text_placements():
    source, _ = own_pdf(commands=b'q 20 0 0 20 40 80 cm /Im1 Do Q\n')
    with PdfDocument(source) as pdf:
        assert pdf.page_text_placements(0) == ()


def test_horizontal_scale_rise_and_tj_adjustment_are_in_the_native_matrix_and_positions():
    font = own_placement_font()
    source, _ = own_pdf(font_program=font, commands=b'BT /F1 12 Tf 50 Tz 3 Ts 30 300 Td [(A) -200 (B)] TJ ET\n')
    with PdfDocument(source) as pdf:
        span, = pdf.page_text_placements(0)
    assert span.glyphs[0].transform == pytest.approx((6, 0, 0, -12, 30, 97), abs=.0001)
    assert span.glyphs[1].transform == pytest.approx((6, 0, 0, -12, 34.8, 97), abs=.0001)


def test_empty_space_outline_keeps_the_native_record_and_advance_position():
    source, _ = own_pdf(commands=b'BT /F1 12 Tf 30 300 Td (A B) Tj ET\n')
    with PdfDocument(source) as pdf:
        first, space, last = pdf.page_text_placements(0)[0].glyphs
    assert space.unicode == 32 and space.glyph_id >= 0
    assert space.glyph_bbox == (space.transform[4], space.transform[5], space.transform[4], space.transform[5])
    assert first.transform[4] < space.transform[4] < last.transform[4]


def test_callback_failure_does_not_escape_through_c_or_keep_borrowed_pages_alive(monkeypatch):
    import opendoc_formats.native.pdf_placements as native

    def broken(*args):
        raise LookupError('Own caller-side failure')

    with PdfDocument(own_source(rotation=b'/Rotate 90 ')) as pdf:
        before = tuple(pdf.iter_objects())
        with monkeypatch.context() as context:
            context.setattr(native, 'PdfPlacedGlyph', broken)
            with pytest.raises(LookupError, match='Own caller-side failure'):
                pdf.page_text_placements(0)
        assert tuple(pdf.iter_objects()) == before
        assert pdf.page_text_placements(0)


def test_nonfinite_matrix_is_refused_before_calling_native_glyph_bounds(monkeypatch):
    from types import SimpleNamespace

    def forbidden(*args):
        pytest.fail('Non-finite transform was passed back into the native bound calculation')

    monkeypatch.setattr(pymupdf.mupdf, 'fz_concat', lambda *args: SimpleNamespace(a=float('nan'), b=0, c=0, d=1, e=0, f=0))
    monkeypatch.setattr(pymupdf.mupdf, 'fz_bound_glyph', forbidden)
    with PdfDocument(own_source()) as pdf:
        with pytest.raises(InvalidDocumentError, match='Non-finite'):
            pdf.page_text_placements(0)


def test_unavailable_native_device_profile_is_explicit_and_restores_page_dictionary(monkeypatch):
    with PdfDocument(own_source(rotation=b'/Rotate 90 ')) as pdf:
        before = tuple(pdf.iter_objects())
        with monkeypatch.context() as context:
            context.delattr(pymupdf.mupdf, 'FzDevice2')
            with pytest.raises(UnsupportedDocumentError, match='profile unavailable'):
                pdf.page_text_placements(0)
        assert tuple(pdf.iter_objects()) == before
        assert pdf.page_text_placements(0)
