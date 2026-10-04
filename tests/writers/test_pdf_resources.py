"""Ресурсы PDF: однократная подготовка, снимок источника и безопасный отказ."""

import pytest
from opendoc.document_model import DocumentModel, Image, Paragraph, Resource, ResourceKind, Section
from PIL import Image as PillowImage

from opendoc_formats.writers.pdf_resources import PdfResourceStage
from opendoc_formats.writers.pdf_writer import write_pdf_model
from opendoc_formats.writers.stages import StageContext

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80"><rect width="120" height="80" fill="red"/></svg>'


def test_repeated_svg_is_prepared_once_and_unused_svg_is_not_decoded(tmp_path):
    source = tmp_path / "vector.svg"
    source.write_bytes(SVG)
    original = Resource("vector", ResourceKind.VECTOR_IMAGE, "image/svg+xml", source=source)
    unused = Resource("unused", ResourceKind.VECTOR_IMAGE, "image/svg+xml", data=b"not SVG")
    document = DocumentModel(
        resources={"vector": original, "unused": unused},
        sections=[Section(blocks=[Image("vector"), Paragraph([Image("vector")])], footers=[Image("vector")])],
    )
    result = PdfResourceStage().execute(document, StageContext(tmp_path / "result.pdf"))
    assert result.report.success and not result.report.lossless
    metrics = result.report.metrics["resource_preparation"]
    assert metrics["stage"] == "pdf.resources"
    assert metrics["references"] == 3 and metrics["resolved"] == 1
    assert metrics["svg_rasterized"] == 1 and metrics["png_bytes"] > 0
    assert len([issue for issue in result.report.issues if issue.feature == "image-vector"]) == 1
    assert result.value.resources["vector"].media_type == "image/png"
    assert result.value.resources["vector"].data.startswith(b"\x89PNG")
    assert result.value.resources["unused"] is unused
    assert document.resources["vector"] is original and original.data is None
    assert original.media_type == "image/svg+xml" and source.read_bytes() == SVG


def test_external_png_snapshot_remains_visible_after_source_removed(tmp_path):
    import fitz

    source = tmp_path / "image.png"
    PillowImage.new("RGB", (80, 40), "green").save(source)
    original = Resource("picture", ResourceKind.RASTER_IMAGE, "image/png", source=source)
    document = DocumentModel(resources={"picture": original}, sections=[Section(blocks=[Image("picture")])])
    result = PdfResourceStage().execute(document, StageContext(tmp_path / "result.pdf"))
    source.unlink()
    report = write_pdf_model(result.value, tmp_path / "result.pdf")
    assert report.success
    assert original.data is None
    with fitz.open(tmp_path / "result.pdf") as pdf:
        assert pdf[0].get_images()
        samples = pdf[0].get_pixmap(alpha=False).samples
        assert sum(r < 10 and 100 < g < 150 and b < 10 for r, g, b in zip(samples[::3], samples[1::3], samples[2::3])) > 1000


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("broken_svg", [False, True])
def test_resource_failure_does_not_publish_pdf(tmp_path, existing, broken_svg):
    output = tmp_path / "result.pdf"
    if existing:
        output.write_bytes(b"previous PDF")
    resources = {"image": Resource("image", ResourceKind.VECTOR_IMAGE, "image/svg+xml", data=b"broken")} if broken_svg else {}
    report = write_pdf_model(DocumentModel(resources=resources, sections=[Section(blocks=[Image("image")])]), output)
    assert not report.success
    assert report.metrics["resource_preparation"]["accepted"] is False
    if existing:
        assert output.read_bytes() == b"previous PDF"
    else:
        assert not output.exists()
