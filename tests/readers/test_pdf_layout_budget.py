"""Aggregate observation work across pages, independently of final Model quotas."""

import json
from dataclasses import replace
from threading import Event

import pymupdf
import pytest
from opendoc_model import (
    ArtifactLimitError,
    DocumentLimits,
    DocumentModel,
    IntegrationModel,
    Resource,
    ResourceKind,
    document_from_json,
    document_to_json,
    get_integration,
)

from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from opendoc_formats.native.pdf_placements import placement_budget, text_placements
from opendoc_formats.pdf import PdfLimits
from opendoc_formats.readers.pdf_layout_bindings import LogicalBindings
from opendoc_formats.readers.pdf_text_layout import capture_pdf_text_layouts
from tests.binary_fixtures import own_pdf, own_placement_font
from tests.native.test_pdf_placements import metadata_size


def original(pages=3, repeats=1):
    """Native editor duplicates page dictionaries with one shared FONT and content stream."""
    font = own_placement_font()
    data = own_pdf(font_program=font, commands=b'BT /F1 12 Tf 60 300 Td (' + b'ABC' * repeats + b') Tj ET\n')[0]
    with pymupdf.open(stream=data, filetype='pdf') as native:
        entries = [3]
        for _ in range(pages - 1):
            xref = native.get_new_xref()
            native.update_object(xref, native.xref_object(3))
            entries.append(xref)
        native.xref_set_key(2, 'Kids', '[' + ' '.join(f'{entry} 0 R' for entry in entries) + ']')
        native.xref_set_key(2, 'Count', str(pages))
        return native.tobytes(), font


def observations(native, limits, state=None):
    return tuple(text_placements(page, index, limits, None, include_bounds=False, _budget=state)
                 for index, page in enumerate(native))


@pytest.mark.parametrize('quota', ['max_text_spans', 'max_text_chars', 'max_text_metadata_bytes'])
def test_exact_native_work_budget_is_shared_across_pages(quota):
    source, _ = original()
    with pymupdf.open(stream=source, filetype='pdf') as native:
        baseline = observations(native, PdfLimits())
    bound = {'max_text_spans': 3, 'max_text_chars': 12,
             'max_text_metadata_bytes': sum(metadata_size(page) for page in baseline)}[quota]
    selected = replace(PdfLimits(), **{quota: bound})
    with pymupdf.open(stream=source, filetype='pdf') as native, placement_budget(selected) as state:
        assert observations(native, selected, state) == baseline
    selected = replace(selected, **{quota: bound - 1})
    with pymupdf.open(stream=source, filetype='pdf') as native, placement_budget(selected) as state:
        with pytest.raises(ResourceLimitError, match=quota):
            observations(native, selected, state)
    assert not state.fonts and state.owner is None
    # A later independent operation receives a new budget, not the failed counter state.
    with pymupdf.open(stream=source, filetype='pdf') as native:
        assert observations(native, PdfLimits()) == baseline


def test_shared_font_buffer_is_copied_once_and_released_before_document_close(monkeypatch):
    source, font = original()
    copied = []
    copy_buffer = pymupdf.mupdf.ll_fz_buffer_extract_copy
    def counted(buffer):
        payload = copy_buffer(buffer)
        copied.append(payload)
        return payload

    monkeypatch.setattr(pymupdf.mupdf, 'll_fz_buffer_extract_copy', counted)
    selected = PdfLimits(max_inspection_bytes=len(font), max_object_bytes=len(font))
    with pymupdf.open(stream=source, filetype='pdf') as native:
        with placement_budget(selected) as state:
            captured = observations(native, selected, state)
            assert len(captured) == 3 and copied == [font]
            assert state.font_bytes == len(font) and len(state.fonts) == 1
        assert not state.fonts and state.owner is None
        assert native.page_count == 3


def test_shared_state_refuses_changed_limits_and_another_document():
    source, _ = original()
    limits = PdfLimits()
    with pymupdf.open(stream=source, filetype='pdf') as first, pymupdf.open(stream=source, filetype='pdf') as second:
        with placement_budget(limits) as state:
            text_placements(first[0], 0, limits, None, _budget=state)
            before = state.spans, state.glyphs, state.metadata_bytes, state.font_bytes
            with pytest.raises(ValueError, match='unchanged limits'):
                text_placements(first[1], 1, replace(limits, max_text_chars=100), None, _budget=state)
            with pytest.raises(ValueError, match='another document'):
                text_placements(second[0], 0, limits, None, _budget=state)
            assert (state.spans, state.glyphs, state.metadata_bytes, state.font_bytes) == before
        with pytest.raises(ValueError, match='closed'):
            text_placements(first[1], 1, limits, None, _budget=state)


def style_cost(native):
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_MEDIABOX_CLIP & ~pymupdf.TEXT_PRESERVE_IMAGES
    return sum(len(json.dumps(span, ensure_ascii=False, allow_nan=False).encode('utf-8'))
               for page in native for block in page.get_text('dict', sort=False, flags=flags,
                    clip=pymupdf.INFINITE_RECT()).get('blocks', [])
               for line in block.get('lines', []) for span in line.get('spans', []))


def test_source_style_metadata_budget_is_shared_instead_of_reset_per_page():
    source, _ = original()
    document = DocumentModel()
    before = document_to_json(document)
    with pymupdf.open(stream=source, filetype='pdf') as native:
        exact = style_cost(native)
        for maximum in (exact, exact - 1):
            binding = LogicalBindings(document, IntegrationModel(), DocumentLimits(max_bytes=maximum), None)
            if maximum == exact:
                for page in native:
                    binding.read_source_styles(page, pymupdf)
                assert binding.source_style_nodes == 3 and binding.source_style_bytes == exact
            else:
                binding.read_source_styles(native[0], pymupdf)
                binding.read_source_styles(native[1], pymupdf)
                with pytest.raises(ArtifactLimitError) as error:
                    binding.read_source_styles(native[2], pymupdf)
                assert error.value.quota == 'bytes' and error.value.path == '$.text_layouts.source_styles'
    assert document_to_json(document) == before


def test_cancellation_before_style_decode_and_shared_font_cleanup():
    source, _ = original()
    event = Event()
    binding = LogicalBindings(DocumentModel(), IntegrationModel(), DocumentLimits(), event.is_set)
    with pymupdf.open(stream=source, filetype='pdf') as native:
        binding.read_source_styles(native[0], pymupdf)
        event.set()
        class ForbiddenPage:
            def get_text(self, *args, **kwargs):
                pytest.fail('Cancelled source style decoding started')

        with pytest.raises(OperationCancelledError):
            binding.read_source_styles(ForbiddenPage(), pymupdf)
        event.clear()
        with placement_budget(PdfLimits()) as state:
            text_placements(native[0], 0, PdfLimits(), None, _budget=state)
            event.set()
            with pytest.raises(OperationCancelledError):
                text_placements(native[1], 1, PdfLimits(), event.is_set, _budget=state)
        assert not state.fonts and state.owner is None


def test_production_capture_stops_at_aggregate_native_metadata_limit_before_model_batch(tmp_path, monkeypatch):
    import opendoc_formats.readers.pdf_text_layout as capture
    source, font = original(pages=8, repeats=4)
    path = tmp_path / 'own-pages.pdf'
    path.write_bytes(source)
    document = DocumentModel(resources={'font': Resource('font', ResourceKind.FONT, 'font/ttf', font)})
    before = document_to_json(document)
    with pymupdf.open(stream=source, filetype='pdf') as native:
        standalone = observations(native, PdfLimits())
    maximum = max(len(font), sum(metadata_size(page) for page in standalone[:4]))
    assert maximum < sum(metadata_size(page) for page in standalone)
    def forbidden(*args, **kwargs):
        pytest.fail('Final Model batch started after native work budget exhaustion')

    monkeypatch.setattr(capture, 'set_integration', forbidden)
    with pytest.raises(ArtifactLimitError) as error:
        capture_pdf_text_layouts(document, path, limits=DocumentLimits(max_bytes=maximum))
    assert error.value.quota == 'bytes'
    assert 'max_text_metadata_bytes' in str(error.value) and '$.text_layouts.page[' in error.value.path
    assert document_to_json(document) == before and path.read_bytes() == source


def test_generous_capture_retains_all_source_occurrences_through_two_json_cycles(tmp_path):
    source, font = original()
    path = tmp_path / 'own-pages.pdf'
    path.write_bytes(source)
    document = DocumentModel(resources={'font': Resource('font', ResourceKind.FONT, 'font/ttf', font)})
    result = capture_pdf_text_layouts(document, path)
    baseline = get_integration(result).text_layouts
    assert len(baseline) == 3 and {layout.page_id for layout in baseline} == {'pdf-page-1', 'pdf-page-2', 'pdf-page-3'}
    for _ in range(2):
        result = document_from_json(document_to_json(result))
        assert get_integration(result).text_layouts == baseline
    assert any(resource.data == source for resource in result.resources.values())
    assert path.read_bytes() == source
