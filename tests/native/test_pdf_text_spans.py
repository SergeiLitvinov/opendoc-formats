"""Native glyph evidence is independent of plain-text reconstruction and does not modify the source."""

import copy
import json
from dataclasses import FrozenInstanceError
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
from tests.binary_fixtures import own_pdf

COMMANDS = (
    b'q BT /F1 12 Tf 0 Tr 30 350 Td (Visible) Tj ET Q\n'
    b'q BT /F1 12 Tf 2 Tr 30 320 Td (Both) Tj ET Q\n'
    b'q BT /F1 12 Tf 3 Tr 30 290 Td (Hidden) Tj ET Q\n'
    b'q /Zero gs BT /F1 12 Tf 0 Tr 30 260 Td (Zero) Tj ET Q\n'
    b'q 30 185 15 25 re W n BT /F1 12 Tf 0 Tr 30 200 Td (Partial) Tj ET Q\n'
)
RESOURCES = b'/ExtGState << /Zero << /ca 0 /CA 0 >> >> '


def raw_trace():
    return {'seqno': 0, 'type': 0, 'font': 'Own font', 'size': 12.0, 'bbox': [10, 20, 30, 32],
            'dir': [1, 0], 'opacity': 1.0, 'flags': 0, 'layer': '', 'color': [0, 0, 0], 'linewidth': None,
            'chars': [[65, 1, [10, 30], [10, 20, 20, 32]], [66, 2, [20, 30], [20, 20, 30, 32]]]}


@pytest.mark.parametrize('rotation', [0, 90])
def test_direct_pdf_commands_preserve_hidden_stroke_alpha_clip_and_unrotated_glyphs(tmp_path, rotation):
    data, _ = own_pdf(commands=COMMANDS, page_extra=f'/Rotate {rotation} '.encode(), resource_extra=RESOURCES)
    source = tmp_path/'original.pdf'
    source.write_bytes(data)
    with PdfDocument(source, limits=PdfLimits(cache_bytes=0)) as pdf:
        before = pdf.render_page(0, dpi=72)
        spans = pdf.page_text_spans(0)
        after = pdf.render_page(0, dpi=72)
        assert before.png == after.png  # disabled cache forces a fresh native render
        assert all(span.page_index == 0 and span.span_index == index for index, span in enumerate(spans))
        assert [span.paint_type for span in spans if span.text == 'Both'] == [0, 1]
        assert next(span for span in spans if span.text == 'Hidden').paint_type == 3
        assert next(span for span in spans if span.text == 'Zero').opacity == 0
        assert next(span for span in spans if span.text == 'Partial').text == 'Partial'
        first = spans[0]
        assert first.text == 'Visible' and first.font_size == 12 and first.font == 'Helvetica'
        assert first.glyphs[0].unicode == ord('V') and first.glyphs[0].glyph_id >= 0
        assert first.glyphs[0].origin == (30, 50)
        assert dict(first.metadata)['flags'] == 0
        with pytest.raises(FrozenInstanceError):
            first.opacity = 0
    assert first.text == 'Visible' and source.read_bytes() == data
    with pytest.raises(DocumentClosedError):
        pdf.page_text_spans(0)


def test_copies_detach_all_mutable_backend_arrays(monkeypatch):
    raw = raw_trace()
    monkeypatch.setattr(pymupdf.Page, 'get_texttrace', lambda self: [raw])
    with PdfDocument(own_pdf()[0]) as pdf:
        span = pdf.page_text_spans(0)[0]
    raw['chars'][0][2][0] = 999
    raw['color'][0] = 1
    assert span.text == 'AB' and span.glyphs[0].origin == (10, 30)
    assert dict(span.metadata)['color'] == (0, 0, 0)
    assert dict(span.metadata)['linewidth'] is None


def test_image_only_source_has_no_native_glyph_observations():
    source, _ = own_pdf(commands=b'q 20 0 0 20 40 80 cm /Im1 Do Q\n')
    with PdfDocument(source) as pdf:
        assert pdf.page_text_spans(0) == ()
        assert pdf.page_info(0).text == ''


@pytest.mark.parametrize('failure', [False, True])
def test_inherited_rotation_and_native_page_dictionary_are_restored_even_after_backend_failure(monkeypatch, failure):
    source, _ = own_pdf(parent_extra=b'/Rotate 90 ')
    if failure:
        def failed(page):
            page.set_rotation(0)
            raise RuntimeError('Own native failure after temporary rotation')

        monkeypatch.setattr(pymupdf.Page, 'get_texttrace', failed)
    with PdfDocument(source, limits=PdfLimits(cache_bytes=0)) as pdf:
        before = tuple(pdf.iter_objects())
        raster = pdf.render_page(0, dpi=72)
        if failure:
            with pytest.raises(InvalidDocumentError, match='Own native failure'):
                pdf.page_text_spans(0)
        else:
            assert pdf.page_text_spans(0)[0].text == 'Before'
        assert pdf.page_info(0).rotation == 90
        assert tuple(pdf.iter_objects()) == before
        assert pdf.render_page(0, dpi=72).png == raster.png


@pytest.mark.parametrize('unicode,glyph_id,text', [
    (ord('i'), -1, 'Ai'), (-1, -1, None), (0xd800, 1, None), (0xfffd, 2, 'A\ufffd'),
])
def test_raw_unicode_unknowns_and_ligature_continuations_are_not_guessed(monkeypatch, unicode, glyph_id, text):
    raw = raw_trace()
    raw['chars'][1] = [unicode, glyph_id, [20, 30], [20, 20, 20, 32]]
    monkeypatch.setattr(pymupdf.Page, 'get_texttrace', lambda self: [raw])
    with PdfDocument(own_pdf()[0]) as pdf:
        span = pdf.page_text_spans(0)[0]
    assert span.text == text and span.glyphs[1].unicode == unicode and span.glyphs[1].glyph_id == glyph_id
    assert span.glyphs[1].bbox == (20, 20, 20, 32)


@pytest.mark.parametrize('limits', [PdfLimits(max_text_spans=1), PdfLimits(max_text_chars=3),
                                   PdfLimits(max_text_metadata_bytes=1)])
def test_quotas_apply_to_the_complete_page_before_returning_any_snapshot(monkeypatch, limits):
    raw = [raw_trace(), raw_trace()]
    original = copy.deepcopy(raw)
    monkeypatch.setattr(pymupdf.Page, 'get_texttrace', lambda self: raw)
    with PdfDocument(own_pdf()[0], limits=limits) as pdf:
        with pytest.raises(ResourceLimitError):
            pdf.page_text_spans(0)
    assert raw == original


def test_metadata_budget_is_exact_compact_json_and_stops_before_copying_another_value(monkeypatch):
    raw = raw_trace()
    metadata = {key: value for key, value in raw.items() if key != 'chars'}
    size = len(json.dumps(metadata, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode())
    monkeypatch.setattr(pymupdf.Page, 'get_texttrace', lambda self: [raw])
    with PdfDocument(own_pdf()[0], limits=PdfLimits(max_text_metadata_bytes=size)) as pdf:
        assert pdf.page_text_spans(0)[0].text == 'AB'
    with PdfDocument(own_pdf()[0], limits=PdfLimits(max_text_metadata_bytes=size-1)) as pdf:
        with pytest.raises(ResourceLimitError, match='max_text_metadata_bytes'):
            pdf.page_text_spans(0)

    class GuardedValues(list):
        def __iter__(self):
            yield 'A'*32
            yield 'B'*32
            pytest.fail('Metadata copy continued after exceeding its budget')

    raw['own'] = GuardedValues(['A'*32, 'B'*32, 'C'*32])
    with PdfDocument(own_pdf()[0], limits=PdfLimits(max_text_metadata_bytes=size+45)) as pdf:
        with pytest.raises(ResourceLimitError):
            pdf.page_text_spans(0)


@pytest.mark.parametrize('change,error', [
    ('nan', InvalidDocumentError), ('reversed', InvalidDocumentError), ('bool-codepoint', InvalidDocumentError),
    ('missing', InvalidDocumentError), ('nested-metadata', UnsupportedDocumentError),
])
def test_invalid_or_unsupported_backend_shapes_have_explicit_errors(monkeypatch, change, error):
    raw = raw_trace()
    if change == 'nan':
        raw['chars'][0][2][0] = float('nan')
    elif change == 'reversed':
        raw['bbox'] = [20, 20, 10, 32]
    elif change == 'bool-codepoint':
        raw['chars'][0][0] = True
    elif change == 'missing':
        del raw['seqno']
    else:
        raw['own'] = {'nested': 'unsupported'}
    monkeypatch.setattr(pymupdf.Page, 'get_texttrace', lambda self: [raw])
    with PdfDocument(own_pdf()[0]) as pdf, pytest.raises(error):
        pdf.page_text_spans(0)


def test_cancel_inside_glyph_copy_leaves_source_and_context_reusable(monkeypatch):
    import opendoc_formats.pdf as public

    stop, calls = Event(), []
    construct = public.PdfGlyphInfo

    def first(*args):
        assert not calls, 'Another glyph was copied after cancellation'
        result = construct(*args)
        calls.append(True)
        stop.set()
        return result

    source = own_pdf()[0]
    with PdfDocument(source, cancelled=stop.is_set) as pdf:
        with monkeypatch.context() as context:
            context.setattr(public, 'PdfGlyphInfo', first)
            with pytest.raises(OperationCancelledError):
                pdf.page_text_spans(0)
        stop.clear()
        assert pdf.page_text_spans(0)[0].text == 'Before'
    assert calls == [True]


def test_cancel_after_native_call_and_invalid_page_do_not_return_partial_results(monkeypatch):
    stop, calls = Event(), []

    def native(self):
        calls.append(True)
        stop.set()
        return [raw_trace()]

    monkeypatch.setattr(pymupdf.Page, 'get_texttrace', native)
    with PdfDocument(own_pdf()[0], cancelled=stop.is_set) as pdf:
        with pytest.raises(PageIndexError):
            pdf.page_text_spans(1)
        with pytest.raises(OperationCancelledError):
            pdf.page_text_spans(0)
    assert calls == [True]


def test_page_dictionary_budget_is_checked_before_native_text_extraction(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Text extraction ran after its page-state budget was exceeded')

    monkeypatch.setattr(pymupdf.Page, 'get_texttrace', forbidden)
    monkeypatch.setattr(pymupdf.Page, 'get_text', forbidden)
    with PdfDocument(own_pdf()[0], limits=PdfLimits(max_object_bytes=1)) as pdf:
        for inspect in (pdf.page_info, pdf.page_text_spans):
            with pytest.raises(ResourceLimitError, match='max_object_bytes'):
                inspect(0)
