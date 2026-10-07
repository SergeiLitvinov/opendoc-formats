"""Original, bounded EPUB container reader; no network or XML entity expansion."""

from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

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


def _local_path(base: str, href: str) -> str:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        raise ValueError("Remote EPUB package references are not supported")
    decoded = unquote(parsed.path)
    if not decoded or decoded.startswith("/") or "\\" in decoded or "\x00" in decoded:
        raise ValueError("Invalid EPUB package path")
    name = posixpath.normpath(posixpath.join(posixpath.dirname(base), decoded))
    if name in {".", ".."} or name.startswith("../") or ":" in name.split("/")[0]:
        raise ValueError("EPUB package reference escapes the archive")
    return name


def _xml(data: bytes) -> ET.Element:
    # Strip NUL only for inspection, so UTF-16/32 cannot hide declarations.
    probe = data.replace(b"\x00", b"")
    if re.search(br"<!\s*ENTITY\b|<!\s*DOCTYPE[^>]*\[", probe, re.IGNORECASE):
        raise ValueError("Internal DTD subsets and entity declarations are not accepted in EPUB")
    root = ET.fromstring(data)  # External DTDs are never fetched by ElementTree.
    pending = [(root, 1)]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if depth > 128 or count > 100_000:
            raise ValueError("EPUB XML structure exceeds limits")
        pending.extend((child, depth + 1) for child in node)
    return root


def _opf_name(container_data: bytes) -> str:
    container = _xml(container_data)
    candidates = container.findall(f"{{{_CONTAINER}}}rootfiles/{{{_CONTAINER}}}rootfile")
    entry = next((item for item in candidates if item.get("media-type") == "application/oebps-package+xml"), None)
    if entry is None:
        raise ValueError("EPUB container has no OPF rootfile")
    return _local_path("", entry.get("full-path", ""))


def read_epub_package(path: str | Path) -> EpubPackage:
    """Read OPF, spine, EPUB 3 navigation and EPUB 2 NCX without extracting files."""
    check_archive_safety(path)
    with zipfile.ZipFile(path) as archive:
        def read(name: str) -> bytes:
            try:
                return archive.read(name)
            except KeyError as error:
                raise ValueError(f"Missing EPUB package member: {name}") from error

        if read("mimetype") != b"application/epub+zip":
            raise ValueError("Invalid EPUB mimetype")
        opf_name = _opf_name(read("META-INF/container.xml"))
        opf = _xml(read(opf_name))
        if opf.tag != f"{{{_OPF}}}package":
            raise ValueError("Invalid EPUB OPF root")
        items: dict[str, EpubItem] = {}
        names: set[str] = set()
        for entry in opf.findall(f"{{{_OPF}}}manifest/{{{_OPF}}}item"):
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
            for point in _xml(ncx.content).iter(f"{{{_NCX}}}navPoint"):
                content = point.find(f"{{{_NCX}}}content")
                label = point.find(f"{{{_NCX}}}navLabel/{{{_NCX}}}text")
                if content is not None and label is not None and content.get("src"):
                    titles.setdefault(_local_path(ncx.name, content.get("src", "")), "".join(label.itertext()))
        for item in items.values():
            if "nav" not in item.properties:
                continue
            root = _xml(item.content)
            for nav in root.iter(f"{{{_XHTML}}}nav"):
                if "toc" not in nav.get(f"{{{_EPUB}}}type", "").split():
                    continue
                for link in nav.iter(f"{{{_XHTML}}}a"):
                    href = link.get("href", "")
                    if href and not urlsplit(href).scheme and not urlsplit(href).netloc:
                        titles[_local_path(item.name, href)] = "".join(link.itertext()).strip()
        # Keep public chapter/resource identifiers relative to OPF, as in the
        # legacy backend. Archive lookup above always uses absolute ZIP names.
        base = posixpath.dirname(opf_name) or "."
        items = {key: EpubItem(item.id, posixpath.relpath(item.name, base), item.media_type,
                               item.content, item.properties) for key, item in items.items()}
        titles = {posixpath.relpath(name, base): title for name, title in titles.items()}
        return EpubPackage(items, tuple(spine), metadata, titles, root_directory=posixpath.dirname(opf_name))


def read_ebooklib_package(path: str | Path) -> EpubPackage:
    """Optional legacy backend normalized to the same internal contract."""
    from ebooklib import epub

    check_archive_safety(path)
    with zipfile.ZipFile(path) as archive:
        root_directory = posixpath.dirname(_opf_name(archive.read("META-INF/container.xml")))
    book = epub.read_epub(str(path))
    items = {
        item.id: EpubItem(item.id, posixpath.normpath(item.get_name()), item.media_type, item.content,
                          ("nav",) if isinstance(item, epub.EpubNav) else ())
        for item in book.get_items()
    }
    titles: dict[str, str] = {}

    def visit(entries: tuple) -> None:
        for entry in entries:
            link, children = entry if isinstance(entry, tuple) else (entry, ())
            if getattr(link, "href", ""):
                titles[posixpath.normpath(unquote(urlsplit(link.href).path))] = link.title
            visit(children)

    visit(book.toc)
    metadata = {}
    for name in ("title", "language", "identifier"):
        values = book.get_metadata("DC", name)
        metadata[name] = values[0][0] if values else ""
    return EpubPackage(items, tuple(book.spine), metadata, titles, "ebooklib+bs4", root_directory)
