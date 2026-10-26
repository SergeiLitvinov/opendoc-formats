"""Source-backed native glyph observations in the public Model layout registry."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from opendoc_model import (
    AffineTransform,
    ArtifactLimitError,
    DiagnosticIssue,
    DocumentLimits,
    DocumentModel,
    FontReference,
    GlyphPlacement,
    IntegrationModel,
    IssueSeverity,
    PreservationRecord,
    PreservationState,
    Provenance,
    Resource,
    ResourceKind,
    TextLayout,
    get_integration,
    get_page_geometry,
    set_integration,
    set_text_layouts,
)

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.common import backend, read_source
from opendoc_formats.native.pdf_placements import text_placements
from opendoc_formats.pdf import PdfLimits
from opendoc_formats.pdf_page_geometry import read_page_geometry
from opendoc_formats.readers.pdf_font_bindings import _cff_digest, font_program_candidates, font_program_inventory
from opendoc_formats.readers.pdf_layout_bindings import LogicalBindings
from opendoc_formats.support.cancellation import check_cancelled


def _face(resource: Resource, budget: DocumentLimits, cancelled: Callable[[], bool] | None) -> int | None:
    data = resource.data
    if not data or resource.media_type not in {'font/ttf', 'font/otf'}:
        return None
    if data.startswith(b'OTTO'):
        return 0 if _cff_digest(resource, budget, cancelled) is not None else None
    if not data.startswith(b'\0\1\0\0'):
        return None
    inventory = font_program_inventory(resource, budget, cancelled)
    if inventory is None:
        return None
    return None if inventory.variation_tables or any(t.tag in {'CFF ', 'CFF2'} for t in inventory.tables) else 0


def capture_pdf_text_layouts(document: DocumentModel, source: str | Path, *, limits: DocumentLimits | None = None,
                             cancelled: Callable[[], bool] | None = None) -> DocumentModel:
    """Return a staged copy; observations remain unknown until logical bindings are proven."""
    check_cancelled(cancelled, 'PDF text layout capture')
    budget = limits or DocumentLimits()
    source_id = 'pdf-text-layout-source'
    try:
        snapshot = read_source(source, budget.max_embedded_bytes, cancelled)
    except ResourceLimitError as error:
        raise ArtifactLimitError(str(error), path=f'$.resources[{source_id!r}].data', quota='embedded bytes',
                                 maximum=budget.max_embedded_bytes) from error
    digest = hashlib.sha256(snapshot).hexdigest()
    source_id += '-'+digest
    resources = dict(document.resources)
    same_source = next((r for r in resources.values() if r.kind is ResourceKind.ATTACHMENT
                        and r.media_type == 'application/pdf' and r.data == snapshot), None)
    if same_source is not None:
        source_id = same_source.id
    else:
        if source_id in resources:
            raise InvalidDocumentError('PDF layout source resource ID is occupied')
        resources[source_id] = Resource(source_id, ResourceKind.ATTACHMENT, 'application/pdf', snapshot,
                                        filename=Path(source).name, provenance=Provenance('pdf', str(source)))
    total = 0
    for resource in resources.values():
        check_cancelled(cancelled, 'PDF layout source budget')
        total += len(resource.data or b'')
        if total > budget.max_embedded_bytes:
            raise ArtifactLimitError('PDF layout snapshot exceeds embedded-byte budget',
                                     path=f'$.resources[{source_id!r}].data', quota='embedded bytes',
                                     maximum=budget.max_embedded_bytes)
    if budget.max_bytes == 0:
        raise ArtifactLimitError('PDF layout observations exceed byte budget', path='$.text_layouts', quota='bytes', maximum=0)
    native_limits = PdfLimits(max_text_spans=budget.max_nodes, max_text_chars=budget.max_nodes,
                              max_text_metadata_bytes=budget.max_bytes, max_object_bytes=budget.max_bytes,
                              max_inspection_bytes=budget.max_bytes)
    candidates = font_program_candidates(resources, budget, cancelled)
    faces: dict[str, int | None] = {}
    integration = get_integration(document, limits=budget) or IntegrationModel()
    candidate = replace(document, sections=deepcopy(document.sections), resources=resources, metadata=deepcopy(document.metadata))
    bindings = LogicalBindings(candidate, integration, budget, cancelled)
    pages = {page.id: page for page in integration.pages}
    layouts: list[TextLayout] = []
    raw_count = 0
    engine = backend('pymupdf', 'pdf')
    with engine.open(stream=snapshot, filetype='pdf') as native:
        if native.needs_pass or native.is_encrypted:
            raise UnsupportedDocumentError('Encrypted PDF layout source is not supported')
        if native.page_count == 0:
            raise InvalidDocumentError('PDF layout source contains no pages')
        maximum_pages = min(native_limits.max_pages, budget.max_nodes)
        if native.page_count > maximum_pages:
            raise ArtifactLimitError('PDF layout page count exceeds budget', path='$.text_layouts.pages',
                                     quota='pages', maximum=maximum_pages)
        for index, page in enumerate(native):
            check_cancelled(cancelled, 'PDF layout page')
            if index >= budget.max_nodes:
                raise ArtifactLimitError('PDF layout pages exceed node budget', path='$.text_layouts',
                                         quota='nodes', maximum=budget.max_nodes)
            page_id = f'pdf-page-{index+1}'
            physical_page = read_page_geometry(page, page_id)
            if page_id in pages:
                existing = pages[page_id]
                if (existing.width != physical_page.width or existing.height != physical_page.height
                        or get_page_geometry(existing) != get_page_geometry(physical_page)):
                    raise InvalidDocumentError('PDF layout page geometry differs from imported document')
            else:
                pages[page_id] = physical_page
            geometry = get_page_geometry(physical_page)
            region = (geometry.crop_box or geometry.media_box) if geometry is not None else None
            transform = AffineTransform(e=region.x, f=region.y) if region is not None else AffineTransform()
            page.set_rotation(0)
            bindings.read_source_styles(page, engine)
            try:
                observations = text_placements(page, index, native_limits, cancelled, include_bounds=False)
            except ResourceLimitError as error:
                nodes = 'max_text_chars' in str(error) or 'max_text_spans' in str(error)
                raise ArtifactLimitError(str(error), path=f'$.text_layouts.page[{index}]',
                                         quota='nodes' if nodes else 'bytes',
                                         maximum=budget.max_nodes if nodes else budget.max_bytes) from error
            for observation in observations:
                check_cancelled(cancelled, 'PDF layout occurrence')
                raw_count += len(observation.glyphs)
                if raw_count > budget.max_nodes or len(layouts) >= budget.max_nodes:
                    raise ArtifactLimitError('PDF layout observations exceed node budget', path='$.text_layouts',
                                             quota='nodes', maximum=budget.max_nodes)
                matched = candidates.get(observation.font_program_sha256 or '', [])
                identifier = matched[0] if len(matched) == 1 else None
                if identifier is not None and identifier not in faces:
                    faces[identifier] = _face(resources[identifier], budget, cancelled)
                face = faces.get(identifier) if identifier else None
                binding = ('source-program' if face is not None else 'face-unknown') if len(matched) == 1 else (
                    'ambiguous' if matched else 'unmatched')
                fonts = (FontReference(identifier, face),) if identifier else ()
                rows: list[GlyphPlacement] = []
                native_indices = []
                for offset, glyph in enumerate(observation.glyphs):
                    check_cancelled(cancelled, 'PDF layout glyph')
                    if glyph.glyph_id < 0:
                        continue  # Nonplaced continuations remain in the retained source, never invented glyphs.
                    rows.append((0 if fonts else None, glyph.glyph_id if face is not None else None, *glyph.transform))
                    native_indices.append(offset)
                layout = TextLayout(
                    f'pdf-text-layout-{digest}-{index}-{observation.occurrence_index}',
                    glyphs=tuple(rows), fonts=fonts, page_id=page_id if region is not None else None, transform=transform,
                    provenance=Provenance('pdf', str(source), page=index,
                                          object_id=f'text-placement:{observation.occurrence_index}'),
                    extra={'opendoc_formats.pdf_source_resource_id': source_id, 'opendoc_formats.pdf_source_sha256': digest,
                           'opendoc_formats.pdf_native_glyph_indices': native_indices,
                           'opendoc_formats.pdf_native_records': len(observation.glyphs),
                           'opendoc_formats.pdf_text_operation': observation.operation,
                           'opendoc_formats.pdf_native_opacity': observation.opacity,
                           'opendoc_formats.pdf_native_program_sha256': observation.font_program_sha256,
                           'opendoc_formats.pdf_font_binding': binding,
                           'opendoc_formats.pdf_page_binding': 'source-page' if region is not None else 'unknown-frame',
                           'opendoc_formats.pdf_observer': 'pymupdf/fz-page-contents',
                           'opendoc_formats.pdf_observer_version': str(getattr(engine, 'VersionBind', 'unknown')),
                           'opendoc_formats.glyph_space': 'font-at-1pt',
                           'opendoc_formats.coordinate_space': 'pymupdf-unrotated',
                           'opendoc_formats.logical_mapping': 'unknown', 'opendoc_formats.paint_state': 'unassessed'},
                )
                layouts.append(bindings.bind(layout, observation))
    record = PreservationRecord(
        DiagnosticIssue('pdf.text-layout-observations', IssueSeverity.INFO,
                        'Native glyph observations retained; complete paint state remains unverified',
                        str(source), measurement={'layouts': len(layouts), 'native_glyph_records': raw_count,
                                                 'verified_logical_bindings': len(bindings.verified)},
                        reason='native-observations-with-partial-logical-bindings'),
        PreservationState.OPAQUE, provenance=Provenance('pdf', str(source)),
        extra={'source_resource_id': source_id},
    )
    records = integration.preservation if record in integration.preservation else integration.preservation+(record,)
    refreshed = {layout.id for layout in layouts}
    # Rebuild these snapshots from the immutable source, preserving their extra fields.
    # Other producers' occurrences still undergo normal Model owner validation.
    previous = tuple(replace(layout, state='unknown', binding_sha256=None)
                     if layout.id in refreshed else layout for layout in integration.text_layouts)
    set_integration(candidate, replace(integration, pages=tuple(pages.values()),
                                       ranges=tuple(bindings.ranges),
                                       text_layouts=previous,
                                       preservation=records,
                                       assessment_complete=False,
                                       assessed_features=tuple(dict.fromkeys((*integration.assessed_features,
                                                                             record.issue.code)))), limits=budget)
    check_cancelled(cancelled, 'PDF layout batch')
    set_text_layouts(candidate, layouts, limits=budget)
    if bindings.verified:
        check_cancelled(cancelled, 'PDF verified layout batch')
        set_text_layouts(candidate, bindings.verified, verify=True, limits=budget)
    check_cancelled(cancelled, 'PDF layout capture completion')
    return candidate
