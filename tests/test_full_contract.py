"""Standalone installed-adapter acceptance; real format cycles, no application."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from opendoc_model import DocumentModel, Paragraph, Section, TextRun

from opendoc_formats import (
    ExporterRegistry,
    ExporterSpec,
    ExportOptions,
    default_exporter_registry,
    default_registry,
    read_document,
    write_document,
)


@pytest.mark.parametrize("format_id", ["txt", "html", "docx", "pptx", "pdf", "json"])
def test_real_format_export_import_cycle(tmp_path, format_id):
    document = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun("Standalone document 123")])])])
    suffix = ".html" if format_id == "html" else "." + format_id
    path = tmp_path / ("document" + suffix)
    report = write_document(document, path)
    assert report.success, report.to_dict()
    assert path.is_file()
    result = read_document(path)
    assert result.success, result.issues
    from opendoc_formats.support.document_adapters import document_to_text

    assert "Standalone document 123" in document_to_text(result.document).plain
    assert result.document.validate() == []


def test_registry_declares_all_existing_model_routes():
    assert {adapter.id for adapter in default_registry().adapters()} == {
        "latex",
        "txt",
        "html",
        "docx",
        "pptx",
        "pdf",
        "epub",
        "json",
        "djvu",
    }
    assert {adapter.id for adapter in default_exporter_registry().exporters()} == {
        "epub",
        "txt",
        "html",
        "docx",
        "pptx",
        "pdf",
        "json",
        "latex",
    }


def test_export_invalid_model_and_cancellation_preserve_previous_file(tmp_path):
    from opendoc_model import ConversionReport

    output = tmp_path / "result.txt"
    output.write_text("previous", encoding="utf-8")
    document = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun("changed")])])])
    registry = ExporterRegistry()
    cancelled = [False]

    def writer(model, path):
        path.write_text("replacement", encoding="utf-8")
        cancelled[0] = True
        return ConversionReport(path)

    registry.register(ExporterSpec("custom", (".txt",), writer))
    assert not registry.write(document, output, options=ExportOptions(cancelled=lambda: cancelled[0])).success
    assert output.read_text(encoding="utf-8") == "previous"
    assert not list(tmp_path.glob(".opendoc-formats-export-*"))
    document.sections[0].blocks[0].properties["invalid"] = float("nan")
    assert not write_document(document, output).success
    assert output.read_text(encoding="utf-8") == "previous"


def test_every_module_has_no_application_import():
    import opendoc_formats

    for path in Path(opendoc_formats.__file__).parent.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            assert not any(name.startswith("textalchemy") for name in names), path
    code = "import importlib.util; import opendoc_formats; assert importlib.util.find_spec('textalchemy') is None"
    subprocess.run([sys.executable, "-I", "-c", code], check=True)


def test_latex_export_and_text_rendering_are_independent(tmp_path):
    from opendoc_formats.support.latex import escape_latex
    from opendoc_formats.types import Block, BlockType, Text
    from opendoc_formats.writers.text_render import render_latex, render_latex_pandoc

    text = Text(blocks=[Block(BlockType.HEADING, "Heading", level=1), Block(BlockType.PARAGRAPH, "A & B")])
    source = render_latex(text=text, title="Title", author="Author")
    assert r"\section{Heading}" in source and r"A \& B" in source
    assert render_latex_pandoc(text=text, input_path=None) == render_latex(text=text)
    assert escape_latex("50%") == r"50\%"
    model = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun("Independent LaTeX")])])])
    output = tmp_path / "document.tex"
    report = write_document(model, output)
    assert report.success, report.to_dict()
    assert "Independent LaTeX" in output.read_text(encoding="utf-8")
    assert any(issue.feature == "latex-layout" for issue in report.issues)


def test_pandoc_uses_distributed_lua_filter(tmp_path, monkeypatch):
    from opendoc_formats.readers import latex

    source = tmp_path / "source.docx"
    source.write_bytes(b"input")

    def pandoc(command, **kwargs):
        assert "--lua-filter" in command
        filter_path = Path(command[command.index("--lua-filter") + 1])
        assert filter_path.is_file() and "opendoc_formats" in str(filter_path)
        Path(command[command.index("-o") + 1]).write_text(r"\begin{document}Body\end{document}", encoding="utf-8")

    monkeypatch.setattr(latex.subprocess, "run", pandoc)
    output = tmp_path / "document.tex"
    assert "Body" in latex.docx_to_latex_pandoc(source, output)
    assert "Body" in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("format_id", ["txt", "tex", "docx"])
def test_raw_extracted_text_export_without_ocr(tmp_path, format_id):
    from opendoc_formats.writers.extracted_text import write_extracted_text

    path = tmp_path / ("text." + format_id)
    assert write_extracted_text("First & second", path, format_id=format_id) == path
    if format_id == "tex":
        assert r"First \& second" in path.read_text(encoding="utf-8")
    elif format_id == "docx":
        from opendoc_formats.readers.docx import read_docx_model

        assert read_docx_model(path).sections[0].blocks[0].plain_text == "First & second"
    else:
        assert path.read_text(encoding="utf-8") == "First & second"
