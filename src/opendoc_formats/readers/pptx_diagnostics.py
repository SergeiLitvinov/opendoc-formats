"""Partial, source-located PPTX preservation diagnostics; never execute content."""

from __future__ import annotations

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

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


class PptxDiagnostics:
    def __init__(self, source: Path) -> None:
        self.source = source
        self.records: list[PreservationRecord] = []
        self.part = "/ppt/presentation.xml"
        self.page: int | None = None

    def record(
        self, feature: str, reason: str, message: str, node: Any = None,
        *, state: PreservationState = PreservationState.LOST, resource_id: str | None = None,
    ) -> None:
        shape = node
        while shape is not None and shape.tag not in {P + name for name in ("sp", "grpSp", "pic", "graphicFrame", "cxnSp")}:
            shape = shape.getparent()
        identity = shape.find(".//" + P + "cNvPr") if shape is not None else None
        object_id = identity.get("id") if identity is not None else None
        xpath = node.getroottree().getpath(node) if node is not None else ""
        location = f"{self.source}!{self.part}" + (f"#xpath={xpath}" if xpath else "")
        self.records.append(PreservationRecord(
            issue=DiagnosticIssue(feature, IssueSeverity.LOSS, message, location,
                                  {"resource_id": resource_id} if resource_id else None, reason),
            state=state,
            provenance=Provenance("pptx", str(self.source), page=self.page, object_id=object_id, package_part=self.part),
        ))

    def slide(self, slide: Any, page: int, original_part: str) -> None:
        self.part, self.page = original_part, page
        features = {
            P + "transition": ("pptx.transition", "unsupported-transition", "Slide transition is not imported"),
            P + "timing": ("pptx.timing", "unsupported-timing", "Animation and timing tree are not imported"),
            P + "grpSp": ("pptx.group", "flattened-group", "Group hierarchy is flattened; child geometry may survive"),
            A + "videoFile": ("pptx.media", "unsupported-video", "Video playback and source references are not imported"),
            A + "audioFile": ("pptx.media", "unsupported-audio", "Audio playback and source references are not imported"),
            A + "scene3d": ("pptx.3d", "unsupported-3d", "3D scene settings are not imported"),
            A + "sp3d": ("pptx.3d", "unsupported-3d", "3D shape settings are not imported"),
        }
        for node in slide._element.iter():
            if node.tag in features:
                self.record(*features[node.tag], node)

    def graphic(self, element: Any, *, resource_id: str | None = None) -> None:
        data = element.find(".//" + A + "graphicData")
        uri = data.get("uri", "") if data is not None else ""
        feature = "pptx.ole" if element.find(".//" + P + "oleObj") is not None else (
            "pptx.diagram" if uri.endswith("/diagram") else "pptx.graphic-object"
        )
        self.record(
            feature, "visual-only-graphic" if resource_id else "unsupported-graphic",
            f"Graphic object semantics are not imported ({uri}); " +
            ("only the embedded preview is retained" if resource_id else "no preview is retained"),
            element, state=PreservationState.VISUAL if resource_id else PreservationState.LOST, resource_id=resource_id,
        )

    def attach(self, document: DocumentModel) -> None:
        set_integration(document, IntegrationModel(
            preservation=tuple(self.records),
            assessed_features=tuple(dict.fromkeys(record.issue.code for record in self.records)),
            assessment_complete=False,
        ))
