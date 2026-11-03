"""Native media/crop regions, nonzero origins and exact viewport pixels."""

from dataclasses import replace

import pymupdf as fitz
import pytest
from opendoc_model import (
    Rect2D,
    document_from_json,
    document_to_json,
    get_integration,
    get_page_geometry,
    set_integration,
    with_page_geometry,
)

from opendoc_formats import read_document, write_document


def own_source(path, media, rotation, cropped=True, outline=False):
    with fitz.open() as pdf:
        page = pdf.new_page(width=300, height=400)
        page.set_mediabox(fitz.Rect(*media))
        image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 180), False)
        image.clear_with(128)
        image.set_pixel(10, 15, (255, 0, 0))
        image.set_pixel(50, 90, (0, 0, 255))
        page.insert_image(fitz.Rect(-10, -20, 310, 420), stream=image.tobytes("png"), keep_proportion=False)
        if cropped:
            page.set_cropbox(fitz.Rect(media[0]+20, 40, media[2]-20, 360))
        page.set_rotation(rotation)
        if outline:
            pdf.set_toc([[1, "Own point", 1, {"kind": fitz.LINK_GOTO, "page": 0, "to": fitz.Point(80, 120)}]])
        pdf.save(path)


def snapshot(path):
    with fitz.open(path) as pdf:
        return [(tuple(p.mediabox), tuple(p.cropbox), p.rotation, tuple(p.rect),
                 p.get_pixmap(alpha=False).samples) for p in pdf]


@pytest.mark.parametrize("media", [(0, 0, 300, 400), (36, 45, 336, 445), (-20, -30, 280, 370)])
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("cropped", [False, True])
def test_native_regions_and_pixels_survive_two_cycles(tmp_path, media, rotation, cropped):
    source = tmp_path / "own.pdf"
    own_source(source, media, rotation, cropped)
    original = source.read_bytes()
    expected = snapshot(source)
    current = source
    first_geometry = None
    for cycle in range(2):
        imported = read_document(current)
        assert imported.success, imported.issues
        model = document_from_json(document_to_json(imported.document))
        page = get_integration(model).pages[0]
        geometry = get_page_geometry(page)
        assert (page.width, page.height) == (300, 400)
        assert geometry.media_box == Rect2D(media[0], -media[3], 300, 400)
        if first_geometry is None:
            first_geometry = geometry
        else:
            assert geometry == first_geometry
        before = document_to_json(model)
        current = tmp_path / f"cycle-{cycle}.pdf"
        result = write_document(model, current)
        assert result.success, result.issues
        assert document_to_json(model) == before
        assert snapshot(current) == expected
    assert source.read_bytes() == original


def test_typed_crop_and_rotation_edit_has_native_precedence(tmp_path):
    source = tmp_path / "own.pdf"
    own_source(source, (36, 45, 336, 445), 90, outline=True)
    model = read_document(source).document
    integration = get_integration(model)
    page = integration.pages[0]
    geometry = get_page_geometry(page)
    edited = replace(geometry, crop_box=Rect2D(46, -415, 280, 350), rotation=270)
    set_integration(model, replace(integration, pages=(with_page_geometry(page, edited),)))
    transport = document_from_json(document_to_json(model))
    target = tmp_path / "edited.pdf"
    assert write_document(transport, target).success
    with fitz.open(source) as pdf:
        pdf[0].set_cropbox(fitz.Rect(46, 30, 326, 380))
        pdf[0].set_rotation(270)
        pdf.save(tmp_path / "reference.pdf")
    assert snapshot(target) == snapshot(tmp_path / "reference.pdf")
    with fitz.open(target) as pdf, fitz.open(tmp_path / "reference.pdf") as reference:
        assert tuple(pdf.get_toc(False)[0][3]["to"]) == tuple(reference.get_toc(False)[0][3]["to"])
    assert get_page_geometry(get_integration(read_document(target).document).pages[0]) == edited


def test_explicit_geometry_removal_does_not_restore_native_regions(tmp_path):
    source = tmp_path / "own.pdf"
    own_source(source, (36, 45, 336, 445), 90)
    model = read_document(source).document
    integration = get_integration(model)
    set_integration(model, replace(integration, pages=(with_page_geometry(integration.pages[0], None),)))
    transport = tmp_path / "removed.json"
    assert write_document(model, transport).success
    result = read_document(transport)
    assert result.success
    assert get_page_geometry(get_integration(result.document).pages[0]) is None
    target = tmp_path / "removed.pdf"
    assert write_document(result.document, target).success
    with fitz.open(target) as pdf:
        assert pdf[0].rotation == 0
        assert tuple(pdf[0].mediabox) == tuple(pdf[0].cropbox) == (0, 0, 260, 320)


def test_layout_links_keep_rectangles_and_local_destinations_after_native_translation(tmp_path):
    from opendoc_model import DocumentModel, DocumentPage, PageGeometry, Paragraph, Section, TextRun

    model = DocumentModel(sections=[Section(blocks=[
        Paragraph([TextRun("External", link="https://example.invalid/inert")]),
        Paragraph([TextRun("Internal", link="#own")]),
        Paragraph([TextRun("Target")], properties={"anchor_id": "own"}),
    ])])
    original = tmp_path / "flat.pdf"
    assert write_document(model, original).success
    model.sections[0].properties["pdf"] = {"page_id": "own-page", "crop_origin": [36, -850]}
    from opendoc_model import IntegrationModel

    geometry = PageGeometry(Rect2D(16, -890, 700, 1000), Rect2D(36, -850, 600, 850), rotation=0)
    page = with_page_geometry(DocumentPage("own-page", 700, 1000), geometry)
    set_integration(model, IntegrationModel(pages=(page,)))
    target = tmp_path / "translated.pdf"
    assert write_document(model, target).success
    with fitz.open(original) as a, fitz.open(target) as b:
        expected, actual = a[0].get_links(), b[0].get_links()
        assert len(expected) == len(actual) == 2
        for e, v in zip(expected, actual, strict=True):
            assert v["kind"] == e["kind"]
            assert tuple(v["from"]) == pytest.approx(tuple(e["from"]), abs=0.001)
            if v["kind"] == fitz.LINK_GOTO:
                assert tuple(v["to"]) == pytest.approx(tuple(e["to"]), abs=0.001)


def test_unknown_outline_point_is_not_invented_by_backend_default(tmp_path):
    from opendoc_model import Outline, OutlineEntry, OutlineTarget, get_outline, set_outline

    source = tmp_path / "own.pdf"
    own_source(source, (0, 0, 300, 400), 0)
    model = read_document(source).document
    set_outline(model, Outline(entries=(OutlineEntry("own", "Page only", 0,
                                                    target=OutlineTarget("page", target_id="pdf-page-1", zoom=1.25)),)))
    for cycle in range(2):
        target = tmp_path / f"unknown-{cycle}.pdf"
        assert write_document(model, target).success
        model = read_document(target).document
        destination = get_outline(model).entries[0].target
        assert destination.point is None and destination.zoom == 1.25


def test_unbound_geometry_has_located_loss_instead_of_silent_omission(tmp_path):
    from opendoc_model import DocumentModel, DocumentPage, IntegrationModel, PageGeometry, Paragraph, Section, TextRun

    model = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun("Own")])])])
    page = with_page_geometry(DocumentPage("unbound", 300, 400), PageGeometry(Rect2D(0, -400, 300, 400)))
    set_integration(model, IntegrationModel(pages=(page,)))
    report = write_document(model, tmp_path / "unbound.pdf")
    assert report.success
    assert any(issue.feature == "pdf.page-geometry" and issue.location == "pages[unbound]" for issue in report.issues)


def test_user_unit_retains_source_without_fabricating_shared_regions(tmp_path):
    source = tmp_path / "scaled.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page(width=300, height=400)
        page.insert_text((20, 40), "Own scaled page")
        pdf.xref_set_key(page.xref, "UserUnit", "2")
        pdf.save(source)
    result = read_document(source)
    assert result.success and not result.lossless
    integration = get_integration(result.document)
    assert (integration.pages[0].width, integration.pages[0].height) == (600, 800)
    assert get_page_geometry(integration.pages[0]) is None
    assert any(issue.code == "pdf.page-geometry" and issue.reason == "unsupported-user-unit" for issue in result.issues)
    assert result.document.resources["pdf-original-source"].data == source.read_bytes()
