"""Measured PDF fallback occurrences using the public OpenDoc mapping contract."""

from __future__ import annotations

import hashlib
import json
import secrets
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
    Provenance,
    Resource,
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
        self.generated: set[int] = set()
        self.story_markers: dict[int, tuple[bytes, Resource, Resource]] = {}
        self.story_locations: dict[str, int] = {}
        self.pending_story: set[int] = set()
        self.sources: list[ObjectOccurrence] = []
        self.entries: list[ObjectMappingEntry] = []
        self.bindings: dict[tuple[int, str], tuple[Image, int]] = {}
        self.placements: dict[int, list[tuple[int, int, bytes]]] = {}

    def record(self, image: Image, location: str, replacement_id: str | None, message: str, *, rejected: bool = False,
               history: dict[str, Any] | None = None, generated: bool = False,
               provenance: Provenance | None = None) -> int:
        index = len(self.sources)
        if index >= 10_000:
            raise ValueError('PDF fallback mapping occurrence limit exceeded')
        anchor = get_anchor(image)
        self.sources.append(ObjectOccurrence(
            id=f'source-{index}', node_id=anchor.id if anchor else None,
            resource_id=image.resource_id, provenance=deepcopy(image.provenance or provenance),
        ))
        self.entries.append(ObjectMappingEntry(
            id=f'mapping-{index}', source_ids=(f'source-{index}',),
            state=PreservationState.REJECTED if rejected else PreservationState.VISUAL,
            issue=DiagnosticIssue('pdf.svg-rasterized' if generated else
                                  'pdf.vector-origin' if history is not None else 'pdf.vector-surrogate',
                                  IssueSeverity.ERROR if rejected else IssueSeverity.LOSS, message, location,
                                  reason='svg-rasterization' if generated else
                                  'declared-vector-editability-unavailable' if history is not None
                                  else 'unsupported-native-vector'),
            replacement=MappingReplacement('raster', replacement_id, 'source') if replacement_id else None,
        ))
        if not rejected:
            from opendoc_formats.support.pdf_mapping_history import checked_history, origin_history

            self.histories[index] = checked_history(history) if history is not None else origin_history(
                self.sources[-1], self.entries[-1].issue
            )
            if generated:
                self.generated.add(index)
        self.report.metrics['object_mapping'] = object_mapping_to_dict(ObjectMapping(
            sources=tuple(self.sources), entries=tuple(self.entries), publication='attempted', output_format='pdf',
            extra={'profile': 'pdf-vector-raster-routing-v1', 'scope': 'declared-fallback-occurrences'},
        ))

        return index

    def bind(self, image: Image, index: int, location: str = '') -> None:
        self.bindings[id(image), location] = image, index

    def source_for(self, image: Image, location: str = '') -> int | None:
        bound = self.bindings.get((id(image), location)) or self.bindings.get((id(image), ''))
        return bound[1] if bound is not None and bound[0] is image else None

    def placed(self, index: int | None, page: int, occurrence: int, digest: bytes) -> None:
        if index is not None and 0 <= index < len(self.sources):
            self.placements.setdefault(index, []).append((page, occurrence, digest))

    def embed(self, pdf: Any) -> None:
        from opendoc_formats.support.pdf_mapping_history import embed_history

        embed_history(pdf, self.histories, self.placements)

    def story_resource(self, image: Image, location: str, resource: Resource, *, layout: bool = True) -> Resource:
        """Unique temporary pixels preserve Story's real image layout without guessed addresses."""
        index = self.source_for(image, location)
        if index is None:
            index = self.story_locations.get(location)
        if index not in self.generated or image.box is not None:
            return resource
        self.story_locations[location] = index
        if layout:
            self.pending_story.add(index)
        if index not in self.story_markers:
            import pymupdf

            source = pymupdf.Pixmap(resource.data)
            original_digest = pymupdf.Pixmap(source, 0).digest if source.alpha else source.digest
            marker = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, source.width, source.height), False)
            marker.set_dpi(source.xres, source.yres)
            for _attempt in range(32):
                marker.clear_with(secrets.randbelow(256))
                for pixel in range(min(source.width * source.height, 32)):
                    marker.set_pixel(pixel % source.width, pixel // source.width, tuple(secrets.token_bytes(3)))
                if marker.digest != original_digest and marker.digest not in {item[0] for item in self.story_markers.values()}:
                    break
            else:
                raise ValueError('Unable to allocate a unique temporary SVG raster')
            temporary = replace(resource, data=marker.tobytes('png'))
            self.story_markers[index] = marker.digest, temporary, resource
        if self.story_markers[index][2].data != resource.data:
            raise ValueError('Generated SVG resource changed after preparation')
        return self.story_markers[index][1]

    def prepare_story(self, document: Any) -> None:
        from opendoc_formats.writers.html_resources import document_images

        for image, location in document_images(document):
            index = self.source_for(image, location)
            if index in self.generated and image.box is None:
                self.story_resource(image, location, document.resources[image.resource_id], layout=False)

    def resolve_story(self, pdf: Any, page_offset: int) -> None:
        """Bind before replacement, then remeasure; markers never reach the published PDF."""
        if not self.story_markers:
            return
        owners = {digest: index for index, (digest, _, _) in self.story_markers.items()}
        routes = []
        replacements = {}
        for page_number, page in enumerate(pdf):
            images = page.get_image_info(hashes=True, xrefs=True)
            counts = {}
            for image in images:
                index = owners.get(image['digest'])
                if index is not None:
                    counts[index] = counts.get(index, 0) + 1
            for number, image in enumerate(images):
                index = owners.get(image['digest'])
                if index is None:
                    continue
                xref = image['xref']
                if xref <= 0 or counts[index] != 1 or xref in replacements and replacements[xref][1] != index:
                    raise ValueError('Ambiguous temporary SVG image ownership')
                replacements[xref] = page_number, index
                routes.append((page_number, number, index, tuple(image['bbox'])))
        if len(pdf):
            del page
        missing = self.pending_story - {index for _, index in replacements.values()}
        if missing:
            for index in sorted(missing):
                self.report.add(IssueSeverity.ERROR, 'pdf.svg-target-unconfirmed',
                                'Temporary SVG image could not be bound to its native replacement',
                                self.entries[index].issue.location)
            raise ValueError('SVG replacement binding incomplete')
        for xref, (page_number, index) in replacements.items():
            pdf[page_number].replace_image(xref, stream=self.story_markers[index][2].data)
        cached = {}
        for page_number, number, index, bbox in routes:
            if page_number not in cached:
                cached[page_number] = pdf.reload_page(pdf[page_number]).get_image_info(hashes=True)
            images = cached[page_number]
            if number >= len(images) or tuple(images[number]['bbox']) != bbox:
                raise ValueError('Temporary SVG occurrence changed during replacement')
            self.placed(index, page_offset + page_number, number, images[number]['digest'])
        self.pending_story.clear()

    def materialize(self, path: Path) -> None:
        if not self.sources:
            return
        import pymupdf

        targets: list[ObjectOccurrence] = []
        entries: list[ObjectMappingEntry] = []
        target_resources = {}
        if self.generated:
            from opendoc_formats.readers.pdf_model import read_pdf_model
            from opendoc_formats.writers.html_resources import document_images

            snapshot = read_pdf_model(path=path)
            for image, _ in document_images(snapshot):
                if image.provenance is not None and 'pdf_mapping_number' in image.properties:
                    target_resources[image.provenance.page - 1, image.properties['pdf_mapping_number']] = image.resource_id
        with pymupdf.open(path) as pdf:
            cached: dict[int, list[dict[str, Any]]] = {}
            for index, entry in enumerate(self.entries):
                ids: list[str] = []
                placements = self.placements.get(index, ())
                confirmed = bool(placements)
                replacement = entry.replacement
                for number, (page, occurrence, digest) in enumerate(placements):
                    if page not in cached:
                        cached[page] = pdf[page].get_image_info(hashes=True, xrefs=True)
                    images = cached[page]
                    if occurrence >= len(images) or images[occurrence]['digest'] != digest:
                        confirmed = False
                        break
                    native = images[occurrence]
                    resource_id = target_resources.get((page, native['number'])) if index in self.generated else None
                    if index in self.generated and resource_id is None:
                        confirmed = False
                        break
                    if index in self.generated and replacement is None:
                        replacement = MappingReplacement('raster', resource_id, 'target')
                    identifier = f'target-{index}-{number}'
                    locator = json.dumps({'page': page, 'image': occurrence, 'xref': native['xref'],
                                          'bbox': list(native['bbox']), 'digest': digest.hex()}, sort_keys=True)
                    targets.append(ObjectOccurrence(id=identifier, resource_id=resource_id,
                                                    native_locator=NativeObjectLocator('pdf', locator)))
                    ids.append(identifier)
                if not confirmed:
                    self.report.add(IssueSeverity.WARNING, 'pdf.mapping-target-unconfirmed',
                                    'Native target occurrence could not be confirmed', entry.issue.location)
                    targets = [item for item in targets if item.id not in ids]
                entries.append(replace(entry, target_ids=tuple(ids) if confirmed else None,
                                       replacement=replacement if confirmed else entry.replacement,
                                       extra={'target_confirmation': 'measured' if confirmed else 'unknown',
                                              'target_reason': None if confirmed else 'occurrence-not-confirmed'}))
        self.report.metrics['object_mapping'] = object_mapping_to_dict(ObjectMapping(
            sources=tuple(self.sources), targets=tuple(targets), entries=tuple(entries), publication='staged',
            output_format='pdf', result_id=_result_id(path),
            assessment_complete=all(entry.target_ids is not None for entry in entries),
            extra={'profile': 'pdf-vector-raster-routing-v1', 'scope': 'declared-fallback-occurrences'},
        ))
