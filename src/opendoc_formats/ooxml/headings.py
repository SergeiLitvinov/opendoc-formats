"""Map native Word outline levels to OpenDoc's explicit heading contract."""

from __future__ import annotations

from typing import Any

from opendoc_model import Heading, PackageGraph, Paragraph, get_heading, set_heading


def _builtin_level(style: Any) -> int | None:
    if style is not None and style.builtin:
        ids = {f"Heading{level}": level - 1 for level in range(1, 10)}
        names = {f"Heading {level}": level - 1 for level in range(1, 10)}
        return ids.get(style.style_id, names.get(style.name))
    return None


def import_heading(native: Any, paragraph: Paragraph) -> None:
    from docx.oxml.ns import qn

    owners = [native._p]
    fixed = _builtin_level(native.style)
    if fixed is not None:
        paragraph.properties["docx_outline_level"] = fixed
        set_heading(paragraph, Heading(fixed + 1))
        return
    style = native.style
    seen = set()
    while style is not None and style.style_id not in seen:
        seen.add(style.style_id)
        owners.append(style.element)
        style = style.base_style
    defaults = native.part.package.main_document_part.styles.element.xpath("./w:docDefaults/w:pPrDefault")
    owners.extend(defaults)
    for owner in owners:
        properties = owner.find(qn("w:pPr"))
        node = properties.find(qn("w:outlineLvl")) if properties is not None else None
        if node is None:
            continue
        try:
            level = int(node.get(qn("w:val"), ""))
        except ValueError as error:
            raise ValueError("DOCX outline level must be an integer from 0 to 9") from error
        if not 0 <= level <= 9:
            raise ValueError("DOCX outline level must be an integer from 0 to 9")
        paragraph.properties["docx_outline_level"] = level
        if level < 9:
            set_heading(paragraph, Heading(level + 1))
        return


def export_heading(paragraph: Paragraph, native: Any) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    heading = get_heading(paragraph)
    original = paragraph.properties.get("docx_outline_level")
    if original is not None and (type(original) is not int or not 0 <= original <= 9):
        raise ValueError("docx_outline_level must be an integer from 0 to 9")
    if heading is None and original is None:
        return
    # An explicitly removed imported role overrides the retained Heading style.
    level = heading.level - 1 if heading is not None else 9
    fixed = _builtin_level(native.style)
    if fixed is not None and fixed != level:
        from docx.enum.style import WD_STYLE_TYPE

        part = native.part.package.main_document_part
        cache = getattr(part, "_opendoc_heading_styles", {})
        part._opendoc_heading_styles = cache
        key = native.style.style_id, level
        if key not in cache:
            base = native.style
            name = f"OpenDoc outline {level} from {base.style_id}"
            candidate, suffix = name, 0
            while candidate in part.styles:
                suffix += 1
                candidate = f"{name} {suffix}"
            derived = part.styles.add_style(candidate, WD_STYLE_TYPE.PARAGRAPH)
            derived.base_style = base
            cache[key] = derived
        native.style = cache[key]
    properties = native._p.get_or_add_pPr()
    for node in list(properties.findall(qn("w:outlineLvl"))):
        properties.remove(node)
    node = OxmlElement("w:outlineLvl")
    node.set(qn("w:val"), str(level))
    properties.append(node)


def retain_derived_styles(part: Any, graph: PackageGraph) -> PackageGraph:
    """Keep new role styles when restoring the original opaque styles part."""
    from copy import deepcopy
    from dataclasses import replace

    from docx.oxml import parse_xml
    from lxml import etree

    from opendoc_formats.ooxml.package import RELATIONSHIP_TYPE

    created = getattr(part, "_opendoc_heading_styles", {})
    source = graph.related_part(graph.root, RELATIONSHIP_TYPE["styles"])
    if not created or source is None:
        return graph
    styles = parse_xml(source.data)
    for style in created.values():
        styles.append(deepcopy(style.element))
    parts = dict(graph.parts)
    parts[source.name] = replace(source, data=etree.tostring(styles, encoding="UTF-8", xml_declaration=True))
    return replace(graph, parts=parts)
