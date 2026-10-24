"""Source-only diagnostics for lossy legacy text views; Model owns the codec."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from opendoc_model import (
    DiagnosticIssue,
    DocumentLimits,
    DocumentModel,
    IntegrationModel,
    IssueSeverity,
    PreservationRecord,
    PreservationState,
    Provenance,
    get_integration,
)

from opendoc_formats.support.cancellation import checkpoint
from opendoc_formats.types import Text


def ledger(records: tuple[PreservationRecord, ...], *, extra: dict[str, Any] | None = None) -> IntegrationModel:
    properties = dict(extra or {})
    key = 'opendoc_formats.legacy_source_diagnostics'
    if key in properties and properties[key] is not True:
        raise ValueError('Conflicting legacy source diagnostics declaration')
    properties[key] = True
    return IntegrationModel(
        preservation=records, assessed_features=tuple(dict.fromkeys(record.issue.code for record in records)),
        assessment_complete=False, extra=properties,
    )


def append_text_warning(
    text: Text, issue: DiagnosticIssue, provenance: Provenance,
    state: PreservationState = PreservationState.OPAQUE,
) -> None:
    index = len(text.warnings)
    text.warnings.append(issue.message)
    issue = replace(issue, measurement={**(issue.measurement or {}), 'legacy_warning_path': f'metadata.warnings[{index}]'})
    previous = text.diagnostics
    text.diagnostics = ledger((previous.preservation if previous else ())+(PreservationRecord(
        issue, state, provenance=provenance,
    ),), extra=previous.extra if previous else None)


def offset_records(value: IntegrationModel | None, offset: int) -> tuple[PreservationRecord, ...]:
    if value is None:
        return ()
    records = []
    for record in value.preservation:
        checkpoint()
        measurement = dict(record.issue.measurement or {})
        location = measurement.get('legacy_warning_path')
        match = re.fullmatch(r'metadata\.warnings\[(\d+)\]', location) if isinstance(location, str) else None
        if match:
            measurement['legacy_warning_path'] = f'metadata.warnings[{offset+int(match[1])}]'
        records.append(replace(record, issue=replace(record.issue, measurement=measurement)))
    return tuple(records)


def source_diagnostics(
    document: DocumentModel, *, limits: DocumentLimits | None = None,
) -> tuple[list[str], IntegrationModel | None]:
    """Retain negative source evidence; do not transfer graph refs or positive claims."""
    integration = get_integration(document, limits=limits)
    warnings: list[str] = []
    source_warnings = {}
    containers = [('metadata', document.metadata)]
    nested = document.metadata.get(document.source_format or '')
    if isinstance(nested, dict):
        containers.append((f'metadata.{document.source_format}', nested))
    for prefix, container in containers:
        values = container.get('warnings', [])
        if not isinstance(values, list):
            raise ValueError(f'{prefix}.warnings must be a list for a legacy text view')
        for index, value in enumerate(values):
            checkpoint()
            message = value if isinstance(value, str) else value.get('message') if isinstance(value, dict) else None
            if not isinstance(message, str):
                raise ValueError(f'{prefix}.warnings[{index}] must contain a string message')
            path = f'{prefix}.warnings[{index}]'
            source_warnings[path] = (len(warnings), message, value)
            warnings.append(message)
    records = []
    linked = set()
    for record in integration.preservation if integration else ():
        checkpoint()
        if record.state is PreservationState.SEMANTIC:
            continue
        extra = dict(record.extra)
        if record.node_id is not None:
            key = 'opendoc_formats.legacy_source_node_id'
            if key in extra and extra[key] != record.node_id:
                raise ValueError('Conflicting source node identity in legacy diagnostics')
            extra[key] = record.node_id
        measurement = dict(record.issue.measurement or {})
        source_path = measurement.get('legacy_warning_path')
        source_warning = source_warnings.get(source_path) if isinstance(source_path, str) else None
        if source_warning and source_warning[1] == record.issue.message:
            measurement['legacy_warning_path'] = f'metadata.warnings[{source_warning[0]}]'
            linked.add(source_path)
        records.append(replace(record, node_id=None, extra=extra, issue=replace(record.issue, measurement=measurement)))
    for path, (index, message, value) in source_warnings.items():
        checkpoint()
        if path in linked:
            continue
        properties = value if isinstance(value, dict) else {}
        code = str(properties.get('feature') or f'{document.source_format or "unknown"}.legacy-warning')
        location = str(properties.get('location') or path)
        records.append(PreservationRecord(
            DiagnosticIssue(code, IssueSeverity.LOSS, message, location,
                            {'legacy_warning_path': f'metadata.warnings[{index}]'}, 'legacy-warning-unassessed'),
            PreservationState.OPAQUE, provenance=Provenance(document.source_format or 'unknown', object_id=path),
            extra={'source_warning': value},
        ))
    if not records and (integration is None or not integration.extra):
        return warnings, None
    from opendoc_model import integration_from_dict, integration_to_dict

    result = ledger(tuple(records), extra=integration.extra if integration else None)
    return warnings, integration_from_dict(integration_to_dict(result, limits=limits), limits=limits)
