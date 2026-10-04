"""Exercise the installed wheel in an isolated interpreter, without importing the checkout."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-formats", action="store_true")
    args = parser.parse_args()
    from opendoc import DocumentModel, Paragraph, Section, Table, TableCell, TableRow, TextRun

    import opendoc_formats
    from opendoc_formats import default_exporter_registry, default_registry, read_document, write_document

    assert opendoc_formats.__version__ == version("opendoc-formats")
    assert version("opendoc") == "0.1.0"
    assert all(name not in sys.modules for name in ("bs4", "fitz", "docx", "pptx", "ebooklib", "fontTools"))
    installed = Path(opendoc_formats.__file__).resolve().parent
    assert "site-packages" in installed.parts, installed
    assert (installed / "py.typed").is_file()
    default_registry()
    default_exporter_registry()
    if not args.all_formats:
        assert all(importlib.util.find_spec(name) is None for name in ("bs4", "fitz", "docx", "pptx", "ebooklib", "fontTools"))
    document = DocumentModel(
        sections=[
            Section(
                blocks=[
                    Paragraph([TextRun("Installed package / Проверка 123")]),
                    Table([TableRow([TableCell([Paragraph([TextRun("Cell")])])])]),
                ]
            )
        ]
    )
    with TemporaryDirectory(prefix="opendoc-formats-installed-") as directory:
        root = Path(directory)
        formats = ("txt", "json", "html", "docx", "pptx", "pdf", "latex") if args.all_formats else ("txt", "json", "html")
        for format_id in formats:
            path = root / ("document." + ("tex" if format_id == "latex" else format_id))
            report = write_document(document, path)
            assert report.success, report.to_dict()
            assert report.metrics["output_verified"] is True
            if format_id != "latex" and (args.all_formats or format_id != "html"):
                result = read_document(path)
                assert result.success, result.issues
                assert result.document.validate() == []
                assert "Cell" in str(result.document)
    print(f"Installed wheel smoke passed: {', '.join(formats)}")


if __name__ == "__main__":
    main()
