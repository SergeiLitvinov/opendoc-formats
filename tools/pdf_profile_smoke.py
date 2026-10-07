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
            import fitz
            from opendoc_model import get_integration

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
            interactive_source = output / "interactive.pdf"
            with fitz.open() as fixture:
                page = fixture.new_page(width=300, height=400)
                page.insert_text((30, 60), "Interactive PDF")
                page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(30, 40, 140, 65), "uri": "https://example.invalid"})
                page.add_text_annot((160, 90), "Own note")
                widget = fitz.Widget()
                widget.field_name = "own-field"
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                widget.field_value = "Own value"
                widget.rect = fitz.Rect(30, 150, 170, 175)
                page.add_widget(widget)
                page.set_rotation(90)
                fixture.save(interactive_source)
            interactive = read_document(interactive_source)
            assert interactive.success, interactive.issues
            interaction_model = document_from_json(document_to_json(interactive.document))
            interaction = get_integration(interaction_model)
            assert len(interaction.annotations) == 2 and interaction.forms[0].value == "Own value"
            assert interaction_model.resources["pdf-original-source"].data == interactive_source.read_bytes()
            interaction_report = write_document(interaction_model, output / "interactive-export.pdf")
            assert interaction_report.success and not interaction_report.lossless, interaction_report.to_dict()
            with fitz.open(output / "interactive-export.pdf") as converted:
                assert converted[0].rotation == 90
            vector = read_document(corpus / "vector-export.pdf")
            assert vector.success, vector.issues
            assert any(r.media_type == "application/pdf+vector" for r in vector.document.resources.values())
            restored = document_from_json(document_to_json(vector.document))
            assert restored.resources == vector.document.resources
            vector_report = write_document(vector.document, output / "vector.pdf")
            assert vector_report.success and vector_report.metrics["pdf_vectors"]["native"] == 1, vector_report.to_dict()
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
