"""Bind painted glyph origins to actual native font bytes, never family guesses."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from opendoc_model import ArtifactLimitError, DocumentLimits, Resource, ResourceKind

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_placements import text_placements
from opendoc_formats.native.sfnt import SfntInventory, SfntLimits, inspect_sfnt
from opendoc_formats.pdf import PdfLimits
from opendoc_formats.support.cancellation import check_cancelled

ProgramBindings = dict[tuple[tuple[float, float], int], set[str | None]]


def font_program_inventory(resource: Resource, budget: DocumentLimits,
                           cancelled: Callable[[], bool] | None) -> SfntInventory | None:
    """Inspect source font bounds under the selected document budgets."""
    data = resource.data
    if not data:
        return None
    limits = SfntLimits(max_input_bytes=max(1, budget.max_embedded_bytes), max_tables=min(4096, budget.max_nodes),
                        max_table_bytes=budget.max_embedded_bytes, max_total_table_bytes=budget.max_embedded_bytes)
    try:
        return inspect_sfnt(data, limits=limits, cancelled=cancelled)
    except ResourceLimitError as error:
        tables = 'max_tables' in str(error)
        raise ArtifactLimitError(str(error), path=f'$.resources[{resource.id!r}].data',
                                 quota='font tables' if tables else 'embedded bytes',
                                 maximum=limits.max_tables if tables else budget.max_embedded_bytes) from error
    except (InvalidDocumentError, UnsupportedDocumentError):
        return None


def _cff_digest(resource: Resource, budget: DocumentLimits, cancelled: Callable[[], bool] | None) -> str | None:
    """Recognize an actual CFF buffer only inside an inspected static standalone OTF."""
    data = resource.data
    if resource.media_type != 'font/otf' or not data or not data.startswith(b'OTTO'):
        return None
    inventory = font_program_inventory(resource, budget, cancelled)
    if inventory is None:
        return None
    if inventory.variation_tables or any(table.tag == 'CFF2' for table in inventory.tables):
        return None
    table = next((table for table in inventory.tables if table.tag == 'CFF '), None)
    if table is None or table.length < 6:
        return None
    start = table.offset
    major, minor, header, offset_size = data[start:start+4]
    if (major != 1 or minor != 0 or not 4 <= header <= table.length-2 or not 1 <= offset_size <= 4
            or int.from_bytes(data[start+header:start+header+2], 'big') != 1):
        return None  # CFF1 with one Name INDEX entry; never guess a font-set face or CFF2 profile.
    return table.sha256


def font_program_candidates(resources: dict[str, Resource], budget: DocumentLimits,
                            cancelled: Callable[[], bool] | None) -> dict[str, list[str]]:
    """Index exact source programs and inspected CFF container payloads, preserving ambiguity."""
    by_digest: dict[str, list[str]] = {}
    total = 0
    for resource in resources.values():
        check_cancelled(cancelled, 'PDF font resource digest')
        if resource.kind is ResourceKind.FONT and resource.data:
            total += len(resource.data)
            if total > budget.max_embedded_bytes:
                raise ArtifactLimitError('PDF font programs exceed embedded-byte budget',
                                         path=f'$.resources[{resource.id!r}]', quota='embedded bytes',
                                         maximum=budget.max_embedded_bytes)
            by_digest.setdefault(hashlib.sha256(resource.data).hexdigest(), []).append(resource.id)
    for resource in resources.values():
        check_cancelled(cancelled, 'PDF OTF program binding')
        if resource.kind is ResourceKind.FONT and (digest := _cff_digest(resource, budget, cancelled)):
            by_digest.setdefault(digest, []).append(resource.id)
    return by_digest


def painted_font_programs(page: Any, resources: dict[str, Resource], origins: set[tuple[float, float]], *,
                          limits: DocumentLimits | None = None,
                          cancelled: Callable[[], bool] | None = None) -> ProgramBindings:
    """Reuse bounded placement observations; retain the existing fill-only binding policy."""
    check_cancelled(cancelled, 'PDF painted font bindings')
    if not origins:
        return {}
    budget = limits or DocumentLimits()
    by_digest = font_program_candidates(resources, budget, cancelled)
    if not by_digest:
        return {}
    address = f'$.sections[{page.number}].pdf_font_bindings'
    if budget.max_bytes == 0:
        raise ArtifactLimitError('PDF font bindings exceed byte budget', path=address, quota='bytes', maximum=0)
    native = PdfLimits(max_text_spans=budget.max_nodes, max_text_chars=budget.max_bytes,
                       max_text_metadata_bytes=budget.max_bytes, max_object_bytes=budget.max_bytes,
                       max_inspection_bytes=budget.max_bytes)
    rotation = page.rotation
    try:
        page.set_rotation(0)
        observations = text_placements(page, page.number, native, cancelled, include_bounds=False)
    except ResourceLimitError as error:
        quota = 'nodes' if 'max_text_spans' in str(error) else 'bytes'
        raise ArtifactLimitError(str(error), path=address, quota=quota,
                                 maximum=budget.max_nodes if quota == 'nodes' else budget.max_bytes) from error
    except (AttributeError, TypeError, RuntimeError):
        # An unavailable native profile leaves bindings unknown, never guessed by name.
        return {}
    finally:
        page.set_rotation(rotation)
    result: ProgramBindings = {}
    for occurrence in observations:
        check_cancelled(cancelled, 'PDF painted font occurrence')
        if occurrence.operation != 'fill':
            continue
        identifiers = by_digest.get(occurrence.font_program_sha256 or '', [])
        identifier = identifiers[0] if len(identifiers) == 1 else None
        for glyph in occurrence.glyphs:
            check_cancelled(cancelled, 'PDF painted font glyph')
            origin = (round(glyph.transform[4], 3), round(glyph.transform[5], 3))
            if origin in origins:
                result.setdefault((origin, glyph.unicode), set()).add(identifier)
    return result
