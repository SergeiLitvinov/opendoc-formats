"""Resolve DOCX colors in a private renderer view, preserving public declarations."""

from __future__ import annotations

from copy import deepcopy

from opendoc_model import DocumentModel, Paragraph, TextRun, resolve_style, walk_model
from opendoc_model.color import ColorValue
from opendoc_model.limits import DocumentLimits


def materialize_docx_colors(document: DocumentModel, limits: DocumentLimits | None = None) -> DocumentModel:
    if document.source_format != 'docx':
        return document
    prepared = deepcopy(document)
    context = DocumentModel(styles=prepared.styles, resources=prepared.resources)
    cache = {}

    def named_color(identifier: str | None) -> ColorValue | str | None:
        if identifier is None:
            return None
        if identifier not in cache:
            cache[identifier] = resolve_style(context, identifier, limits=limits).color
        return cache[identifier]

    for reference in walk_model(prepared, limits=limits):
        paragraph = reference.node
        if not isinstance(paragraph, Paragraph):
            continue
        inherited = named_color(paragraph.style_id)
        for run in paragraph.content:
            if isinstance(run, TextRun) and run.style.color is None:
                character = named_color(run.style.properties.base_style_id)
                run.style.color = deepcopy(character if character is not None else inherited)
    return prepared
