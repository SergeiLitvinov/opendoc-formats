"""Located, partial EPUB preservation assessment using the OpenDoc contract."""

from __future__ import annotations

import hashlib
import posixpath
from collections.abc import Callable
from itertools import chain
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from opendoc_model import (
    ArtifactLimitError,
    DiagnosticIssue,
    DocumentLimits,
    DocumentModel,
    IntegrationModel,
    IssueSeverity,
    PreservationRecord,
    PreservationState,
    Provenance,
    Resource,
    ResourceKind,
    set_integration,
)

from opendoc_formats.readers.epub_anchors import EpubAnchors
from opendoc_formats.support.cancellation import check_cancelled


class EpubDiagnostics:
    def __init__(self, source: Path, root_directory: str = "", resources: dict[str, Resource] | None = None, *,
                 source_chapters: dict[str, bytes] | None = None,
                 limits: DocumentLimits | None = None,
                 cancelled: Callable[[], bool] | None = None) -> None:
        if limits is not None and not isinstance(limits, DocumentLimits):
            raise TypeError('limits must be DocumentLimits or None')
        self.source = source
        self.root_directory = root_directory
        self.records: list[PreservationRecord] = []
        self.resources = resources if resources is not None else {}
        self.cancelled = cancelled
        self.source_chapters = source_chapters if source_chapters is not None else {}
        self.retained_chapters: dict[str, str] = {}
        self.limits = limits if limits is not None else DocumentLimits()
        # This early object-count guard bounds staging only. The SDK still
        # measures the complete ledger/document against the chosen Model budget.
        self.max_records = min(10_000, self.limits.max_nodes)
        self.table_cells = 0
        self.anchors = EpubAnchors(self.limits.max_nodes, cancelled, root_directory=root_directory)

    def claim_table_cell(self, part: str) -> None:
        """Bound native cell construction across tables/chapters, before SDK validation."""
        self.checkpoint()
        if self.table_cells >= self.limits.max_nodes:
            raise ArtifactLimitError('EPUB table cell staging exceeds selected limit at '+part,
                                     path=f'epub.table_cells[{self.table_cells}]',
                                     quota='table cells', maximum=self.limits.max_nodes)
        self.table_cells += 1

    def retain_chapter(self, part: str) -> str | None:
        """Retain original bytes once; a soup serialization is not the original XHTML."""
        self.checkpoint()
        if part in self.retained_chapters:
            return self.retained_chapters[part]
        payload = self.source_chapters.get(part)
        if payload is None:
            return None
        digest = hashlib.sha256(part.encode('utf-8'))
        digest.update(payload)
        resource_id = 'epub-compound-source-'+digest.hexdigest()
        while resource_id in self.resources:
            self.checkpoint()
            resource_id += '-source'
        package_part = posixpath.normpath(posixpath.join(self.root_directory, part))
        self.resources[resource_id] = Resource(
            resource_id, ResourceKind.ATTACHMENT, 'application/xhtml+xml', data=payload,
            filename=posixpath.basename(part),
            provenance=Provenance('epub', str(self.source), package_part='/'+package_part.lstrip('/')),
        )
        self.retained_chapters[part] = resource_id
        return resource_id

    def checkpoint(self) -> None:
        check_cancelled(self.cancelled, 'EPUB model')

    def lost(self, feature: str, reason: str, message: str, part: str, node: Any = None, *,
             measurement: dict[str, Any] | None = None, attribute: str | None = None) -> None:
        self._record(feature, reason, message, part, node, PreservationState.LOST,
                     measurement=measurement, attribute=attribute)

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
        measurement: dict[str, Any] | None = None,
        attribute: str | None = None,
    ) -> None:
        self.checkpoint()
        if len(self.records) >= self.max_records:
            raise ArtifactLimitError('EPUB diagnostic objects exceed staging limit at '+part,
                                     path=f'epub.diagnostics[{len(self.records)}]',
                                     quota='diagnostic objects', maximum=self.max_records)
        part = posixpath.normpath(posixpath.join(self.root_directory, part))
        object_id = str(node.get("id")) if node is not None and node.get("id") else None
        line = getattr(node, "sourceline", None)
        column = getattr(node, "sourcepos", None)
        fragment = object_id or (f"line={line},column={column}" if line is not None else "")
        if attribute is not None:
            fragment += '/@'+attribute
        location = f"{self.source}!/{part}" + (f"#{fragment}" if fragment else "")
        self.records.append(
            PreservationRecord(
                issue=DiagnosticIssue(feature, IssueSeverity.LOSS, message, location, measurement, reason=reason),
                state=state,
                provenance=Provenance("epub", str(self.source), object_id=object_id, package_part="/" + part.lstrip("/")),
                extra={"resource_id": resource_id} if resource_id else {},
            )
        )

    def attach(self, document: DocumentModel, *, limits: DocumentLimits | None = None) -> None:
        self.checkpoint()
        # Detected losses do not constitute an exhaustive assessment of EPUB/CSS.
        set_integration(
            document,
            IntegrationModel(
                preservation=tuple(self.records),
                assessed_features=tuple(dict.fromkeys(record.issue.code for record in self.records)),
                assessment_complete=False,
            ), limits=self.limits if limits is None else limits,
        )

    def chapter(self, body: Any, part: str, blocks: set[str]) -> None:
        features = {
            "audio": ("epub.media", "unsupported-media", "Audio playback and source references are not imported"),
            "video": ("epub.media", "unsupported-media", "Video playback and source references are not imported"),
            "object": ("epub.object", "unsupported-object", "Embedded object structure is not imported"),
            "script": ("epub.script", "inactive-script", "Script is never executed and has no semantic model"),
            "iframe": ("epub.frame", "unsupported-frame", "Embedded browsing context is not modeled; source is not opened"),
            "embed": ("epub.object", "unsupported-object", "Embedded resource behavior is not modeled; source is not opened"),
            "form": ("epub.form", "unsupported-form", "Form submission and interactive state are not modeled"),
        }
        controls = {"input", "button", "select", "textarea", "option", "optgroup", "output", "datalist", "progress", "meter"}
        attributes = ("src", "data", "type", "name", "value", "label", "action", "method", "checked", "selected",
                      "multiple", "disabled", "readonly", "min", "max")
        for node in chain((body,), body.find_all(True)):
            self.checkpoint()
            for name, value in node.attrs.items():
                self.checkpoint()
                # The same finite prefix policy is used when embedded SVG and
                # MathML are cleaned. No handler attribute is imported as code.
                if name.lower().startswith('on'):
                    self.lost('epub.event-handler', 'inactive-event-handler',
                              'Attribute beginning with on has no behavior model and is never executed', part, node,
                              measurement={'element': node.name, 'attribute': name, 'value': value}, attribute=name)
            href = node.get('href')
            if node.name in {'a', 'area'} and isinstance(href, str):
                try:
                    scheme = urlsplit(href).scheme.lower()
                except ValueError:
                    # Link projection reports malformed URI syntax at /@href;
                    # it must not fail first in this script-action inventory.
                    scheme = ''
                if scheme in {'javascript', 'vbscript'}:
                    self.lost('epub.link-action', 'unsupported-link-action',
                              'Script link behavior is not modeled; the original URI remains source link data', part, node,
                              measurement={'element': node.name, 'attribute': 'href', 'value': href, 'scheme': scheme},
                              attribute='href')
            if node.name == "table" and node.find_parent(blocks - {"table"}):
                resource = self.retain_chapter(part)
                message = 'Table inside a text block has no semantic compound-flow projection'
                if resource:
                    self.opaque('epub.table', 'nested-table-block', message+'; original chapter XHTML bytes retained',
                                part, resource, node)
                else:
                    self.lost('epub.table', 'nested-table-block', message, part, node)
            elif node.name in features or node.name in controls:
                feature = features.get(node.name, (
                    "epub.control", "unsupported-control", "Control state and behavior have no semantic model",
                ))
                self.lost(*feature, part, node,
                          measurement={"element": node.name,
                                       "attributes": {name: node.get(name) for name in attributes if node.has_attr(name)}})
