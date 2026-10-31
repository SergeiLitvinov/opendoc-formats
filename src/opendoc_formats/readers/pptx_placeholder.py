"""Наследование оформления текстовых заполнителей из макета и образца."""

from __future__ import annotations

from typing import Any

from opendoc_formats.ooxml.pptx_placeholders import placeholder_chain as placeholder_chain
from opendoc_formats.readers.pptx_paragraph import (
    frame_metadata,
    merge_paragraph_settings,
    merge_text_styles,
    paragraph_properties,
)
from opendoc_formats.support.cancellation import cancellable_items, checkpoint

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"




def inherited_frame(chain: list[Any], element: Any) -> dict[str, Any]:
    # Materialize the DrawingML default before merging explicit master/layout settings.
    # Otherwise add_shape's default centered anchor changes an imported top-aligned box.
    result = {"anchor": "t"}
    for shape in [*chain, element]:
        checkpoint()
        result.update(frame_metadata(shape.find(P + "txBody")))
    return result


def inherited_paragraph(
    chain: list[Any],
    body: Any,
    level: int,
    meta: dict[str, Any],
    style: Any,
    *,
    parse_style: Any,
    alignments: dict[str, str],
    colors: dict[str, str],
) -> tuple[dict[str, Any], Any]:
    """Наложить свойства каждого уровня, сохранив независимость стилей фрагментов."""
    for shape in [*chain, None]:
        checkpoint()
        current = shape.find(P + "txBody") if shape is not None else body
        if current is None:
            continue
        nodes = [current.find(f"{A}lstStyle/{A}defPPr"), current.find(f"{A}lstStyle/{A}lvl{level + 1}pPr")]
        if shape is not None:
            matching = [
                paragraph.find(A + "pPr")
                for paragraph in cancellable_items(current.findall(A + "p"))
                if paragraph.find(A + "pPr") is not None and paragraph.find(A + "pPr").get("lvl", "0") == str(level)
            ]
            nodes.extend(matching[:1])
        for properties in nodes:
            checkpoint()
            if properties is None:
                continue
            meta = merge_paragraph_settings(meta, paragraph_properties(properties, alignments))
            style = merge_text_styles(style, parse_style(properties.find(A + "defRPr"), colors))
    return meta, style
