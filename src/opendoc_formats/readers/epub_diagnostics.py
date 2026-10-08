"""Located, partial EPUB preservation assessment using the OpenDoc contract."""

from __future__ import annotations

import posixpath
from pathlib import Path
from typing import Any

from opendoc_model import (
    DiagnosticIssue,
    DocumentModel,
    IntegrationModel,
    IssueSeverity,
    PreservationRecord,
    PreservationState,
    Provenance,
    set_integration,
)


class EpubDiagnostics:
    def __init__(self, source: Path, root_directory: str = "") -> None:
        self.source = source
        self.root_directory = root_directory
        self.records: list[PreservationRecord] = []

    def lost(self, feature: str, reason: str, message: str, part: str, node: Any = None) -> None:
        part = posixpath.normpath(posixpath.join(self.root_directory, part))
        object_id = str(node.get("id")) if node is not None and node.get("id") else None
        line = getattr(node, "sourceline", None)
        column = getattr(node, "sourcepos", None)
        fragment = object_id or (f"line={line},column={column}" if line is not None else "")
        location = f"{self.source}!/{part}" + (f"#{fragment}" if fragment else "")
        self.records.append(PreservationRecord(
            issue=DiagnosticIssue(feature, IssueSeverity.LOSS, message, location, reason=reason),
            state=PreservationState.LOST,
            provenance=Provenance("epub", str(self.source), object_id=object_id, package_part="/" + part.lstrip("/")),
        ))

    def attach(self, document: DocumentModel) -> None:
        # Detected losses do not constitute an exhaustive assessment of EPUB/CSS.
        set_integration(document, IntegrationModel(
            preservation=tuple(self.records),
            assessed_features=tuple(dict.fromkeys(record.issue.code for record in self.records)),
            assessment_complete=False,
        ))

    def chapter(self, body: Any, part: str, blocks: set[str]) -> None:
        features = {
            "svg": ("epub.inline-svg", "unsupported-inline-svg", "Inline SVG geometry is not imported"),
            "audio": ("epub.media", "unsupported-media", "Audio playback and source references are not imported"),
            "video": ("epub.media", "unsupported-media", "Video playback and source references are not imported"),
            "object": ("epub.object", "unsupported-object", "Embedded object structure is not imported"),
            "script": ("epub.script", "inactive-script", "Script is never executed and has no semantic model"),
        }
        for node in body.find_all(True):
            if node.name == "table" and node.find_parent(blocks - {"table"}):
                self.lost("epub.table", "nested-table-block",
                          "Table inside a text block is flattened by this profile", part, node)
            elif node.name in features:
                self.lost(*features[node.name], part, node)
            elif node.name == "img" and not node.find_parent(blocks):
                self.lost("epub.image", "standalone-image", "Image outside supported text blocks is not imported", part, node)
