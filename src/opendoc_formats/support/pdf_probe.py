"""Small PDF checks use an already installed profile instead of requiring another parser."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from opendoc_formats.errors import (
    EncryptedDocumentError,
    InvalidDocumentError,
    ResourceLimitError,
    UnsupportedDocumentError,
)
from opendoc_formats.native.pdf_metadata import read_info, read_page_count


def probe_pdf(path: str | Path, *, metadata: bool = False) -> tuple[int | None, dict[str, str]]:
    """Read page count and optional Info fields without extracting page content.

    Prove the page tree natively when possible; preserve backend compatibility for
    inputs the native profile cannot accept. Metadata-only requests keep backend
    precedence because engines can choose different values for conflicting fields.
    """
    result = {'title': '', 'author': '', 'subject': ''}
    native_error = None
    if not metadata:
        try:
            return read_page_count(path), result
        except (InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError) as error:
            native_error = error
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
            if metadata:
                info = document.metadata or {}
                for key in result:
                    native_key = '/' + key.title() if name == 'pypdf' else key if name == 'pymupdf' else key.title()
                    value = info.get(native_key)
                    result[key] = value if isinstance(value, str) else ''
            return count, result
    if native_error is not None:
        raise native_error
    return None, read_info(path)
