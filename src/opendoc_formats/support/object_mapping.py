"""Measured PDF fallback occurrences using the public OpenDoc mapping contract."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

from opendoc_model import (
    ConversionReport,
    DiagnosticIssue,
    Image,
    IssueSeverity,
    MappingReplacement,
    NativeObjectLocator,
    ObjectMapping,
    ObjectMappingEntry,
    ObjectOccurrence,
    PreservationState,
    get_anchor,
    object_mapping_from_dict,
    object_mapping_to_dict,
    with_mapping_publication,
)
from opendoc_model.object_mapping import MappingPublication


def get_object_mapping(report: ConversionReport) -> ObjectMapping | None:
    """Return an independent typed copy, or unknown if the writer supplies no map."""
    raw = report.metrics.get('object_mapping')
    return object_mapping_from_dict(raw) if raw is not None else None


def mapping_publication(
    report: ConversionReport, state: MappingPublication, *, code: str | None = None, reason: str | None = None,
) -> None:
    mapping = get_object_mapping(report)
    if mapping is None:
        return
    issue = DiagnosticIssue(code, IssueSeverity.ERROR, reason or code, reason=reason) if code else None
    locators = {item.id: item.native_locator for item in mapping.targets} if state in ('staged', 'published') else None
    report.metrics['object_mapping'] = object_mapping_to_dict(
        with_mapping_publication(mapping, state, issue=issue, target_locators=locators)
    )


def mapping_result_matches(report: ConversionReport, path: Path) -> bool:
    mapping = get_object_mapping(report)
    if mapping is None:
        return True
    try:
        return mapping.result_id == _result_id(path)
    except OSError:
        return False


def _result_id(path: Path) -> str:
    with path.open('rb') as stream:
        return 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()


class PdfFallbackMapping:
    """One-to-many page repetitions; unrelated document objects remain outside the scope."""

    def __init__(self, report: ConversionReport) -> None:
        self.report = report
        self.histories: dict[int, dict[str, Any]] = {}
        self.sources: list[ObjectOccurrence] = []
        self.entries: list[ObjectMappingEntry] = []
        self.bindings: dict[int, tuple[Image, int]] = {}
        self.placements: dict[int, list[tuple[int, int, bytes]]] = {}

    def record(self, image: Image, location: str, replacement_id: str | None, message: str, *, rejected: bool = False,
               history: dict[str, Any] | None = None) -> int:
        index = len(self.sources)
        if index >= 10_000:
            raise ValueError('PDF fallback mapping occurrence limit exceeded')
        anchor = get_anchor(image)
        self.sources.append(ObjectOccurrence(
            id=f'source-{index}', node_id=anchor.id if anchor else None,
            resource_id=image.resource_id, provenance=deepcopy(image.provenance),
        ))
        self.entries.append(ObjectMappingEntry(
            id=f'mapping-{index}', source_ids=(f'source-{index}',),
            state=PreservationState.REJECTED if rejected else PreservationState.VISUAL,
            issue=DiagnosticIssue('pdf.vector-origin' if history is not None else 'pdf.vector-surrogate',
                                  IssueSeverity.ERROR if rejected else IssueSeverity.LOSS, message, location,
                                  reason='declared-vector-editability-unavailable' if history is not None
                                  else 'unsupported-native-vector'),
            replacement=MappingReplacement('raster', replacement_id, 'source') if replacement_id else None,
        ))
        if not rejected:
            from opendoc_formats.support.pdf_mapping_history import checked_history, origin_history

            self.histories[index] = checked_history(history) if history is not None else origin_history(
                self.sources[-1], self.entries[-1].issue
            )
        self.report.metrics['object_mapping'] = object_mapping_to_dict(ObjectMapping(
            sources=tuple(self.sources), entries=tuple(self.entries), publication='attempted', output_format='pdf',
            extra={'profile': 'pdf-vector-raster-routing-v1', 'scope': 'declared-fallback-occurrences'},
        ))

        return index

    def bind(self, image: Image, index: int) -> None:
        self.bindings[id(image)] = image, index

    def source_for(self, image: Image) -> int | None:
        bound = self.bindings.get(id(image))
        return bound[1] if bound is not None and bound[0] is image else None

    def placed(self, index: int | None, page: int, occurrence: int, digest: bytes) -> None:
        if index is not None and 0 <= index < len(self.sources):
            self.placements.setdefault(index, []).append((page, occurrence, digest))

    def embed(self, pdf: Any) -> None:
        from opendoc_formats.support.pdf_mapping_history import embed_history

        embed_history(pdf, self.histories, self.placements)

    def materialize(self, path: Path) -> None:
        if not self.sources:
            return
        import pymupdf

        targets: list[ObjectOccurrence] = []
        entries: list[ObjectMappingEntry] = []
        with pymupdf.open(path) as pdf:
            cached: dict[int, list[dict[str, Any]]] = {}
            for index, entry in enumerate(self.entries):
                ids: list[str] = []
                placements = self.placements.get(index, ())
                confirmed = bool(placements)
                for number, (page, occurrence, digest) in enumerate(placements):
                    if page not in cached:
                        cached[page] = pdf[page].get_image_info(hashes=True, xrefs=True)
                    images = cached[page]
                    if occurrence >= len(images) or images[occurrence]['digest'] != digest:
                        confirmed = False
                        break
                    native = images[occurrence]
                    identifier = f'target-{index}-{number}'
                    locator = json.dumps({'page': page, 'image': occurrence, 'xref': native['xref'],
                                          'bbox': list(native['bbox']), 'digest': digest.hex()}, sort_keys=True)
                    targets.append(ObjectOccurrence(id=identifier, native_locator=NativeObjectLocator('pdf', locator)))
                    ids.append(identifier)
                if not confirmed:
                    self.report.add(IssueSeverity.WARNING, 'pdf.mapping-target-unconfirmed',
                                    'Native target occurrence could not be confirmed', entry.issue.location)
                    targets = [item for item in targets if item.id not in ids]
                entries.append(replace(entry, target_ids=tuple(ids) if confirmed else None,
                                       extra={'target_confirmation': 'measured' if confirmed else 'unknown',
                                              'target_reason': None if confirmed else 'occurrence-not-confirmed'}))
        self.report.metrics['object_mapping'] = object_mapping_to_dict(ObjectMapping(
            sources=tuple(self.sources), targets=tuple(targets), entries=tuple(entries), publication='staged',
            output_format='pdf', result_id=_result_id(path),
            assessment_complete=all(entry.target_ids is not None for entry in entries),
            extra={'profile': 'pdf-vector-raster-routing-v1', 'scope': 'declared-fallback-occurrences'},
        ))
