"""Shared unambiguous native placeholder ancestry and source frame overrides."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from opendoc_formats.support.cancellation import cancellable_items

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"

MASTER_TYPES = {
    "ctrTitle": "title",
    "subTitle": "body",
    "obj": "body",
    "pic": "body",
    "chart": "body",
    "tbl": "body",
    "clipArt": "body",
    "dgm": "body",
    "media": "body",
}

def placeholder_chain(element: Any, layout: Any, master: Any) -> list[Any]:
    """Вернуть образец → макет для однозначной связи idx, затем типа."""
    ph = element.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
    if ph is None or layout is None:
        return []
    matches = [
        shape
        for shape in cancellable_items(layout.iter(P + "sp"))
        if (candidate := shape.find(f"{P}nvSpPr/{P}nvPr/{P}ph")) is not None and candidate.get("idx", "0") == ph.get("idx", "0")
    ]
    if len(matches) != 1:
        return []
    parent = matches[0]
    parent_ph = parent.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
    kind = parent_ph.get("type", "obj")
    kind = MASTER_TYPES.get(kind, kind)
    ancestors = (
        []
        if master is None
        else [
            shape
            for shape in cancellable_items(master.iter(P + "sp"))
            if (candidate := shape.find(f"{P}nvSpPr/{P}nvPr/{P}ph")) is not None and candidate.get("type", "obj") == kind
        ]
    )
    return (ancestors if len(ancestors) == 1 else []) + [parent]


def inherited_source_frame(shape: Any, part: str, graph: Any, roots: Any) -> Any:
    """Resolve one complete inherited frame; never fill in partial local transforms."""
    if (shape.tag != P+'sp' or shape.find(P+'spPr') is None
            or shape.find(P+'spPr/'+A+'xfrm') is not None or any(shape.iterancestors(P+'grpSp'))):
        return None

    def related(owner: str, kind: str, root_tag: str) -> tuple[str, Any] | None:
        relation = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'+kind
        edges = [edge for edge in cancellable_items(graph.relationships)
                 if edge.source == owner and edge.relationship_type == relation]
        if len(edges) != 1 or edges[0].external or edges[0].target not in graph.parts:
            return None
        target = edges[0].target
        if graph.parts[target].media_type != 'application/vnd.openxmlformats-officedocument.presentationml.'+kind+'+xml':
            return None
        root = roots.load(graph, target)
        return (target, root) if root.tag == P+root_tag else None

    layout = related(part, 'slideLayout', 'sldLayout')
    if layout is None:
        return None
    chain = placeholder_chain(shape, layout[1], None)
    if not chain:
        return None
    frame = chain[-1].find(P+'spPr/'+A+'xfrm')
    if frame is None:
        master = related(layout[0], 'slideMaster', 'sldMaster')
        chain = placeholder_chain(shape, layout[1], master[1] if master else None)
    for parent in reversed(chain):
        frame = parent.find(P+'spPr/'+A+'xfrm')
        if frame is not None:
            if (any(parent.iterancestors(P+'grpSp')) or frame.find(A+'off') is None or frame.find(A+'ext') is None):
                return None
            return deepcopy(frame)
    return None
