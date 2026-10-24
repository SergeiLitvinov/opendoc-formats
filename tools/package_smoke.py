"""Exercise the installed wheel in an isolated interpreter, without importing the checkout."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import sys
import zipfile
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory


def diagnostics_smoke() -> None:
    from opendoc_model import (
        DiagnosticIssue,
        IssueSeverity,
        Provenance,
        document_from_json,
        document_to_json,
        integration_from_dict,
    )

    from opendoc_formats.support.document_adapters import document_to_text, text_to_document
    from opendoc_formats.support.text_diagnostics import append_text_warning
    from opendoc_formats.types import DocFormat, Text

    text = Text(plain='Own portable text', source_format=DocFormat.PDF)
    append_text_warning(text, DiagnosticIssue(
        'pdf.own-source-warning', IssueSeverity.LOSS, 'Own uncertainty', 'own.pdf#page=2',
        reason='own-source-unassessed',
    ), Provenance('pdf', 'own.pdf', page=2))
    for _ in range(2):
        restored = document_to_text(document_from_json(document_to_json(text_to_document(text))))
        assert restored.diagnostics == text.diagnostics
        assert restored.warnings == text.warnings and not restored.diagnostics.assessment_complete
        assert integration_from_dict(restored.to_dict()['diagnostics']) == text.diagnostics
        text = restored


def anatomy_smoke() -> None:
    from opendoc_formats.anatomy import compare_snapshots, inspect_binary

    source = io.BytesIO()
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('word/own', '<own xmlns="urn:own"><child>Own text</child></own>')
        archive.writestr('word/unknown.bin', b'Own opaque bytes\x00\xff')
        archive.writestr('[Content_Types].xml',
                         '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                         '<Default Extension="bin" ContentType="application/octet-stream"/>'
                         '<Override PartName="/word/own" ContentType="application/vnd.own+xml"/></Types>')
        archive.writestr('_rels/.rels',
                         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         '<Relationship Id="own" Type="urn:own" Target="word/own"/></Relationships>')
    snapshot = inspect_binary(source.getvalue(), capture=True)
    assert snapshot.items[1].payload == b'Own opaque bytes\x00\xff'
    assert snapshot.items[0].xml_nodes[1].tag == '{urn:own}child'
    assert dict(snapshot.items[0].details)['xml_detection'] == 'opc-content-type'
    assert snapshot.opc is not None and snapshot.opc.reachability_complete
    assert snapshot.opc.reachable_parts == ('/word/own',)
    assert snapshot.opc.unreachable_parts == ('/word/unknown.bin',)
    assert compare_snapshots(snapshot, inspect_binary(source.getvalue()))['binary_identical']
    epub = io.BytesIO()
    with zipfile.ZipFile(epub, 'w') as archive:
        archive.writestr('mimetype', b'application/epub+zip')
        archive.writestr('Book/chapter', '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Own</p></body></html>')
        archive.writestr('META-INF/container.xml',
                         '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                         '<rootfile full-path="Book/package" media-type="application/oebps-package+xml"/>'
                         '</rootfiles></container>')
        archive.writestr('Book/package', '<package xmlns="http://www.idpf.org/2007/opf"><manifest>'
                         '<item id="own" href="chapter" media-type="application/xhtml+xml"/></manifest></package>')
    snapshot = inspect_binary(epub.getvalue())
    assert snapshot.opc is None and dict(snapshot.details)['epub_rootfiles'] == ('Book/package',)
    assert dict(snapshot.items[1].details)['xml_detection'] == 'epub-media-type'
    assert snapshot.items[1].xml_nodes[0].tag == '{http://www.w3.org/1999/xhtml}html'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-formats", action="store_true")
    parser.add_argument("--pdf-text", action="store_true")
    parser.add_argument("--epub", action="store_true")
    args = parser.parse_args()
    from opendoc_model import (
        DocumentLimits,
        DocumentModel,
        Formula,
        FormulaFormat,
        Paragraph,
        Section,
        Table,
        TableCell,
        TableRow,
        TextRun,
        document_from_json,
        document_to_json,
        get_heading,
        get_list_item,
        iter_list_numbers,
    )

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
    from opendoc_formats.support.inspection import inspect_path

    assert opendoc_formats.__version__ == version("opendoc-formats")
    assert version("opendoc-model") == "0.18.0"
    assert importlib.util.find_spec("ebooklib") is None, "Removed EPUB engine leaked into the installed profile"
    engines = ("bs4", "fitz", "pymupdf", "lxml", "docx", "pptx", "ebooklib", "fontTools")
    assert all(name not in sys.modules for name in engines)
    installed = Path(opendoc_formats.__file__).resolve().parent
    assert "site-packages" in installed.parts, installed
    assert (installed / "py.typed").is_file()
    diagnostics_smoke()
    anatomy_smoke()
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
        from opendoc_formats.readers.pdf import get_pdf_info, read_pdf
        from opendoc_formats.support.io import validate_pdf

        pdf_source = Path(__file__).resolve().parents[1] / "tests/corpus/native/text-pages.pdf"
        text = read_pdf(str(pdf_source))
        assert text.engine == "pypdf" and text.pages == 2 and "Native PDF" in text.plain, text
        assert validate_pdf(pdf_source) and get_pdf_info(str(pdf_source)) == {'title': '', 'author': '', 'subject': ''}
    with TemporaryDirectory(prefix="opendoc-formats-installed-") as directory:
        root = Path(directory)
        tex = root / "own-source.tex"
        tex.write_text(r"\documentclass{article}\begin{document}\section{Own}Text $x^2$.\end{document}", encoding="utf-8")
        source_tex = read_document(tex)
        assert source_tex.success and not source_tex.lossless and not source_tex.assessment_complete
        assert source_tex.document.sections[0].blocks[0].plain_text == "Own"
        assert source_tex.document.sections[0].blocks[1].content[-2].format is FormulaFormat.LATEX
        assert source_tex.document.resources["latex-original-source"].data == tex.read_bytes()
        native_tex = DocumentModel(sections=[Section(blocks=[Paragraph(content=[TextRun('Own [text] & percent 100%')])])])
        for index in range(2):
            native_target = root / f'native-text-{index}.tex'
            native_report = write_document(native_tex, native_target)
            assert native_report.success and native_report.metrics['latex_route'] == 'native-text-v1'
            native_tex = document_from_json(document_to_json(read_document(native_target).document))
            assert native_tex.sections[0].blocks[0].plain_text == 'Own [text] & percent 100%'
        headings = root / 'source-headings.tex'
        scripts = root / 'source-scripts.tex'
        scripts.write_text(r'\begin{document}Own\textsuperscript{\bfseries B\normalfont N} '
                           r'and H\textsubscript{2}O.\end{document}', encoding='utf-8')
        script_model = read_document(scripts).document
        for index in range(2):
            script_target = root / f'scripts-{index}.tex'
            script_report = write_document(document_from_json(document_to_json(script_model)), script_target)
            assert script_report.success and script_report.metrics['latex_route'] == 'native-text-v1'
            script_model = read_document(script_target).document
            runs = script_model.sections[0].blocks[0].content
            assert any(run.style.superscript for run in runs) and any(run.style.subscript for run in runs)
            assert r'\textsuperscript{{\bfseries B}N}' in script_target.read_text(encoding='utf-8')
        headings.write_text(r'\begin{document}\section{Own}\subsection*{Child}'
                            r'\subsubsection{Math $x^2$}\end{document}', encoding='utf-8')
        native_headings = read_document(headings).document
        for index in range(2):
            target = root / f'headings-{index}.tex'
            heading_report = write_document(native_headings, target)
            assert heading_report.success and heading_report.metrics['latex_route'] == 'native-text-v1'
            native_headings = document_from_json(document_to_json(read_document(target).document))
            assert [get_heading(p).level for p in native_headings.sections[0].blocks] == [1, 2, 3]
            assert next(f for f in native_headings.sections[0].blocks[-1].content if isinstance(f, Formula)).value == 'x^2'
            assert r'\section{Own}' in target.read_text(encoding='utf-8')
            assert r'\subsection*{Child}' in target.read_text(encoding='utf-8')
        list_source = root / 'source-list.tex'
        list_source.write_text(r'\begin{enumerate}\item First\par Continuation\end{enumerate} Outside', encoding='utf-8')
        list_model = read_document(list_source).document
        assert [p.plain_text for p in list_model.sections[0].blocks] == ['First', 'Continuation', 'Outside']
        assert get_list_item(list_model.sections[0].blocks[1]).continuation_of is not None
        assert [entry.number for entry in iter_list_numbers(list_model)] == [1, None]
        for index in range(2):
            target = root / f'lists-{index}.tex'
            list_report = write_document(list_model, target)
            assert list_report.success and list_report.metrics['latex_route'] == 'native-text-v1'
            list_model = document_from_json(document_to_json(read_document(target).document))
            assert [entry.number for entry in iter_list_numbers(list_model)] == [1, None]
        native_math = DocumentModel(sections=[Section(blocks=[Paragraph(content=[
            TextRun('Before '), Formula(r'\frac{x}{2}', FormulaFormat.LATEX, fallback_text='own fraction'),
            Formula(r'\begin{pmatrix}1&2\\3&4\end{pmatrix}', FormulaFormat.LATEX, display=True),
            TextRun(' after'),
        ])])])
        for index in range(2):
            target = root / f'math-{index}.tex'
            report = write_document(native_math, target)
            assert report.success and report.metrics['latex_route'] == 'native-text-v1'
            native_math = document_from_json(document_to_json(read_document(target).document))
            paragraph, = native_math.sections[0].blocks
            formulas = [run for run in paragraph.content if isinstance(run, Formula)]
            assert [(f.value, f.display, f.fallback_text) for f in formulas] == [
                (r'\frac{x}{2}', False, 'own fraction'), (r'\begin{pmatrix}1&2\\3&4\end{pmatrix}', True, ''),
            ]
        book = root / "base-writer.epub"
        from opendoc_formats.readers.epub_package import read_epub_package

        book_report = write_document(DocumentModel(metadata={"creator": ["Own author"], "identifier": "urn:example:installed"},
                                                    sections=[Section(blocks=[Paragraph(content=[TextRun("Own EPUB")])])]), book)
        assert book_report.success and book_report.metrics["output_verified"], book_report.to_dict()
        assert read_epub_package(book).spine == (("chapter", "yes"),)
        assert read_epub_package(book).dc_values["creator"] == ("Own author",)
        assert read_epub_package(book).metadata["identifier"] == "urn:example:installed"
        for cancel_model, cancel_target in ((native_tex, native_target), (native_math, target), (native_tex, book)):
            previous = cancel_target.read_bytes()
            export_polls = 0

            def stop_text_export() -> bool:
                nonlocal export_polls
                export_polls += 1
                return export_polls >= 12

            refused_export = write_document(cancel_model, cancel_target, options=ExportOptions(cancelled=stop_text_export))
            assert export_polls == 12 and not refused_export.success
            assert any(issue.feature == 'export.cancelled' for issue in refused_export.issues)
            assert cancel_target.read_bytes() == previous
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
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            inspected = inspect_path(path, options=ImportOptions(document_limits=DocumentLimits(max_nodes=200000)))
            assert inspected.valid and inspected.metadata['inspection_status'] == 'completed', inspected.to_dict()
            assert inspected.metadata['inspection_source_sha256'] == digest
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
            if format_id in {'txt', 'json', 'docx', 'pptx'}:
                refused = inspect_path(path, options=ImportOptions(document_limits=DocumentLimits(max_nodes=10)))
                assert not refused.valid and refused.metadata['document_limit']['maximum'] == 10
            if format_id != "latex" and (args.all_formats or format_id != "html"):
                result = read_document(path)
                assert result.success, result.issues
                assert result.document.validate() == []
                assert "Cell" in str(result.document)
                if format_id in {'docx', 'pptx'}:
                    native_polls = 0

                    def stop_native() -> bool:
                        nonlocal native_polls
                        native_polls += 1
                        return native_polls >= 12

                    cancelled = read_document(path, options=ImportOptions(cancelled=stop_native))
                    assert native_polls == 12
                    assert cancelled.document is None and any(issue.code == 'import.cancelled' for issue in cancelled.issues)
                    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
                    assert document_to_json(read_document(path).document) == document_to_json(result.document)
                    export_polls = 0

                    def stop_export() -> bool:
                        nonlocal export_polls
                        export_polls += 1
                        return export_polls >= 12

                    cancelled_export = write_document(document, path, options=ExportOptions(cancelled=stop_export))
                    assert export_polls == 12 and not cancelled_export.success
                    assert any(issue.feature == 'export.cancelled' for issue in cancelled_export.issues)
                    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
            if args.all_formats and format_id == "docx":
                from opendoc_model import (
                    Heading,
                    TableIndent,
                    TabStop,
                    TabStops,
                    WidthMeasure,
                    get_heading,
                    get_preferred_width,
                    get_tab_stops,
                    get_table_indent,
                    set_heading,
                    set_preferred_width,
                    set_tab_stops,
                    set_table_indent,
                )
                from opendoc_model.document_codec import document_from_json, document_to_json

                heading = Paragraph([TextRun("Own formal heading")])
                set_tab_stops(heading, TabStops((TabStop(396, alignment='right', leader='line'),)))
                set_heading(heading, Heading(2))
                width_cell = TableCell([Paragraph([TextRun("Own typed width")])])
                width_table = Table([TableRow([width_cell])])
                set_table_indent(width_table, TableIndent(30))
                set_preferred_width(width_table, WidthMeasure("relative", 0.8, "ratio", "content"))
                set_preferred_width(width_cell, WidthMeasure("absolute", 120, "pt"))
                heading_model = DocumentModel(sections=[Section(blocks=[heading, width_table])])
                for cycle in range(2):
                    heading_target = root / f"heading-{cycle}.docx"
                    restored = document_from_json(document_to_json(heading_model))
                    assert write_document(restored, heading_target).success
                    heading_result = read_document(heading_target)
                    assert heading_result.success, heading_result.issues
                    heading_model = heading_result.document
                    assert get_heading(heading_model.sections[0].blocks[0]) == Heading(2)
                    assert get_tab_stops(heading_model.sections[0].blocks[0]) == TabStops((
                        TabStop(396, alignment='right', leader='line'),
                    ))
                    returned_table = heading_model.sections[0].blocks[1]
                    assert get_table_indent(returned_table) == TableIndent(30)
                    assert get_preferred_width(returned_table) == WidthMeasure("relative", 0.8, "ratio", "content")
                    assert get_preferred_width(returned_table.rows[0].cells[0]) == WidthMeasure("absolute", 120, "pt")
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
