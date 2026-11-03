"""Evidence-based partial preservation assessment of advanced DOCX objects."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import fields, is_dataclass, replace
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
    Table,
    TableCell,
    get_integration,
    set_integration,
    walk_model,
)

from opendoc_formats.ooxml.borders import native_only
from opendoc_formats.ooxml.docx_whitespace import SPACE
from opendoc_formats.ooxml.layout import native_layout_supported
from opendoc_formats.ooxml.orphans import retained_original
from opendoc_formats.ooxml.paragraph_flow import native_flow_supported
from opendoc_formats.ooxml.paragraph_indent import native_indents_supported
from opendoc_formats.ooxml.spacing import native_spacing_supported
from opendoc_formats.readers.docx_features import _relationship_feature
from opendoc_formats.support.cancellation import cancellable_items, checkpoint

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
    if isinstance(node.tag, str) and node.tag.startswith(W) and node.get(SPACE) not in (None, 'default', 'preserve'):
        return 'text-whitespace'
    if (node.getparent() is None and node.tag in {W+name for name in ('hdr', 'ftr', 'footnotes', 'endnotes', 'comments')}
            and node.get(SPACE) is not None):
        return 'text-whitespace'
    if node.tag in {W + 'txbxContent', V + 'textbox'}:
        from opendoc_formats.ooxml.positioned_text import native_positioned_content_supported

        if native_positioned_content_supported(node):
            return None
    if node.tag == W + 'ind' and not native_indents_supported(node):
        return 'paragraph-indent'
    if (node.tag in {W + name for name in ('spacing', 'keepLines', 'keepNext', 'pageBreakBefore', 'widowControl')}
            and not native_flow_supported(node)):
        return 'paragraph-flow'
    if node.tag == W + 'spacing' and not native_spacing_supported(node):
        return 'line-spacing'
    if node.tag == W + 'tabs' and any(child.get(W + 'val') in ('start', 'end', 'num') for child in cancellable_items(node)):
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
        checkpoint()
        value = pending.pop()
        if is_dataclass(value) and not isinstance(value, type):
            pending.extend(getattr(value, field.name) for field in cancellable_items(fields(value)))
        elif isinstance(value, (list, tuple)):
            pending.extend(value)
        elif isinstance(value, dict):
            for key, item in value.items():
                checkpoint()
                if key in _XML_KEYS:
                    for fragment in item if isinstance(item, list) else [item]:
                        checkpoint()
                        if not isinstance(fragment, str):
                            continue
                        try:
                            root = _parse(fragment)
                            retained.update(_fingerprint(node) for node in cancellable_items(root.iter()) if _feature(node))
                        except (etree.XMLSyntaxError, etree.C14NError):
                            continue
                else:
                    pending.append(item)
    return retained


def attach_docx_diagnostics(document: Any, model: DocumentModel, source: Path, *, limits: DocumentLimits | None = None) -> None:
    fragments = _retained_fragments(model)
    graph = model.package
    existing = get_integration(model, limits=limits) or IntegrationModel()
    physical_relationships = set()
    for retained in cancellable_items(existing.preservation):
        measurement = retained.issue.measurement
        if (retained.issue.code == 'docx.orphan-relationship' and retained.state is PreservationState.OPAQUE
                and retained.provenance is not None and retained.provenance.source_path == str(source)
                and measurement is not None):
            physical_relationships.add((measurement['owner_part'], retained.provenance.object_id,
                                        measurement['relationship_type'], measurement['external'],
                                        measurement['target'] if measurement['external'] else measurement['target_part']))
    records: list[PreservationRecord] = []
    from opendoc_formats.ooxml.page_geometry import unresolved

    for index, section in enumerate(model.sections):
        checkpoint()
        missing = unresolved(section)
        if missing:
            records.append(PreservationRecord(
                issue=DiagnosticIssue('docx.page-geometry', IssueSeverity.WARNING,
                                      'Source omits page declarations; numeric Model values are a projection, '
                                      'not evidence of source/environment geometry',
                                      f'{source}!{document.part.partname}#section={index+1}:page-declarations',
                                      {'unresolved_fields': missing}, 'source-page-unspecified'),
                state=PreservationState.OPAQUE,
                provenance=Provenance('docx', str(source), package_part=str(document.part.partname)),
            ))

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

    retained_edges = {
        (edge.source, edge.id, edge.target, edge.relationship_type)
        for edge in cancellable_items(graph.relationships if graph is not None else ()) if not edge.external
    }

    def record_relationships(owner: Any, name: str, diagnostic_part: str) -> None:
        for relation in owner.rels.values():
            checkpoint()
            feature = _relationship_feature(relation.reltype)
            if feature is None:
                continue
            target = relation.target_ref if relation.is_external else str(relation.target_part.partname)
            if (name, relation.rId, relation.reltype, relation.is_external, target) in physical_relationships:
                continue  # Exact captured .rels already has a per-object opaque assessment.
            target_kept = (
                not relation.is_external and graph is not None and target in graph.parts
                and graph.parts[target].data == relation.target_part.blob
                and (name, relation.rId, target, relation.reltype) in retained_edges
            )
            record("relationship." + feature, target_kept, diagnostic_part,
                   "relationship=" + relation.rId, relation.rId,
                   {"target": target, "external": relation.is_external, "relationship_type": relation.reltype})

    # OPC package relationships have no owning XML part. Their physical .rels
    # is the diagnostic source; '/' is only the graph's package-root address.
    record_relationships(document.part.package, "/", "/_rels/.rels")
    for part in document.part.package.iter_parts():
        checkpoint()
        name = str(part.partname)
        stored = graph.parts.get(name) if graph is not None else None
        complete_part = stored is not None and (stored.data == part.blob or retained_original(model, name, stored.data))
        if "xml" in str(part.content_type):
            try:
                root = _parse(part.blob)
            except etree.XMLSyntaxError:
                root = None
            if root is not None:
                if root.tag == '{urn:opendoc-formats:source-grid:1}grid':
                    marker = '_og_'+root.get('id', '')
                    if not any(node.get(W+'name') == marker for node in document.part.element.iter(W+'bookmarkStart')):
                        records.append(PreservationRecord(
                            issue=DiagnosticIssue('docx.source-grid', IssueSeverity.WARNING,
                                                  'Source grid has no table binding; actual Word grid is retained',
                                                  f'{source}!{name}', reason='source-grid-unbound'),
                            state=PreservationState.OPAQUE if complete_part else PreservationState.LOST,
                            provenance=Provenance('docx', str(source), package_part=name),
                        ))
                for node in root.iter():
                    checkpoint()
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
        record_relationships(part, name, name)
    for reference in walk_model(model, limits=limits):
        checkpoint()
        grid = reference.node.properties.get('docx_source_grid_identity') if isinstance(reference.node, Table) else None
        if grid is not None and grid.get('state') != 'verified':
            records.append(PreservationRecord(
                issue=DiagnosticIssue('docx.source-grid', IssueSeverity.WARNING,
                                      'Source grid identity is unverified; actual Word grid is retained',
                                      f'{source}#{reference.path}', reason='source-grid-unverified'),
                state=PreservationState.OPAQUE,
                provenance=Provenance('docx', str(source), object_id=reference.path),
            ))
        if isinstance(reference.node, TableCell) and reference.node.properties.get('docx_merge_borders_unsupported'):
            records.append(PreservationRecord(
                issue=DiagnosticIssue('docx.merge-borders', IssueSeverity.LOSS,
                                      'Native merged-cell border segments require explicit resolution',
                                      f'{source}#{reference.path}', reason='unsupported-native-segments'),
                state=PreservationState.OPAQUE,
                provenance=Provenance('docx', str(source), object_id=reference.path),
            ))
    set_integration(model, replace(existing,
        preservation=(*existing.preservation, *records),
        assessed_features=tuple(dict.fromkeys((*existing.assessed_features,
                                              *(record.issue.code for record in cancellable_items(records))))),
        assessment_complete=False,
    ), limits=limits)
