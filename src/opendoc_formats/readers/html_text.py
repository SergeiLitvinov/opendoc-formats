"""Lazy public HTML readers."""

from __future__ import annotations

from pathlib import Path

import opendoc_model as od

from opendoc_formats.support.document_adapters import document_to_text
from opendoc_formats.types import DocFormat, Text


def read_html_model(path: str | Path, *, resource_root: str | Path | None = None) -> od.DocumentModel:
    from opendoc_formats.readers.html import read_html_model as read_model

    return read_model(path, resource_root=resource_root)


def read_html(path: str | Path) -> Text:
    try:
        model = read_html_model(path)
    except ImportError:
        return Text(source_format=DocFormat.HTML, engine="bs4+tinycss2", warnings=["Install opendoc-formats[html]"])
    result = document_to_text(model)
    result.warnings.extend(item["message"] for item in model.metadata["html"]["warnings"])
    return result
