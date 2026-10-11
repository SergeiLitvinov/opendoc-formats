"""Bounded inert vector-origin declarations, bound anew to measured native rasters."""

from __future__ import annotations

import json
import math
import re
import uuid
import zlib
from dataclasses import replace
from pathlib import Path
from typing import Any

from opendoc_model import (
    DiagnosticIssue,
    DocumentLimits,
    DocumentModel,
    IssueSeverity,
    NativeObjectLocator,
    ObjectMapping,
    ObjectMappingEntry,
    ObjectOccurrence,
    PreservationRecord,
    PreservationState,
    Provenance,
    get_anchor,
    get_integration,
    object_mapping_from_dict,
    object_mapping_to_dict,
    set_integration,
    validate_object_mapping,
)

HISTORY_KEY = 'opendoc_formats_pdf_origin'
CATALOG_KEY = 'OpenDocFormatsMapping'
MAX_HISTORY_BYTES = 8 * 1024 * 1024
MAX_HISTORY_ROUTES = 10_000


def origin_history(source: ObjectOccurrence, issue: DiagnosticIssue) -> dict[str, Any]:
    origin = ObjectOccurrence(
        id='origin-' + uuid.uuid4().hex,
        provenance=source.provenance or Provenance(source_format='opendoc'),
        extra={'declared_resource_label': source.resource_id, 'declared_anchor_label': source.node_id},
    )
    return object_mapping_to_dict(ObjectMapping(
        sources=(origin,), entries=(ObjectMappingEntry('origin', (origin.id,), PreservationState.VISUAL, issue),),
        publication='attempted', output_format='pdf',
        extra={'profile': 'pdf-vector-origin-v1', 'source_evidence': 'artifact-declaration'},
    ))


def checked_history(raw: Any) -> dict[str, Any]:
    mapping = object_mapping_from_dict(raw)
    if (mapping.extra.get('profile') != 'pdf-vector-origin-v1'
            or mapping.extra.get('source_evidence') != 'artifact-declaration' or mapping.publication != 'attempted'
            or mapping.output_format != 'pdf' or mapping.assessment_complete or mapping.result_id is not None
            or len(mapping.sources) != 1 or len(mapping.entries) != 1 or mapping.targets
            or mapping.entries[0].state is not PreservationState.VISUAL or mapping.entries[0].replacement is not None
            or mapping.entries[0].target_ids is not None):
        raise ValueError('Unsupported vector origin declaration')
    source = mapping.sources[0]
    if (source.provenance is None
            or any(value is not None for value in (source.node_id, source.resource_id, source.native_locator))):
        raise ValueError('Historical declaration cannot claim current model/resource/native handles')
    return object_mapping_to_dict(mapping)


def embed_history(pdf: Any, histories: dict[int, dict[str, Any]], placements: dict[int, list[tuple[int, int, bytes]]]) -> None:
    routes = []
    cached = {}
    for index, values in placements.items():
        for page, occurrence, digest in values:
            if page not in cached:
                cached[page] = pdf[page].get_image_info(hashes=True)
            images = cached[page]
            if occurrence >= len(images) or images[occurrence]['digest'] != digest:
                continue
            image = images[occurrence]
            routes.append({'page': page, 'image': occurrence, 'number': image['number'],
                           'bbox': list(image['bbox']), 'digest': digest.hex(), 'history': histories[index]})
            if len(routes) > MAX_HISTORY_ROUTES:
                raise ValueError('PDF history route limit exceeded')
    if not routes:
        return
    raw = json.dumps({'format': 'opendoc-formats.pdf-mapping-history', 'version': 1, 'routes': routes},
                     ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if len(raw) > MAX_HISTORY_BYTES:
        raise ValueError('PDF mapping history exceeds 8 MiB')
    xref = pdf.get_new_xref()
    pdf.update_object(xref, '<</Type/OpenDocFormatsMapping/Version 1>>')
    pdf.update_stream(xref, raw, compress=True)
    pdf.xref_set_key(pdf.pdf_catalog(), CATALOG_KEY, f'{xref} 0 R')


def _read_stream(pdf: Any) -> bytes | None:
    kind, reference = pdf.xref_get_key(pdf.pdf_catalog(), CATALOG_KEY)
    if kind == 'null':
        return None
    match = re.fullmatch(r'(\d+)\s+0\s+R', reference.strip()) if kind == 'xref' else None
    if match is None:
        raise ValueError('Unsupported history stream reference')
    xref = int(match[1])
    length_kind, length = pdf.xref_get_key(xref, 'Length')
    if length_kind != 'int' or not 0 <= int(length) <= MAX_HISTORY_BYTES:
        raise ValueError('History compressed stream exceeds limit')
    if pdf.xref_get_key(xref, 'DecodeParms')[0] != 'null':
        raise ValueError('Unsupported history decode parameters')
    raw = pdf.xref_stream_raw(xref)
    if raw is None or len(raw) > MAX_HISTORY_BYTES:
        raise ValueError('Invalid history stream')
    kind, value = pdf.xref_get_key(xref, 'Filter')
    if kind == 'null':
        return raw
    if kind != 'name' or value != '/FlateDecode':
        raise ValueError('Unsupported history compression')
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(raw, MAX_HISTORY_BYTES + 1)
    if len(decoded) > MAX_HISTORY_BYTES or not decoder.eof or decoder.unused_data:
        raise ValueError('Invalid or excessive decoded history stream')
    return decoded


def load_history(path: str | Path) -> tuple[dict[tuple[int, int], dict[str, Any]], list[DiagnosticIssue]]:
    import pymupdf

    result: dict[tuple[int, int], dict[str, Any]] = {}
    issues: list[DiagnosticIssue] = []
    location = f'catalog.{CATALOG_KEY}'
    try:
        with pymupdf.open(path) as pdf:
            raw = _read_stream(pdf)
            if raw is None:
                return result, issues
            data = json.loads(raw)
            if (type(data) is not dict or data.get('format') != 'opendoc-formats.pdf-mapping-history'
                    or type(data.get('version')) is not int or data['version'] != 1
                    or type(data.get('routes')) is not list or len(data['routes']) > MAX_HISTORY_ROUTES):
                raise ValueError('Unsupported history envelope or route limit')
            cached = {}
            origins: dict[str, dict[str, Any]] = {}
            for index, route in enumerate(data['routes']):
                location = f'catalog.{CATALOG_KEY}.routes[{index}]'
                if type(route) is not dict:
                    raise ValueError('Invalid history route')
                page, occurrence, number = (route.get(key) for key in ('page', 'image', 'number'))
                if (type(page) is not int or not 0 <= page < MAX_HISTORY_ROUTES
                        or any(type(value) is not int or not 0 <= value < 1_000_000 for value in (occurrence, number))):
                    raise ValueError('Invalid history occurrence indices')
                bbox = route.get('bbox')
                digest = route.get('digest')
                if (type(bbox) is not list or len(bbox) != 4
                        or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1_000_000 for v in bbox)
                        or type(digest) is not str or re.fullmatch('[0-9a-f]{32}', digest) is None):
                    raise ValueError('Invalid history geometry or digest')
                history = checked_history(route.get('history'))
                identifier = history['sources'][0]['id']
                if identifier in origins and origins[identifier] != history:
                    raise ValueError('Conflicting historical origin identifier')
                origins[identifier] = history
                if page not in cached and page < len(pdf):
                    cached[page] = pdf[page].get_image_info(hashes=True, xrefs=True)
                images = cached.get(page, ())
                image = images[occurrence] if occurrence < len(images) else None
                if (image is None or image['number'] != number or image['digest'].hex() != digest
                        or any(abs(a-b) > 0.01 for a, b in zip(image['bbox'], bbox, strict=True))):
                    issues.append(DiagnosticIssue('pdf.mapping-history-stale', IssueSeverity.LOSS,
                                                  'History does not match current native raster', location,
                                                  reason='native-occurrence-changed'))
                    continue
                key = page, number
                if key in result:
                    raise ValueError('Multiply owned native history occurrence')
                locator = {'page': page, 'image': occurrence, 'xref': image['xref'],
                           'bbox': list(image['bbox']), 'digest': digest}
                result[key] = {'history': history, 'locator': locator}
    except (ValueError, KeyError, TypeError, RuntimeError, RecursionError, OverflowError, zlib.error) as error:
        result.clear()
        issues.append(DiagnosticIssue('pdf.mapping-history-invalid', IssueSeverity.LOSS, str(error), location,
                                      reason='unsupported-or-invalid-history'))
    return result, issues


def attach_history_map(document: DocumentModel, path: str | Path, matched: list[tuple[Any, dict[str, Any]]],
                       issues: list[DiagnosticIssue], *, limits: DocumentLimits | None = None) -> ObjectMapping | None:
    from opendoc_formats.support.object_mapping import _result_id

    mapping = None
    sources = {}
    targets = []
    entries = {}
    for index, (image, route) in enumerate(matched):
        history = object_mapping_from_dict(route['history'])
        source = history.sources[0]
        sources[source.id] = source
        target_id = f'imported-target-{index}'
        anchor = get_anchor(image)
        targets.append(ObjectOccurrence(target_id, node_id=anchor.id if anchor else None, resource_id=image.resource_id,
                                        native_locator=NativeObjectLocator('pdf', json.dumps(route['locator'], sort_keys=True))))
        ids, first_resource, issue = entries.setdefault(source.id, ([], image.resource_id, history.entries[0].issue))
        ids.append(target_id)
    if matched:
        from opendoc_model import MappingReplacement

        mapping = ObjectMapping(
            sources=tuple(sources.values()), targets=tuple(targets),
            entries=tuple(ObjectMappingEntry(f'origin-{index}', (key,), PreservationState.VISUAL, issue,
                                            tuple(ids), MappingReplacement('raster', resource, 'target'))
                          for index, (key, (ids, resource, issue)) in enumerate(entries.items())),
            publication='staged', output_format='pdf', result_id=_result_id(Path(path)), assessment_complete=not issues,
            extra={'profile': 'pdf-imported-vector-origin-v1', 'source_evidence': 'artifact-declaration',
                   'target_evidence': 'measured-native-raster'},
        )
        validate_object_mapping(mapping, target=document, limits=limits)
        object_mapping_to_dict(mapping, limits=limits)
    integration = get_integration(document, limits=limits)
    if integration is not None and issues:
        set_integration(document, replace(integration,
            assessed_features=tuple(dict.fromkeys((*integration.assessed_features, *(issue.code for issue in issues)))),
            preservation=integration.preservation + tuple(
            PreservationRecord(issue, PreservationState.OPAQUE,
                               provenance=Provenance(source_format='pdf', source_path=str(path),
                                                     object_id=f'mapping-history-{index}'))
            for index, issue in enumerate(issues)
        )), limits=limits)

    return mapping


def read_pdf_origin_mapping(path: str | Path) -> ObjectMapping | None:
    """Read a fresh native snapshot; editable models carry only origin declarations."""
    from opendoc_formats.readers.pdf_model import read_pdf_model
    from opendoc_formats.writers.html_resources import document_images

    document = read_pdf_model(path=path)
    routes, issues = load_history(path)
    matched = []
    for image, _ in document_images(document):
        page = image.provenance.page if image.provenance is not None else None
        route = routes.get((page - 1 if page is not None else None, image.properties.get('pdf_mapping_number')))
        if route is not None and image.properties.get(HISTORY_KEY) == route['history']:
            matched.append((image, route))
    return attach_history_map(document, path, matched, issues)
