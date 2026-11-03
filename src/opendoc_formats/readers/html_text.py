"""Lazy public HTML readers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import opendoc_model as od

from opendoc_formats.support.cancellation import cancellation_scope
from opendoc_formats.support.document_adapters import document_to_text
from opendoc_formats.support.text_diagnostics import append_text_warning
from opendoc_formats.types import DocFormat, Text


def read_html_model(path: str | Path, *, resource_root: str | Path | None = None,
                    limits: od.DocumentLimits | None = None, cancelled: Callable[[], bool] | None = None) -> od.DocumentModel:
    from opendoc_formats.readers.html import read_html_model as read_model

    return read_model(path, resource_root=resource_root, limits=limits, cancelled=cancelled)


def read_html(path: str | Path, *, limits: od.DocumentLimits | None = None,
              cancelled: Callable[[], bool] | None = None) -> Text:
    with cancellation_scope(cancelled, 'HTML legacy text', inherit=True):
        return _read_html(path, limits=limits, cancelled=cancelled)


def _read_html(path: str | Path, *, limits: od.DocumentLimits | None, cancelled: Callable[[], bool] | None) -> Text:
    try:
        model = read_html_model(path, limits=limits, cancelled=cancelled)
    except ImportError:
        result = Text(source_format=DocFormat.HTML, engine="bs4+tinycss2")
        append_text_warning(result, od.DiagnosticIssue(
            'html.text-backend-unavailable', od.IssueSeverity.LOSS, 'Install opendoc-formats[html]',
            str(path), reason='html-text-backend-unavailable',
        ), od.Provenance('html', str(path), object_id='text-extraction'))
        return result
    return document_to_text(model, limits=limits)
