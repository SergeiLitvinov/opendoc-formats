"""Exercise the installed wheel in an isolated interpreter, without importing the checkout."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import zipfile
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-formats", action="store_true")
    parser.add_argument("--pdf-text", action="store_true")
    parser.add_argument("--epub", action="store_true")
    args = parser.parse_args()
    from opendoc_model import DocumentModel, Formula, FormulaFormat, Paragraph, Section, Table, TableCell, TableRow, TextRun

    import opendoc_formats
    from opendoc_formats import (
        ExportOptions,
        ImportOptions,
        TextProfile,
        default_exporter_registry,
        default_registry,
        read_document,
        write_document,
    )
    from opendoc_formats.docx import DocxPackage, ReplaceTextSpan
    from opendoc_formats.errors import BackendUnavailableError
    from opendoc_formats.office import find_libreoffice
    from opendoc_formats.package_resources import assemble_docx_package_resources
    from opendoc_formats.pdf import PdfDocument

    assert opendoc_formats.__version__ == version("opendoc-formats")
    assert version("opendoc-model") == "0.6.0"
    engines = ("bs4", "fitz", "pymupdf", "lxml", "docx", "pptx", "ebooklib", "fontTools")
    assert all(name not in sys.modules for name in engines)
    installed = Path(opendoc_formats.__file__).resolve().parent
    assert "site-packages" in installed.parts, installed
    assert (installed / "py.typed").is_file()
    default_registry()
    default_exporter_registry()
    if not args.all_formats:
        absent = tuple(name for name in engines if name != "bs4" or not args.epub)
        assert all(importlib.util.find_spec(name) is None for name in absent)
        for constructor in (DocxPackage, PdfDocument):
            try:
                constructor(b"missing engine")
            except BackendUnavailableError:
                pass
            else:
                raise AssertionError("Native access should diagnose absent optional backend")
        find_libreoffice()
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
    assert assemble_docx_package_resources(document, {}) == document
    if args.pdf_text:
        from opendoc_formats.readers.pdf import read_pdf

        text = read_pdf(str(Path(__file__).resolve().parents[1] / "tests/corpus/native/text-pages.pdf"))
        assert text.engine == "pypdf" and text.pages == 2 and "Native PDF" in text.plain, text
    with TemporaryDirectory(prefix="opendoc-formats-installed-") as directory:
        root = Path(directory)
        tex = root / "own-source.tex"
        tex.write_text(r"\documentclass{article}\begin{document}\section{Own}Text $x^2$.\end{document}", encoding="utf-8")
        source_tex = read_document(tex)
        assert source_tex.success and not source_tex.lossless and not source_tex.assessment_complete
        assert source_tex.document.sections[0].blocks[0].plain_text == "Own"
        assert source_tex.document.sections[0].blocks[1].content[-2].format is FormulaFormat.LATEX
        assert source_tex.document.resources["latex-original-source"].data == tex.read_bytes()
        book = root / "base-writer.epub"
        from opendoc_formats.readers.epub_package import read_epub_package

        book_report = write_document(DocumentModel(metadata={"creator": ["Own author"], "identifier": "urn:example:installed"},
                                                    sections=[Section(blocks=[Paragraph(content=[TextRun("Own EPUB")])])]), book)
        assert book_report.success and book_report.metrics["output_verified"], book_report.to_dict()
        assert read_epub_package(book).spine == (("chapter", "yes"),)
        assert read_epub_package(book).dc_values["creator"] == ("Own author",)
        assert read_epub_package(book).metadata["identifier"] == "urn:example:installed"
        for encoding in ("utf-8", "utf-16-le", "utf-16-be", "cp1251"):
            source = root / "profile.txt"
            original = "Первая\r\nВторая\rПоследняя\n".encode(encoding)
            source.write_bytes(original)
            imported = read_document(source, options=ImportOptions(txt_profile=TextProfile(encoding)))
            assert imported.success, imported.issues
            transport = root / "profile.json"
            assert write_document(imported.document, transport).success
            restored = read_document(transport)
            target = root / "profile-copy.txt"
            copied = write_document(restored.document, target, options=ExportOptions(txt_profile=TextProfile()))
            assert copied.success and copied.lossless and copied.metrics["output_verified"], copied.to_dict()
            assert target.read_bytes() == original
        if args.epub:
            source = root / "native.epub"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip")
                archive.writestr("META-INF/container.xml", '''
                  <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>
                  <rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>''')
                archive.writestr("book.opf", '''<package xmlns="http://www.idpf.org/2007/opf"><metadata/>
                  <manifest><item id="c" href="c.xhtml" media-type="application/xhtml+xml"/>
                  <item id="appendix" href="appendix.xhtml" media-type="application/xhtml+xml"/></manifest>
                  <spine><itemref idref="c"/><itemref idref="appendix" linear="no"/></spine></package>''')
                archive.writestr("c.xhtml", '''<html><body><p style="position:absolute;font-size:12pt">Native EPUB 123</p>
                    <table><tr><td colspan="2">Own cell</td></tr></table>
                    <math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>
                    </body></html>''')
                archive.writestr("appendix.xhtml", "<html><body><p>Own nonlinear appendix</p></body></html>")
            result = read_document(source)
            assert result.success, result.issues
            assert result.document.sections[0].blocks[0].plain_text == "Native EPUB 123"
            assert any(issue.reason == "unsupported-declaration" for issue in result.issues)
            assert isinstance(result.document.sections[0].blocks[1], Table)
            assert result.document.sections[0].blocks[1].rows[0].cells[0].column_span == 2
            assert isinstance(result.document.sections[0].blocks[2].content[0], Formula)
            vector = result.document.sections[0].blocks[3].content[0]
            assert result.document.resources[vector.resource_id].media_type == "image/svg+xml"
            assert len(result.document.sections) == 1
            inclusive = read_document(source, options=ImportOptions(epub_include_nonlinear=True))
            assert inclusive.success and len(inclusive.document.sections) == 2
            assert inclusive.document.sections[1].blocks[0].plain_text == "Own nonlinear appendix"
            assert inclusive.document.sections[1].properties["epub"]["linear"] == "no"
            assert all(name not in sys.modules for name in ("lxml", "ebooklib"))
        math_path = root / "math.html"
        math = DocumentModel(sections=[Section(blocks=[Formula(
            '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>', FormulaFormat.MATHML,
        )])])
        math_report = write_document(math, math_path)
        assert math_report.success, math_report.to_dict()
        assert "<mi>x</mi>" in math_path.read_text(encoding="utf-8")
        if not args.all_formats:
            assert "lxml" not in sys.modules
        if args.all_formats:
            from bs4 import BeautifulSoup
            from opendoc_model.document_codec import document_from_json, document_to_json

            source = root / "semantic.html"
            source.write_text('<html lang="en"><body><table><caption>Own measurements</caption>'
                              '<thead><tr><th id="value" scope="col">Value</th></tr></thead>'
                              '<tbody><tr><td headers="value">12</td></tr></tbody></table></body></html>')
            for cycle in range(2):
                imported = read_document(source)
                assert imported.success, imported.issues
                restored = document_from_json(document_to_json(imported.document))
                target = root / f"semantic-{cycle}.html"
                assert write_document(restored, target).success
                parsed = BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser")
                assert parsed.html["lang"] == "en"
                assert parsed.table.caption.get_text() == "Own measurements"
                assert parsed.table.th["scope"] == "col"
                assert parsed.table.td["headers"] == ["value"]
                source = target
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
            if args.all_formats and format_id == "docx":
                from opendoc_model import Heading, get_heading, set_heading
                from opendoc_model.document_codec import document_from_json, document_to_json

                heading = Paragraph([TextRun("Own formal heading")])
                set_heading(heading, Heading(2))
                heading_model = DocumentModel(sections=[Section(blocks=[heading])])
                for cycle in range(2):
                    heading_target = root / f"heading-{cycle}.docx"
                    restored = document_from_json(document_to_json(heading_model))
                    assert write_document(restored, heading_target).success
                    heading_result = read_document(heading_target)
                    assert heading_result.success, heading_result.issues
                    heading_model = heading_result.document
                    assert get_heading(heading_model.sections[0].blocks[0]) == Heading(2)
                with DocxPackage(path) as package:
                    paragraph = next(p for p in package.paragraphs if p.is_body and p.text)
                    updated = package.to_bytes([ReplaceTextSpan(paragraph.id, 0, 0, "Native ")])
                with DocxPackage(updated) as package:
                    assert package.paragraphs[0].text.startswith("Native ")
            if args.all_formats and format_id == "pdf":
                with PdfDocument(path) as pdf:
                    assert pdf.page_count > 0 and pdf.page_info(0).width > 0
                    rendered = pdf.render_page(0, max_dimension=512)
                    assert rendered.png.startswith(b"\x89PNG") and rendered.effective_scale > 0
    print(f"Installed wheel smoke passed: epub writer, {', '.join(formats)}")


if __name__ == "__main__":
    main()
