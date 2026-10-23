"""Lazy public HTML readers."""

from __future__ import annotations

from pathlib import Path

import opendoc_model as od

from opendoc_formats.support.document_adapters import document_to_text
from opendoc_formats.support.text_diagnostics import append_text_warning
from opendoc_formats.types import DocFormat, Text


def read_html_model(path: str | Path, *, resource_root: str | Path | None = None) -> od.DocumentModel:
    from opendoc_formats.readers.html import read_html_model as read_model

    return read_model(path, resource_root=resource_root)


def read_html(path: str | Path) -> Text:
    try:
        model = read_html_model(path)
    except ImportError:
        result = Text(source_format=DocFormat.HTML, engine="bs4+tinycss2")
        append_text_warning(result, od.DiagnosticIssue(
            'html.text-backend-unavailable', od.IssueSeverity.LOSS, 'Install opendoc-formats[html]',
            str(path), reason='html-text-backend-unavailable',
        ), od.Provenance('html', str(path), object_id='text-extraction'))
        return result
    return document_to_text(model)
