"""Exercise each installed PDF profile in a fresh, isolated interpreter."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("pdf-rich", "pdf-layout", "pdf-docx"))
    args = parser.parse_args()
    from opendoc_model import document_from_json, document_to_json

    import opendoc_formats
    from opendoc_formats import ExportOptions, ImportOptions, read_document, write_document

    assert "site-packages" in Path(opendoc_formats.__file__).resolve().parts
    corpus = Path(__file__).resolve().parents[1] / "tests/corpus/native"
    source = corpus / "text-pages.pdf"
    absent = {
        "pdf-rich": ("pypdf", "pdfplumber", "pdf2docx", "cv2", "numpy", "docx", "lxml", "PIL"),
        "pdf-layout": ("pypdf", "fitz", "pdf2docx", "cv2", "numpy", "docx", "lxml"),
        "pdf-docx": ("pypdf", "pdfplumber"),
    }[args.profile]
    assert all(importlib.util.find_spec(name) is None for name in absent), absent
    with TemporaryDirectory(prefix="opendoc-formats-pdf-profile-") as directory:
        output = Path(directory)
        if args.profile == "pdf-rich":
            from opendoc_formats.pdf import PdfDocument

            with PdfDocument(source) as pdf:
                assert pdf.page_count == 2
                assert pdf.page_info(0).width > 0
                assert pdf.render_page(0, max_dimension=256).png.startswith(b"\x89PNG")
            result = read_document(source)
            assert result.success, result.issues
            assert "Native PDF" in str(result.document)
            report = write_document(result.document, output / "document.pdf")
            assert report.success, report.to_dict()
            assert read_document(output / "document.pdf").success
            vector = read_document(corpus / "vector-export.pdf")
            assert vector.success, vector.issues
            assert any(r.media_type == "application/pdf+vector" for r in vector.document.resources.values())
            restored = document_from_json(document_to_json(vector.document))
            assert restored.resources == vector.document.resources
            assert not read_document(source, options=ImportOptions(cancelled=lambda: True)).success
            target = output / "cancelled.pdf"
            target.write_bytes(b"existing")
            cancelled = write_document(result.document, target, options=ExportOptions(cancelled=lambda: True))
            assert not cancelled.success and target.read_bytes() == b"existing"
        elif args.profile == "pdf-layout":
            from opendoc_formats.readers.pdf import read_pdf

            text = read_pdf(str(source))
            assert text.engine == "pdfplumber" and text.pages == 2 and "Native PDF" in text.plain
            result = read_document(source)
            assert not result.success and result.issues[0].code == "import.backend-unavailable"
        else:
            from docx import Document
            from pdf2docx import Converter

            # The engine's single-worker route keeps this acceptance bounded.
            converter = Converter(str(source))
            try:
                target = output / "document.docx"
                converter.convert(str(target), multi_processing=False)
            finally:
                converter.close()
            assert "Native PDF" in "\n".join(p.text for p in Document(target).paragraphs)
            assert read_document(source).success  # pdf2docx transitively provides PyMuPDF.
    print(f"Installed profile passed: {args.profile}; excluded engines are absent")


if __name__ == "__main__":
    main()
