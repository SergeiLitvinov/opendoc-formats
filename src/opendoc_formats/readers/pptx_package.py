"""Physical PPTX source package, distinct from the engine's repaired/reordered view."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from opendoc_model import (
    ArtifactLimitError,
    DiagnosticIssue,
    DocumentLimits,
    PackageGraph,
    PackagePart,
    PackageRelationship,
    PreservationRecord,
    PreservationState,
    Provenance,
)
from opendoc_model.diagnostics import IssueSeverity

from opendoc_formats.anatomy import AnatomyLimits, BinarySnapshot, inspect_binary
from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.native.opc import part_name
from opendoc_formats.support.cancellation import cancellable_items, checkpoint

OFFICE_DOCUMENT = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument'


def capture_pptx_package(source: bytes, *, limits: DocumentLimits | None = None) -> tuple[PackageGraph, BinarySnapshot]:
    """Retain physical parts and only proved edges; rejected edges stay in raw .rels and audit."""
    budget = limits or DocumentLimits()
    if budget.max_bytes == 0 or budget.max_embedded_bytes == 0:
        quota = 'bytes' if budget.max_bytes == 0 else 'embedded_bytes'
        raise ArtifactLimitError('PPTX source package exceeds byte budget', path='package', quota=quota, maximum=0)
    snapshot = inspect_binary(source, container='zip', capture=True, limits=AnatomyLimits(
        max_input_bytes=budget.max_bytes, max_items=budget.max_nodes, max_part_bytes=budget.max_embedded_bytes,
        max_total_bytes=budget.max_embedded_bytes, max_xml_nodes=budget.max_nodes, max_xml_depth=budget.max_depth,
        max_xml_name_chars=budget.max_bytes, max_xml_characters=budget.max_bytes,
    ))
    audit = snapshot.opc
    if audit is None:
        raise InvalidDocumentError('PPTX has no physical OPC inventory')
    identities = Counter((edge.owner, dict(edge.attributes).get('Id')) for edge in cancellable_items(audit.relationships))
    roots = [edge for edge in cancellable_items(audit.relationships)
             if edge.owner == '/' and dict(edge.attributes).get('Type') == OFFICE_DOCUMENT]
    if (len(roots) != 1 or roots[0].status != 'internal' or roots[0].resolved_target is None
            or identities[(roots[0].owner, dict(roots[0].attributes).get('Id'))] != 1):
        raise InvalidDocumentError('PPTX requires one proved physical officeDocument relationship')
    parts = []
    for item in cancellable_items(snapshot.items):
        if item.kind != 'zip-member':
            continue
        name = part_name(item.locator.removeprefix('zip:'))
        media_type = dict(item.details).get('content_type') or 'application/octet-stream'
        if name == '/[Content_Types].xml':
            media_type = 'application/xml'
        assert item.payload is not None  # capture=True
        parts.append(PackagePart(name, media_type, item.payload))
    names = {part.name for part in parts}
    relationships = []
    for edge in cancellable_items(audit.relationships):
        if edge.status not in {'internal', 'external'} or edge.owner is None:
            continue
        # The audit may retain an external URI from an orphan .rels for inspection.
        # It is not a proved graph edge unless its physical owner exists.
        if edge.owner != '/' and edge.owner not in names:
            continue
        attributes = dict(edge.attributes)
        if identities[(edge.owner, attributes['Id'])] != 1:
            continue  # a duplicate Id makes every occurrence ambiguous, including the first
        relationships.append(PackageRelationship(
            id=attributes['Id'], relationship_type=attributes['Type'], source=edge.owner,
            target=attributes['Target'] if edge.status == 'external' else edge.resolved_target,
            external=edge.status == 'external',
        ))
    checkpoint()
    graph = PackageGraph('pptx', root=roots[0].resolved_target,
                         parts={part.name: part for part in parts}, relationships=relationships)
    errors = graph.validate(limits=limits)
    if errors:
        raise InvalidDocumentError('; '.join(errors))
    return graph, snapshot


def package_records(source: Path, snapshot: BinarySnapshot) -> list[PreservationRecord]:
    """Locate every opaque source part and every physical audit finding; no semantic fidelity claim."""
    records = []
    for item in cancellable_items(snapshot.items):
        if item.kind != 'zip-member':
            continue
        name = item.locator.removeprefix('zip:')
        records.append(PreservationRecord(
            DiagnosticIssue('pptx.package-part', IssueSeverity.LOSS,
                            'Original part bytes retained as opaque source data; semantic and export coverage are finite',
                            f'{source}!{name}#zip-entry',
                            {'sha256': item.sha256, 'bytes': item.size,
                             'declared_content_type': dict(item.details).get('content_type')},
                            'source-part-retained'),
            PreservationState.OPAQUE, provenance=Provenance('pptx', str(source), object_id=name, package_part=name),
        ))
    if snapshot.opc is not None:
        for finding in cancellable_items(snapshot.opc.findings):
            name, _, address = finding.location.removeprefix('zip:').partition('#')
            records.append(PreservationRecord(
                DiagnosticIssue('pptx.package-audit', IssueSeverity.LOSS, finding.message,
                                f'{source}!{name}'+('#'+address if address else '#zip-entry'),
                                reason=finding.code),
                PreservationState.OPAQUE, provenance=Provenance('pptx', str(source), object_id=name, package_part=name),
            ))
    return records
