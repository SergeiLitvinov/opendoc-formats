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
    Resource,
    set_integration,
)


class EpubDiagnostics:
    def __init__(self, source: Path, root_directory: str = "", resources: dict[str, Resource] | None = None) -> None:
        self.source = source
        self.root_directory = root_directory
        self.records: list[PreservationRecord] = []
        self.resources = resources if resources is not None else {}

    def lost(self, feature: str, reason: str, message: str, part: str, node: Any = None) -> None:
        self._record(feature, reason, message, part, node, PreservationState.LOST)

    def opaque(self, feature: str, reason: str, message: str, part: str, resource_id: str, node: Any = None) -> None:
        if resource_id not in self.resources or self.resources[resource_id].data is None:
            raise ValueError("EPUB opaque record requires a retained resource")
        self._record(feature, reason, message, part, node, PreservationState.OPAQUE, resource_id)

    def _record(
        self,
        feature: str,
        reason: str,
        message: str,
        part: str,
        node: Any,
        state: PreservationState,
        resource_id: str | None = None,
    ) -> None:
        if len(self.records) >= 10_000:
            raise ValueError("EPUB diagnostic objects exceed profile limit")
        part = posixpath.normpath(posixpath.join(self.root_directory, part))
        object_id = str(node.get("id")) if node is not None and node.get("id") else None
        line = getattr(node, "sourceline", None)
        column = getattr(node, "sourcepos", None)
        fragment = object_id or (f"line={line},column={column}" if line is not None else "")
        location = f"{self.source}!/{part}" + (f"#{fragment}" if fragment else "")
        self.records.append(
            PreservationRecord(
                issue=DiagnosticIssue(feature, IssueSeverity.LOSS, message, location, reason=reason),
                state=state,
                provenance=Provenance("epub", str(self.source), object_id=object_id, package_part="/" + part.lstrip("/")),
                extra={"resource_id": resource_id} if resource_id else {},
            )
        )

    def attach(self, document: DocumentModel) -> None:
        # Detected losses do not constitute an exhaustive assessment of EPUB/CSS.
        set_integration(
            document,
            IntegrationModel(
                preservation=tuple(self.records),
                assessed_features=tuple(dict.fromkeys(record.issue.code for record in self.records)),
                assessment_complete=False,
            ),
        )

    def chapter(self, body: Any, part: str, blocks: set[str]) -> None:
        features = {
            "audio": ("epub.media", "unsupported-media", "Audio playback and source references are not imported"),
            "video": ("epub.media", "unsupported-media", "Video playback and source references are not imported"),
            "object": ("epub.object", "unsupported-object", "Embedded object structure is not imported"),
            "script": ("epub.script", "inactive-script", "Script is never executed and has no semantic model"),
        }
        for node in body.find_all(True):
            if node.name == "table" and node.find_parent(blocks - {"table"}):
                self.lost(
                    "epub.table", "nested-table-block", "Table inside a text block is flattened by this profile", part, node
                )
            elif node.name in features:
                self.lost(*features[node.name], part, node)
