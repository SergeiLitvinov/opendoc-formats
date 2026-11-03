"""Inventory what the legacy text view drops; all addresses belong to the source."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import fields
from typing import Any

from opendoc_model import (
    INTEGRATION_PROPERTY,
    DiagnosticIssue,
    DocumentLimits,
    DocumentModel,
    Footnote,
    Formula,
    Image,
    IntegrationModel,
    IssueSeverity,
    ModelNode,
    NodeLocation,
    PageSettings,
    Paragraph,
    PreservationRecord,
    PreservationState,
    Provenance,
    Section,
    Table,
    TableCell,
    TextRun,
    TextStyle,
    get_integration,
    integration_to_dict,
)

from opendoc_formats.support.cancellation import checkpoint
from opendoc_formats.types import DocFormat


def in_body(reference: NodeLocation[ModelNode]) -> bool:
    current = reference
    while current.parent is not None:
        if isinstance(current.parent.node, Section):
            return current.field == 'blocks'
        current = current.parent
    return False


def projection_losses(
    document: DocumentModel, references: Sequence[NodeLocation[ModelNode]], *, limits: DocumentLimits | None = None,
) -> list[PreservationRecord]:
    records: list[PreservationRecord] = []

    def lost(feature: str, path: str, reference: NodeLocation[ModelNode] | None = None, *,
             origin_provenance: Provenance | None = None,
             **measurement: Any) -> None:
        checkpoint()
        origin = reference
        provenance = origin_provenance
        while provenance is None and origin is not None:
            provenance = getattr(origin.node, 'provenance', None)
            if provenance is not None:
                break
            origin = origin.parent
        provenance = provenance or Provenance(document.source_format or 'unknown', object_id=path)
        if feature not in {'node-provenance', 'resource'}:
            # Keep history once on its owner's loss, not once per discarded property.
            provenance = Provenance(provenance.source_format, provenance.source_path, provenance.page,
                                    provenance.object_id, provenance.package_part)
        records.append(PreservationRecord(
            DiagnosticIssue(f'legacy.{feature}', IssueSeverity.LOSS,
                            f'Legacy text view drops {feature}: {path}', path,
                            {'source_model_path': path, **measurement}, 'legacy-text-projection'),
            PreservationState.LOST,
            provenance=provenance.transformed('legacy-text-projection', detail=path),
        ))

    if document.source_format is not None and document.source_format not in {value.value for value in DocFormat}:
        lost('source-format', 'source_format')
    for reference in references:
        checkpoint()
        node, path = reference.node, reference.path
        if isinstance(node, DocumentModel):
            continue
        body = in_body(reference)
        if reference.parent is not None and isinstance(reference.parent.node, Section) and not body:
            lost('nonbody-content', path, reference, scope=reference.field)
        if isinstance(node, Section):
            if len(document.sections) > 1:
                lost('section-boundary', path, reference)
            if node.page != PageSettings():
                lost('page-settings', path+'.page', reference)
        if isinstance(node, Footnote):
            lost('footnote', path, reference, footnote_id=node.id)
        if isinstance(node, Paragraph):
            expected_style = (f'heading-{node.properties.get("level")}'
                              if node.properties.get('legacy_type') == 'heading' and node.properties.get('level') else None)
            if node.style_id is not None and node.style_id != expected_style:
                lost('paragraph-style', path+'.style_id', reference, style_id=node.style_id)
            if node.alignment is not None:
                lost('paragraph-alignment', path+'.alignment', reference)
            if len(node.content) > 1:
                lost('inline-boundaries', path+'.content', reference, count=len(node.content))
        if isinstance(node, TextRun):
            if node.style != TextStyle():
                lost('text-style', path+'.style', reference)
            if node.link is not None:
                lost('link', path+'.link', reference)
        if isinstance(node, Image):
            lost('image', path, reference, resource_id=node.resource_id, alt_text_retained=body and bool(node.alt_text))
            if node.crop is not None:
                lost('image-crop', path+'.crop', reference)
        if isinstance(node, Formula):
            lost('formula', path, reference, format=node.format.value,
                 text_retained=body, fallback_used=bool(node.fallback_text))
        if isinstance(node, Table):
            if node.style_id is not None:
                lost('table-style', path+'.style_id', reference)
            if reference.parent is not None and isinstance(reference.parent.node, TableCell):
                lost('nested-table', path, reference, text_retained=body)
        if isinstance(node, TableCell):
            if node.row_span != 1 or node.column_span != 1:
                lost('table-merge', path, reference, row_span=node.row_span, column_span=node.column_span)
            if len(node.blocks) > 1 or any(not isinstance(child, Paragraph) for child in node.blocks):
                lost('cell-blocks', path+'.blocks', reference, count=len(node.blocks))
        if getattr(node, 'box', None) is not None:
            lost('geometry', path+'.box', reference)
        if getattr(node, 'visual_surrogate', None) is not None:
            lost('visual-surrogate', path+'.visual_surrogate', reference)
        if getattr(node, 'provenance', None) is not None:
            lost('node-provenance', path+'.provenance', reference)
        properties = getattr(node, 'properties', {})
        retained = ({'legacy_type', 'level', 'page'} if isinstance(node, Paragraph)
                    else {'page'} if isinstance(node, Table) else set())
        for key in properties:
            if key not in retained:
                lost('property', f'{path}.properties[{key!r}]', reference, property_name=key)
        if isinstance(node, Footnote) and node.extensions:
            lost('footnote-extensions', path+'.extensions', reference)

    for identifier, resource in document.resources.items():
        lost('resource', f'resources[{identifier!r}]', origin_provenance=resource.provenance, resource_id=identifier)
    for identifier in document.styles:
        lost('style-definition', f'styles[{identifier!r}]', style_id=identifier)
    if document.package is not None:
        lost('package', 'package')
    for name in ('footnote_properties', 'footnote_extensions'):
        if getattr(document, name):
            lost(name.replace('_', '-'), name)
    for key, value in document.metadata.items():
        if key in {'language', 'engine', 'pages', 'warnings', INTEGRATION_PROPERTY}:
            continue
        if key == document.source_format and isinstance(value, dict) and not value.keys()-{'warnings'}:
            continue
        lost('metadata', f'metadata[{key!r}]')
    integration = get_integration(document, limits=limits)
    raw_integration = document.metadata.get(INTEGRATION_PROPERTY)
    if INTEGRATION_PROPERTY in document.metadata and integration is None:
        lost('integration-opaque', f'metadata[{INTEGRATION_PROPERTY!r}]')
    if integration is not None:
        if not isinstance(raw_integration, dict):
            raise ValueError('Expected the recognized Model integration envelope')
        envelope_keys = integration_to_dict(IntegrationModel(), limits=limits).keys()
        for key in raw_integration.keys()-envelope_keys:
            lost('integration-envelope-field', f'metadata[{INTEGRATION_PROPERTY!r}][{key!r}]')
        informational = {'extra', 'profiles', 'preservation', 'assessed_features', 'assessment_complete'}
        defaults = IntegrationModel()
        for definition in fields(integration):
            name = definition.name
            if name not in informational and getattr(integration, name) != getattr(defaults, name):
                lost('integration-structure', f'metadata[{INTEGRATION_PROPERTY!r}].data.{name}', field=name)
    return records
