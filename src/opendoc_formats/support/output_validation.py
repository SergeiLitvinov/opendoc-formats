"""Readability checks for staged exports; these do not measure visual fidelity."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile


class _HTMLStructure(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag)


def validate_output(path: Path, format_id: str) -> None:
    """Raise if a built-in export cannot be reopened by its selected backend.

    Office checks include ZIP CRC and the main XML part. HTML checks the outer
    document structure; LaTeX checks delimiters, without running a TeX engine.
    """
    if format_id == "txt":
        path.read_text(encoding="utf-8")
    elif format_id == "json":
        from opendoc import load_document

        errors = load_document(path).validate()
        if errors:
            raise ValueError("; ".join(errors))
    elif format_id == "html":
        parser = _HTMLStructure()
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()
        if not {"html", "head", "body"} <= parser.tags:
            raise ValueError("HTML export is missing the document structure")
    elif format_id in {"docx", "pptx"}:
        part = "word/document.xml" if format_id == "docx" else "ppt/presentation.xml"
        with ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"ZIP checksum failed: {bad}")
            ET.fromstring(archive.read("[Content_Types].xml"))
            ET.fromstring(archive.read(part))
        if format_id == "docx":
            from docx import Document

            Document(str(path))
        else:
            from pptx import Presentation

            Presentation(str(path))
    elif format_id == "pdf":
        import fitz

        with fitz.open(path) as document:
            if document.needs_pass or document.page_count < 1:
                raise ValueError("PDF export is encrypted or has no pages")
            for page in document:
                page.get_text()
    elif format_id == "latex":
        source = path.read_text(encoding="utf-8")
        if r"\begin{document}" not in source or r"\end{document}" not in source:
            raise ValueError("LaTeX export is missing document delimiters")
    else:
        raise ValueError(f"No output validator for {format_id}")
