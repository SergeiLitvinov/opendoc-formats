"""Small PDF checks use an already installed profile instead of requiring another parser."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from opendoc_formats.errors import BackendUnavailableError, EncryptedDocumentError, InvalidDocumentError


def probe_pdf(path: str | Path, *, metadata: bool = False) -> tuple[int | None, dict[str, str]]:
    """Read page count and optional Info fields without extracting page content.

    Prefer the existing pypdf behavior when installed. Minimal rich/layout profiles
    use their own engine; parser errors are preserved rather than hidden by repair.
    This checks readability, not conformance to the complete PDF specification.
    Metadata-only requests leave the page count unknown and do not traverse pages.
    """
    for name in ('pypdf', 'pymupdf', 'pdfplumber'):
        try:
            module = import_module(name)
        except ImportError:
            continue
        opener = module.PdfReader if name == 'pypdf' else module.open
        with opener(str(path)) as document:
            if name == 'pymupdf':
                if not document.is_pdf:
                    raise InvalidDocumentError('Expected a PDF document')
                if document.needs_pass:
                    raise EncryptedDocumentError('PDF requires a password')
                count = None if metadata else document.page_count
            else:
                count = None if metadata else len(document.pages)
            result = {'title': '', 'author': '', 'subject': ''}
            if metadata:
                info = document.metadata or {}
                for key in result:
                    native_key = '/' + key.title() if name == 'pypdf' else key if name == 'pymupdf' else key.title()
                    value = info.get(native_key)
                    result[key] = value if isinstance(value, str) else ''
            return count, result
    raise BackendUnavailableError('Install one PDF profile: pdf-text, pdf-rich or pdf-layout')
