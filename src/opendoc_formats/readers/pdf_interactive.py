"""Finite PDF interaction profile; actions are inert data, never executed."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from opendoc_model import (
    Annotation,
    Box,
    DiagnosticIssue,
    DocumentModel,
    DocumentPage,
    FormControl,
    IntegrationModel,
    IssueSeverity,
    PreservationRecord,
    PreservationState,
    Provenance,
    Resource,
    ResourceKind,
    set_integration,
)

MAX_OBJECTS = 10_000
MAX_STRING = 65_536
MAX_SOURCE_BYTES = 10 * 1024 * 1024


def _plain(value: Any) -> Any:
    if value is None or type(value) in (bool, int):
        return value
    if isinstance(value, str):
        if len(value) > MAX_STRING:
            raise ValueError("PDF interaction string exceeds profile limit")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Nonfinite PDF interaction value")
        return float(value)
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)) or type(value).__name__ in {"Point", "Rect", "Quad"}:
        return [_plain(item) for item in value]
    raise ValueError(f"Unsupported PDF interaction value: {type(value).__name__}")


def _box(rect: Any) -> Box:
    values = [float(item) for item in rect]
    if len(values) != 4 or not all(math.isfinite(item) and abs(item) <= 1_000_000 for item in values):
        raise ValueError("Invalid PDF interaction geometry")
    x0, y0, x1, y1 = values
    if x1 < x0 or y1 < y0:
        raise ValueError("Negative PDF interaction extent")
    return Box(x0, y0, x1 - x0, y1 - y0)


def _actions(pdf: Any, xref: int) -> dict[str, Any]:
    actions = {}
    for key in ("A", "AA"):
        kind, value = pdf.xref_get_key(xref, key)
        if kind != "null":
            actions[key] = {"pdf_type": kind, "value": _plain(value)}
    return actions


def attach_pdf_interactions(model: DocumentModel, source: str | Path) -> None:
    import fitz

    source = Path(source)
    pages, annotations, forms, records = [], [], [], []
    count = 0
    preserve_source = False

    def record(feature: str, state: PreservationState, page: int | None, xref: int, reason: str, message: str) -> None:
        nonlocal count, preserve_source
        count += 1
        if count > MAX_OBJECTS:
            raise ValueError("PDF interaction objects exceed profile limit")
        preserve_source = True
        records.append(
            PreservationRecord(
                issue=DiagnosticIssue(
                    feature,
                    IssueSeverity.INFO if state is PreservationState.SEMANTIC else IssueSeverity.LOSS,
                    message,
                    f"{source}#page={page or 0},xref={xref}",
                    reason=reason,
                ),
                state=state,
                provenance=Provenance("pdf", str(source), page=page, object_id=f"xref-{xref}"),
            )
        )

    with fitz.open(source) as pdf:
        note_types = {fitz.PDF_ANNOT_TEXT: "note", fitz.PDF_ANNOT_FREE_TEXT: "note", fitz.PDF_ANNOT_HIGHLIGHT: "highlight"}
        form_types = {
            fitz.PDF_WIDGET_TYPE_TEXT: "text",
            fitz.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
            fitz.PDF_WIDGET_TYPE_COMBOBOX: "choice",
            fitz.PDF_WIDGET_TYPE_LISTBOX: "choice",
            fitz.PDF_WIDGET_TYPE_BUTTON: "button",
        }
        for index, page in enumerate(pdf, 1):
            page_id = f"pdf-page-{index}"
            pages.append(
                DocumentPage(
                    page_id,
                    float(page.cropbox.width),
                    float(page.cropbox.height),
                    extra={"pdf_rotation": int(page.rotation), "coordinate_space": "pymupdf-unrotated"},
                )
            )
            for ordinal, link in enumerate(page.get_links(), 1):
                xref = int(link.get("xref", 0))
                target = link.get("uri") or (f"#pdf-page-{link['page'] + 1}" if link.get("page", -1) >= 0 else None)
                annotations.append(
                    Annotation(
                        f"pdf-link-{index}-{xref}-{ordinal}",
                        page_id,
                        "link",
                        target=target,
                        action={"destination": _plain(link), **(_actions(pdf, xref) if xref else {})},
                        box=_box(link["from"]),
                        extra={"source_xref": xref},
                    )
                )
                record(
                    "pdf.link", PreservationState.SEMANTIC, index, xref, "parsed-link", "Link destination retained as inert data"
                )
            for annotation in page.annots() or ():
                xref, kind = int(annotation.xref), int(annotation.type[0])
                if kind not in note_types:
                    record(
                        "pdf.annotation",
                        PreservationState.OPAQUE,
                        index,
                        xref,
                        "unsupported-annotation",
                        f"Annotation type {annotation.type[1]} retained only in source PDF",
                    )
                    continue
                annotations.append(
                    Annotation(
                        f"pdf-annotation-{xref}",
                        page_id,
                        note_types[kind],
                        text=str(annotation.info.get("content", "")),
                        action=_actions(pdf, xref),
                        box=_box(annotation.rect),
                        extra={
                            "source_xref": xref,
                            "pdf_type": kind,
                            "info": _plain(annotation.info),
                            "flags": int(annotation.flags),
                            "colors": _plain(annotation.colors),
                            "opacity": float(annotation.opacity),
                            "vertices": _plain(annotation.vertices),
                        },
                    )
                )
                record(
                    "pdf.annotation",
                    PreservationState.SEMANTIC,
                    index,
                    xref,
                    "parsed-annotation",
                    "Finite annotation profile imported",
                )
            for widget in page.widgets() or ():
                xref, kind = int(widget.xref), int(widget.field_type)
                if kind not in form_types or not isinstance(widget.field_value, (str, int, float, bool, type(None))):
                    record(
                        "pdf.form",
                        PreservationState.OPAQUE,
                        index,
                        xref,
                        "unsupported-form",
                        f"Form type {widget.field_type_string} retained only in source PDF",
                    )
                    continue
                choices = widget.choice_values or []
                actions = _actions(pdf, xref)
                for key in (
                    "script",
                    "script_stroke",
                    "script_format",
                    "script_change",
                    "script_calc",
                    "script_blur",
                    "script_focus",
                ):
                    value = getattr(widget, key, None)
                    if value:
                        actions[key] = _plain(value)
                forms.append(
                    FormControl(
                        f"pdf-form-{xref}",
                        page_id,
                        form_types[kind],
                        value="" if widget.field_value is None else str(_plain(widget.field_value)),
                        choices=tuple(str(item[-1] if isinstance(item, (list, tuple)) else item) for item in choices),
                        action=actions,
                        box=_box(widget.rect),
                        extra={
                            "source_xref": xref,
                            "field_name": _plain(widget.field_name or ""),
                            "field_label": _plain(widget.field_label or ""),
                            "field_flags": int(widget.field_flags),
                            "pdf_type": kind,
                            "pdf_choices": _plain(choices),
                        },
                    )
                )
                record(
                    "pdf.form",
                    PreservationState.SEMANTIC,
                    index,
                    xref,
                    "parsed-form",
                    "Finite form profile imported; scripts remain inert",
                )
        outline = _plain(pdf.get_toc(simple=False))
        if len(outline) > MAX_OBJECTS:
            raise ValueError("PDF outline exceeds profile limit")
        if outline:
            record(
                "pdf.outline",
                PreservationState.OPAQUE,
                None,
                pdf.pdf_catalog(),
                "outline-extension",
                "Outline retained in extension and source PDF; no typed outline contract",
            )
        catalog = pdf.pdf_catalog()
        for key in ("StructTreeRoot", "OCProperties", "OpenAction", "AA", "Names"):
            if pdf.xref_get_key(catalog, key)[0] != "null":
                record(
                    "pdf.catalog",
                    PreservationState.OPAQUE,
                    None,
                    catalog,
                    "unsupported-" + key,
                    f"Catalog {key} retained only in source PDF",
                )
    if preserve_source:
        with source.open("rb") as stream:
            snapshot = stream.read(MAX_SOURCE_BYTES + 1)
        if len(snapshot) > MAX_SOURCE_BYTES:
            raise ValueError("Source PDF exceeds opaque snapshot limit")
        model.add_resource(
            Resource(
                "pdf-original-source",
                ResourceKind.ATTACHMENT,
                "application/pdf",
                data=snapshot,
                filename=source.name,
                provenance=Provenance("pdf", str(source)),
            )
        )
    set_integration(
        model,
        IntegrationModel(
            pages=tuple(pages),
            annotations=tuple(annotations),
            forms=tuple(forms),
            preservation=tuple(records),
            assessed_features=tuple(dict.fromkeys(item.issue.code for item in records)),
            assessment_complete=False,
            extra={"pdf_outline": outline, "pdf_source_resource_id": "pdf-original-source" if preserve_source else None},
        ),
    )
