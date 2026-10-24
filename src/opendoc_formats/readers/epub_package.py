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

from opendoc_formats.epub_metadata import read_dc_values
from opendoc_formats.native.epub import local_path
from opendoc_formats.support.cancellation import check_cancelled
from opendoc_formats.support.io import check_archive_safety

_CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
_OPF = "http://www.idpf.org/2007/opf"
_DC = "http://purl.org/dc/elements/1.1/"
_XHTML = "http://www.w3.org/1999/xhtml"
_EPUB = "http://www.idpf.org/2007/ops"
_NCX = "http://www.daisy.org/z3986/2005/ncx/"


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


def _source_snapshot(archive: zipfile.ZipFile, opf_name: str, *, cancelled: Callable[[], bool] | None = None
                      ) -> tuple[dict[str, bytes], tuple[str, ...], dict[str, str]]:
    """Original inert XML parts, independent of backend serialization."""
    check_cancelled(cancelled, 'EPUB source snapshot')
    payload = archive.read(opf_name)
    opf = _xml(payload, cancelled=cancelled)
    parts = {"META-INF/container.xml": archive.read("META-INF/container.xml"), opf_name: payload}
    for item in opf.findall(f"{{{_OPF}}}manifest/{{{_OPF}}}item"):
        check_cancelled(cancelled, 'EPUB source part')
        if "nav" in item.get("properties", "").split() or item.get("media-type") == "application/x-dtbncx+xml":
            name = _local_path(opf_name, item.get("href", ""))
            parts[name] = archive.read(name)
    metadata = opf.find(f"{{{_OPF}}}metadata")
    entries = tuple(ET.tostring(entry, encoding="unicode") for entry in metadata) if metadata is not None else ()
    return parts, entries, dict(opf.attrib)


def _local_path(base: str, href: str) -> str:
    return local_path(base, href)


def _xml(data: bytes, *, cancelled: Callable[[], bool] | None = None) -> ET.Element:
    check_cancelled(cancelled, 'EPUB XML')
    # Strip NUL only for inspection, so UTF-16/32 cannot hide declarations.
    probe = data.replace(b"\x00", b"")
    if re.search(rb"<!\s*ENTITY\b|<!\s*DOCTYPE[^>]*\[", probe, re.IGNORECASE):
        raise ValueError("Internal DTD subsets and entity declarations are not accepted in EPUB")
    root = ET.fromstring(data)  # External DTDs are never fetched by ElementTree.
    pending = [(root, 1)]
    count = 0
    while pending:
        check_cancelled(cancelled, 'EPUB XML node')
        node, depth = pending.pop()
        count += 1
        if depth > 128 or count > 100_000:
            raise ValueError("EPUB XML structure exceeds limits")
        pending.extend((child, depth + 1) for child in node)
    return root


def _opf_name(container_data: bytes, *, cancelled: Callable[[], bool] | None = None) -> str:
    container = _xml(container_data, cancelled=cancelled)
    candidates = container.findall(f"{{{_CONTAINER}}}rootfiles/{{{_CONTAINER}}}rootfile")
    entry = next((item for item in candidates if item.get("media-type") == "application/oebps-package+xml"), None)
    if entry is None:
        raise ValueError("EPUB container has no OPF rootfile")
    return _local_path("", entry.get("full-path", ""))


def read_epub_package(path: str | Path, *, cancelled: Callable[[], bool] | None = None) -> EpubPackage:
    """Read OPF, spine, EPUB 3 navigation and EPUB 2 NCX without extracting files."""
    check_cancelled(cancelled, 'EPUB package')
    check_archive_safety(path)
    with zipfile.ZipFile(path) as archive:

        def read(name: str) -> bytes:
            check_cancelled(cancelled, 'EPUB archive member')
            try:
                payload = archive.read(name)
            except KeyError as error:
                raise ValueError(f"Missing EPUB package member: {name}") from error
            check_cancelled(cancelled, 'EPUB archive read')
            return payload

        if read("mimetype") != b"application/epub+zip":
            raise ValueError("Invalid EPUB mimetype")
        opf_name = _opf_name(read("META-INF/container.xml"), cancelled=cancelled)
        opf = _xml(read(opf_name), cancelled=cancelled)
        if opf.tag != f"{{{_OPF}}}package":
            raise ValueError("Invalid EPUB OPF root")
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
            items[identifier] = EpubItem(identifier, name, media_type, read(name), tuple(entry.get("properties", "").split()))
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
        parts, entries, properties = _source_snapshot(archive, opf_name, cancelled=cancelled)
        check_cancelled(cancelled, 'EPUB package completion')
        return EpubPackage(
            items,
            tuple(spine),
            metadata,
            titles,
            root_directory=posixpath.dirname(opf_name),
            source_parts=parts,
            metadata_entries=entries,
            package_properties=properties,
            dc_values=read_dc_values(opf),
        )
