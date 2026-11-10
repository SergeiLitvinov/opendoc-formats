"""Located, partial EPUB preservation assessment using the OpenDoc contract."""

from __future__ import annotations

import hashlib
import posixpath
from collections import Counter
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
    get_anchor,
    set_integration,
    walk_model,
)

from opendoc_formats.readers.epub_anchors import EpubAnchors
from opendoc_formats.support.cancellation import check_cancelled
from opendoc_formats.support.mathml import MATHML_ELEMENTS, MATHML_NAMESPACE


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
        self.internal_links: list[tuple[str, str, Provenance]] = []
        self.ambiguous_targets: set[str] = set()
        self.embedded_targets: Counter[str] = Counter()
        self.decoded_fonts: dict[str, str] = {}

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
        location, provenance = self._source_location(part, node, attribute)
        self._append(DiagnosticIssue(feature, IssueSeverity.LOSS, message, location, measurement, reason=reason),
                     provenance, state, resource_id)

    def _source_location(self, part: str, node: Any, attribute: str | None) -> tuple[str, Provenance]:
        part = posixpath.normpath(posixpath.join(self.root_directory, part))
        object_id = str(node.get("id")) if node is not None and node.get("id") else None
        line = getattr(node, "sourceline", None)
        column = getattr(node, "sourcepos", None)
        fragment = object_id or (f"line={line},column={column}" if line is not None else "")
        if attribute is not None:
            fragment += '/@'+attribute
        location = f"{self.source}!/{part}" + (f"#{fragment}" if fragment else "")
        return location, Provenance("epub", str(self.source), object_id=object_id, package_part="/" + part.lstrip("/"))

    def _append(self, issue: DiagnosticIssue, provenance: Provenance, state: PreservationState,
                resource_id: str | None = None) -> None:
        self.checkpoint()
        if len(self.records) >= self.max_records:
            raise ArtifactLimitError('EPUB diagnostic objects exceed staging limit at '+str(provenance.package_part),
                                     path=f'epub.diagnostics[{len(self.records)}]',
                                     quota='diagnostic objects', maximum=self.max_records)
        self.records.append(
            PreservationRecord(
                issue=issue,
                state=state,
                provenance=provenance,
                extra={"resource_id": resource_id} if resource_id else {},
            )
        )

    def internal_link(self, target: str, part: str, node: Any) -> None:
        self.checkpoint()
        if len(self.internal_links) >= self.limits.max_nodes:
            raise ArtifactLimitError('EPUB internal link staging exceeds node limit', path='epub.internal_links',
                                     quota='nodes', maximum=self.limits.max_nodes)
        location, provenance = self._source_location(part, node, 'href')
        self.internal_links.append((target, location, provenance))

    def bind_mathml_anchors(self, root: Any, part: str) -> bool:
        for element in root.iter():
            self.checkpoint()
            tag = element.tag
            namespace, _, name = tag[1:].partition("}") if tag.startswith("{") else (None, "", tag)
            if namespace not in {None, MATHML_NAMESPACE} or name not in MATHML_ELEMENTS:
                return False
        return bool(self.bind_embedded_anchors(root, part))

    def bind_embedded_anchors(self, root: Any, part: str) -> dict[str, str]:
        identifiers = {}
        for element in root.iter():
            self.checkpoint()
            identifier = element.get('id')
            if element is root or not identifier:
                continue
            target = self.anchors.get(part, identifier)
            identifiers[identifier] = target
            element.set('id', target)
            self.embedded_targets[target] += 1
        if not identifiers:
            return {}
        for element in root.iter():
            self.checkpoint()
            for attribute in ('href', '{http://www.w3.org/1999/xlink}href'):
                href = element.get(attribute, '')
                if href.startswith('#') and href[1:] in identifiers:
                    element.set(attribute, '#' + identifiers[href[1:]])
        return identifiers

    def _check_internal_links(self, document: DocumentModel) -> None:
        if not self.internal_links:
            return
        targets = self.embedded_targets.copy()
        for reference in walk_model(document, limits=self.limits):
            self.checkpoint()
            properties = getattr(reference.node, 'properties', {})
            identifier = properties.get('anchor_id')
            if isinstance(identifier, str):
                targets[identifier] += 1
            if 'opendoc.anchor' in properties and (anchor := get_anchor(reference.node, limits=self.limits)) is not None:
                if anchor.id != identifier:
                    targets[anchor.id] += 1
        for target, location, provenance in self.internal_links:
            self.checkpoint()
            if target in self.ambiguous_targets or targets[target] > 1:
                reason = 'ambiguous-link-target'
                message = 'Internal EPUB link target has more than one source or imported occurrence'
            elif not targets[target]:
                reason = 'missing-link-target'
                message = 'Internal EPUB link target is absent from the imported document'
            else:
                continue
            self._append(DiagnosticIssue('epub.hyperlink', IssueSeverity.LOSS, message, location,
                                         {'target': '#' + target}, reason=reason), provenance, PreservationState.LOST)

    def attach(self, document: DocumentModel, *, limits: DocumentLimits | None = None) -> None:
        self.checkpoint()
        self._check_internal_links(document)
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
        seen_ids: set[str] = set()
        for node in chain((body,), body.find_all(True)):
            self.checkpoint()
            identifier = node.get('id')
            if isinstance(identifier, str) and identifier:
                if identifier in seen_ids:
                    self.ambiguous_targets.add(self.anchors.get(part, identifier))
                seen_ids.add(identifier)
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
