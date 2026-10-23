"""Located OCR uncertainty, recorded at its source without classifying warning prose."""

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


def attach_ocr_diagnostics(
    document: DocumentModel, path: str | Path, mode: str, geometry: PdfGeometryDocument,
    pages: Sequence[OcrPageResult] | None, failures: Sequence[tuple[str, str, int]], *,
    limits: DocumentLimits | None = None, cancelled: Callable[[], bool] | None = None,
) -> None:
    records = []

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
