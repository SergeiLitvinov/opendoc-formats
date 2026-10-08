"""Bridge native preferred widths to the shared model without layout guesses."""

from __future__ import annotations

import re
from decimal import Decimal, localcontext
from typing import Any

from opendoc_model import Table, TableCell, WidthMeasure, get_preferred_width, set_preferred_width

from opendoc_formats.errors import ConvertError


def native_width(value: object, *, cell: bool) -> WidthMeasure | None:
    """Validate native syntax; retain negative preferences only as native data."""
    if not isinstance(value, dict) or set(value) != {"type", "value"}:
        raise ConvertError("docx_preferred_width must contain type and value")
    kind, number = value["type"], value["value"]
    if kind not in (None, "auto", "dxa", "nil", "pct"):
        raise ConvertError("Unsupported DOCX preferred width type")
    kind = kind or "dxa"
    if number is not None:
        if not isinstance(number, str) or len(number) > 128:
            raise ConvertError("DOCX preferred width value must be a bounded string or null")
        pattern = r"[+-]?[0-9]+"
        if kind == "pct":
            pattern += r"|[+-]?[0-9]+(?:\.[0-9]+)?%"
        elif kind == "dxa":
            pattern += r"|[+-]?[0-9]+(?:\.[0-9]+)?(?:mm|cm|in|pt|pc|pi)"
        if re.fullmatch(pattern, number) is None:
            raise ConvertError("Invalid DOCX preferred width value")
    if kind == "auto":
        return WidthMeasure("auto")
    if kind == "nil":
        return WidthMeasure("unspecified")
    if number is None:
        return None
    with localcontext() as context:
        context.prec = 160
        return _numeric_width(kind, number, cell=cell)


def _numeric_width(kind: str, number: str, *, cell: bool) -> WidthMeasure | None:
    if kind == "pct":
        result = Decimal(number[:-1]) / 100 if number.endswith("%") else Decimal(number) / 5000
        if result < 0:
            return None
        return WidthMeasure("relative", float(result), "ratio", "table" if cell else "content")
    factors = {"mm": Decimal(72) / Decimal("25.4"), "cm": Decimal(72) / Decimal("2.54"),
               "in": Decimal(72), "pt": Decimal(1), "pc": Decimal(12), "pi": Decimal(12)}
    suffix = number[-2:]
    result = Decimal(number[:-2]) * factors[suffix] if suffix in factors else Decimal(number) / 20
    if result < 0:
        return None
    return WidthMeasure("absolute", float(result), "pt")


def import_width(source: Table | TableCell) -> None:
    raw = source.properties.get("docx_preferred_width")
    measure = native_width(raw, cell=isinstance(source, TableCell)) if raw is not None else None
    legacy = source.properties.get("width_twips")
    if legacy is not None:
        measure = get_preferred_width(source)
    if raw is None or measure is not None:
        set_preferred_width(source, measure)
        # Keep the existing integer convenience field for older consumers.
        if legacy is not None:
            source.properties["width_twips"] = legacy
        source.properties["docx_width_imported"] = True


def export_width(source: Table | TableCell, owner: Any, tag: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    cell = isinstance(source, TableCell)
    raw = source.properties.get("docx_preferred_width")
    baseline = native_width(raw, cell=cell) if raw is not None else None
    measure = get_preferred_width(source)
    if raw is None and measure is None and "docx_width_imported" not in source.properties:
        return
    if measure is None and source.properties.get("docx_width_imported") is not True:
        value = raw
    elif measure is None:
        value = None
    elif baseline is not None and (measure.kind, measure.value, measure.unit, measure.reference) == (
        baseline.kind, baseline.value, baseline.unit, baseline.reference,
    ):
        value = raw
    elif measure.kind in ("auto", "unspecified"):
        value = {"type": "auto" if measure.kind == "auto" else "nil", "value": "0"}
    else:
        with localcontext() as context:
            context.prec = 160
            number = Decimal(str(measure.value))
            scaled = number * (20 if measure.kind == "absolute" else 5000)
            if scaled == scaled.to_integral_value():
                text = format(scaled, ".0f")
            else:
                text = format(number * (1 if measure.kind == "absolute" else 100), "f")
                text += "pt" if measure.kind == "absolute" else "%"
        value = {"type": "dxa" if measure.kind == "absolute" else "pct", "value": text}
        native_width(value, cell=cell)
    existing = list(owner.findall(qn(tag)))
    index = owner.index(existing[0]) if existing else None
    for previous in existing:
        owner.remove(previous)
    if value is None:
        return
    node = OxmlElement(tag)
    for key, attribute in (("type", "type"), ("value", "w")):
        if value[key] is not None:
            node.set(qn("w:" + attribute), value[key])
    if index is not None:
        owner.insert(index, node)
    elif cell:
        placeholder = owner.get_or_add_tcW()
        placeholder.addprevious(node)
        owner.remove(placeholder)
    else:
        owner.insert_element_before(
            node, "w:jc", "w:tblCellSpacing", "w:tblInd", "w:tblBorders", "w:shd", "w:tblLayout", "w:tblCellMar",
            "w:tblLook", "w:tblCaption", "w:tblDescription", "w:tblPrChange",
        )
