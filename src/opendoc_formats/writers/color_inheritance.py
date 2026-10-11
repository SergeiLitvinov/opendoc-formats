"""Resolve DOCX color and spacing in a private renderer view, preserving public declarations."""

from __future__ import annotations

from copy import deepcopy

from opendoc_model import (
    LINE_SPACING_PROPERTY,
    DocumentModel,
    Paragraph,
    TextRun,
    TextStyle,
    get_line_spacing,
    resolve_style,
    walk_model,
)
from opendoc_model.color import ColorValue
from opendoc_model.limits import DocumentLimits


def materialize_docx_colors(document: DocumentModel, limits: DocumentLimits | None = None) -> DocumentModel:
    if document.source_format != 'docx':
        return document
    prepared = deepcopy(document)
    from opendoc_formats.ooxml.spacing import prepare_legacy_spacing_view

    for style in prepared.styles.values():
        prepare_legacy_spacing_view(style, limits)
    context = DocumentModel(styles=prepared.styles, resources=prepared.resources)
    cache = {}

    def named_style(identifier: str | None) -> TextStyle | None:
        if identifier is None:
            return None
        if identifier not in cache:
            cache[identifier] = resolve_style(context, identifier, limits=limits)
        return cache[identifier]

    def named_color(identifier: str | None) -> ColorValue | str | None:
        style = named_style(identifier)
        return style.color if style is not None else None

    for reference in walk_model(prepared, limits=limits):
        paragraph = reference.node
        if not isinstance(paragraph, Paragraph):
            continue
        prepare_legacy_spacing_view(paragraph, limits)
        style = named_style(paragraph.style_id)
        declaration = get_line_spacing(paragraph, limits=limits)
        if declaration is None and LINE_SPACING_PROPERTY not in paragraph.properties and style is not None:
            declaration = get_line_spacing(style, limits=limits)
        if declaration is not None or LINE_SPACING_PROPERTY in paragraph.properties:
            paragraph.properties.pop('line_spacing', None)
            paragraph.properties.pop('line_spacing_pt', None)
        if declaration is not None and declaration.rule is not None:
            # Renderers keep their existing finite preview; the public model stays direct-only.
            paragraph.properties['line_spacing' if declaration.rule == 'relative' else 'line_spacing_pt'] = declaration.value
        inherited = named_color(paragraph.style_id)
        for run in paragraph.content:
            if isinstance(run, TextRun) and run.style.color is None:
                character = named_color(run.style.properties.base_style_id)
                run.style.color = deepcopy(character if character is not None else inherited)
    prepared.validate(limits=limits)
    return prepared
