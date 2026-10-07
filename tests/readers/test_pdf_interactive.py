"""Own PDF links, annotations, widgets and opaque catalog acceptance fixtures."""

import fitz
import pytest
from opendoc_model import document_from_json, document_to_json, get_integration

from opendoc_formats import read_document, write_document


def _source(path, *, rotation=0):
    with fitz.open() as pdf:
        pdf.new_page(width=300, height=400)
        pdf.new_page(width=300, height=400)
        page = pdf[0]
        page.insert_text((20, 30), "Hello PDF")
        page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(20, 40, 120, 55), "uri": "https://example.invalid/inert"})
        page.insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(20, 60, 120, 75), "page": 1, "to": fitz.Point(10, 20)})
        note = page.add_text_annot((20, 90), "Own note")
        note.set_info(title="Fixture author", subject="Own subject")
        highlight = page.add_highlight_annot(page.search_for("Hello"))
        highlight.set_info(content="Own highlight")
        page.add_rect_annot(fitz.Rect(170, 40, 210, 80))
        text = fitz.Widget()
        text.field_type, text.field_name, text.field_value = fitz.PDF_WIDGET_TYPE_TEXT, "own-text", "Value 0"
        text.rect = fitz.Rect(20, 140, 140, 160)
        text.script = "throw new Error('fixture action must remain inert');"
        page.add_widget(text)
        choice = fitz.Widget()
        choice.field_type, choice.field_name = fitz.PDF_WIDGET_TYPE_COMBOBOX, "own-choice"
        choice.choice_values, choice.field_value = ["Red", "Blue"], "Blue"
        choice.rect = fitz.Rect(20, 180, 140, 200)
        page.add_widget(choice)
        checkbox = fitz.Widget()
        checkbox.field_type, checkbox.field_name = fitz.PDF_WIDGET_TYPE_CHECKBOX, "own-check"
        checkbox.rect = fitz.Rect(20, 220, 40, 240)
        page.add_widget(checkbox)
        page.set_rotation(rotation)
        pdf.set_toc([[1, "Own chapter", 2]])
        pdf.save(path)


@pytest.mark.parametrize("rotation", [0, 90])
def test_pdf_interactions_and_inert_actions_survive_json(tmp_path, rotation):
    source = tmp_path / "interactive.pdf"
    _source(source, rotation=rotation)
    result = read_document(source)
    assert result.success and not result.lossless and not result.assessment_complete
    model = result.document
    ledger = get_integration(model)
    assert len(ledger.pages) == 2 and ledger.pages[0].width == 300 and ledger.pages[0].height == 400
    assert ledger.pages[0].extra["pdf_rotation"] == rotation
    assert {item.kind for item in ledger.annotations} == {"note", "highlight", "link"}
    assert {item.target for item in ledger.annotations if item.kind == "link"} == {
        "https://example.invalid/inert",
        "#pdf-page-2",
    }
    note = next(item for item in ledger.annotations if item.kind == "note")
    assert note.text == "Own note" and note.extra["info"]["title"] == "Fixture author"
    assert next(item for item in ledger.annotations if item.kind == "highlight").extra["vertices"]
    assert {item.kind for item in ledger.forms} == {"text", "choice", "checkbox"}
    text = next(item for item in ledger.forms if item.kind == "text")
    assert text.value == "Value 0" and text.extra["field_name"] == "own-text"
    assert text.action["script"] == "throw new Error('fixture action must remain inert');"
    assert next(item for item in ledger.forms if item.kind == "choice").choices == ("Red", "Blue")
    assert ledger.extra["pdf_outline"][0][:3] == [1, "Own chapter", 2]
    assert model.resources[ledger.extra["pdf_source_resource_id"]].data == source.read_bytes()
    assert any(item.state.value == "opaque" and item.issue.reason == "unsupported-annotation" for item in ledger.preservation)
    with fitz.open(source) as pdf:
        assert all(int(item.provenance.object_id.removeprefix("xref-")) < pdf.xref_length() for item in ledger.preservation)
    restored = document_from_json(document_to_json(model))
    assert get_integration(restored) == ledger
    transport = tmp_path / "transport.json"
    transport.write_text(document_to_json(restored), encoding="utf-8")
    assert read_document(transport).issues == result.issues
    output = tmp_path / "layout.pdf"
    report = write_document(restored, output)
    assert report.success and not report.lossless
    assert {issue.feature for issue in report.issues} >= {"pdf.annotations", "pdf.forms", "pdf.outline", "pdf.annotation"}
    with fitz.open(output) as pdf:
        assert not list(pdf[0].widgets() or ()) and not list(pdf[0].annots() or ())
        assert pdf[0].rotation == rotation
        assert pdf[0].rect.width == (400 if rotation else 300)


def test_pdf_catalog_structure_and_layers_are_opaque_without_reading_order_claim(tmp_path):
    source = tmp_path / "catalog.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((20, 30), "Own catalog fixture")
        root = pdf.get_new_xref()
        pdf.update_object(root, "<< /Type /StructTreeRoot /K [] >>")
        pdf.xref_set_key(pdf.pdf_catalog(), "StructTreeRoot", f"{root} 0 R")
        pdf.add_ocg("Own layer")
        pdf.xref_set_key(pdf.pdf_catalog(), "OpenAction", "<< /S /JavaScript /JS (fixture inert) >>")
        pdf.save(source)
    result = read_document(source)
    ledger = get_integration(result.document)
    assert {item.issue.reason for item in ledger.preservation} >= {
        "unsupported-StructTreeRoot",
        "unsupported-OCProperties",
        "unsupported-OpenAction",
    }
    assert all(item.state.value == "opaque" for item in ledger.preservation)
    assert all(not page.reading_order for page in ledger.pages)
    assert result.document.resources[ledger.extra["pdf_source_resource_id"]].data == source.read_bytes()


def test_unsupported_signature_and_profile_limits_do_not_fake_semantics(tmp_path, monkeypatch):
    from opendoc_model import DocumentModel

    from opendoc_formats.readers import pdf_interactive

    source = tmp_path / "signature.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        widget = fitz.Widget()
        widget.field_type, widget.field_name = fitz.PDF_WIDGET_TYPE_SIGNATURE, "own-unsigned-signature"
        widget.rect = fitz.Rect(20, 30, 120, 50)
        page.add_widget(widget)
        pdf.save(source)
    result = read_document(source)
    ledger = get_integration(result.document)
    assert not ledger.forms
    assert any(item.state.value == "opaque" and item.issue.reason == "unsupported-form" for item in ledger.preservation)
    monkeypatch.setattr(pdf_interactive, "MAX_SOURCE_BYTES", 1)
    with pytest.raises(ValueError, match="snapshot limit"):
        pdf_interactive.attach_pdf_interactions(DocumentModel(), source)
    monkeypatch.setattr(pdf_interactive, "MAX_SOURCE_BYTES", 10 * 1024 * 1024)
    monkeypatch.setattr(pdf_interactive, "MAX_OBJECTS", 0)
    with pytest.raises(ValueError, match="objects exceed"):
        pdf_interactive.attach_pdf_interactions(DocumentModel(), source)
