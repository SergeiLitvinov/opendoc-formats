"""Write shared outline hierarchy with explicit page and anchor destination maps."""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import urlsplit

from opendoc_model import ConversionReport, DocumentModel, IssueSeverity, get_outline


def _safe_uri(value: str | None) -> bool:
    if value is None:
        return False
    try:
        return urlsplit(value).scheme.lower() in ("http", "https", "mailto")
    except ValueError:
        return False


def write_outline(
    pdf: Any, document: DocumentModel, report: ConversionReport,
    pages: dict[str, tuple[int, tuple[float, float], bool]],
    anchors: dict[str, tuple[int, tuple[float, float]]],
    source_origins: dict[int, tuple[float, float]] | None = None,
) -> None:
    """Unknown or unmapped destinations remain untargeted, with a located loss."""
    import pymupdf

    outline = get_outline(document)
    if outline is None:
        return
    children: dict[str | None, list] = {}
    for entry in outline.entries:
        children.setdefault(entry.parent_id, []).append(entry)
    toc = []
    native_points: dict[int, Any] = {}
    source_origins = source_origins or {}

    def visit(parent: str | None, level: int) -> None:
        for entry in sorted(children.get(parent, []), key=lambda item: item.order):
            location = f"outline.entries[{entry.id}]"
            destination: dict[str, Any] = {"kind": pymupdf.LINK_NONE}
            page_number = -1
            target = entry.target
            if target is not None:
                if target.kind == "external" and _safe_uri(target.uri):
                    destination = {"kind": pymupdf.LINK_URI, "uri": target.uri}
                elif target.kind == "page" and target.target_id in pages:
                    page_index, origin, stable = pages[target.target_id]
                    page_number = page_index + 1
                    destination = {"kind": pymupdf.LINK_GOTO, "page": page_index, "zoom": target.zoom or 0}
                    if target.point is not None and stable:
                        point = pymupdf.Point(target.point.x-origin[0], target.point.y-origin[1])
                        destination["to"] = point
                        if page_index in source_origins:
                            native_points[len(toc)] = pymupdf.Point(target.point.x, -target.point.y)
                    elif target.point is not None:
                        report.add(IssueSeverity.LOSS, "pdf.outline-point",
                                   "Changed page layout has no verified source point mapping", location)
                elif target.kind == "anchor" and target.target_id in anchors:
                    page_index, position = anchors[target.target_id]
                    page_number = page_index + 1
                    destination = {"kind": pymupdf.LINK_GOTO, "page": page_index,
                                   "to": pymupdf.Point(*position)}
                    if page_index in source_origins:
                        origin = source_origins[page_index]
                        native_points[len(toc)] = pymupdf.Point(position[0]+origin[0], -position[1]-origin[1])
                else:
                    report.add(IssueSeverity.LOSS, "pdf.outline-target",
                               "Destination has no supported safe mapping; entry remains untargeted", location)
            native = entry.extra.get("pdf_destination", {})
            if isinstance(native, dict):
                for key in ("bold", "italic", "collapse"):
                    if type(native.get(key)) is bool:
                        destination[key] = native[key]
                color = native.get("color")
                if (isinstance(color, (list, tuple)) and len(color) == 3
                        and all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1 for value in color)):
                    destination["color"] = tuple(color)
                if native.get("kind") not in (None, 0, 1, 2):
                    report.add(IssueSeverity.LOSS, "pdf.outline-action",
                               "Native action remains inert and is not recreated", location)
            toc.append([level, entry.title, page_number, destination])
            visit(entry.id, level + 1)

    visit(None, 1)
    pdf.set_toc(toc, collapse=0)
    # Set only our freshly created page actions in native PDF coordinates.
    # This avoids backend TOC rotation conventions differing for 270 degrees.
    outline_xrefs = pdf.get_outline_xrefs()
    for index, item in enumerate(toc):
        destination = item[3]
        if destination["kind"] == pymupdf.LINK_GOTO:
            page = pdf[destination["page"]]
            point = None
            if "to" in destination:
                point = native_points.get(index, destination["to"] * ~page.transformation_matrix)
                if any(not math.isfinite(v) or abs(v) > 1_000_000 for v in point):
                    raise ValueError("Excessive PDF outline destination point")
            position = f"{point.x:.10f} {point.y:.10f}" if point is not None else "null null"
            action = (f"<< /S /GoTo /D [{pdf.page_xref(destination['page'])} 0 R /XYZ "
                      f"{position} {destination.get('zoom', 0):.10f}] >>")
            pdf.xref_set_key(outline_xrefs[index], "A", action)
    report.metrics["pdf_outline"] = {"entries": len(toc)}
