"""Bridge inert native PDF outlines to the shared Model contract."""

from __future__ import annotations

import math
from typing import Any

from opendoc_model import (
    DocumentLimits,
    DocumentModel,
    Outline,
    OutlineEntry,
    OutlineTarget,
    Point2D,
    Provenance,
    get_integration,
    set_outline,
)


def import_pdf_outline(
    document: DocumentModel, *, pdf: Any = None, source: str = "", limits: DocumentLimits | None = None,
) -> None:
    """Migrate a retained native outline once; opaque occupied keys are never overwritten."""
    integration = get_integration(document, limits=limits)
    if integration is None or "pdf_outline" not in integration.extra:
        return
    if "opendoc.outline" in integration.extra or integration.extra.get("pdf_outline_imported"):
        return
    raw = integration.extra["pdf_outline"]
    if not isinstance(raw, list) or len(raw) > 10000:
        raise ValueError("Invalid or excessive PDF outline")
    parents: list[str] = []
    entries = []
    orders: dict[str | None, int] = {}
    for index, item in enumerate(raw):
        if (not isinstance(item, list) or len(item) != 4 or type(item[0]) is not int
                or not isinstance(item[1], str) or len(item[1]) > 65536 or not isinstance(item[3], dict)):
            raise ValueError(f"Invalid PDF outline entry {index}")
        level, title, _, destination = item
        if not 1 <= level <= 64 or level > len(parents) + 1:
            raise ValueError(f"Invalid PDF outline hierarchy at entry {index}")
        parents = parents[:level - 1]
        parent = parents[-1] if parents else None
        identifier = f"pdf-outline-{index + 1}"
        target = None
        kind = destination.get("kind")
        if kind == 1 and type(destination.get("page")) is int:
            page_index = destination["page"]
            if 0 <= page_index < len(integration.pages):
                point = None
                position = destination.get("to")
                # The old opaque JSON lacks the crop origin: do not invent a source point.
                if pdf is not None and isinstance(position, list) and len(position) == 2:
                    import pymupdf

                    page = pdf[page_index]
                    native = pymupdf.Point(*position) * page.derotation_matrix
                    point = Point2D(native.x + page.cropbox.x0, native.y + page.cropbox.y0)
                zoom = destination.get("zoom")
                zoom = zoom if type(zoom) in (int, float) and math.isfinite(zoom) and zoom > 0 else None
                target = OutlineTarget("page", target_id=integration.pages[page_index].id, point=point, zoom=zoom)
        elif kind == 2 and isinstance(destination.get("uri"), str) and destination["uri"]:
            target = OutlineTarget("external", uri=destination["uri"])
        order = orders.get(parent, 0)
        orders[parent] = order + 1
        entries.append(OutlineEntry(
            identifier, title, order, parent_id=parent, target=target,
            provenance=Provenance("pdf", source, object_id=f"xref-{destination.get('xref', 0)}"),
            extra={"pdf_destination": destination},
        ))
        parents.append(identifier)
    set_outline(document, Outline(entries=tuple(entries)), limits=limits)
    # Mark even an empty migrated declaration: explicit removal must not resurrect it.
    current = get_integration(document, limits=limits)
    assert current is not None
    from dataclasses import replace

    from opendoc_model import set_integration

    set_integration(document, replace(current, extra={**current.extra, "pdf_outline_imported": True}), limits=limits)
    for section in document.sections:
        profile = section.properties.get("pdf")
        provenance = section.provenance
        if (isinstance(profile, dict) and "page_id" not in profile and provenance is not None
                and provenance.source_format == "pdf" and type(provenance.page) is int
                and 1 <= provenance.page <= len(integration.pages)):
            profile["page_id"] = integration.pages[provenance.page - 1].id
