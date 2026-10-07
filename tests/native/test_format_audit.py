"""Finite evidence for inherited format requests: fallback JSON and transparent PDF paint."""

import io
from pathlib import Path

import pymupdf
from opendoc_model import (
    Box,
    DocumentModel,
    Image,
    Paragraph,
    Resource,
    ResourceKind,
    Section,
    document_from_json,
    document_to_json,
)
from PIL import Image as PillowImage

from opendoc_formats import read_document, write_document
from opendoc_formats.pdf import PdfDocument
from opendoc_formats.readers.docx import read_docx_model
from opendoc_formats.readers.pdf_images import extract_pdf_vector_drawings
from opendoc_formats.writers.docx_writer import write_docx_model


def test_office_svg_surrogate_ids_reason_and_provenance_survive_json_and_export(tmp_path):
    png = io.BytesIO()
    PillowImage.new("RGB", (12, 8), "blue").save(png, format="PNG")
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="8"><rect width="12" height="8" fill="blue"/></svg>'
    source = DocumentModel(
        resources={
            "source": Resource("source", ResourceKind.VECTOR_IMAGE, "image/svg+xml", data=svg),
            "preview": Resource("preview", ResourceKind.RASTER_IMAGE, "image/png", data=png.getvalue()),
        },
        sections=[
            Section(
                blocks=[
                    Paragraph(content=[Image("source", box=Box(0, 0, 12, 8), properties={"fallback_resource_id": "preview"})])
                ]
            )
        ],
    )
    first = tmp_path / "source.docx"
    assert write_docx_model(source, first).success
    imported = read_docx_model(first)
    image = imported.sections[0].blocks[0].content[0]
    surrogate = image.visual_surrogate
    assert surrogate and surrogate.reason
    assert any(event.fallback_reason == surrogate.reason for event in image.provenance.events)
    restored = document_from_json(document_to_json(imported))
    restored_image = restored.sections[0].blocks[0].content[0]
    assert restored_image.visual_surrogate == surrogate
    assert restored_image.provenance == image.provenance
    assert restored.resources[surrogate.resource_id].data == png.getvalue()
    second = tmp_path / "roundtrip.docx"
    assert write_docx_model(restored, second).success
    again = read_docx_model(second).sections[0].blocks[0].content[0]
    assert again.resource_id == image.resource_id and again.visual_surrogate.resource_id == surrogate.resource_id
    assert again.visual_surrogate.reason == surrogate.reason


def test_pdf_zero_opacity_preserves_fill_stroke_and_json_metadata(tmp_path):
    source = tmp_path / "zero-opacity.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=100, height=100)
        page.draw_rect(pymupdf.Rect(10, 10, 90, 90), color=(0, 0, 1), fill=(1, 0, 0), fill_opacity=0, stroke_opacity=0)
        pdf.save(source)
    drawings, warnings = extract_pdf_vector_drawings(source)
    assert not warnings and len(drawings) == 1
    drawing = drawings[0]
    assert drawing.fill_opacity == drawing.stroke_opacity == drawing.fill.alpha == drawing.stroke.alpha == 0
    result = read_document(source)
    assert result.success
    model = document_from_json(document_to_json(result.document))
    vector = next(r for r in model.resources.values() if r.media_type == "application/pdf+vector")
    assert vector.properties["fill_opacity"] == vector.properties["stroke_opacity"] == 0
    assert vector.properties["fill"]["alpha"] == 0
    with PdfDocument(source) as pdf:
        raster = pdf.render_page(0, scale=1)
    with PillowImage.open(io.BytesIO(raster.png)) as image:
        assert image.getpixel((50, 50)) == (255, 255, 255)


def test_confirmed_vector_export_gap_has_loss_diagnostic(tmp_path):
    source = Path(__file__).parents[1] / "corpus/native/vector-export.pdf"
    imported = read_document(source)
    assert imported.success
    output = tmp_path / "result.pdf"
    report = write_document(imported.document, output)
    assert not report.success and not report.lossless
    assert any("vector" in issue.message.lower() or "application/pdf" in issue.message.lower() for issue in report.issues)
