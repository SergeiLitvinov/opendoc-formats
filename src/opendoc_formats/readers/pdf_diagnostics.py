"""Located PDF import uncertainty, recorded without classifying warning prose."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

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
    set_integration,
)

from opendoc_formats.readers.pdf_geometry import PdfGeometryDocument
from opendoc_formats.readers.pdf_ocr_types import OcrPageResult
from opendoc_formats.support.cancellation import check_cancelled


def append_pdf_warning(
    warnings: list[str], records: list[PreservationRecord] | None, issue: DiagnosticIssue,
    provenance: Provenance, state: PreservationState = PreservationState.OPAQUE,
) -> None:
    """Keep the legacy list and optional typed occurrence linked at creation."""
    warnings.append(issue.message)
    if records is not None:
        records.append(PreservationRecord(replace(
            issue, measurement={**(issue.measurement or {}), 'warning_index': len(warnings)-1},
        ), state, provenance=provenance))


def bind_warning_records(
    records: Sequence[PreservationRecord], offset: int = 0, *, cancelled: Callable[[], bool] | None = None,
) -> list[PreservationRecord]:
    """Bind local extraction-list indices to the assembled rich metadata list."""
    result = []
    for record in records:
        check_cancelled(cancelled, 'PDF warning binding')
        measurement = dict(record.issue.measurement or {})
        index = measurement.pop('warning_index')
        measurement['legacy_warning_path'] = f'metadata.warnings[{offset+index}]'
        result.append(replace(record, issue=replace(record.issue, measurement=measurement)))
    return result


def attach_pdf_diagnostics(
    document: DocumentModel, path: str | Path, mode: str, geometry: PdfGeometryDocument,
    pages: Sequence[OcrPageResult] | None, failures: Sequence[tuple[str, str, int]], *,
    limits: DocumentLimits | None = None, cancelled: Callable[[], bool] | None = None,
) -> None:
    records = []
    for record in geometry.diagnostics:
        check_cancelled(cancelled, 'PDF geometry diagnostics')
        records.append(record)

    def add(code: str, reason: str, message: str, warning_index: int, page_index: int | None = None) -> None:
        check_cancelled(cancelled, 'PDF OCR diagnostics')
        page = geometry.pages[page_index].number if page_index is not None and page_index < len(geometry.pages) else None
        location = f'{path}#page={page}/ocr' if page is not None else f'{path}#ocr'
        records.append(PreservationRecord(
            DiagnosticIssue(code, IssueSeverity.LOSS, message, location,
                            {'legacy_warning_path': f'metadata.warnings[{warning_index}]', 'pdf_mode': mode,
                             'ocr_page_index': page_index}, reason),
            PreservationState.OPAQUE,
            provenance=Provenance('pdf', str(path), page=page, object_id=f'ocr-warning-{warning_index}'),
        ))

    for code, reason, index in failures:
        add(code, reason, geometry.warnings[index], index)
    offset = len(geometry.warnings)
    for index, result in enumerate(pages or ()):
        check_cancelled(cancelled, 'PDF OCR diagnostics')
        for warning in result.warnings:
            add('pdf.ocr-provider-warning', 'ocr-provider-warning-unassessed', warning, offset, index)
            offset += 1
    if not records:
        return
    integration = get_integration(document, limits=limits) or IntegrationModel()
    set_integration(document, replace(
        integration, preservation=integration.preservation+tuple(records), assessment_complete=False,
        assessed_features=tuple(dict.fromkeys((*integration.assessed_features, *(record.issue.code for record in records)))),
    ), limits=limits)
