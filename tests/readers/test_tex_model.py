"""Own source LaTeX fixtures: semantic text, inert commands and source spans through JSON."""

import builtins

import pytest
from opendoc_model import Formula, FormulaFormat, TextRun, document_from_json, document_to_json, get_integration

from opendoc_formats import read_document, write_document
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError
from opendoc_formats.readers.tex_model import read_tex_model
from opendoc_formats.readers.tex_source import tokenize_tex


def test_source_text_styles_headings_math_lists_refs_and_json(tmp_path, monkeypatch):
    source = tmp_path / "own.tex"
    raw = r"""\documentclass{article}
\title{Own title}
\author{Own author}
\begin{document}
\section{Start}\label{start}
Before \textbf{bold \textit{both}} after \ref{start}.

Price \$5, caf\'{e}, \% and $x^2$.
\[\frac{1}{2}\]
\begin{itemize}
\item First
\item Second
\begin{enumerate}\item Nested\end{enumerate}
\end{itemize}
\end{document}
""".encode()
    source.write_bytes(raw)
    original = builtins.__import__

    def no_engines(name, *args, **kwargs):
        if name.split(".")[0] in {"docx", "lxml", "bs4", "ebooklib", "pylatexenc"}:
            raise ImportError("Optional engine is absent")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_engines)
    result = read_document(source)
    assert result.success and result.format_id == "latex" and not result.lossless and not result.assessment_complete
    blocks = result.document.sections[0].blocks
    assert blocks[0].style_id == "Heading 1" and blocks[0].properties["anchor_id"] == "start"
    assert blocks[1].plain_text == "Before bold both after start."
    both = next(item for item in blocks[1].content if isinstance(item, TextRun) and item.text == "both")
    assert both.style.bold and both.style.italic
    assert next(item for item in blocks[1].content if item.link).link == "#start"
    assert blocks[2].plain_text == "Price $5, café, % and x^2."
    inline = next(item for item in blocks[2].content if isinstance(item, Formula))
    assert inline.format is FormulaFormat.LATEX and inline.value == "x^2" and not inline.display
    assert blocks[3].content[0].value == r"\frac{1}{2}" and blocks[3].content[0].display
    assert [(b.plain_text, b.properties.get("list_level")) for b in blocks[4:]] == [("First", 0), ("Second", 0), ("Nested", 1)]
    assert result.document.metadata["title"] == "Own title"
    assert result.document.resources["latex-original-source"].data == raw
    restored = document_from_json(document_to_json(result.document))
    assert document_to_json(restored) == document_to_json(result.document)
    text = raw.decode()
    span = both.properties["source_span"]
    assert text[span["start"] : span["end"]] == "both"
    assert both.provenance.source_path == str(source)
    assert all(record.extra["source_span"]["source"] == str(source) for record in get_integration(restored).preservation)
    output = tmp_path / "own.html"
    report = write_document(restored, output)
    assert report.success and any(issue.feature == "latex.source" for issue in report.issues)
    assert "<h1" in output.read_text(encoding="utf-8")


def test_comments_escapes_accents_and_local_style_scope(tmp_path):
    source = tmp_path / "escapes.tex"
    source.write_text("a% comment\nb {\\bfseries bold} plain caf\\'e\\% ~ end", encoding="utf-8")
    result = read_document(source)
    assert result.success
    block = result.document.sections[0].blocks[0]
    assert block.plain_text == "ab bold plain café% \u00a0 end"
    assert next(item for item in block.content if item.text == "plain").style.bold is None


def test_file_and_macro_commands_are_inert_located_and_json_preserved(tmp_path, monkeypatch):
    from pathlib import Path

    source = tmp_path / "inert.tex"
    raw = r"\input{../secret.tex}\includegraphics{https://invalid.example/image}\newcommand{\hello}[1]{Hello #1}\hello{Reader}"
    source.write_text(raw, encoding="utf-8")
    opened = []
    original = Path.open

    def only_source(self, *args, **kwargs):
        opened.append(self)
        assert self == source, "File commands must not read another source"
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", only_source)
    result = read_document(source)
    assert result.success and opened == [source]
    assert {issue.reason for issue in result.issues} == {
        "inactive-command",
        "unexpanded-macro",
        "unknown-command",
        "inert-original-source",
    }
    assert all(issue.location.startswith(str(source) + ":") for issue in result.issues)
    ledger = get_integration(document_from_json(document_to_json(result.document)))
    assert all(record.extra["resource_id"] == "latex-original-source" for record in ledger.preservation)


@pytest.mark.parametrize(
    "text", [r"\textbf{Unclosed", r"\begin{itemize}\end{enumerate}", "$unclosed", r"\[unclosed", "Unexpected}"]
)
def test_invalid_source_is_an_explicit_failure(tmp_path, text):
    source = tmp_path / "invalid.tex"
    source.write_text(text, encoding="utf-8")
    with pytest.raises(InvalidDocumentError):
        read_document(source)


def test_input_token_depth_and_cancellation_limits(tmp_path):
    source = tmp_path / "limits.tex"
    source.write_text("x" * 32, encoding="utf-8")
    with pytest.raises(ResourceLimitError):
        read_tex_model(source, max_input_bytes=10)
    with pytest.raises(ResourceLimitError):
        tokenize_tex("a b c", max_tokens=3)
    source.write_text("{" * 65 + "deep" + "}" * 65, encoding="utf-8")
    with pytest.raises(ResourceLimitError):
        read_tex_model(source)
    with pytest.raises(OperationCancelledError):
        read_tex_model(source, cancelled=lambda: True)
    with pytest.raises(ValueError):
        read_tex_model(source, max_input_bytes=-1)
