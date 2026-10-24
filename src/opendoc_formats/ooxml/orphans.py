"""Preserve physically present, unreachable OPC components without inventing root links."""

from __future__ import annotations

import copy
import hashlib
import io
import zipfile
from collections.abc import Collection
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from opendoc_model import (
    ArtifactLimitError,
    DiagnosticIssue,
    DocumentLimits,
    DocumentModel,
    IntegrationModel,
    IssueSeverity,
    PackageGraph,
    PackagePart,
    PreservationRecord,
    PreservationState,
    Provenance,
    get_integration,
    set_integration,
)

from opendoc_formats.anatomy import AnatomyLimits, XmlNodeInfo, _Budget, _xml_nodes
from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.native.docx_package import parse_xml
from opendoc_formats.package_resources import _part_name
from opendoc_formats.support.cancellation import cancellable_items, checkpoint
from opendoc_formats.support.io import check_archive_safety

KEY = 'opendoc_formats.opc_orphans'
CT = '{http://schemas.openxmlformats.org/package/2006/content-types}'
REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'
RELS_TYPE = 'application/vnd.openxmlformats-package.relationships+xml'


def _rels_name(owner: str) -> str:
    path = PurePosixPath(owner)
    return str(path.parent/'_rels'/(path.name+'.rels'))


def _owner(name: str) -> str | None:
    path = PurePosixPath(name)
    if path.parent.name != '_rels' or not name.endswith('.rels'):
        return None
    return str(path.parent.parent/path.name[:-5])


def _target(owner: str, value: str) -> str:
    parsed = urlsplit(value)
    if not value or parsed.scheme or parsed.netloc or parsed.query:
        raise InvalidDocumentError(f'{owner}: invalid internal OPC target {value!r}')
    path = parsed.path
    if not path:
        return owner
    segments = [] if path.startswith('/') else owner.split('/')[1:-1]
    for segment in path.split('/'):
        if segment in ('', '.'):
            continue
        if segment == '..':
            if not segments:
                raise InvalidDocumentError(f'{owner}: OPC target escapes package root')
            segments.pop()
        else:
            decoded = unquote(segment)
            if decoded in ('.', '..') or '/' in decoded or '\\' in decoded:
                raise InvalidDocumentError(f'{owner}: ambiguous encoded OPC target')
            segments.append(segment)
    return _name('/'+'/'.join(segments))


def _name(value: str) -> str:
    value = _part_name(value)
    if any(segment in ('', '.', '..') for segment in value[1:].split('/')):
        raise InvalidDocumentError(f'Unnormalized OPC part name: {value!r}')
    return value


def _nodes(data: bytes, location: str, limits: DocumentLimits | None) -> tuple[XmlNodeInfo, ...]:
    budget = limits or DocumentLimits()
    if len(data) > budget.max_bytes:
        raise ArtifactLimitError('Native XML exceeds byte budget', path=location,
                                 quota='bytes', maximum=budget.max_bytes)
    native = AnatomyLimits(max_xml_nodes=budget.max_nodes, max_xml_depth=budget.max_depth,
                            max_xml_characters=budget.max_bytes, max_xml_name_chars=budget.max_bytes)
    return _xml_nodes(data, location, _Budget(native))


def _targets(data: bytes, rels: str, *, limits: DocumentLimits | None = None) -> list[str]:
    nodes = _nodes(data, rels, limits)
    if not nodes or nodes[0].tag != REL+'Relationships':
        raise InvalidDocumentError(f'{rels}: expected OPC Relationships root')
    owner = _owner(rels)
    if owner is None:
        raise InvalidDocumentError(f'{rels}: relationship part has no owner address')
    seen, result = set(), []
    for node in cancellable_items(nodes):
        if node.path.count('/') != 1 or node.tag != REL+'Relationship':
            continue  # retained as opaque bytes, including extension markup
        attributes = dict(node.attributes)
        identifier, value = attributes.get('Id'), attributes.get('Target')
        if not identifier or identifier in seen or not attributes.get('Type') or not value:
            raise InvalidDocumentError(f'{rels}: invalid/duplicate native relationship')
        seen.add(identifier)
        mode = attributes.get('TargetMode', 'Internal')
        if mode == 'External':
            continue
        if mode != 'Internal':
            raise InvalidDocumentError(f'{rels}: unsupported TargetMode {mode!r}')
        result.append(_target(owner, value))
    return result


def _types(data: bytes, *, limits: DocumentLimits | None = None) -> tuple[dict[str, str], dict[str, str]]:
    nodes = _nodes(data, '/[Content_Types].xml', limits)
    if not nodes or nodes[0].tag != CT+'Types':
        raise InvalidDocumentError('Invalid OPC content-types root')
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for node in cancellable_items(nodes):
        if node.path.count('/') != 1:
            continue
        attributes = dict(node.attributes)
        if node.tag == CT+'Default':
            key, value = attributes.get('Extension'), attributes.get('ContentType')
            mapping = defaults
            key = key.lower() if key else key
        elif node.tag == CT+'Override':
            key, value = attributes.get('PartName'), attributes.get('ContentType')
            mapping = overrides
            key = _name(key) if key else key
        else:
            continue
        if not key or not value or (key in mapping and mapping[key] != value):
            raise InvalidDocumentError('Invalid/conflicting OPC content-type declaration')
        mapping[key] = value
    return defaults, overrides


def capture_orphans(document: Any, model: DocumentModel, source: bytes, path: Path,
                    *, loaded_parts: Collection[str], limits: DocumentLimits | None = None) -> None:
    """Capture all unreachable roots and their native dependency closure from one source snapshot."""
    budget = limits or DocumentLimits()
    loaded = set(cancellable_items(loaded_parts))
    root = str(document.part.partname)
    known = loaded | {_rels_name(name) for name in loaded} | {'/[Content_Types].xml', '/_rels/.rels'}
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        infos = {_name('/'+item.filename): item for item in cancellable_items(archive.infolist()) if not item.is_dir()}
        roots = sorted(infos.keys()-known)
        if not roots:
            return
        defaults, overrides = _types(archive.read('[Content_Types].xml'), limits=limits)
        graph = model.package or PackageGraph('ooxml', root=root)
        parts = dict(graph.parts)
        embedded = sum(len(part.data) for part in cancellable_items(parts.values()))
        embedded += sum(len(resource.data or b'') for resource in cancellable_items(model.resources.values()))
        pending, captured = list(reversed(roots)), {}
        while pending:
            checkpoint()
            name = pending.pop()
            if name == root or name in captured:
                continue
            if name not in infos:
                raise InvalidDocumentError(f'{name}: orphan OPC dependency is missing')
            info = infos[name]
            previous = parts.get(name)
            remaining = budget.max_embedded_bytes - embedded + (len(previous.data) if previous else 0)
            if info.file_size > remaining:
                raise ArtifactLimitError('Opaque OPC parts exceed embedded-byte budget', path=f'package.parts[{name!r}]',
                                         quota='embedded bytes', maximum=budget.max_embedded_bytes)
            content_type = overrides.get(name) or defaults.get(PurePosixPath(name).suffix[1:].lower())
            if not content_type:
                raise InvalidDocumentError(f'{name}: no declared OPC content type')
            with archive.open(info) as stream:
                data = stream.read(remaining+1)
            checkpoint()
            if len(data) != info.file_size or len(data) > remaining:
                raise InvalidDocumentError(f'{name}: inconsistent native part size')
            embedded += len(data)-(len(previous.data) if previous else 0)
            parts[name] = PackagePart(name, content_type, data)
            captured[name] = hashlib.sha256(data).hexdigest()
            if len(captured) > budget.max_nodes:
                raise ArtifactLimitError('Too many opaque OPC parts', path='package.parts',
                                         quota='nodes', maximum=budget.max_nodes)
            owner = _owner(name)
            if owner is not None:
                if owner != root and owner not in infos:
                    raise InvalidDocumentError(f'{name}: relationship owner is missing')
                pending.append(owner)
                pending.extend(reversed(_targets(data, name, limits=limits)))
            else:
                rels = _rels_name(name)
                if rels in infos:
                    pending.append(rels)
        model.package = replace(graph, parts=parts)
        model.metadata[KEY] = {'version': 1, 'roots': roots, 'parts': sorted(captured),
                               'original_sha256': captured, 'source_sha256': hashlib.sha256(source).hexdigest()}
    integration = get_integration(model, limits=limits) or IntegrationModel()
    records = tuple(PreservationRecord(
        DiagnosticIssue('docx.orphan-part', IssueSeverity.LOSS, 'Unreachable OPC part retained as opaque native data',
                        f'{path}!{name}#zip-entry', {'part': name, 'sha256': captured[name], 'root': name in roots},
                        'unreachable-native-component'),
        PreservationState.OPAQUE, provenance=Provenance('docx', str(path), object_id=name, package_part=name),
    ) for name in cancellable_items(sorted(captured)))
    set_integration(model, replace(integration, preservation=integration.preservation+records,
                                   assessed_features=tuple(dict.fromkeys((*integration.assessed_features, 'docx.orphan-part'))),
                                   assessment_complete=False), limits=limits)


def orphan_names(model: DocumentModel, *, limits: DocumentLimits | None = None) -> set[str]:
    if KEY not in model.metadata:
        return set()
    raw = model.metadata[KEY]
    if not isinstance(raw, dict) or type(raw.get('version')) is not int or raw['version'] != 1:
        raise InvalidDocumentError('Unsupported native OPC orphan binding')
    names = raw.get('parts')
    roots = raw.get('roots')
    if (not isinstance(names, list) or not isinstance(roots, list)
            or any(not isinstance(name, str) for name in (*names, *roots))):
        raise InvalidDocumentError('Malformed native OPC orphan binding')
    selected = {_name(name) for name in names}
    if len(selected) != len(names) or len(set(roots)) != len(roots) or not set(roots) <= selected:
        raise InvalidDocumentError('Conflicting native OPC orphan binding')
    graph = model.package
    if graph is None or graph.format != 'ooxml' or not selected <= graph.parts.keys() or graph.root in selected:
        raise InvalidDocumentError('Native OPC orphan parts are missing from their package graph')
    # Revalidate edited native relationships; never fetch external targets or invent missing data.
    for name in cancellable_items(sorted(selected)):
        owner = _owner(name)
        if owner is not None:
            if owner != graph.root and owner not in selected:
                raise InvalidDocumentError(f'{name}: native relationship owner binding is missing')
            for target in _targets(graph.parts[name].data, name, limits=limits):
                if target != graph.root and target not in selected:
                    raise InvalidDocumentError(f'{name}: native target binding is missing: {target}')
    return selected


def retained_original(model: DocumentModel, name: str, data: bytes) -> bool:
    """Bind diagnostics to captured source bytes rather than python-opc's reserialized XML."""
    raw = model.metadata.get(KEY)
    return (isinstance(raw, dict) and isinstance(raw.get('original_sha256'), dict)
            and raw['original_sha256'].get(name) == hashlib.sha256(data).hexdigest())


def reserve_orphan_names(root_part: Any, graph: PackageGraph, names: set[str]) -> None:
    """Separate editable/generated parts from preserved native dependencies at their original URIs."""
    if not names:
        return
    from docx.opc.packuri import PackURI

    occupied = set(graph.parts) | {str(part.partname) for part in root_part.package.iter_parts()}
    for part in list(cancellable_items(root_part.package.iter_parts())):
        name = str(part.partname)
        if part is root_part or name not in names:
            continue
        path, index = PurePosixPath(name), 1
        while True:
            candidate = str(path.with_name(f'{path.stem}-opendoc-opaque{index}{path.suffix}'))
            if candidate not in occupied and _rels_name(candidate) not in occupied:
                break
            checkpoint()
            index += 1
        part.partname = PackURI(candidate)
        occupied.add(candidate)


def relocate_root(root_part: Any, name: str) -> None:
    """Keep every rId/target while rebuilding python-opc's cached relationship base URI."""
    if str(root_part.partname) == name:
        return
    from docx.opc.packuri import PackURI

    original = list(root_part.rels.values())
    relationships_type = type(root_part.rels)
    root_part.partname = PackURI(name)
    relationships = relationships_type(root_part.partname.baseURI)
    for relation in cancellable_items(original):
        relationships.add_relationship(relation.reltype,
                                       relation.target_ref if relation.is_external else relation.target_part,
                                       relation.rId, is_external=relation.is_external)
    root_part.__dict__['rels'] = relationships
    root_part._rels = relationships  # documented legacy cache kept by python-docx


def restore_detached_parts(
    staged: Path, model: DocumentModel, native_parts: dict[str, Any], *, limits: DocumentLimits | None = None,
) -> None:
    """Emit detached graph objects after python-opc saves only its reachable graph."""
    from lxml import etree

    names = orphan_names(model, limits=limits)
    graph = model.package
    if graph is None or graph.format != 'ooxml':
        return
    expected = {str(part.partname): PackagePart(str(part.partname), part.content_type, part.blob)
                for part in cancellable_items(native_parts.values())}
    expected.update({name: graph.parts[name] for name in names})
    if graph.root in expected:
        raise InvalidDocumentError('Opaque package part conflicts with the editable document root')
    check_archive_safety(staged)
    rewritten = staged.with_suffix('.detached.docx')
    try:
        with zipfile.ZipFile(staged) as original:
            existing = {item.filename: item for item in original.infolist()}
            missing = {name: part for name, part in expected.items() if name[1:] not in existing}
            for name, part in cancellable_items(expected.items()):
                if name[1:] in existing and original.read(name[1:]) != part.data:
                    raise InvalidDocumentError(f'{name}: generated data conflicts with a native opaque part')
            if not missing:
                return
            content_types = parse_xml(original.read('[Content_Types].xml'), etree)
            defaults, overrides = _types(original.read('[Content_Types].xml'), limits=limits)
            for name, part in cancellable_items(missing.items()):
                actual = overrides.get(name) or defaults.get(PurePosixPath(name).suffix[1:].lower())
                if actual != part.media_type:
                    node = next((entry for entry in content_types if entry.tag == CT+'Override'
                                 and entry.get('PartName') == name), None)
                    if node is None:
                        node = etree.SubElement(content_types, CT+'Override', PartName=name)
                    node.set('ContentType', part.media_type)
            with zipfile.ZipFile(rewritten, 'w', compression=zipfile.ZIP_DEFLATED) as target:
                for item in cancellable_items(original.infolist()):
                    if item.filename == '[Content_Types].xml':
                        target.writestr(copy.copy(item), etree.tostring(content_types, encoding='UTF-8', xml_declaration=True))
                    else:
                        with original.open(item) as reader, target.open(copy.copy(item), 'w') as writer:
                            while chunk := reader.read(65536):
                                checkpoint()
                                writer.write(chunk)
                for name, part in cancellable_items(sorted(missing.items())):
                    target.writestr(name[1:], part.data)
        checkpoint()
        rewritten.replace(staged)
    finally:
        rewritten.unlink(missing_ok=True)
