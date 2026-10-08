"""Resolve source-node diagnostics to stable, JSON-persisted imported blocks."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import opendoc_model as od
from opendoc_model import Paragraph


class HtmlDiagnostics:
    def __init__(self) -> None:
        self.node = None
        self.pending = []
        self.bindings = {}
        self.locations = {}

    @contextmanager
    def at(self, node: Any) -> Iterator[None]:
        previous = self.node
        self.node = node
        try:
            yield
        finally:
            self.node = previous

    def warn(self, feature: str, message: str, node: Any = None) -> None:
        if len(self.pending) >= 10_000:
            raise ValueError("HTML diagnostic objects exceed profile limit")
        self.pending.append((feature, message, node if node is not None else self.node))

    def bind(self, block: od.Block, root: Any, nodes: Iterable[Any] = ()) -> None:
        location = f"html:block:{len(self.locations) + 1}"
        block.properties.setdefault("html", {})["block_id"] = location
        self.bindings.setdefault(id(root), location)
        images = []
        for node in nodes:
            self.bindings.setdefault(id(node), location)
            if getattr(node, "name", None) == "img":
                src = node.get("src", "")
                images.append(
                    {
                        "alt": node.get("alt", ""),
                        "source": "Встроенное изображение" if src.startswith("data:") else src[:240],
                    }
                )
        self.locations[location] = {
            "label": f"{'Абзац' if isinstance(block, Paragraph) else 'Таблица'} {len(self.locations) + 1}",
            "text": block.plain_text[:1200] if isinstance(block, Paragraph) else root.get_text(" ", strip=True)[:1200],
            "images": images,
        }

    def resolve(self, node: Any) -> str:
        if node is None or node.name in {"[document]", "html", "head", "body", "style"}:
            return "html:document"
        if id(node) in self.bindings:
            return self.bindings[id(node)]
        # Container rules point to their first imported block; inline rules to
        # the block containing their text. Omitted nodes use the nearest owner.
        for child in node.descendants:
            if id(child) in self.bindings:
                return self.bindings[id(child)]
        for parent in node.parents:
            if parent.name in {"[document]", "html", "body"}:
                break
            if id(parent) in self.bindings:
                return self.bindings[id(parent)]
        return "html:document"

    def finish(self) -> dict[str, Any]:
        warnings, seen = [], set()
        for feature, message, node in self.pending:
            location = self.resolve(node)
            key = feature, message, location
            if key not in seen:
                seen.add(key)
                warnings.append({"feature": feature, "message": message, "location": location})
        referenced = {warning["location"] for warning in warnings}
        locations = {key: value for key, value in self.locations.items() if key in referenced}
        if "html:document" in referenced:
            locations["html:document"] = {
                "label": "Весь документ",
                "text": "Общее предупреждение: оно не относится к отдельному импортированному блоку.",
                "images": [],
            }
        return {"warnings": warnings, "locations": locations, "scope": "static-html-v1"}

    def attach(self, document: od.DocumentModel, source: Path, data: bytes) -> None:
        """Retain source markup separately from known semantic/profile losses."""
        records, seen = [], set()
        for feature, message, node in self.pending:
            block = self.resolve(node)
            line = getattr(node, "sourceline", None)
            column = getattr(node, "sourcepos", None)
            key = feature, message, block, line, column
            if key in seen:
                continue
            seen.add(key)
            location = str(source) + (f"#line={line},column={column}" if line is not None else "#document")
            records.append(
                od.PreservationRecord(
                    issue=od.DiagnosticIssue(
                        feature, od.IssueSeverity.LOSS, message, location, reason="outside-static-html-profile"
                    ),
                    state=od.PreservationState.LOST,
                    provenance=od.Provenance(
                        "html", str(source), object_id=str(node.get("id")) if node and node.get("id") else None
                    ),
                    extra={"block_location": block, "source_line": line, "source_column": column},
                )
            )
        if records:
            resource_id = "html-original-source"
            document.add_resource(
                od.Resource(
                    resource_id,
                    od.ResourceKind.ATTACHMENT,
                    "text/html",
                    data=data,
                    filename=source.name,
                    provenance=od.Provenance("html", str(source)),
                )
            )
            records.append(
                od.PreservationRecord(
                    issue=od.DiagnosticIssue(
                        "html.source",
                        od.IssueSeverity.LOSS,
                        "Original markup retained as inert attachment; external assets and browser behavior are not preserved",
                        str(source),
                        reason="inert-source-snapshot",
                    ),
                    state=od.PreservationState.OPAQUE,
                    provenance=od.Provenance("html", str(source)),
                    extra={"resource_id": resource_id},
                )
            )
        od.set_integration(
            document,
            od.IntegrationModel(
                preservation=tuple(records),
                assessed_features=tuple(dict.fromkeys(record.issue.code for record in records)),
                assessment_complete=False,
            ),
        )
