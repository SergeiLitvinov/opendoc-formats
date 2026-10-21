"""DOCX style exporter for definitions, font formatting, and numbering."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from opendoc_model import LINE_SPACING_PROPERTY
from opendoc_model.diagnostics import ConversionReport, IssueSeverity
from opendoc_model.document_model import TextStyle
from opendoc_model.limits import DocumentLimits

from opendoc_formats.support.cancellation import cancellable_items, checkpoint


def write_styles(
    target: Any, styles: dict[str, TextStyle], report: ConversionReport, *, limits: DocumentLimits | None = None,
) -> None:
    from docx.enum.style import WD_STYLE_TYPE

    created: dict[str, Any] = {}
    for style_id, source in styles.items():
        checkpoint()
        properties = source.properties
        if properties.get('docx_run_position_pt') is not None:
            report.add(IssueSeverity.ERROR, 'docx.run-position',
                       'This finite profile supports baseline shifts on direct runs only', f'styles[{style_id}]')
            continue
        from opendoc_formats.ooxml.paragraph_flow import FIELDS, export_flow

        if properties.style_type in {"character", "table"} and any(
            properties.get(key) is not None for key in cancellable_items(FIELDS)
        ):
            report.add(IssueSeverity.ERROR, 'docx.paragraph-flow',
                       'Paragraph flow requires a paragraph style or document defaults', f'styles[{style_id}]')
            continue
        from opendoc_formats.ooxml.paragraph_indent import ATTRIBUTES

        if properties.style_type in {"character", "table"} and any(
            properties.get(key) is not None for key in cancellable_items(ATTRIBUTES)
        ):
            report.add(IssueSeverity.ERROR, 'docx.paragraph-indent',
                       'Paragraph indentation requires a paragraph style or document defaults', f'styles[{style_id}]')
            continue
        if (LINE_SPACING_PROPERTY in properties
                and properties.style_type in {'character', 'table'}):
            report.add(IssueSeverity.ERROR, 'docx.line-spacing',
                       'Common line spacing requires a paragraph style or document defaults in this Word profile',
                       f'styles[{style_id}]')
            continue
        if properties.style_type == "document-default":
            from opendoc_formats.ooxml.word_color import apply_color, default_color_owner

            apply_color(default_color_owner(target.styles.element), source)
            from opendoc_formats.ooxml.spacing import default_spacing_owner, export_spacing

            export_spacing(properties, default_spacing_owner(target.styles.element), report, 'styles[__doc_defaults__]',
                           limits=limits)
            from opendoc_formats.ooxml.paragraph_indent import export_indents

            export_indents(properties, default_spacing_owner(target.styles.element), report, 'styles[__doc_defaults__]')
            export_flow(properties, default_spacing_owner(target.styles.element), report, 'styles[__doc_defaults__]')
            continue
        style_name = properties.style_name or style_id
        style_type_name = str(properties.style_type or "paragraph").upper()
        style_type = getattr(WD_STYLE_TYPE, style_type_name, WD_STYLE_TYPE.PARAGRAPH)
        try:
            style = target.styles[style_name]
            if style.type != style_type:
                report.add(
                    IssueSeverity.WARNING,
                    "style-type",
                    f"style {style_name!r} exists with incompatible type {style.type.name.lower()}",
                )
                continue
        except KeyError:
            style = target.styles.add_style(style_name, style_type)
        created[style_id] = style
        apply_font_style(style.font, source)
        _apply_style_language(style, source.language)
        if style_type == WD_STYLE_TYPE.PARAGRAPH:
            apply_paragraph_format(style.paragraph_format, properties, report, f'styles[{style_id}]', limits=limits)
            from opendoc_formats.ooxml.layout import export_layout

            export_layout(properties, style.element.get_or_add_pPr(), report, f'styles[{style_id}]')
            apply_numbering(style.element.get_or_add_pPr(), properties)
        if properties.hidden is not None:
            style.hidden = properties.hidden
        if properties.priority is not None:
            style.priority = properties.priority

    for style_id, source in styles.items():
        checkpoint()
        style = created.get(style_id)
        base_style = created.get(source.properties.base_style_id)
        if style is not None and base_style is not None and style != base_style:
            style.base_style = base_style


def apply_paragraph_format(
    paragraph_format: Any, properties: Mapping[str, Any], report: ConversionReport, location: str,
    *, limits: DocumentLimits | None = None,
) -> None:
    from opendoc_formats.ooxml.paragraph_flow import export_flow
    from opendoc_formats.ooxml.paragraph_indent import export_indents

    export_indents(properties, paragraph_format._element.get_or_add_pPr(), report, location)
    export_flow(properties, paragraph_format._element.get_or_add_pPr(), report, location)
    from opendoc_formats.ooxml.spacing import export_spacing

    export_spacing(properties, paragraph_format._element.get_or_add_pPr(), report, location, limits=limits)


def apply_numbering(paragraph_properties: Any, properties: Mapping[str, Any]) -> None:
    if properties.get("numbering_id") is None:
        return
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    existing = paragraph_properties.find(qn("w:numPr"))
    if existing is not None:
        paragraph_properties.remove(existing)
    number_properties = OxmlElement("w:numPr")
    if properties.get("numbering_level") is not None:
        level = OxmlElement("w:ilvl")
        level.set(qn("w:val"), str(int(properties["numbering_level"])))
        number_properties.append(level)
    number_id = OxmlElement("w:numId")
    number_id.set(qn("w:val"), str(int(properties["numbering_id"])))
    number_properties.append(number_id)
    paragraph_properties.append(number_properties)


def apply_text_style(run: Any, style: TextStyle) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    apply_font_style(run.font, style)
    from opendoc_formats.ooxml.run_position import export_run_position

    export_run_position(style.properties, run._r.get_or_add_rPr())
    if style.language:
        run_properties = run._r.get_or_add_rPr()
        language = OxmlElement("w:lang")
        language.set(qn("w:val"), style.language)
        run_properties.append(language)


def apply_font_style(font: Any, style: TextStyle) -> None:
    from docx.shared import Pt

    from opendoc_formats.ooxml.word_color import apply_color

    if style.font_family:
        font.name = style.font_family
    if style.font_size:
        font.size = Pt(style.font_size.pt)
    font.bold = style.bold
    font.italic = style.italic
    font.underline = style.underline
    font.superscript = style.superscript
    font.subscript = style.subscript
    apply_color(font._element.get_or_add_rPr(), style)


def _apply_style_language(style: Any, language_code: str | None) -> None:
    if not language_code:
        return
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    run_properties = style.element.get_or_add_rPr()
    language = OxmlElement("w:lang")
    language.set(qn("w:val"), language_code)
    run_properties.append(language)


__all__ = [
    "apply_font_style",
    "apply_numbering",
    "apply_paragraph_format",
    "apply_text_style",
    "write_styles",
]
