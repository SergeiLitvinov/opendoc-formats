"""Original, bounded EPUB container reader; no network or XML entity expansion."""

from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
from xml.parsers import expat

from opendoc_formats.epub_metadata import read_dc_values
from opendoc_formats.errors import ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.epub import ENCRYPTION_PATH, IDPF_EMBEDDING, XML_ENCRYPTION, idpf_font_key, local_path
from opendoc_formats.support.cancellation import check_cancelled
from opendoc_formats.support.io import open_checked_archive, read_archive_member

_CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
_OPF = "http://www.idpf.org/2007/opf"
_DC = "http://purl.org/dc/elements/1.1/"
_XHTML = "http://www.w3.org/1999/xhtml"
_EPUB = "http://www.idpf.org/2007/ops"
_NCX = "http://www.daisy.org/z3986/2005/ncx/"
_ENC = XML_ENCRYPTION


@dataclass(frozen=True)
class EpubItem:
    id: str
    name: str
    media_type: str
    content: bytes
    properties: tuple[str, ...] = ()


@dataclass(frozen=True)
class EpubPackage:
    items: dict[str, EpubItem]
    spine: tuple[tuple[str, str], ...]
    metadata: dict[str, str]
    titles: dict[str, str] = field(default_factory=dict)
    engine: str = "native-epub+bs4"
    root_directory: str = ""
    source_parts: dict[str, bytes] = field(default_factory=dict)
    metadata_entries: tuple[str, ...] = ()
    package_properties: dict[str, str] = field(default_factory=dict)
    dc_values: dict[str, tuple[str, ...]] = field(default_factory=dict)
    obfuscated_fonts: dict[str, bytes | None] = field(default_factory=dict)


def _font_keys(opf: ET.Element, data: bytes, items: dict[str, EpubItem],
               cancelled: Callable[[], bool] | None) -> dict[str, bytes | None]:
    root = _xml(data, cancelled=cancelled)
    if root.tag != f"{{{_CONTAINER}}}encryption":
        raise ValueError("Invalid EPUB encryption.xml root")
    by_path = {item.name: item for item in items.values()}
    keys: dict[str, bytes | None] = {}
    key = None
    for entry in root.iter(_ENC + "EncryptedData"):
        check_cancelled(cancelled, 'EPUB font obfuscation')
        methods = entry.findall(_ENC + "EncryptionMethod")
        ciphers = entry.findall(f"./{_ENC}CipherData/{_ENC}CipherReference")
        if len(ciphers) != 1 or not ciphers[0].get("URI") or "#" in ciphers[0].attrib["URI"]:
            raise ValueError("EPUB encryption entry requires one local resource URI")
        cipher = ciphers[0]
        item = by_path.get(_local_path("", cipher.attrib["URI"]))
        if item is None:
            continue
        if not (item.media_type.startswith("font/") or item.media_type in {
            "application/vnd.ms-opentype", "application/font-sfnt", "application/font-woff",
        }):
            raise UnsupportedDocumentError("Encrypted EPUB content is outside the font obfuscation profile")
        if item.id in keys:
            raise ValueError("Duplicate EPUB font encryption entry")
        keys[item.id] = None
        if len(methods) != 1 or methods[0].get("Algorithm") != IDPF_EMBEDDING or len(cipher) or len(methods[0]):
            continue
        if key is None:
            unique = opf.get("unique-identifier")
            identifiers = [node for node in opf.findall(f"{{{_OPF}}}metadata/{{{_DC}}}identifier")
                           if unique and node.get("id") == unique]
            value = "".join(identifiers[0].itertext()) if len(identifiers) == 1 else ""
            key = idpf_font_key(value)
        keys[item.id] = key
    return keys


def _local_path(base: str, href: str) -> str:
    return local_path(base, href)


class _XmlTarget:
    """Check native structure before asking ElementTree to allocate each element."""

    def __init__(self, cancelled: Callable[[], bool] | None) -> None:
        self.cancelled = cancelled
        self.tree = ET.TreeBuilder()
        self.depth = 0
        self.nodes = 0

    def start(self, tag: str, attributes: dict[str, str]) -> ET.Element:
        check_cancelled(self.cancelled, 'EPUB XML node')
        if self.depth >= 128:
            raise ResourceLimitError('EPUB XML depth exceeds profile maximum 128')
        if self.nodes >= 100_000:
            raise ResourceLimitError('EPUB XML nodes exceed profile maximum 100000')
        self.depth += 1
        self.nodes += 1
        return self.tree.start(tag, attributes)

    def end(self, tag: str) -> ET.Element:
        check_cancelled(self.cancelled, 'EPUB XML end')
        element = self.tree.end(tag)
        self.depth -= 1
        return element

    def data(self, value: str) -> None:
        check_cancelled(self.cancelled, 'EPUB XML text')
        self.tree.data(value)

    def close(self) -> ET.Element:
        check_cancelled(self.cancelled, 'EPUB XML close')
        return self.tree.close()


def _xml(data: bytes, *, cancelled: Callable[[], bool] | None = None,
         positions: dict[ET.Element, tuple[int, int]] | None = None) -> ET.Element:
    check_cancelled(cancelled, 'EPUB XML')
    # Strip NUL only for inspection, so UTF-16/32 cannot hide declarations.
    probe = data.replace(b"\x00", b"")
    if re.search(rb"<!\s*ENTITY\b|<!\s*DOCTYPE[^>]*\[", probe, re.IGNORECASE):
        raise ValueError("Internal DTD subsets and entity declarations are not accepted in EPUB")
    # External DTDs are never fetched. The target checks limits/cancellation
    # during construction, without a second walk or a wide pending-node list.
    target = _XmlTarget(cancelled)
    if positions is None:
        parser = ET.XMLParser(target=target)
        feed, close = parser.feed, parser.close
    else:
        located = expat.ParserCreate(namespace_separator="}")

        def qualified(name: str) -> str:
            return "{" + name if "}" in name else name

        def start(tag: str, attributes: dict[str, str]) -> None:
            node = target.start(qualified(tag), {qualified(name): value for name, value in attributes.items()})
            positions[node] = located.CurrentLineNumber, located.CurrentColumnNumber

        located.StartElementHandler = start
        located.EndElementHandler = lambda tag: target.end(qualified(tag))
        located.CharacterDataHandler = target.data

        def feed(chunk: bytes) -> None:
            located.Parse(chunk, False)

        def close() -> ET.Element:
            located.Parse(b"", True)
            return target.close()

    for offset in range(0, len(data), 64 * 1024):
        check_cancelled(cancelled, 'EPUB XML feed')
        feed(data[offset:offset + 64 * 1024])
    check_cancelled(cancelled, 'EPUB XML feed')
    return close()


def _opf_name(container_data: bytes, *, cancelled: Callable[[], bool] | None = None) -> str:
    container = _xml(container_data, cancelled=cancelled)
    candidates = container.findall(f"{{{_CONTAINER}}}rootfiles/{{{_CONTAINER}}}rootfile")
    entry = next((item for item in candidates if item.get("media-type") == "application/oebps-package+xml"), None)
    if entry is None:
        raise ValueError("EPUB container has no OPF rootfile")
    return _local_path("", entry.get("full-path", ""))


def _read_member(archive: zipfile.ZipFile, name: str, cancelled: Callable[[], bool] | None) -> bytes:
    check_cancelled(cancelled, 'EPUB archive member')
    try:
        payload = read_archive_member(archive, name, check=lambda: check_cancelled(cancelled, 'EPUB archive read'))
    except KeyError as error:
        raise ValueError(f"Missing EPUB package member: {name}") from error
    check_cancelled(cancelled, 'EPUB archive read')
    return payload


def _read_opf(archive: zipfile.ZipFile, cancelled: Callable[[], bool] | None,
              ) -> tuple[str, ET.Element, dict[str, bytes]]:
    if _read_member(archive, 'mimetype', cancelled) != b'application/epub+zip':
        raise ValueError('Invalid EPUB mimetype')
    container = _read_member(archive, 'META-INF/container.xml', cancelled)
    name = _opf_name(container, cancelled=cancelled)
    payload = _read_member(archive, name, cancelled)
    opf = _xml(payload, cancelled=cancelled)
    if opf.tag != f'{{{_OPF}}}package':
        raise ValueError('Invalid EPUB OPF root')
    return name, opf, {'META-INF/container.xml': container, name: payload}


def read_epub_metadata(path: str | Path, *, cancelled: Callable[[], bool] | None = None) -> dict[str, tuple[str, ...]]:
    """Read Dublin Core fields from OPF without opening chapter or resource payloads."""
    check_cancelled(cancelled, 'EPUB metadata')
    with open_checked_archive(path, check=lambda: check_cancelled(cancelled, 'EPUB ZIP inventory')) as archive:
        _, opf, _ = _read_opf(archive, cancelled)
        return read_dc_values(opf)


def read_epub_package(path: str | Path, *, cancelled: Callable[[], bool] | None = None) -> EpubPackage:
    """Read OPF, spine, EPUB 3 navigation and EPUB 2 NCX without extracting files."""
    check_cancelled(cancelled, 'EPUB package')
    with open_checked_archive(path, check=lambda: check_cancelled(cancelled, 'EPUB ZIP inventory')) as archive:

        opf_name, opf, parts = _read_opf(archive, cancelled)
        items: dict[str, EpubItem] = {}
        names: set[str] = set()
        for entry in opf.findall(f"{{{_OPF}}}manifest/{{{_OPF}}}item"):
            check_cancelled(cancelled, 'EPUB manifest entry')
            identifier = entry.get("id", "")
            name = _local_path(opf_name, entry.get("href", ""))
            media_type = entry.get("media-type", "")
            if not identifier or not media_type or identifier in items or name in names:
                raise ValueError("Invalid or duplicate EPUB manifest item")
            names.add(name)
            payload = _read_member(archive, name, cancelled)
            properties = tuple(entry.get('properties', '').split())
            items[identifier] = EpubItem(identifier, name, media_type, payload, properties)
            if 'nav' in properties or media_type == 'application/x-dtbncx+xml':
                parts[name] = payload
        obfuscated_fonts = {}
        if ENCRYPTION_PATH in archive.namelist():
            parts[ENCRYPTION_PATH] = _read_member(archive, ENCRYPTION_PATH, cancelled)
            obfuscated_fonts = _font_keys(opf, parts[ENCRYPTION_PATH], items, cancelled)
        spine_node = opf.find(f"{{{_OPF}}}spine")
        if spine_node is None:
            raise ValueError("Missing EPUB spine")
        spine = []
        for entry in spine_node.findall(f"{{{_OPF}}}itemref"):
            check_cancelled(cancelled, 'EPUB spine entry')
            identifier = entry.get("idref", "")
            if identifier not in items:
                raise ValueError(f"Unknown EPUB spine item: {identifier}")
            spine.append((identifier, entry.get("linear", "yes")))
        metadata = {}
        for name in ("title", "language", "identifier"):
            element = opf.find(f"{{{_OPF}}}metadata/{{{_DC}}}{name}")
            metadata[name] = "" if element is None else "".join(element.itertext())
        titles: dict[str, str] = {}
        ncx = items.get(spine_node.get("toc", ""))
        if ncx is not None:
            for point in _xml(ncx.content, cancelled=cancelled).iter(f"{{{_NCX}}}navPoint"):
                check_cancelled(cancelled, 'EPUB NCX entry')
                content = point.find(f"{{{_NCX}}}content")
                label = point.find(f"{{{_NCX}}}navLabel/{{{_NCX}}}text")
                if content is not None and label is not None and content.get("src"):
                    titles.setdefault(_local_path(ncx.name, content.get("src", "")), "".join(label.itertext()))
        for item in items.values():
            check_cancelled(cancelled, 'EPUB navigation item')
            if "nav" not in item.properties:
                continue
            root = _xml(item.content, cancelled=cancelled)
            for nav in root.iter(f"{{{_XHTML}}}nav"):
                if "toc" not in nav.get(f"{{{_EPUB}}}type", "").split():
                    continue
                for link in nav.iter(f"{{{_XHTML}}}a"):
                    check_cancelled(cancelled, 'EPUB navigation link')
                    href = link.get("href", "")
                    if href and not urlsplit(href).scheme and not urlsplit(href).netloc:
                        titles[_local_path(item.name, href)] = "".join(link.itertext()).strip()
        # Keep public chapter/resource identifiers relative to OPF, as in the
        # legacy backend. Archive lookup above always uses absolute ZIP names.
        base = posixpath.dirname(opf_name) or "."
        items = {
            key: EpubItem(item.id, posixpath.relpath(item.name, base), item.media_type, item.content, item.properties)
            for key, item in items.items()
        }
        titles = {posixpath.relpath(name, base): title for name, title in titles.items()}
        metadata_node = opf.find(f"{{{_OPF}}}metadata")
        entries = tuple(ET.tostring(entry, encoding='unicode') for entry in metadata_node) if metadata_node is not None else ()
        check_cancelled(cancelled, 'EPUB package completion')
        return EpubPackage(
            items,
            tuple(spine),
            metadata,
            titles,
            root_directory=posixpath.dirname(opf_name),
            source_parts=parts,
            metadata_entries=entries,
            package_properties=dict(opf.attrib),
            dc_values=read_dc_values(opf),
            obfuscated_fonts=obfuscated_fonts,
        )
