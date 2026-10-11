"""Evidence-based partial preservation assessment of advanced DOCX objects."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from lxml import etree
from opendoc_model import (
    DiagnosticIssue,
    DocumentLimits,
    DocumentModel,
    IntegrationModel,
    IssueSeverity,
    PreservationRecord,
    PreservationState,
    Provenance,
    set_integration,
)

from opendoc_formats.ooxml.borders import native_only
from opendoc_formats.ooxml.layout import native_layout_supported
from opendoc_formats.ooxml.spacing import native_spacing_supported
from opendoc_formats.readers.docx_features import _relationship_feature

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
V = "{urn:schemas-microsoft-com:vml}"
OFFICE = "{urn:schemas-microsoft-com:office:office}"
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"
DGM = "{http://schemas.openxmlformats.org/drawingml/2006/diagram}"
_TAGS = {
    **{W + tag: "revisions" for tag in ("ins", "del", "moveFrom", "moveTo")},
    **{W + tag: "comments" for tag in ("comment", "commentReference", "commentRangeStart", "commentRangeEnd")},
    W + "sdt": "content-controls", W + "txbxContent": "text-boxes", V + "textbox": "text-boxes",
    V + "textpath": "wordart", W14 + "textFill": "wordart", W14 + "textOutline": "wordart",
    OFFICE + "OLEObject": "embedded-ole", DGM + "relIds": "smartart",
    W + "documentProtection": "protection", W + "fldSimple": "fields",
    W + "smartTag": "smart-tags",
}
_XML_KEYS = {"docx_raw_inline_xml", "docx_raw_block_xml", "field_xml", "vml_xml", "document_protection_xml",
             "docx_tabs_native_xml", "docx_line_spacing_native_xml"}


def _feature(node: Any) -> str | None:
    if node.tag == W + 'spacing' and not native_spacing_supported(node):
        return 'line-spacing'
    if node.tag == W + 'tabs' and any(child.get(W + 'val') in ('start', 'end', 'num') for child in node):
        return 'tab-stops-semantics'
    if node.tag in {W + 'tblInd', W + 'tabs'} and not native_layout_supported(node):
        return 'table-indent' if node.tag == W + 'tblInd' else 'tab-stops'
    if node.tag in {W + 'tblBorders', W + 'tcBorders'}:
        parent = node.getparent()
        owner = parent.getparent() if parent is not None else None
        if owner is not None and owner.tag in {W + 'tbl', W + 'tc'} and native_only(node):
            return 'table-borders'
    if node.tag == W + "fldChar" and node.get(W + "fldCharType") == "begin":
        return "fields"
    return _TAGS.get(node.tag)


def _parse(data: str | bytes) -> Any:
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    return etree.fromstring(data.encode("utf-8") if isinstance(data, str) else data, parser)


def _fingerprint(node: Any) -> bytes:
    return hashlib.sha256(etree.tostring(node, method="c14n", exclusive=True, with_comments=True)).digest()


def _retained_fragments(model: DocumentModel) -> Counter[bytes]:
    retained: Counter[bytes] = Counter()
    pending: list[Any] = [model.sections, model.metadata]
    while pending:
        value = pending.pop()
        if is_dataclass(value) and not isinstance(value, type):
            pending.extend(getattr(value, field.name) for field in fields(value))
        elif isinstance(value, (list, tuple)):
            pending.extend(value)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in _XML_KEYS:
                    for fragment in item if isinstance(item, list) else [item]:
                        if not isinstance(fragment, str):
                            continue
                        try:
                            root = _parse(fragment)
                            retained.update(_fingerprint(node) for node in root.iter() if _feature(node))
                        except (etree.XMLSyntaxError, etree.C14NError):
                            continue
                else:
                    pending.append(item)
    return retained


def attach_docx_diagnostics(document: Any, model: DocumentModel, source: Path, *, limits: DocumentLimits | None = None) -> None:
    fragments = _retained_fragments(model)
    graph = model.package
    records: list[PreservationRecord] = []

    def record(feature: str, kept: bool, part: str, pointer: str, object_id: str | None, measurement: dict | None = None) -> None:
        state = PreservationState.OPAQUE if kept else PreservationState.LOST
        records.append(PreservationRecord(
            issue=DiagnosticIssue(
                "docx." + feature, IssueSeverity.LOSS,
                "Source XML/part is retained without semantic support" if kept else "Source object is not retained",
                f"{source}!{part}#{pointer}", measurement, "native-opaque" if kept else "unsupported-object",
            ), state=state,
            provenance=Provenance("docx", str(source), object_id=object_id, package_part=part),
        ))

    for part in document.part.package.iter_parts():
        name = str(part.partname)
        stored = graph.parts.get(name) if graph is not None else None
        complete_part = stored is not None and stored.data == part.blob
        if "xml" in str(part.content_type):
            try:
                root = _parse(part.blob)
            except etree.XMLSyntaxError:
                root = None
            if root is not None:
                for node in root.iter():
                    feature = _feature(node)
                    if feature is None:
                        continue
                    # Unused numbering definitions are deliberately omitted by
                    # the reader; their tab positions do not affect this document.
                    if (feature in {'tab-stops', 'tab-stops-semantics', 'table-indent'}
                            and root.tag == W + 'numbering' and stored is None):
                        continue
                    try:
                        fingerprint = _fingerprint(node)
                    except etree.C14NError:
                        fingerprint = b""
                    kept = complete_part or bool(fragments[fingerprint])
                    if not complete_part and kept:
                        fragments[fingerprint] -= 1
                    record(feature, kept, name, "xpath=" + node.getroottree().getpath(node), node.get(W + "id"))
        for relation in part.rels.values():
            feature = _relationship_feature(relation.reltype)
            if feature is None:
                continue
            target = relation.target_ref if relation.is_external else str(relation.target_part.partname)
            target_kept = (
                not relation.is_external and graph is not None and target in graph.parts
                and graph.parts[target].data == relation.target_part.blob
                and any(edge.source == name and edge.id == relation.rId and edge.target == target
                        and not edge.external and edge.relationship_type == relation.reltype for edge in graph.relationships)
            )
            record("relationship." + feature, target_kept, name, "relationship=" + relation.rId, relation.rId,
                   {"target": target, "external": relation.is_external})
    set_integration(model, IntegrationModel(
        preservation=tuple(records), assessed_features=tuple(dict.fromkeys(record.issue.code for record in records)),
        assessment_complete=False,
    ), limits=limits)
