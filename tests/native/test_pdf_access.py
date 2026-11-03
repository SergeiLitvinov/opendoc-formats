"""PDF text/scans, bounded rendering and explicit ownership without backend objects."""

import io
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from opendoc_formats.errors import (
    BackendUnavailableError,
    DocumentClosedError,
    EncryptedDocumentError,
    InvalidDocumentError,
    OperationCancelledError,
    PageIndexError,
    ResourceLimitError,
)
from opendoc_formats.pdf import PdfDocument, PdfLimits


@pytest.fixture
def source():
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=300, height=600)
        page.insert_text((30, 50), "First native page")
        page = pdf.new_page(width=300, height=600)
        page.set_rotation(90)
        image = io.BytesIO()
        Image.new("RGB", (40, 20), "blue").save(image, format="PNG")
        page.insert_image(pymupdf.Rect(10, 10, 200, 200), stream=image.getvalue())
        return pdf.tobytes()


def test_text_geometry_scan_bytes_and_path(source, tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(source)
    for input_source in (source, path, str(path)):
        with PdfDocument(input_source) as pdf:
            assert pdf.page_count == 2
            info = pdf.page_info(0)
            assert info.width == 300 and info.height == 600
            assert info.rotation == 0 and "First native page" in info.text
            scan = pdf.page_info(1)
            assert scan.width == 600 and scan.height == 300 and scan.rotation == 90 and scan.text == ""
            image = pdf.render_page(0, dpi=72)
            with Image.open(io.BytesIO(image.png)) as decoded:
                assert decoded.mode == "RGB" and decoded.size == (image.width, image.height) == (300, 600)
            assert image.effective_scale == 1
        assert pdf.closed
        pdf.close()
        for use in (lambda: pdf.page_count, lambda: pdf.page_info(0), lambda: pdf.render_page(0)):
            with pytest.raises(DocumentClosedError):
                use()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270, 45, -90])
def test_rotation_and_maximum_dimensions(source, rotation):
    with PdfDocument(source) as pdf:
        image = pdf.render_page(0, scale=6, max_dimension=200, rotation=rotation)
        assert 0 < image.width <= 200 and 0 < image.height <= 200
        if rotation in {0, 180}:
            assert image.height > image.width
        elif rotation in {90, 270, -90}:
            assert image.width > image.height
        assert image.effective_scale < 6


def test_pixel_budget_is_applied_before_native_render(source, monkeypatch):
    original = pymupdf.Page.get_pixmap
    calls = []

    def render(page, **kwargs):
        bounds = (page.rect * kwargs["matrix"]).irect
        calls.append(bounds.width * bounds.height)
        return original(page, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "get_pixmap", render)
    with PdfDocument(source, limits=replace(PdfLimits(), max_pixels=10000)) as pdf:
        image = pdf.render_page(0, scale=100000)
        assert image.width * image.height <= 10000
        assert 0 < image.effective_scale < 1
    assert calls and max(calls) <= 10000


def test_rerender_cache_is_bounded_and_closed(source, monkeypatch):
    original = pymupdf.Page.get_pixmap
    calls = []

    def render(page, **kwargs):
        calls.append(page.number)
        return original(page, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "get_pixmap", render)
    with PdfDocument(source, limits=replace(PdfLimits(), cache_pages=1)) as pdf:
        first = pdf.render_page(0, scale=1)
        assert pdf.render_page(0, scale=1) is first
        pdf.page_info(0)  # Text extraction does not force another raster.
        pdf.render_page(1, scale=1)
        pdf.render_page(0, scale=1)
    assert calls == [0, 1, 0]


@pytest.mark.parametrize("index", [-1, 2, 100])
def test_out_of_range(source, index):
    with PdfDocument(source) as pdf:
        with pytest.raises(PageIndexError):
            pdf.page_info(index)
        with pytest.raises(PageIndexError):
            pdf.render_page(index)


@pytest.mark.parametrize(
    "options",
    [
        {"dpi": 0},
        {"scale": -1},
        {"dpi": True},
        {"dpi": float("nan")},
        {"scale": float("inf")},
        {"dpi": 72, "scale": 1},
        {"max_dimension": 0},
        {"max_dimension": True},
        {"rotation": float("nan")},
    ],
)
def test_invalid_render_options(source, options):
    with PdfDocument(source) as pdf:
        with pytest.raises(ValueError):
            pdf.render_page(0, **options)


def test_encrypted_and_corrupt_pdf(source):
    with pymupdf.open(stream=source, filetype="pdf") as pdf:
        encrypted = pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    with pytest.raises(EncryptedDocumentError):
        PdfDocument(encrypted)
    with pytest.raises(InvalidDocumentError):
        PdfDocument(b"%PDF-1.7\ninvalid")


@pytest.mark.parametrize("limits", [replace(PdfLimits(), max_input_bytes=100), replace(PdfLimits(), max_pages=1)])
def test_open_budgets_release_native_handle(source, limits, monkeypatch):
    original = pymupdf.open
    opened = []

    def tracked(*args, **kwargs):
        doc = original(*args, **kwargs)
        opened.append(doc)
        return doc

    monkeypatch.setattr(pymupdf, "open", tracked)
    with pytest.raises(ResourceLimitError):
        PdfDocument(source, limits=limits)
    assert all(doc.is_closed for doc in opened)


def test_png_and_text_post_call_budgets(source):
    with PdfDocument(source, limits=replace(PdfLimits(), max_png_bytes=1)) as pdf:
        with pytest.raises(ResourceLimitError):
            pdf.render_page(0)
    with PdfDocument(source, limits=replace(PdfLimits(), max_text_chars=1)) as pdf:
        with pytest.raises(ResourceLimitError):
            pdf.page_info(0)


def test_missing_backend(source, monkeypatch):
    import opendoc_formats.native.common as common

    original = common.importlib.import_module

    def unavailable(name):
        if name == "pymupdf":
            raise ImportError("blocked")
        return original(name)

    monkeypatch.setattr(common.importlib, "import_module", unavailable)
    with pytest.raises(BackendUnavailableError):
        PdfDocument(source)


def test_cooperative_cancel_after_render_and_before_open(source, monkeypatch):
    original = pymupdf.Page.get_pixmap
    state = {"cancel": False}

    def render(page, **kwargs):
        result = original(page, **kwargs)
        state["cancel"] = True
        return result

    monkeypatch.setattr(pymupdf.Page, "get_pixmap", render)
    with PdfDocument(source, cancelled=lambda: state["cancel"]) as pdf:
        with pytest.raises(OperationCancelledError):
            pdf.render_page(0)
    with pytest.raises(OperationCancelledError):
        PdfDocument(source, cancelled=lambda: True)


def test_existing_office_chart_pdf_corpus():
    corpus = Path(__file__).parents[1] / "corpus/visual/charts/chart-corpus.pdf"
    with PdfDocument(corpus) as pdf:
        assert pdf.page_count > 10
        info = pdf.page_info(0)
        assert info.width > 0 and info.height > 0
        image = pdf.render_page(0, max_dimension=512)
        assert image.png.startswith(b"\x89PNG") and max(image.width, image.height) <= 512
