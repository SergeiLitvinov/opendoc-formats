"""EPUB → Text.

Использует собственный EPUB-контейнер и BeautifulSoup для XHTML.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Union

import opendoc_model as od

from opendoc_formats.support.cancellation import cancellation_scope, check_cancelled
from opendoc_formats.support.document_adapters import document_to_text
from opendoc_formats.support.text_diagnostics import append_text_warning
from opendoc_formats.types import DocFormat, Text


def read_epub(path: Union[str, Path], *, backend: str = "native", include_nonlinear: bool = False,
              limits: od.DocumentLimits | None = None, cancelled: Callable[[], bool] | None = None) -> Text:
    """Project the common spine reader to Text, retaining located loss diagnostics."""
    with cancellation_scope(cancelled, 'EPUB legacy text', inherit=True):
        return _read_epub(path, backend=backend, include_nonlinear=include_nonlinear, limits=limits, cancelled=cancelled)


def _read_epub(path: Union[str, Path], *, backend: str, include_nonlinear: bool,
               limits: od.DocumentLimits | None, cancelled: Callable[[], bool] | None) -> Text:
    check_cancelled(cancelled, 'EPUB text import')
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    try:
        __import__('bs4')
    except ImportError:
        result = Text(
            source_format=DocFormat.EPUB,
            engine="native-epub",
        )
        append_text_warning(result, od.DiagnosticIssue(
            'epub.text-backend-unavailable', od.IssueSeverity.LOSS, 'beautifulsoup4 not installed',
            str(p), reason='epub-text-backend-unavailable',
        ), od.Provenance('epub', str(p), object_id='text-extraction'))
        return result

    model = read_epub_model(p, backend=backend, include_nonlinear=include_nonlinear, limits=limits, cancelled=cancelled)
    return document_to_text(model, limits=limits)


def read_epub_model(path: Union[str, Path], *, backend: str = "native", include_nonlinear: bool = False,
                    limits: od.DocumentLimits | None = None, cancelled: Callable[[], bool] | None = None) -> od.DocumentModel:
    """Import EPUB spine chapters, links, media, and basic CSS into DocumentModel."""
    from opendoc_formats.readers.epub_model import read_epub_model as read_model

    return read_model(path, backend=backend, include_nonlinear=include_nonlinear, limits=limits, cancelled=cancelled)


__all__ = ["read_epub", "read_epub_model"]
