"""DOCX style resolver for inheritance, themes, defaults, and numbering."""

from __future__ import annotations

from typing import Any

from opendoc_model.color import ColorValue
from opendoc_model.document_model import DocumentModel, Length, TextStyle

from opendoc_formats.ooxml.layout import import_layout
from opendoc_formats.ooxml.package import OOXML_NAMESPACES, RELATIONSHIP_TYPE, package_part_for_relationship


def read_document_styles(document: Any, model: DocumentModel | None = None) -> dict[str, TextStyle]:
    from docx.enum.style import WD_STYLE_TYPE

    result: dict[str, TextStyle] = {}
    for style in document.styles:
        if style.type not in {WD_STYLE_TYPE.PARAGRAPH, WD_STYLE_TYPE.CHARACTER, WD_STYLE_TYPE.TABLE}:
            continue
        properties = {
            "style_name": style.name,
            "style_type": style.type.name.lower(),
            "base_style_id": style.base_style.style_id if style.base_style is not None else None,
            "hidden": bool(style.hidden),
            "priority": style.priority,
        }
        if style.type is WD_STYLE_TYPE.PARAGRAPH:
            properties.update(_style_paragraph_properties(style))
            properties.update(_numbering_properties(style.element.pPr))
        result[style.style_id] = _resolved_font_style(style, properties=properties, model=model)
    return result


def read_document_defaults(document: Any, model: DocumentModel) -> TextStyle | None:
    from docx.oxml.ns import qn
    from lxml import etree

    run_defaults = document.styles.element.xpath("./w:docDefaults/w:rPrDefault/w:rPr")
    paragraph_defaults = document.styles.element.xpath("./w:docDefaults/w:pPrDefault/w:pPr")
    if not run_defaults and not paragraph_defaults:
        return None
    run_properties = run_defaults[0] if run_defaults else None
    fonts = run_properties.find(qn("w:rFonts")) if run_properties is not None else None
    font_theme = None
    font_family = None
    if fonts is not None:
        font_family, font_theme = _font_record_family(fonts, model)
    size = run_properties.find(qn("w:sz")) if run_properties is not None else None
    color = run_properties.find(qn("w:color")) if run_properties is not None else None
    resolved_color, color_properties = _word_color(color, model)
    vertical = run_properties.find(qn("w:vertAlign")) if run_properties is not None else None
    vertical_value = vertical.get(qn("w:val")) if vertical is not None else None
    language = run_properties.find(qn("w:lang")) if run_properties is not None else None
    from opendoc_formats.ooxml.spacing import import_spacing_nodes

    spacing_properties: dict[str, Any] = {}
    import_spacing_nodes(spacing_properties, paragraph_defaults)
    from opendoc_formats.ooxml.paragraph_indent import import_indents

    import_indents(spacing_properties, paragraph_defaults[0] if paragraph_defaults else None)
    from opendoc_formats.ooxml.paragraph_flow import import_flow

    import_flow(spacing_properties, paragraph_defaults[0] if paragraph_defaults else None)
    return TextStyle(
        font_family=font_family,
        font_size=Length(int(size.get(qn("w:val"))) / 2) if size is not None and size.get(qn("w:val")) else None,
        bold=_xml_bool(run_properties, "b"),
        italic=_xml_bool(run_properties, "i"),
        underline=_xml_underline(run_properties),
        superscript=True if vertical_value == "superscript" else None,
        subscript=True if vertical_value == "subscript" else None,
        color=resolved_color,
        language=language.get(qn("w:val")) if language is not None else None,
        properties={
            "style_name": "Document Defaults",
            "style_type": "document-default",
            "font_theme": font_theme,
            "docx_color_imported_value": resolved_color.to_dict() if isinstance(resolved_color, ColorValue) else resolved_color,
            **color_properties,
            **spacing_properties,
            "paragraph_defaults_xml": (etree.tostring(paragraph_defaults[0], encoding="unicode") if paragraph_defaults else None),
        },
    )


def read_run_style(run: Any, paragraph: Any, model: DocumentModel | None = None) -> TextStyle:
    sources = [run.font]
    sources.extend(style.font for style in _style_chain(run.style))
    sources.extend(style.font for style in _style_chain(paragraph.style))
    direct_fields = [
        name
        for name in (
            "font_family",
            "font_size",
            "bold",
            "italic",
            "underline",
            "superscript",
            "subscript",
            "color",
            "language",
        )
        if _direct_run_value(run, name) is not None
    ]
    color = _font_color([run.font], model)
    character_style = run._r.xpath('./w:rPr/w:rStyle')
    from docx.oxml.ns import qn

    return TextStyle(
        font_family=_font_family(sources, model),
        font_size=_font_size(_first_font_value(sources, "size")),
        bold=_first_font_value(sources, "bold"),
        italic=_first_font_value(sources, "italic"),
        underline=_underline(_first_font_value(sources, "underline")),
        superscript=_first_font_value(sources, "superscript"),
        subscript=_first_font_value(sources, "subscript"),
        color=color,
        language=_resolved_run_language(run, paragraph),
        properties={
            "style_id": run.style.style_id if run.style is not None else None,
            "style_name": run.style.name if run.style is not None else None,
            "direct_fields": direct_fields,
            "docx_color_imported_value": color.to_dict() if isinstance(color, ColorValue) else color,
            "docx_color_imported_direct": 'color' in direct_fields,
            "docx_character_style_id": character_style[0].get(qn('w:val')) if character_style else None,
            "base_style_id": character_style[0].get(qn('w:val')) if character_style else None,
            **_font_color_properties([run.font], model),
        },
    )


def read_paragraph_properties(paragraph: Any) -> dict[str, Any]:
    properties = _resolved_paragraph_values(
        [paragraph.paragraph_format, *[style.paragraph_format for style in _style_chain(paragraph.style)]]
    )
    properties.update(_resolved_numbering_properties(paragraph))
    import_layout(properties, paragraph._p.pPr)
    if paragraph.style is not None:
        properties["style_name"] = paragraph.style.name
        properties['docx_paragraph_style_imported'] = paragraph.style.style_id
    return properties


def _theme_typeface(model: DocumentModel, theme_key: str) -> str | None:
    from lxml import etree

    theme = package_part_for_relationship(model.package, RELATIONSHIP_TYPE["theme"])
    if theme is None:
        return None
    root = etree.fromstring(theme.data)
    family = "majorFont" if theme_key.startswith("major") else "minorFont"
    script = "ea" if theme_key.endswith("EastAsia") else "cs" if theme_key.endswith("Bidi") else "latin"
    nodes = root.xpath(
        f"./a:themeElements/a:fontScheme/a:{family}/a:{script}",
        namespaces=OOXML_NAMESPACES,
    )
    return nodes[0].get("typeface") or None if nodes else None


def _theme_color(model: DocumentModel, color_key: str) -> str | None:
    from lxml import etree

    theme = package_part_for_relationship(model.package, RELATIONSHIP_TYPE["theme"])
    if theme is None:
        return None
    root = etree.fromstring(theme.data)
    aliases = {"text1": "dk1", "text2": "dk2", "background1": "lt1", "background2": "lt2"}
    key = aliases.get(color_key, color_key)
    nodes = root.xpath(
        f"./a:themeElements/a:clrScheme/a:{key}/*",
        namespaces=OOXML_NAMESPACES,
    )
    return (nodes[0].get("val") or nodes[0].get("lastClr")) if nodes else None


def document_theme_colors(model: DocumentModel) -> dict[str, str]:
    """Read the document DrawingML color scheme for shared OOXML adapters."""
    keys = ("dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink")
    return {key: value for key in keys if (value := _theme_color(model, key)) is not None}


def _xml_bool(parent: Any, local_name: str) -> bool | None:
    from docx.oxml.ns import qn

    if parent is None:
        return None
    node = parent.find(qn(f"w:{local_name}"))
    if node is None:
        return None
    return str(node.get(qn("w:val"), "1")).lower() not in {"0", "false", "off", "none"}


def _xml_underline(parent: Any) -> bool | None:
    from docx.oxml.ns import qn

    if parent is None:
        return None
    node = parent.find(qn("w:u"))
    if node is None:
        return None
    return str(node.get(qn("w:val"), "single")).lower() not in {"0", "false", "off", "none"}


def _resolved_font_style(style: Any, *, properties: dict[str, Any], model: DocumentModel | None = None) -> TextStyle:
    sources = [item.font for item in _style_chain(style)]
    color = _font_color([style.font], model)
    properties.update(_font_color_properties([style.font], model))
    properties['docx_color_imported_value'] = color.to_dict() if isinstance(color, ColorValue) else color
    return TextStyle(
        font_family=_font_family(sources, model),
        font_size=_font_size(_first_font_value(sources, "size")),
        bold=_first_font_value(sources, "bold"),
        italic=_first_font_value(sources, "italic"),
        underline=_underline(_first_font_value(sources, "underline")),
        superscript=_first_font_value(sources, "superscript"),
        subscript=_first_font_value(sources, "subscript"),
        color=color,
        language=_style_language(style),
        properties=properties,
    )


def _style_chain(style: Any) -> list[Any]:
    result = []
    seen: set[str] = set()
    current = style
    while current is not None and current.style_id not in seen:
        seen.add(current.style_id)
        result.append(current)
        current = current.base_style
    return result


def _first_font_value(sources: list[Any], name: str) -> Any:
    for font in sources:
        value = getattr(font, name)
        if value is not None:
            return value
    return None


def _font_family(sources: list[Any], model: DocumentModel | None) -> str | None:
    """Word theme references override literal fallback names at the same cascade level."""

    for font in sources:
        records = font._element.xpath('./w:rPr/w:rFonts')
        if not records:
            continue
        family, theme = _font_record_family(records[0], model)
        if theme:
            # An unresolved declaration must not invent an effective inherited family.
            return family
        if family:
            return family
    if model is not None:
        defaults = model.styles.get('__doc_defaults__')
        if defaults is not None:
            return defaults.font_family
    return None


def _font_record_family(record: Any, model: DocumentModel | None) -> tuple[str | None, str | None]:
    from docx.oxml.ns import qn

    for slot in ('ascii', 'hAnsi'):
        theme = record.get(qn('w:' + slot + 'Theme'))
        if theme:
            return (_theme_typeface(model, theme) if model is not None else None), theme
        family = record.get(qn('w:' + slot))
        if family:
            return family, None
    return None, None


def _font_size(value: Any) -> Length | None:
    return Length(float(value.pt)) if value is not None else None


def _underline(value: Any) -> bool | None:
    return bool(value) if value is not None else None


def _font_color(sources: list[Any], model: DocumentModel | None = None) -> ColorValue | str | None:
    for font in sources:
        color, _ = _font_color_value(font, model)
        if color is not None:
            return color
    return None


def _font_color_properties(sources: list[Any], model: DocumentModel | None) -> dict[str, Any]:
    for font in sources:
        color, properties = _font_color_value(font, model)
        if color is not None:
            return properties
    return {}


def _font_color_value(font: Any, model: DocumentModel | None) -> tuple[ColorValue | str | None, dict[str, Any]]:
    nodes = font._element.xpath("./w:rPr/w:color") if getattr(font, "_element", None) is not None else []
    if nodes:
        return _word_color(nodes[0], model)
    if font.color is not None and font.color.rgb is not None:
        return ColorValue.from_hex(f"#{font.color.rgb}"), {"color_source": "rgb"}
    return None, {}


def _word_color(node: Any, model: DocumentModel | None) -> tuple[ColorValue | str | None, dict[str, Any]]:
    from docx.oxml.ns import qn

    if node is None:
        return None, {}
    raw = node.get(qn("w:val"))
    native_value = raw
    theme = node.get(qn("w:themeColor"))
    if theme and model is not None:
        raw = _theme_color(model, theme) or raw
    if raw and raw.lower() == "auto":
        return "auto", {"color_source": "auto", "color_native_value": native_value}
    if not raw:
        return None, {}
    try:
        color = ColorValue.from_hex(f"#{raw}")
    except ValueError:
        return None, {}
    modifiers: dict[str, float] = {}
    tint = node.get(qn("w:themeTint"))
    shade = node.get(qn("w:themeShade"))
    if tint:
        modifiers["tint"] = int(tint, 16) / 255.0
        color = color.transformed(tint=modifiers["tint"])
    if shade:
        modifiers["shade"] = int(shade, 16) / 255.0
        color = color.transformed(shade=modifiers["shade"])
    properties: dict[str, Any] = {"color_source": "theme" if theme else "rgb", "color_native_value": native_value}
    if theme:
        properties["color_theme"] = theme
    if modifiers:
        properties["color_modifiers"] = modifiers
    return color, properties


def _direct_run_value(run: Any, name: str) -> Any:
    if name == "font_family":
        from docx.oxml.ns import qn

        fonts = run._r.xpath('./w:rPr/w:rFonts')
        return (fonts[0].get(qn('w:asciiTheme')) or fonts[0].get(qn('w:hAnsiTheme'))
                or fonts[0].get(qn('w:ascii')) or fonts[0].get(qn('w:hAnsi'))) if fonts else None
    if name == "font_size":
        return run.font.size
    if name == "color":
        return _font_color([run.font])
    if name == "language":
        return _run_language(run)
    return getattr(run.font, name)


def _resolved_run_language(run: Any, paragraph: Any) -> str | None:
    direct = _run_language(run)
    if direct:
        return direct
    for style in [*_style_chain(run.style), *_style_chain(paragraph.style)]:
        language = _style_language(style)
        if language:
            return language
    return None


def _run_language(run: Any) -> str | None:
    from docx.oxml.ns import qn

    language = run._r.xpath("./w:rPr/w:lang")
    return language[0].get(qn("w:val")) if language else None


def _style_language(style: Any) -> str | None:
    from docx.oxml.ns import qn

    for item in _style_chain(style):
        language = item.element.xpath("./w:rPr/w:lang")
        if language:
            return language[0].get(qn("w:val"))
    return None


def _style_paragraph_properties(style: Any) -> dict[str, Any]:
    result = _resolved_paragraph_values([item.paragraph_format for item in _style_chain(style)])
    import_layout(result, style.element.pPr)
    return result


def _resolved_paragraph_values(formats: list[Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    from opendoc_formats.ooxml.paragraph_indent import import_indents

    import_indents(properties, formats[0]._element.pPr if formats else None)
    from opendoc_formats.ooxml.paragraph_flow import import_flow

    import_flow(properties, formats[0]._element.pPr if formats else None)
    from opendoc_formats.ooxml.spacing import import_spacing

    import_spacing(properties, formats)
    return properties


def _resolved_numbering_properties(paragraph: Any) -> dict[str, Any]:
    properties = _numbering_properties(paragraph._p.pPr)
    if properties:
        properties["numbering_source"] = "direct"
        return properties
    for style in _style_chain(paragraph.style):
        properties = _numbering_properties(style.element.pPr)
        if properties:
            properties["numbering_source"] = "style"
            properties["numbering_source_style_id"] = style.style_id
            return properties
    return {}


def _numbering_properties(paragraph_properties: Any) -> dict[str, Any]:
    from docx.oxml.ns import qn

    if paragraph_properties is None:
        return {}
    number_properties = paragraph_properties.find(qn("w:numPr"))
    if number_properties is None:
        return {}
    number_id = number_properties.find(qn("w:numId"))
    level = number_properties.find(qn("w:ilvl"))
    result: dict[str, Any] = {}
    if number_id is not None and number_id.get(qn("w:val")) is not None:
        result["numbering_id"] = int(number_id.get(qn("w:val")))
    if level is not None and level.get(qn("w:val")) is not None:
        result["numbering_level"] = int(level.get(qn("w:val")))
    return result


__all__ = [
    "read_document_defaults",
    "read_document_styles",
    "read_paragraph_properties",
    "read_run_style",
]
