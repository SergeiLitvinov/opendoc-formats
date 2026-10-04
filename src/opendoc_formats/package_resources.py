"""Attach explicitly selected native DOCX resources to the official OpenDoc package graph."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Literal, TypeAlias

from opendoc import DocumentModel, PackageGraph, PackagePart, PackageRelationship

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError
from opendoc_formats.native.common import Cancellation, check_cancel, positive_int

DocxResourceRole: TypeAlias = Literal["footnotes", "endnotes", "numbering", "styles", "theme", "media"]
_BASE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
_ROLES = {
    "footnotes": ("/word/footnotes.xml", "footnotes"),
    "endnotes": ("/word/endnotes.xml", "endnotes"),
    "numbering": ("/word/numbering.xml", "numbering"),
    "styles": ("/word/styles.xml", "styles"),
    "theme": ("/word/theme/theme1.xml", "theme"),
}


def _part_name(name: str) -> str:
    if (
        not name.startswith("/")
        or name.startswith("//")
        or "\\" in name
        or ".." in PurePosixPath(name).parts
        or any(char in name for char in ("\x00", ":", "?", "#"))
        or name.endswith("/")
    ):
        raise InvalidDocumentError("Unsafe native resource part name")
    return name


def _media_name(filename: str | None, resource_id: str) -> str:
    name = filename or resource_id
    if not re.fullmatch(r"[\w .()-]+", name) or name in {".", ".."}:
        raise InvalidDocumentError("Native media resource requires a safe filename")
    return _part_name("/word/media/" + name)


def assemble_docx_package_resources(
    document: DocumentModel,
    resource_roles: Mapping[str, DocxResourceRole],
    *,
    consume_resources: bool = False,
    max_bytes: int = 128 * 1024 * 1024,
    cancelled: Cancellation | None = None,
) -> DocumentModel:
    """Return a copy with a DOCX graph; mapping keys are resource IDs, values are standard roles.

    Existing graphs are left intact. Optional native resource properties ``partname`` and
    ``relationships`` are interpreted here; no application codec, version or schema is accepted.
    Relationship payloads are retained without fetching external targets or executing content.
    """
    if not isinstance(document, DocumentModel):
        raise TypeError("document must be the official OpenDoc DocumentModel")
    if not isinstance(resource_roles, Mapping):
        raise TypeError("resource_roles must be a mapping")
    if not isinstance(consume_resources, bool):
        raise TypeError("consume_resources must be bool")
    if cancelled is not None and not callable(cancelled):
        raise TypeError("cancelled must be callable")
    positive_int(max_bytes, "max_bytes")
    check_cancel(cancelled)
    result = copy.deepcopy(document)
    if result.package is not None:
        return result
    graph = PackageGraph(format="ooxml", root="/word/document.xml")
    used: set[str] = set()
    total = 0

    def add_resource(resource_id: str, default_name: str) -> str:
        nonlocal total
        check_cancel(cancelled)
        if resource_id not in result.resources:
            raise InvalidDocumentError(f"Unknown native resource: {resource_id}")
        resource = result.resources[resource_id]
        if not isinstance(resource.data, bytes):
            raise InvalidDocumentError(f"Native resource has no embedded bytes: {resource_id}")
        name = _part_name(str(resource.properties.get("partname") or default_name))
        existing = graph.parts.get(name)
        if existing is not None and (existing.data != resource.data or existing.media_type != resource.media_type):
            raise InvalidDocumentError("Multiple native resources map to conflicting package parts")
        if existing is None:
            total += len(resource.data)
            if total > max_bytes:
                raise ResourceLimitError("Native package resource bytes exceed limit")
            graph.add_part(PackagePart(name, resource.media_type, resource.data))
        used.add(resource_id)
        return name

    seen_roles: set[str] = set()
    for resource_id, role in resource_roles.items():
        check_cancel(cancelled)
        if not isinstance(resource_id, str) or role not in {*_ROLES, "media"}:
            raise ValueError("resource_roles must map resource IDs to supported DOCX roles")
        if role in seen_roles and role != "media":
            raise InvalidDocumentError(f"Multiple resources supplied for singleton role: {role}")
        seen_roles.add(role)
        if resource_id not in result.resources:
            raise InvalidDocumentError(f"Unknown native resource: {resource_id}")
        resource = result.resources[resource_id]
        default_name, relation_role = _ROLES[role] if role != "media" else (_media_name(resource.filename, resource_id), "image")
        part_name = add_resource(resource_id, default_name)
        graph.add_relationship(
            PackageRelationship(
                id=f"rIdAttached{len(graph.relationships) + 1}",
                relationship_type=_BASE + relation_role,
                source=graph.root,
                target=part_name,
            )
        )
        relationships = resource.properties.get("relationships", [])
        if not isinstance(relationships, list):
            raise InvalidDocumentError("Native resource relationships must be a list")
        for raw in relationships:
            if not isinstance(raw, dict) or not all(isinstance(raw.get(key), str) and raw[key] for key in ("id", "type")):
                raise InvalidDocumentError("Invalid native resource relationship metadata")
            external = raw.get("external", False)
            if not isinstance(external, bool):
                raise InvalidDocumentError("Native relationship external flag must be bool")
            if external:
                target = raw.get("target")
                if not isinstance(target, str) or not target:
                    raise InvalidDocumentError("External native relationship requires a target")
            else:
                related_id = raw.get("resource_id")
                if not isinstance(related_id, str) or related_id not in result.resources:
                    raise InvalidDocumentError("Native relationship resource is unavailable")
                related = result.resources[related_id]
                target = add_resource(related_id, _media_name(related.filename, related_id))
            graph.add_relationship(
                PackageRelationship(
                    id=raw["id"],
                    relationship_type=raw["type"],
                    source=part_name,
                    target=target,
                    external=external,
                )
            )
    if graph.parts:
        result.package = graph
        if consume_resources:
            for resource_id in used:
                result.resources.pop(resource_id)
    check_cancel(cancelled)
    errors = result.validate()
    if errors:
        raise InvalidDocumentError(f"Invalid assembled OpenDoc model: {errors}")
    return result


__all__ = ["assemble_docx_package_resources", "DocxResourceRole"]
