"""Opt-in production PDF observations use Model DTOs without inventing logical mappings."""

from threading import Event

import pymupdf
import pytest
from opendoc_model import (
    ArtifactLimitError,
    DocumentLimits,
    DocumentModel,
    Resource,
    ResourceKind,
    document_from_json,
    document_to_json,
    get_integration,
    get_text_layout,
)

from opendoc_formats import ImportOptions, read_document, write_document
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError
from opendoc_formats.pdf import PdfDocument
from opendoc_formats.readers.pdf_model import read_pdf_model
from opendoc_formats.readers.pdf_text_layout import capture_pdf_text_layouts
from tests.binary_fixtures import own_pdf, own_placement_font


def fixture(tmp_path, *, rotation=0, crop=False, embedded=True):
    font = own_placement_font() if embedded else None
    data = own_pdf(font_program=font, parent_extra=f'/Rotate {rotation} '.encode(),
                   page_extra=b'/CropBox [20 30 280 370] ' if crop else b'',
                   commands=b'BT /F1 12 Tf 2 Tr 1 .25 .5 1 60 300 Tm (ABC) Tj ET\n')[0]
    path = tmp_path/'own.pdf'
    path.write_bytes(data)
    return path, data, font


@pytest.mark.parametrize('public', [False, True])
@pytest.mark.parametrize('rotation', [0, 90])
@pytest.mark.parametrize('crop', [False, True])
def test_native_occurrences_matrices_font_and_source_survive_two_json_cycles(tmp_path, public, rotation, crop):
    path, data, font = fixture(tmp_path, rotation=rotation, crop=crop)
    if public:
        result = read_document(path, options=ImportOptions(pdf_text_layouts=True))
        assert result.success, result.issues
        document = result.document
        assert any(issue.code == 'pdf.text-layout-observations' for issue in result.issues)
    else:
        document = read_pdf_model(path=path, capture_text_layouts=True)
    with PdfDocument(data) as native:
        observed = native.page_text_placements(0)
        pixels = native.render_page(0).png
    for _ in range(2):
        document = document_from_json(document_to_json(document))
        layouts = get_integration(document).text_layouts
        assert [value.extra['opendoc_formats.pdf_text_operation'] for value in layouts] == ['fill', 'stroke']
        for layout, occurrence in zip(layouts, observed, strict=True):
            assert get_text_layout(document, layout.id).state == 'unknown'
            assert layout.clusters == () and layout.binding_sha256 is None
            assert layout.page_id == 'pdf-page-1' and layout.fonts[0].face_index == 0
            assert document.resources[layout.fonts[0].resource_id].data == font
            assert [row[1] for row in layout.glyphs] == [1, 2, 3]
            assert [row[2:] for row in layout.glyphs] == [glyph.transform for glyph in occurrence.glyphs if glyph.glyph_id >= 0]
            assert layout.extra['opendoc_formats.pdf_native_glyph_indices'] == [0, 1, 2]
            assert layout.extra['opendoc_formats.pdf_native_records'] == 4
            assert layout.transform.e + layout.glyphs[0][6] == pytest.approx(60)
            assert layout.transform.f + layout.glyphs[0][7] == pytest.approx(-300)
            source = document.resources[layout.extra['opendoc_formats.pdf_source_resource_id']].data
            assert source == data
            with PdfDocument(source) as retained:
                assert retained.render_page(0).png == pixels
                assert retained.page_text_placements(0)[0].glyphs[-1].glyph_id == -1
    assert path.read_bytes() == data


def test_default_import_does_not_enable_observations_or_attach_an_extra_snapshot(tmp_path):
    path, _, _ = fixture(tmp_path)
    default = read_document(path).document
    explicit = read_document(path, options=ImportOptions(pdf_text_layouts=False)).document
    assert document_to_json(default) == document_to_json(explicit)
    assert not get_integration(default).text_layouts
    assert not any(key.startswith('pdf-text-layout-source') for key in default.resources)


def test_missing_embedded_font_stays_unknown_without_inventing_a_face_or_glyph_id(tmp_path):
    path, _, _ = fixture(tmp_path, embedded=False)
    result = read_document(path, options=ImportOptions(pdf_text_layouts=True))
    assert result.success, result.issues
    layouts = get_integration(result.document).text_layouts
    assert layouts and all(not value.fonts for value in layouts)
    assert all(row[:2] == (None, None) for value in layouts for row in value.glyphs)


@pytest.mark.parametrize('ambiguous', [False, True])
def test_known_program_unknown_face_and_ambiguous_resources_do_not_get_invented_ids(tmp_path, ambiguous):
    path, _, font = fixture(tmp_path)
    resources = {'font': Resource('font', ResourceKind.FONT, 'application/octet-stream', font)}
    if ambiguous:
        resources['other'] = Resource('other', ResourceKind.FONT, 'font/ttf', font)
    document = capture_pdf_text_layouts(DocumentModel(resources=resources), path)
    for layout in get_integration(document).text_layouts:
        assert layout.extra['opendoc_formats.pdf_font_binding'] == ('ambiguous' if ambiguous else 'face-unknown')
        assert all(row[1] is None for row in layout.glyphs)
        assert not layout.fonts if ambiguous else layout.fonts[0].face_index is None


def test_json_transport_works_and_unsupported_export_preserves_existing_file(tmp_path):
    path, _, _ = fixture(tmp_path)
    document = read_document(path, options=ImportOptions(pdf_text_layouts=True)).document
    target = tmp_path/'own.json'
    assert write_document(document, target).success
    restored = read_document(target)
    assert restored.success and get_integration(restored.document).text_layouts == get_integration(document).text_layouts
    target = tmp_path/'keep.pdf'
    target.write_bytes(b'Previous destination')
    report = write_document(restored.document, target)
    assert not report.success and any(issue.feature == 'export.text-layout' for issue in report.issues)
    assert target.read_bytes() == b'Previous destination'


@pytest.mark.parametrize('value', [0, 1, None, 'yes', [], {}])
def test_capture_options_require_real_booleans(value, tmp_path):
    with pytest.raises(ValueError, match='pdf_text_layouts'):
        ImportOptions(pdf_text_layouts=value)
    with pytest.raises(ValueError, match='capture_text_layouts'):
        read_pdf_model(path=tmp_path/'absent.pdf', capture_text_layouts=value)


def test_source_budget_failure_before_native_capture_is_atomic(tmp_path, monkeypatch):
    import opendoc_formats.readers.pdf_text_layout as capture

    path, data, font = fixture(tmp_path)
    document = DocumentModel(resources={'font': Resource('font', ResourceKind.FONT, 'font/ttf', font)})
    before = document_to_json(document)

    def forbidden(*args, **kwargs):
        pytest.fail('Native capture started before source snapshot budget')

    monkeypatch.setattr(capture, 'text_placements', forbidden)
    with pytest.raises(ArtifactLimitError) as error:
        capture_pdf_text_layouts(document, path, limits=DocumentLimits(max_embedded_bytes=len(data)-1))
    assert error.value.quota == 'embedded bytes'
    assert document_to_json(document) == before and path.read_bytes() == data


@pytest.mark.parametrize('budget,quota', [(DocumentLimits(max_bytes=1), 'bytes'), (DocumentLimits(max_nodes=3), 'nodes')])
def test_native_observation_budget_failure_is_located_and_atomic(tmp_path, budget, quota):
    path, _, font = fixture(tmp_path)
    document = DocumentModel(resources={'font': Resource('font', ResourceKind.FONT, 'font/ttf', font)})
    before = document_to_json(document)
    with pytest.raises(ArtifactLimitError) as error:
        capture_pdf_text_layouts(document, path, limits=budget)
    assert error.value.quota == quota and error.value.path
    assert document_to_json(document) == before


def test_late_cancellation_after_model_batch_is_atomic(tmp_path, monkeypatch):
    import opendoc_formats.readers.pdf_text_layout as capture

    path, _, _ = fixture(tmp_path)
    document = read_document(path).document
    before, stop = document_to_json(document), Event()
    original = capture.set_text_layouts

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        stop.set()

    monkeypatch.setattr(capture, 'set_text_layouts', interrupted)
    with pytest.raises(OperationCancelledError):
        capture_pdf_text_layouts(document, path, cancelled=stop.is_set)
    assert stop.is_set() and document_to_json(document) == before


def test_mismatched_source_page_geometry_is_not_silently_associated(tmp_path):
    path, _, _ = fixture(tmp_path)
    document = read_document(path).document
    before = document_to_json(document)
    other = tmp_path/'other.pdf'
    other.write_bytes(own_pdf(page_extra=b'/CropBox [20 30 280 370] ')[0])
    with pytest.raises(InvalidDocumentError, match='geometry differs'):
        capture_pdf_text_layouts(document, other)
    assert document_to_json(document) == before


def test_repeated_capture_reuses_source_and_existing_page_registry(tmp_path):
    path, _, _ = fixture(tmp_path)
    document = read_document(path, options=ImportOptions(pdf_text_layouts=True)).document
    restored = capture_pdf_text_layouts(document, path)
    assert len(get_integration(restored).pages) == len(get_integration(document).pages) == 1
    assert len(get_integration(restored).text_layouts) == len(get_integration(document).text_layouts) == 2
    assert set(restored.resources) == set(document.resources)
    assert document_to_json(restored) == document_to_json(document)


def test_raw_glyph_budget_is_aggregate_across_pages(tmp_path):
    path, data, font = fixture(tmp_path)
    with pymupdf.open(stream=data, filetype='pdf') as source:
        with pymupdf.open() as target:
            for _ in range(16):
                target.insert_pdf(source)
            target.save(path)
    document = DocumentModel(resources={'font': Resource('font', ResourceKind.FONT, 'font/ttf', font)})
    before = document_to_json(document)
    with pytest.raises(ArtifactLimitError) as error:
        capture_pdf_text_layouts(document, path, limits=DocumentLimits(max_nodes=50))
    assert error.value.quota == 'nodes' and error.value.path == '$.text_layouts'
    assert document_to_json(document) == before


def test_userunit_keeps_native_local_coordinates_without_guessing_page_transform(tmp_path):
    data = own_pdf(page_extra=b'/UserUnit 2 ', font_program=own_placement_font(),
                   commands=b'BT /F1 12 Tf 60 300 Td (ABC) Tj ET\n')[0]
    path = tmp_path/'unit.pdf'
    path.write_bytes(data)
    result = read_document(path, options=ImportOptions(pdf_text_layouts=True))
    assert result.success, result.issues
    layouts = get_integration(result.document).text_layouts
    assert layouts and all(layout.page_id is None and layout.state == 'unknown' for layout in layouts)
    with PdfDocument(data) as native:
        expected = native.page_text_placements(0)
    assert layouts[0].glyphs[0][2:] == expected[0].glyphs[0].transform


def test_otf_cff_uses_proven_container_face_without_fonttools(tmp_path, monkeypatch):
    import builtins

    from tests.writers.test_pdf_resource_fonts import FIXTURE, model

    source = (FIXTURE.parent/'own-cff.otf').read_bytes()
    path = tmp_path/'cff.pdf'
    assert write_document(model(source, text='AB', media='font/otf'), path).success
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name == 'fontTools' or name.startswith('fontTools.'):
            pytest.fail('CFF layout capture imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    result = read_document(path, options=ImportOptions(pdf_text_layouts=True))
    assert result.success, result.issues
    layout = get_integration(result.document).text_layouts[0]
    assert layout.fonts[0].face_index == 0 and [row[1] for row in layout.glyphs] == [1, 2]
    assert result.document.resources[layout.fonts[0].resource_id].data == source


def test_all_native_text_operations_remain_separate_with_only_proven_logical_bindings(tmp_path):
    commands = b''.join(b'q BT /F1 12 Tf '+str(mode).encode()+b' Tr 30 '+str(350-mode*30).encode()+
                        b' Td (AB) Tj ET Q\n' for mode in range(8))
    data = own_pdf(font_program=own_placement_font(), commands=commands)[0]
    path = tmp_path/'modes.pdf'
    path.write_bytes(data)
    result = read_document(path, options=ImportOptions(pdf_text_layouts=True))
    assert result.success, result.issues
    layouts = get_integration(result.document).text_layouts
    assert [layout.extra['opendoc_formats.pdf_text_operation'] for layout in layouts] == [
        'fill', 'stroke', 'fill', 'stroke', 'ignore', 'fill', 'clip', 'stroke', 'clip', 'fill', 'stroke', 'clip', 'clip',
    ]
    assert any(layout.state == 'verified' for layout in layouts)
    assert any(layout.state == 'unknown' for layout in layouts)
    assert all(layout.clusters if layout.state == 'verified' else not layout.clusters for layout in layouts)
