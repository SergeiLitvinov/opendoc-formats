"""Read physical OOXML core properties without loading an Office backend."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from zipfile import ZipFile

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.opc import RELATIONSHIPS, resolve_target
from opendoc_formats.support.cancellation import cancellation_scope, checkpoint
from opendoc_formats.support.io import open_checked_archive

_REL_TYPE = 'http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties'
_CORE = '{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}'
_DC = '{http://purl.org/dc/elements/1.1/}'
_DCTERMS = '{http://purl.org/dc/terms/}'
_FIELDS = {
    **{_DC + name: name for name in ('title', 'subject', 'creator', 'description', 'identifier', 'language')},
    **{_CORE + name: name for name in ('keywords', 'category', 'contentStatus', 'lastModifiedBy', 'revision', 'version',
                                     'lastPrinted')},
    **{_DCTERMS + name: name for name in ('created', 'modified')},
}
_MAX_PART_BYTES = 1024 * 1024


class _MetadataTree(ET.TreeBuilder):
    def __init__(self) -> None:
        super().__init__()
        self.depth = 0

    def start(self, tag: str, attrs: dict[str, str]) -> ET.Element:
        checkpoint()
        if self.depth >= 32:
            raise ResourceLimitError('OOXML metadata XML nesting exceeds 32')
        self.depth += 1
        return super().start(tag, attrs)

    def end(self, tag: str) -> ET.Element:
        self.depth -= 1
        return super().end(tag)

    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise UnsupportedDocumentError('DTD is not accepted in OOXML metadata XML')


def _read_xml(archive: ZipFile, name: str) -> ET.Element:
    checkpoint()
    try:
        member = archive.getinfo(name)
    except KeyError as error:
        raise InvalidDocumentError(f'Missing OOXML package part: {name}') from error
    if member.file_size > _MAX_PART_BYTES:
        raise ResourceLimitError(f'OOXML metadata part exceeds {_MAX_PART_BYTES} bytes: {name}')
    parser = ET.XMLParser(target=_MetadataTree())
    try:
        with archive.open(member) as stream:
            while chunk := stream.read(65536):
                checkpoint()
                parser.feed(chunk)
        return parser.close()
    except ET.ParseError as error:
        raise InvalidDocumentError(f'Invalid OOXML metadata XML: {name}: {error}') from error


def read_ooxml_core_properties(path: str | Path, *, cancelled: Callable[[], bool] | None = None) -> dict[str, str]:
    """Return original known core field values, or an empty mapping if not declared."""
    with cancellation_scope(cancelled, 'OOXML core properties'), open_checked_archive(path) as archive:
        relationships = _read_xml(archive, '_rels/.rels')
        if relationships.tag != RELATIONSHIPS + 'Relationships':
            raise InvalidDocumentError('Invalid OOXML package relationships root')
        candidates = []
        ids: dict[str | None, int] = {}
        for edge in relationships.findall(RELATIONSHIPS + 'Relationship'):
            checkpoint()
            identity = edge.get('Id')
            ids[identity] = ids.get(identity, 0) + 1
            if edge.get('Type') == _REL_TYPE:
                candidates.append(edge)
        if not candidates:
            return {}
        edge = candidates[0]
        identity, target = edge.get('Id'), edge.get('Target', '')
        if (len(candidates) != 1 or not identity or ids[identity] != 1
                or edge.get('TargetMode', 'Internal') != 'Internal' or not target or '#' in target or '?' in target):
            raise InvalidDocumentError('Ambiguous or non-local OOXML core properties relationship')
        root = _read_xml(archive, resolve_target('/', target).removeprefix('/'))
        if root.tag != _CORE + 'coreProperties':
            raise InvalidDocumentError('Invalid OOXML core properties root')
        result: dict[str, str] = {}
        for child in root:
            checkpoint()
            if (key := _FIELDS.get(child.tag)) is not None:
                if key in result or len(child):
                    raise InvalidDocumentError(f'Ambiguous OOXML core property: {key}')
                result[key] = child.text or ''
        return result
