from pathlib import Path

from PIL import Image


def render_pdf_pages(path: str | Path, *, dpi: int = 96) -> list[Image.Image]:
    """Рендерить PDF-страницы в RGB Pillow images."""

    import fitz

    pages: list[Image.Image] = []
    with fitz.open(path) as document:
        for page in document:
            pixmap = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
            pages.append(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples))
    return pages
