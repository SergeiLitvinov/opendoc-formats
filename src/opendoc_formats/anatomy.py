"""Read-only inventories: ZIP/XML, active PDF objects, CFBF sectors/streams and sfnt programs."""

from __future__ import annotations

import hashlib
import io
import struct
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any, NoReturn
from xml.parsers import expat

from opendoc_formats.errors import (
    EncryptedDocumentError,
    InvalidDocumentError,
    ResourceLimitError,
    UnsupportedDocumentError,
)
from opendoc_formats.native.cfbf import SIGNATURE as CFBF_SIGNATURE
from opendoc_formats.native.common import Source, positive_int, read_source
from opendoc_formats.native.epub import inspection_content_types
from opendoc_formats.native.opc import content_types, declared_content_type, xml_content_type
from opendoc_formats.native.opc_audit import audit_package
from opendoc_formats.support.cancellation import cancellation_requested, cancellation_scope, checkpoint
from opendoc_formats.support.io import ArchiveSafetyError, check_archive_safety


@dataclass(frozen=True)
class AnatomyLimits:
    max_input_bytes: int = 128 * 1024 * 1024
    max_items: int = 100_000
    max_part_bytes: int = 32 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024
    max_ratio: int = 200
    max_xml_nodes: int = 100_000
    max_xml_depth: int = 128
    max_xml_name_chars: int = 2048
    max_xml_characters: int = 32 * 1024 * 1024

    def __post_init__(self) -> None:
        for definition in fields(self):
            positive_int(getattr(self, definition.name), definition.name)


@dataclass(frozen=True)
class XmlNodeInfo:
    path: str
    tag: str
    attributes: tuple[tuple[str, str], ...]
    text_sha256: str
    text_characters: int = 0
    start_byte: int = 0
    end_event_byte: int = 0


@dataclass(frozen=True)
class BinaryItem:
    locator: str
    kind: str
    size: int
    sha256: str
    storage_sha256: str | None = None
    details: tuple[tuple[str, Any], ...] = ()
    xml_nodes: tuple[XmlNodeInfo, ...] = ()
    payload: bytes | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class OpcRelationship:
    location: str
    relationship_part: str
    owner: str | None
    attributes: tuple[tuple[str, str], ...]
    resolved_target: str | None
    status: str


@dataclass(frozen=True)
class OpcFinding:
    code: str
    location: str
    message: str


@dataclass(frozen=True)
class OpcAudit:
    relationships: tuple[OpcRelationship, ...]
    findings: tuple[OpcFinding, ...]
    reachable_parts: tuple[str, ...]
    unreached_parts: tuple[str, ...]
    unreachable_parts: tuple[str, ...]
    reachability_complete: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON representation; the audit itself remains immutable."""
        return {
            'relationships': [{**asdict(edge), 'attributes': dict(edge.attributes)} for edge in self.relationships],
            'findings': [asdict(finding) for finding in self.findings],
            'reachable_parts': list(self.reachable_parts), 'unreached_parts': list(self.unreached_parts),
            'unreachable_parts': list(self.unreachable_parts), 'reachability_complete': self.reachability_complete,
            'assessment_complete': False,
        }


@dataclass(frozen=True)
class EpubManifestReference:
    location: str
    package: str
    identifier: str
    href: str
    media_type: str
    resolved_target: str | None
    status: str
    attributes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class EpubAudit:
    references: tuple[EpubManifestReference, ...]

    def to_dict(self) -> dict[str, Any]:
        """Manifest observations, without asserting URL/spec compliance or remote availability."""
        return {
            'references': [{**asdict(reference), 'attributes': dict(reference.attributes)} for reference in self.references],
            'assessment_complete': False,
        }


@dataclass(frozen=True)
class BinarySnapshot:
    container: str
    source_sha256: str
    source_size: int
    items: tuple[BinaryItem, ...]
    details: tuple[tuple[str, Any], ...] = ()
    opc: OpcAudit | None = None
    epub: EpubAudit | None = None

    def to_dict(self) -> dict[str, Any]:
        """An audit schema owned by Formats; payloads are deliberately separate."""
        return {
            'format': 'opendoc-formats.binary-inventory', 'version': 1,
            'container': self.container, 'source_sha256': self.source_sha256, 'source_size': self.source_size,
            'details': dict(self.details),
            'opc': self.opc.to_dict() if self.opc is not None else None,
            'epub': self.epub.to_dict() if self.epub is not None else None,
            'items': [{
                'locator': item.locator, 'kind': item.kind, 'size': item.size, 'sha256': item.sha256,
                'storage_sha256': item.storage_sha256, 'details': dict(item.details),
                'xml_nodes': [{'path': node.path, 'tag': node.tag, 'attributes': dict(node.attributes),
                               'text_sha256': node.text_sha256, 'text_characters': node.text_characters,
                               'start_byte': node.start_byte, 'end_event_byte': node.end_event_byte}
                              for node in item.xml_nodes],
            } for item in self.items],
        }


def compare_snapshots(before: BinarySnapshot, after: BinarySnapshot) -> dict[str, Any]:
    """Literal source-address deltas, never a semantic correspondence or losslessness claim."""
    if before.container != after.container:
        raise ValueError('Binary comparison requires the same container profile')
    old, new = {item.locator: item for item in before.items}, {item.locator: item for item in after.items}
    if len(old) != len(before.items) or len(new) != len(after.items):
        raise ValueError('Binary snapshots must have unique native locators')
    shared = old.keys() & new.keys()
    return {
        'binary_identical': before.source_sha256 == after.source_sha256,
        'container_metadata_changed': before.details != after.details,
        'opc_changed': before.opc != after.opc,
        'epub_changed': before.epub != after.epub,
        'added': sorted(new.keys()-old.keys()), 'removed': sorted(old.keys()-new.keys()),
        'content_changed': sorted(key for key in shared if old[key].sha256 != new[key].sha256),
        'storage_changed': sorted(key for key in shared if old[key].storage_sha256 != new[key].storage_sha256
                                  or old[key].details != new[key].details),
        'assessment_complete': False,
    }


@dataclass
class _XmlFrame:
    index: int
    path: str
    hasher: Any = field(default_factory=hashlib.sha256)
    children: int = 0
    characters: int = 0


@dataclass
class _Budget:
    limits: AnatomyLimits
    nodes: int = 0
    characters: int = 0

    def characters_used(self, size: int, location: str) -> None:
        self.characters += size
        if self.characters > self.limits.max_xml_characters:
            raise ResourceLimitError(f'{location}: max_xml_characters exceeded')


def _xml_nodes(data: bytes, location: str, budget: _Budget, *, count_markup: bool = False) -> tuple[XmlNodeInfo, ...]:
    parser = expat.ParserCreate(namespace_separator='}')
    nodes: list[XmlNodeInfo] = []
    stack: list[_XmlFrame] = []

    def name(value: str) -> str:
        if len(value) > budget.limits.max_xml_name_chars:
            raise ResourceLimitError(f'{location}: max_xml_name_chars exceeded')
        budget.characters_used(len(value), location)
        return '{'+value if '}' in value else value

    def start(tag: str, attributes: dict[str, str]) -> None:
        checkpoint()
        budget.nodes += 1
        if budget.nodes > budget.limits.max_xml_nodes or len(stack) >= budget.limits.max_xml_depth:
            raise ResourceLimitError(f'{location}: XML node/depth limit exceeded')
        path = f'{stack[-1].path}/{stack[-1].children}' if stack else '0'
        if stack:
            stack[-1].children += 1
        pairs = []
        for key, value in attributes.items():
            checkpoint()
            budget.characters_used(len(value), location)
            pairs.append((name(key), value))
        stack.append(_XmlFrame(len(nodes), path))
        nodes.append(XmlNodeInfo(path, name(tag), tuple(sorted(pairs)), '', start_byte=parser.CurrentByteIndex))

    def text(value: str) -> None:
        checkpoint()
        budget.characters_used(len(value), location)
        if stack:
            stack[-1].hasher.update(value.encode('utf-8'))
            stack[-1].characters += len(value)

    def end(tag: str) -> None:
        checkpoint()
        frame = stack.pop()
        nodes[frame.index] = replace(nodes[frame.index], text_sha256=frame.hasher.hexdigest(),
                                     text_characters=frame.characters, end_event_byte=parser.CurrentByteIndex)

    def forbidden(*args: Any) -> NoReturn:
        raise UnsupportedDocumentError(f'{location}: DTD/entities are outside the XML inspection profile')

    def namespace(prefix: str | None, uri: str | None) -> None:
        if uri is not None:
            name(uri)

    def markup(*values: str) -> None:
        checkpoint()
        budget.nodes += 1
        if budget.nodes > budget.limits.max_xml_nodes:
            raise ResourceLimitError(f'{location}: XML markup node limit exceeded')
        budget.characters_used(sum(map(len, values)), location)

    parser.StartElementHandler, parser.EndElementHandler, parser.CharacterDataHandler = start, end, text
    parser.StartNamespaceDeclHandler = namespace
    if count_markup:
        parser.CommentHandler = markup
        parser.ProcessingInstructionHandler = markup
    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    try:
        parser.Parse(data, True)
    except expat.ExpatError as error:
        raise InvalidDocumentError(f'{location}: invalid XML: {error}') from error
    return tuple(nodes)


def _member_payload(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limits: AnatomyLimits) -> bytes:
    location = 'zip:/'+info.filename
    if info.flag_bits & 1:
        raise EncryptedDocumentError(f'{location}: encrypted ZIP member')
    if info.file_size > limits.max_part_bytes:
        raise ResourceLimitError(f'{location}: max_part_bytes exceeded')
    with archive.open(info) as member:
        payload = member.read(limits.max_part_bytes+1)
    checkpoint()
    if len(payload) != info.file_size or len(payload) > limits.max_part_bytes:
        raise InvalidDocumentError(f'{location}: inconsistent ZIP member size')
    return payload


def _zip_items(
    data: bytes, limits: AnatomyLimits, parse_xml: bool, capture: bool,
) -> tuple[tuple[BinaryItem, ...], dict[str, Any], OpcAudit | None, EpubAudit | None]:
    check_archive_safety(io.BytesIO(data), max_entries=limits.max_items,
                         max_total_size=limits.max_total_bytes, max_ratio=limits.max_ratio)
    items, budget = [], _Budget(limits)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        archive_names = set(archive.namelist())
        manifest: bytes | None = None
        mime: bytes | None = None
        manifest_nodes: tuple[XmlNodeInfo, ...] = ()
        defaults: dict[str, str] = {}
        overrides: dict[str, str] = {}
        xml_cache: dict[str, tuple[bytes, tuple[XmlNodeInfo, ...]]] = {}
        epub_types: dict[str, str] = {}
        rootfiles: tuple[str, ...] = ()
        epub: EpubAudit | None = None
        if parse_xml and '[Content_Types].xml' in archive_names:
            manifest = _member_payload(archive, archive.getinfo('[Content_Types].xml'), limits)
            manifest_nodes = _xml_nodes(manifest, 'zip:/[Content_Types].xml', budget)
            defaults, overrides = content_types(manifest_nodes)
        elif parse_xml and 'mimetype' in archive_names:
            mime = _member_payload(archive, archive.getinfo('mimetype'), limits)
            if mime == b'application/epub+zip':

                def read_control(name: str) -> tuple[XmlNodeInfo, ...]:
                    checkpoint()
                    if name not in xml_cache:
                        try:
                            info = archive.getinfo(name)
                        except KeyError as error:
                            raise InvalidDocumentError(f'zip:/{name}: missing EPUB control part') from error
                        payload = _member_payload(archive, info, limits)
                        xml_cache[name] = (payload, _xml_nodes(payload, 'zip:/'+name, budget))
                    return xml_cache[name][1]

                epub_types, rootfiles, epub = inspection_content_types(read_control)
                for name in epub_types:
                    checkpoint()
                    if name not in archive_names or archive.getinfo(name).is_dir():
                        raise InvalidDocumentError(f'zip:/{name}: missing EPUB manifest resource')
        for info in archive.infolist():
            checkpoint()
            location = 'zip:/'+info.filename
            if info.filename == '[Content_Types].xml' and manifest is not None:
                payload = manifest
            elif info.filename == 'mimetype' and mime is not None:
                payload = mime
            elif info.filename in xml_cache:
                payload = xml_cache[info.filename][0]
            else:
                payload = _member_payload(archive, info, limits)
            offset = info.header_offset
            if offset < 0 or offset+30 > len(data):
                raise InvalidDocumentError(f'{location}: invalid local ZIP header offset')
            header = struct.unpack_from('<4s5H3I2H', data, offset)
            start = offset+30+header[-2]+header[-1]
            stop = start+info.compress_size
            if header[0] != b'PK\x03\x04' or stop > len(data):
                raise InvalidDocumentError(f'{location}: invalid ZIP wire entry')
            declared_type = (epub_types.get(info.filename) if rootfiles
                             else declared_content_type('/'+info.filename, defaults, overrides))
            detection = None
            nodes: tuple[XmlNodeInfo, ...] = ()
            if parse_xml and not info.is_dir():
                if info.filename == '[Content_Types].xml' and manifest is not None:
                    nodes, detection = manifest_nodes, 'opc-manifest'
                elif info.filename in xml_cache:
                    nodes = xml_cache[info.filename][1]
                    detection = 'epub-container' if info.filename == 'META-INF/container.xml' else 'epub-package'
                elif declared_type is not None:
                    if xml_content_type(declared_type):
                        nodes = _xml_nodes(payload, location, budget)
                        detection = 'epub-media-type' if rootfiles else 'opc-content-type'
                elif info.filename.lower().endswith(('.xml', '.rels', '.xhtml', '.svg')):
                    nodes, detection = _xml_nodes(payload, location, budget), 'extension'
            item = BinaryItem(location, 'zip-directory' if info.is_dir() else 'zip-member', len(payload),
                              hashlib.sha256(payload).hexdigest(), hashlib.sha256(memoryview(data)[offset:stop]).hexdigest(),
                              tuple({'compression': info.compress_type, 'flags': info.flag_bits, 'crc32': info.CRC,
                                     'header_offset': offset, 'compressed_size': info.compress_size, 'date_time': info.date_time,
                                     'external_attributes': info.external_attr, 'internal_attributes': info.internal_attr,
                                     'original_name': info.orig_filename, 'local_header_hex': data[offset:offset+30].hex(),
                                     'create_system': info.create_system, 'create_version': info.create_version,
                                     'extract_version': info.extract_version,
                                     'extra_sha256': hashlib.sha256(info.extra).hexdigest(),
                                     'comment_sha256': hashlib.sha256(info.comment).hexdigest(),
                                     'xml_parsed': bool(nodes), 'xml_detection': detection,
                                     'content_type': declared_type}.items()), nodes, payload if capture else None)
            items.append(item)
        details = {'comment_size': len(archive.comment), 'comment_sha256': hashlib.sha256(archive.comment).hexdigest()}
        if rootfiles:
            details['epub_rootfiles'] = rootfiles
    opc = audit_package(items, overrides) if manifest is not None else None
    return tuple(items), details, opc, epub


def _pdf_items(data: bytes, limits: AnatomyLimits, capture: bool) -> tuple[tuple[BinaryItem, ...], dict[str, Any]]:
    from opendoc_formats.pdf import PdfDocument, PdfLimits
    from opendoc_formats.support.cancellation import cancellation_requested

    items = []
    native_limits = PdfLimits(max_input_bytes=limits.max_input_bytes, max_objects=limits.max_items,
                              max_object_bytes=limits.max_part_bytes, max_inspection_bytes=limits.max_total_bytes)
    with PdfDocument(data, limits=native_limits, cancelled=cancellation_requested) as document:
        details = {'page_count': document.page_count, 'trailer': document.trailer, 'repaired': document.repaired,
                   'representation': 'active-xref-normalized-dictionaries-and-encoded-streams'}
        total = len(str(details['trailer']).encode('utf-8'))
        for value in document.iter_objects():
            dictionary = value.dictionary.encode('utf-8')
            stream = value.raw_stream or b''
            total += len(dictionary)+len(stream)
            if total > limits.max_total_bytes:
                raise ResourceLimitError(f'pdf:xref={value.xref}: max_total_bytes exceeded')
            digest = hashlib.sha256(b'PDF-object\0'+len(dictionary).to_bytes(8, 'big'))
            digest.update(dictionary)
            digest.update(b'\1' if value.raw_stream is not None else b'\0')
            digest.update(stream)
            items.append(BinaryItem(f'pdf:xref={value.xref}', 'pdf-object-slot', len(dictionary)+len(stream), digest.hexdigest(),
                                    details=tuple({'dictionary': value.dictionary, 'has_stream': value.raw_stream is not None,
                                                   'raw_stream_size': len(stream),
                                                   'raw_stream_sha256': hashlib.sha256(stream).hexdigest()
                                                   if value.raw_stream is not None else None}.items()),
                                    payload=value.raw_stream if capture else None))
    return tuple(items), details


def _sfnt_items(data: bytes, limits: AnatomyLimits, capture: bool,
                checksums: bool, face_index: int | None, structure: bool) -> tuple[tuple[BinaryItem, ...], dict[str, Any]]:
    from opendoc_formats.native.sfnt import SfntLimits, inspect_sfnt, inspect_sfnt_checksums, inspect_sfnt_structure

    if len(data) > limits.max_part_bytes or len(data) > limits.max_total_bytes:
        raise ResourceLimitError('sfnt:source: max_part_bytes/max_total_bytes exceeded by original program')
    font_limits = SfntLimits(
        max_input_bytes=limits.max_input_bytes, max_tables=limits.max_items-1,
        max_table_bytes=limits.max_part_bytes, max_total_table_bytes=limits.max_total_bytes-len(data),
        max_faces=limits.max_items-1,
    )
    if checksums and data.startswith(b'ttcf'):
        raise UnsupportedDocumentError('Checksum audit requires standalone sfnt, not a collection face')
    inventory = inspect_sfnt(data, capture=capture, cancelled=cancellation_requested, limits=font_limits,
                             face_index=face_index)
    items = [BinaryItem('sfnt:source', 'sfnt-source', len(data), inventory.source_sha256,
                        payload=data if capture else None)]
    for table in inventory.tables:
        checkpoint()
        record = memoryview(data)[table.directory_offset:table.directory_offset+16]
        prefix = 'sfnt:' if inventory.face_index is None else f'sfnt:face={inventory.face_index}:'
        items.append(BinaryItem(prefix+'table='+table.tag, 'sfnt-table', table.length, table.sha256,
                                storage_sha256=hashlib.sha256(record).hexdigest(),
                                details=(('tag', table.tag), ('offset', table.offset),
                                         ('directory_offset', table.directory_offset),
                                         ('declared_checksum', table.declared_checksum)), payload=table.payload))
    details: dict[str, Any] = {'sfnt_version': inventory.sfnt_version, 'header_hex': inventory.header_hex,
                               'variation_tables': inventory.variation_tables, 'assessment_complete': False}
    if inventory.face_index is not None:
        details.update(face_index=inventory.face_index, directory_offset=inventory.directory_offset)
    if checksums:
        details['checksums'] = asdict(inspect_sfnt_checksums(data, limits=font_limits, cancelled=cancellation_requested))
    if structure:
        report_limits = replace(font_limits, max_findings=limits.max_items-len(items))
        details['structure'] = asdict(inspect_sfnt_structure(data, limits=report_limits, face_index=face_index,
                                                            cancelled=cancellation_requested))
    return tuple(items), details


def inspect_binary(source: Source, *, container: str | None = None, limits: AnatomyLimits = AnatomyLimits(),
                   parse_xml: bool = True, capture: bool = False, sfnt_checksums: bool = False,
                   sfnt_structure: bool = False,
                   sfnt_face_index: int | None = None,
                   cancelled: Callable[[], bool] | None = None) -> BinarySnapshot:
    """Inspect content without executing macros, following external links or decoding PDF streams."""
    if (not isinstance(limits, AnatomyLimits) or type(parse_xml) is not bool
            or type(capture) is not bool or type(sfnt_checksums) is not bool or type(sfnt_structure) is not bool):
        raise TypeError('Expected AnatomyLimits and boolean inspection flags')
    if sfnt_face_index is not None:
        positive_int(sfnt_face_index, 'sfnt_face_index', zero=True)
    if container not in (None, 'zip', 'pdf', 'cfbf', 'sfnt'):
        raise ValueError('Binary inspection supports container=zip, pdf, cfbf or sfnt')
    with cancellation_scope(cancelled, 'Binary inspection', inherit=True):
        data = read_source(source, limits.max_input_bytes, None)
        checkpoint()
        if container is None:
            is_zip = zipfile.is_zipfile(io.BytesIO(data))
            is_sfnt = data.startswith((b'\x00\x01\x00\x00', b'OTTO', b'ttcf'))
            is_pdf = (b'%PDF-' in data[:1024] and not is_sfnt
                      and not data.startswith((b'PK\x03\x04', b'PK\x05\x06', CFBF_SIGNATURE)))
            profiles = [name for name, present in (('zip', is_zip), ('pdf', is_pdf),
                                                   ('cfbf', data.startswith(CFBF_SIGNATURE)), ('sfnt', is_sfnt)) if present]
            if len(profiles) != 1:
                raise UnsupportedDocumentError('Choose zip/pdf/cfbf/sfnt explicitly for an ambiguous or unsupported container')
            container = profiles[0]
        if sfnt_checksums and container != 'sfnt':
            raise ValueError('sfnt_checksums requires the sfnt container profile')
        if sfnt_face_index is not None and container != 'sfnt':
            raise ValueError('sfnt_face_index requires the sfnt container profile')
        if sfnt_structure and container != 'sfnt':
            raise ValueError('sfnt_structure requires the sfnt container profile')
        try:
            if container == 'zip':
                items, details, opc, epub = _zip_items(data, limits, parse_xml, capture)
            elif container == 'cfbf':
                from opendoc_formats.native.cfbf import inspect_cfbf

                items, details = inspect_cfbf(data, limits, capture)
                opc, epub = None, None
            elif container == 'sfnt':
                items, details = _sfnt_items(data, limits, capture, sfnt_checksums, sfnt_face_index, sfnt_structure)
                opc, epub = None, None
            else:
                items, details = _pdf_items(data, limits, capture)
                opc = None
                epub = None
        except ResourceLimitError:
            raise
        except (zipfile.BadZipFile, ArchiveSafetyError, EOFError, zlib.error) as error:
            raise InvalidDocumentError(f'Invalid container: {error}') from error
        except NotImplementedError as error:
            raise UnsupportedDocumentError(f'Unsupported container encoding: {error}') from error
        checkpoint()
        return BinarySnapshot(container, hashlib.sha256(data).hexdigest(), len(data), items, tuple(details.items()), opc, epub)


__all__ = ['AnatomyLimits', 'BinaryItem', 'BinarySnapshot', 'XmlNodeInfo', 'OpcAudit', 'OpcFinding', 'OpcRelationship',
           'EpubAudit', 'EpubManifestReference',
           'compare_snapshots', 'inspect_binary']
