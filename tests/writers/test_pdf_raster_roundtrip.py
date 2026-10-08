"""Own raster PDFs checked against source geometry and rendered pixels."""

import io

import pymupdf as fitz
import pytest
from opendoc_model import document_from_json, document_to_json
from PIL import Image, ImageDraw

from opendoc_formats import read_document, write_document


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("transparent", [False, True])
def test_two_page_repeated_scan_preserves_geometry_and_pixels(tmp_path, rotation, transparent):
    image = Image.new("RGBA" if transparent else "RGB", (120, 180), (255, 255, 255, 0) if transparent else "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 119, 179), outline="red", width=5)
    draw.line((10, 12, 100, 150), fill="blue", width=4)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    source = tmp_path / "source.pdf"
    with fitz.open() as pdf:
        for _ in range(2):
            page = pdf.new_page(width=240, height=360)
            page.insert_image(page.rect, stream=buffer.getvalue(), keep_proportion=False)
            page.set_rotation(rotation)
        pdf.save(source)
    original = source.read_bytes()

    def snapshot(path):
        with fitz.open(path) as pdf:
            return [
                (
                    tuple(page.rect),
                    page.rotation,
                    [tuple(info["bbox"]) for info in page.get_image_info()],
                    page.get_pixmap(alpha=False).samples,
                )
                for page in pdf
            ]

    expected = snapshot(source)
    path = source
    for cycle in range(2):
        result = read_document(path)
        assert result.success
        model = document_from_json(document_to_json(result.document))
        assert all(len(section.blocks) == 1 for section in model.sections)
        path = tmp_path / f"cycle-{cycle}.pdf"
        assert write_document(model, path).success
        assert snapshot(path) == expected
    assert source.read_bytes() == original


@pytest.mark.parametrize("image_rotation", [0, 90, 180, 270])
def test_multiple_occurrences_crop_and_image_rotation(tmp_path, image_rotation):
    source = tmp_path / "source.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page(width=240, height=360)
        for color, rect, rotate in (
            ("red", (0, 0, 90, 110), image_rotation),
            ("blue", (90, 90, 220, 240), 0),
            ("red", (120, 250, 240, 350), image_rotation),
        ):
            image = Image.new("RGB", (40, 60), color)
            ImageDraw.Draw(image).rectangle((0, 0, 20, 15), fill="green")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            page.insert_image(fitz.Rect(rect), stream=buffer.getvalue(), rotate=rotate, keep_proportion=False)
        page.set_cropbox(fitz.Rect(10, 20, 220, 340))
        pdf.save(source)
    with fitz.open(source) as pdf:
        expected = pdf[0].get_pixmap(alpha=False).samples
    current = source
    for cycle in range(2):
        result = read_document(current)
        assert result.success
        model = document_from_json(document_to_json(result.document))
        assert len(model.sections[0].blocks) == 3
        current = tmp_path / f"cycle-{cycle}.pdf"
        assert write_document(model, current).success
        with fitz.open(current) as pdf:
            assert len(pdf[0].get_image_info()) == 3
            assert pdf[0].get_pixmap(alpha=False).samples == expected


def test_unsupported_transform_protects_previous_file(tmp_path):
    from opendoc_model import Box, DocumentModel, Resource, ResourceKind, Section
    from opendoc_model import Image as ModelImage

    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buffer, format="PNG")
    model = DocumentModel(
        sections=[
            Section(
                blocks=[ModelImage("own", box=Box(0, 0, 100, 100), properties={"pdf_image_transform": [100, 20, 200, 40, 0, 0]})]
            )
        ],
        resources={"own": Resource("own", ResourceKind.RASTER_IMAGE, "image/png", data=buffer.getvalue())},
    )
    target = tmp_path / "existing.pdf"
    target.write_bytes(b"previous")
    result = write_document(model, target)
    assert not result.success
    assert any(issue.feature == "pdf-raster-unsupported" for issue in result.issues)
    assert target.read_bytes() == b"previous"


@pytest.mark.parametrize("matrix", [
    (119.85, 6.28, -4.71, 89.87, 50, 80),
    (120, 20, 30, 90, 20, 30),
    (-120, 0, 0, 90, 160, 40),
    (120, 0, 0, -90, 40, 160),
])
def test_general_affine_two_json_cycles_against_original_native_pdf(tmp_path, matrix):
    image = Image.new("RGBA", (40, 60), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 20, 30), fill="red")
    draw.line((10, 5, 35, 50), fill="blue", width=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    source = tmp_path / "affine-source.pdf"
    a, b, c, d, e, f = matrix
    # Independent native content fixture, not generated by the production writer.
    with fitz.open() as pdf:
        page = pdf.new_page(width=240, height=300)
        page.insert_image(fitz.Rect(0, 0, 1, 1), stream=buffer.getvalue())
        pdf.update_stream(page.get_contents()[-1],
                          f"q {a} {-b} {-c} {d} {e+c} {300-f-d} cm /fzImg0 Do Q".encode())
        pdf.save(source)
    original = source.read_bytes()
    with fitz.open(source) as pdf:
        expected_pixels = pdf[0].get_pixmap(alpha=False).samples
        expected_info = pdf[0].get_image_info()[0]
    current = source
    for cycle in range(2):
        imported = read_document(current)
        assert imported.success
        model = document_from_json(document_to_json(imported.document))
        before = document_to_json(model)
        current = tmp_path / f"affine-{cycle}.pdf"
        result = write_document(model, current)
        assert result.success, result.issues
        assert document_to_json(model) == before
        with fitz.open(current) as pdf:
            info = pdf[0].get_image_info()[0]
            assert info["transform"] == pytest.approx(expected_info["transform"], abs=0.0001)
            assert info["bbox"] == pytest.approx(expected_info["bbox"], abs=0.0001)
            assert pdf[0].get_pixmap(alpha=False).samples == expected_pixels
    assert source.read_bytes() == original


def test_explicit_geometry_edit_and_cancellation(tmp_path):
    from opendoc_model import Box, DocumentModel, Resource, ResourceKind, Section
    from opendoc_model import Image as ModelImage

    from opendoc_formats.writers.pdf_writer import write_pdf_model

    buffer = io.BytesIO()
    image = Image.new("RGB", (10, 20), "red")
    ImageDraw.Draw(image).rectangle((0, 0, 9, 5), fill="blue")
    image.save(buffer, format="PNG")
    model = DocumentModel(
        sections=[Section(blocks=[ModelImage("own", box=Box(20, 30, 100, 80, rotation=90))])],
        resources={"own": Resource("own", ResourceKind.RASTER_IMAGE, "image/png", data=buffer.getvalue())},
    )
    target = tmp_path / "result.pdf"
    assert write_document(model, target).success
    with fitz.open(target) as pdf:
        info = pdf[0].get_image_info()[0]
        assert info["bbox"] == pytest.approx((30, 20, 110, 120), abs=0.0001)
        assert info["transform"][:4] == pytest.approx((0, 100, -80, 0), abs=0.0001)
    before = target.read_bytes()
    assert not write_pdf_model(model, target, cancelled=lambda: True).success
    assert target.read_bytes() == before


def test_inline_image_two_json_cycles(tmp_path):
    source = tmp_path / "inline.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page(width=120, height=120)
        stream = pdf.get_new_xref()
        pdf.update_object(stream, "<<>>")
        pdf.update_stream(stream, b"q 80 0 0 80 10 10 cm BI /W 2 /H 2 /CS /RGB /BPC 8 /F /AHx ID "
                          b"FF000000FF000000FFFFFFFF> EI Q")
        page.set_contents(stream)
        pdf.save(source)
    with fitz.open(source) as pdf:
        expected = pdf[0].get_pixmap(alpha=False).samples
        assert pdf[0].get_image_info(xrefs=True)[0]["xref"] == 0
    path = source
    for cycle in range(2):
        model = document_from_json(document_to_json(read_document(path).document))
        assert len(model.sections[0].blocks) == 1
        path = tmp_path / f"cycle-{cycle}.pdf"
        assert write_document(model, path).success
        with fitz.open(path) as pdf:
            assert pdf[0].get_pixmap(alpha=False).samples == expected
