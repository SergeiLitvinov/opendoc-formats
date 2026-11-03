"""Native-vector fidelity, bounded surrogate, rejection and cancellation."""

import io
from pathlib import Path

import pymupdf
import pytest
from opendoc_model import Resource, ResourceKind, VisualSurrogate, document_from_json, document_to_json, load_document

from opendoc_formats import read_document, write_document
from opendoc_formats.writers.pdf_writer import write_pdf_model


def _document():
    source = Path(__file__).parents[1] / "corpus/native/vector-export.pdf"
    return document_from_json(document_to_json(read_document(source).document))


@pytest.mark.parametrize("opacity", [0, 0.4, 1])
def test_native_curve_line_and_opacity_have_identical_pixels(tmp_path, opacity):
    source = tmp_path / "paths.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=120, height=120)
        shape = page.new_shape()
        shape.draw_bezier((10, 20), (30, 5), (70, 90), (100, 40))
        shape.finish(color=(0.2, 0.3, 0.7), width=3, stroke_opacity=opacity, closePath=False)
        shape.commit()
        page.draw_line((10, 105), (100, 105), color=(1, 0, 0), width=2, stroke_opacity=opacity)
        pdf.save(source)
    document = read_document(source).document
    original = document_to_json(document)
    output = tmp_path / "output.pdf"
    report = write_document(document, output)
    assert report.success and report.lossless, report.to_dict()
    assert document_to_json(document) == original
    with pymupdf.open(source) as before, pymupdf.open(output) as after:
        assert before[0].get_pixmap().samples == after[0].get_pixmap().samples
        assert after[0].get_images() == []


def test_unknown_vector_rejected_atomically_without_surrogate(tmp_path):
    document = load_document(Path(__file__).parents[1] / "corpus/native/unsupported-vector.json")
    output = tmp_path / "output.pdf"
    output.write_bytes(b"existing")
    report = write_document(document, output)
    assert not report.success
    assert any(issue.feature == "pdf-vector-unsupported" for issue in report.issues)
    assert output.read_bytes() == b"existing"


def test_fill_only_quad_and_dashed_scaled_vector(tmp_path):
    source = tmp_path / "shapes.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=120, height=120)
        page.draw_quad(pymupdf.Quad((10, 10), (60, 20), (20, 60), (70, 70)), color=None, fill=(0, 1, 0))
        page.draw_rect(pymupdf.Rect(80, 80, 100, 100), color=(1, 0, 0), dashes="[2 3] 1", width=2)
        pdf.save(source)
    document = read_document(source).document
    output = tmp_path / "output.pdf"
    report = write_document(document, output)
    assert report.success, report.to_dict()
    with pymupdf.open(source) as before, pymupdf.open(output) as after:
        assert before[0].get_pixmap().samples == after[0].get_pixmap().samples
    image = document.sections[0].blocks[-1].content[0]
    image.box.width *= 0.5
    image.box.height *= 0.5
    assert write_document(document, output).success
    with pymupdf.open(output) as pdf:
        drawing = next(value for value in pdf[0].get_drawings() if value["color"] == (1, 0, 0))
        assert drawing["width"] == 1 and drawing["rect"] == pymupdf.Rect(80, 80, 90, 90)
        array, phase = drawing["dashes"].split("]")
        assert [float(value) for value in array.lstrip("[").split()] == [1, 1.5]
        assert float(phase) == 0.5
    assert write_document(read_document(output).document, tmp_path / "second.pdf").success


def test_unknown_vector_uses_supplied_bounded_png_surrogate(tmp_path):
    from PIL import Image as PillowImage

    document = _document()
    next(iter(document.resources.values())).properties["items"] = [["unknown"]]
    buffer = io.BytesIO()
    PillowImage.new("RGB", (20, 20), "red").save(buffer, format="PNG")
    document.resources["visual"] = Resource("visual", ResourceKind.RASTER_IMAGE, "image/png", data=buffer.getvalue())
    image = document.sections[0].blocks[0].content[0]
    image.visual_surrogate = VisualSurrogate("visual", "unsupported source vector command", "image/png")
    original = document_to_json(document)
    report = write_document(document, tmp_path / "surrogate.pdf")
    assert report.success and not report.lossless, report.to_dict()
    assert any(issue.feature == "pdf-vector-surrogate" for issue in report.issues)
    assert document_to_json(document) == original
    with pymupdf.open(tmp_path / "surrogate.pdf") as pdf:
        assert pdf[0].get_images()


def test_vector_command_limit_and_direct_cancellation_preserve_existing_output(tmp_path, monkeypatch):
    from opendoc_formats.writers import pdf_vectors

    document = _document()
    next(iter(document.resources.values())).properties["items"] *= 3
    monkeypatch.setattr(pdf_vectors, "MAX_VECTOR_COMMANDS", 2)
    output = tmp_path / "output.pdf"
    output.write_bytes(b"existing")
    assert not write_document(document, output).success
    assert output.read_bytes() == b"existing"
    report = write_pdf_model(_document(), output, cancelled=lambda: True)
    assert not report.success and output.read_bytes() == b"existing"


def test_surrogate_with_excessive_pixel_dimensions_is_rejected(tmp_path):
    import struct

    document = _document()
    next(iter(document.resources.values())).properties["items"] = [["unknown"]]
    payload = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 100_000, 100_000)
    document.resources["visual"] = Resource("visual", ResourceKind.RASTER_IMAGE, "image/png", data=payload)
    document.sections[0].blocks[0].content[0].visual_surrogate = VisualSurrogate("visual", "unsupported")
    report = write_document(document, tmp_path / "huge.pdf")
    assert not report.success
    assert any("pixel limits" in issue.message for issue in report.issues)
    assert not (tmp_path / "huge.pdf").exists()
