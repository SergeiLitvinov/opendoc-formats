"""Explicit paragraph and frame formatting from DrawingML."""

from __future__ import annotations

from typing import Any

import opendoc_model as od

from opendoc_formats.support.cancellation import cancellable_items, checkpoint

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def merge_text_styles(inherited: od.TextStyle | None, explicit: od.TextStyle) -> od.TextStyle:
    from copy import deepcopy
    from dataclasses import fields

    from opendoc_model.document_model import TextStyle

    result = deepcopy(inherited) if inherited is not None else TextStyle()
    for field in fields(TextStyle):
        checkpoint()
        value = getattr(explicit, field.name)
        if field.name == "properties":
            result.properties.update(deepcopy(value))
        elif value is not None:
            setattr(result, field.name, deepcopy(value))
    return result


def paragraph_metadata(element: Any, alignments: dict[str, str]) -> dict[str, Any]:
    properties = element.find(A + "pPr")
    return paragraph_properties(properties, alignments)


def paragraph_properties(properties: dict[str, Any], alignments: dict[str, str]) -> dict[str, Any]:
    if properties is None:
        return {}
    result = {}
    if properties.get("algn"):
        result["alignment"] = alignments.get(properties.get("algn"), properties.get("algn"))
    for key in ("marL", "marR", "indent", "defTabSz"):
        checkpoint()
        if properties.get(key) is not None:
            result[key] = float(properties.get(key)) / 12700
    if properties.get("lvl") is not None:
        result["level"] = int(properties.get("lvl"))
    tabs = properties.find(A + "tabLst")
    if tabs is not None:
        result["tabs"] = [
            {"position_pt": float(tab.get("pos", "0")) / 12700, "alignment": tab.get("algn", "l")}
            for tab in cancellable_items(tabs.findall(A + "tab"))
        ]
    for tag, key in (("lnSpc", "line_spacing"), ("spcBef", "space_before"), ("spcAft", "space_after")):
        checkpoint()
        node = properties.find(A + tag)
        if node is not None:
            for child, suffix, divisor in (("spcPts", "pt", 100), ("spcPct", "pct", 100000)):
                checkpoint()
                value = node.find(A + child)
                if value is not None:
                    result[f"{key}_{suffix}"] = float(value.get("val", "0")) / divisor
    for tag, attr, key in (
        ("buChar", "char", "bullet_char"),
        ("buFont", "typeface", "bullet_font"),
        ("buAutoNum", "type", "numbered"),
    ):
        checkpoint()
        node = properties.find(A + tag)
        if node is not None:
            result[key] = node.get(attr)
    number = properties.find(A + "buAutoNum")
    if number is not None and number.get("startAt") is not None:
        result["number_start"] = int(number.get("startAt"))
    if properties.find(A + "buNone") is not None:
        result["bullet_none"] = True
    return result


def merge_paragraph_settings(inherited: dict[str, Any], explicit: dict[str, Any]) -> dict[str, Any]:
    result = dict(inherited)
    families = (
        ("bullet_none", "bullet_char", "numbered", "number_start"),
        ("line_spacing_pt", "line_spacing_pct"),
        ("space_before_pt", "space_before_pct"),
        ("space_after_pt", "space_after_pct"),
    )
    for family in families:
        checkpoint()
        if any(key in explicit for key in cancellable_items(family)):
            for key in family:
                checkpoint()
                result.pop(key, None)
    result.update(explicit)
    return result


def frame_metadata(body: Any) -> dict[str, Any]:
    properties = body.find(A + "bodyPr") if body is not None else None
    if properties is None:
        return {}
    result = {key: properties.get(key) for key in ("anchor", "wrap", "vert") if properties.get(key) is not None}
    for tag in ("noAutofit", "normAutofit", "spAutoFit"):
        checkpoint()
        node = properties.find(A + tag)
        if node is not None:
            result["autofit"] = {"mode": tag}
            for attr in ("fontScale", "lnSpcReduction"):
                checkpoint()
                if node.get(attr) is not None:
                    result["autofit"][attr] = int(node.get(attr))
            break
    for key in ("lIns", "rIns", "tIns", "bIns"):
        checkpoint()
        if properties.get(key) is not None:
            result[key] = float(properties.get(key)) / 12700
    return result
