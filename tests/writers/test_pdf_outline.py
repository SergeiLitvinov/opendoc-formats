"""Native outline hierarchy, inert destinations, edits and old JSON migration."""

from dataclasses import replace

import pymupdf as fitz
import pytest
from opendoc_model import (
    DocumentModel,
    Outline,
    OutlineEntry,
    OutlineTarget,
    Paragraph,
    Section,
    TextRun,
    document_from_json,
    document_to_json,
    get_integration,
    get_outline,
    set_integration,
    set_outline,
)

from opendoc_formats import read_document, write_document


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("cropped", [False, True])
def test_native_outline_destinations_survive_two_pdf_json_cycles(tmp_path, rotation, cropped):
    source = tmp_path / "own.pdf"
    with fitz.open() as pdf:
        pdf.new_page(width=300, height=400)
        pdf.new_page(width=300, height=400)
        for page in pdf:
            if cropped:
                page.set_cropbox(fitz.Rect(20, 40, 280, 360))
            page.set_rotation(rotation)
        pdf.set_toc([
            [1, "Root", 1, {"kind": fitz.LINK_GOTO, "page": 0, "to": fitz.Point(60, 80), "zoom": 1.25}],
            [2, "Child", 2, {"kind": fitz.LINK_GOTO, "page": 1, "to": fitz.Point(70, 90), "bold": True}],
            [2, "External", -1, {"kind": fitz.LINK_URI, "uri": "https://example.invalid/inert"}],
            [1, "Unknown", -1, {"kind": fitz.LINK_NONE}],
        ], collapse=0)
        pdf.save(source)
        expected = pdf.get_toc(False)
    original = source.read_bytes()
    current = source
    for cycle in range(2):
        imported = read_document(current)
        assert imported.success, imported.issues
        model = document_from_json(document_to_json(imported.document))
        outline = get_outline(model)
        assert [entry.title for entry in outline.entries] == ["Root", "Child", "External", "Unknown"]
        assert outline.entries[1].parent_id == outline.entries[0].id
        assert outline.entries[2].target.uri == "https://example.invalid/inert"
        assert outline.entries[3].target is None
        before = document_to_json(model)
        current = tmp_path / f"cycle-{cycle}.pdf"
        report = write_document(model, current)
        assert report.success, report.issues
        assert report.metrics["pdf_outline"]["entries"] == 4
        assert document_to_json(model) == before
        with fitz.open(current) as result:
            actual = result.get_toc(False)
            assert [entry[:3] for entry in actual] == [entry[:3] for entry in expected]
            for actual_entry, expected_entry in zip(actual, expected, strict=True):
                a, e = actual_entry[3], expected_entry[3]
                assert a["kind"] == e["kind"]
                if a["kind"] == fitz.LINK_GOTO:
                    assert tuple(a["to"]) == pytest.approx(tuple(e["to"]), abs=0.001)
                    assert a.get("zoom", 0) == e.get("zoom", 0)
                if a["kind"] == fitz.LINK_URI:
                    assert a["uri"] == e["uri"]
            assert actual[1][3]["bold"] is True
    assert source.read_bytes() == original


def test_outline_anchor_uses_actual_later_page_and_explicit_removal(tmp_path):
    model = DocumentModel(sections=[Section(blocks=[
        *[Paragraph([TextRun("Own paragraph " * 12)]) for _ in range(45)],
        Paragraph([TextRun("Target")], properties={"anchor_id": "own-target"}),
    ])])
    from opendoc_model import Anchor, set_anchor

    set_anchor(model.sections[0].blocks[45], Anchor("own-target"))
    set_outline(model, Outline(entries=(OutlineEntry("root", "Target", 0,
                                                    target=OutlineTarget("anchor", target_id="own-target")),)))
    result = tmp_path / "anchor.pdf"
    report = write_document(model, result)
    assert report.success, report.issues
    with fitz.open(result) as pdf:
        destination = pdf.get_toc(False)[0][3]
        assert destination["page"] > 0
        assert "Target" in pdf[destination["page"]].get_text()
    set_outline(model, None)
    assert write_document(model, result).success
    with fitz.open(result) as pdf:
        assert pdf.get_toc() == []


def test_legacy_native_outline_migrates_once_and_does_not_resurrect(tmp_path):
    from opendoc_model import DocumentPage, IntegrationModel, Provenance

    model = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun("Own")])], properties={"pdf": {}},
                                          provenance=Provenance("pdf", "own.pdf", page=1))])
    set_integration(model, IntegrationModel(pages=(DocumentPage("pdf-page-1", 300, 400),), extra={
        "pdf_outline": [[1, "Old", 1, {"kind": 1, "page": 0, "to": [60, 80]}]],
    }))
    transport = tmp_path / "old.json"
    transport.write_text(document_to_json(model), encoding="utf-8")
    old_bytes = transport.read_bytes()
    result = read_document(transport)
    assert result.success, result.issues
    migrated = result.document
    assert get_outline(migrated).entries[0].target.target_id == "pdf-page-1"
    assert get_outline(migrated).entries[0].target.point is None  # Unknown legacy crop origin.
    assert migrated.sections[0].properties["pdf"]["page_id"] == "pdf-page-1"
    assert transport.read_bytes() == old_bytes
    original = get_outline(migrated)
    set_outline(migrated, replace(original, entries=(replace(original.entries[0], title="Edited"),)))
    assert get_outline(migrated).entries[0].title == "Edited"
    set_outline(migrated, None)
    transport.write_text(document_to_json(migrated), encoding="utf-8")
    assert get_outline(read_document(transport).document) is None
    assert get_integration(migrated).extra["pdf_outline"][0][1] == "Old"


@pytest.mark.parametrize("uri", ["javascript:fixture_inert()", "https://["])
def test_unsupported_uri_remains_untargeted_with_located_loss(tmp_path, uri):
    model = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun("Own")])])])
    set_outline(model, Outline(entries=(OutlineEntry("own", "Inert", 0, target=OutlineTarget("external", uri=uri)),)))
    target = tmp_path / "inert.pdf"
    report = write_document(model, target)
    assert report.success
    assert any(issue.feature == "pdf.outline-target" and issue.location == "outline.entries[own]" for issue in report.issues)
    with fitz.open(target) as pdf:
        assert pdf.get_toc(False)[0][3]["kind"] == fitz.LINK_NONE


def test_ambiguous_source_page_id_is_not_guessed_after_composition(tmp_path):
    from opendoc_model import DocumentPage, IntegrationModel

    model = DocumentModel(sections=[
        Section(blocks=[Paragraph([TextRun("First")])], properties={"pdf": {"page_id": "own-page"}}),
        Section(blocks=[Paragraph([TextRun("Second")])], properties={"pdf": {"page_id": "own-page"}}),
    ])
    set_integration(model, IntegrationModel(pages=(DocumentPage("own-page", 300, 400),)))
    set_outline(model, Outline(entries=(OutlineEntry("own", "Ambiguous", 0,
                                                    target=OutlineTarget("page", target_id="own-page")),)))
    target = tmp_path / "composed.pdf"
    report = write_document(model, target)
    assert report.success
    assert any(issue.feature == "pdf.outline-target" for issue in report.issues)
    with fitz.open(target) as pdf:
        assert pdf.page_count == 2
        assert pdf.get_toc(False)[0][3]["kind"] == fitz.LINK_NONE
