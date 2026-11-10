"""Readability checks for staged exports; these do not measure visual fidelity."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from opendoc_formats.support.cancellation import cancellation_requested, checkpoint
from opendoc_formats.support.io import iter_archive_member


def _check_zip_crc(archive: ZipFile) -> None:
    for member in archive.infolist():
        checkpoint()
        try:
            for _ in iter_archive_member(archive, member):
                pass
        except BadZipFile as error:
            raise ValueError(f"ZIP checksum failed: {member.filename}") from error


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
        from opendoc_model import load_document

        errors = load_document(path).validate()
        if errors:
            raise ValueError("; ".join(errors))
    elif format_id == "html":
        parser = _HTMLStructure()
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()
        if not {"html", "head", "body"} <= parser.tags:
            raise ValueError("HTML export is missing the document structure")
    elif format_id == "epub":
        from opendoc_formats.readers.epub_package import read_epub_package

        package = read_epub_package(path, cancelled=cancellation_requested)
        with ZipFile(path) as archive:
            first = archive.infolist()[0]
            if first.filename != "mimetype" or first.compress_type != 0 or first.extra:
                raise ValueError("EPUB mimetype must be first, stored and without extra fields")
            _check_zip_crc(archive)
        if not package.spine:
            raise ValueError("EPUB export has no spine")
        for item in package.items.values():
            checkpoint()
            if item.media_type in {"application/xhtml+xml", "image/svg+xml"}:
                ET.fromstring(item.content)
    elif format_id in {"docx", "pptx"}:
        with ZipFile(path) as archive:
            _check_zip_crc(archive)
            ET.fromstring(archive.read("[Content_Types].xml"))
            if format_id == "docx":
                from docx import Document

                part = str(Document(str(path)).part.partname).lstrip('/')
            else:
                from pptx import Presentation

                part = str(Presentation(str(path)).part.partname).lstrip('/')
            checkpoint()
            ET.fromstring(archive.read(part))
    elif format_id == "pdf":
        import pymupdf as fitz

        with fitz.open(path) as document:
            if document.needs_pass or document.page_count < 1:
                raise ValueError("PDF export is encrypted or has no pages")
            for page in document:
                checkpoint()
                page.get_text()
    elif format_id == "latex":
        source = path.read_text(encoding="utf-8")
        if r"\begin{document}" not in source or r"\end{document}" not in source:
            raise ValueError("LaTeX export is missing document delimiters")
    else:
        raise ValueError(f"No output validator for {format_id}")
