"""Finite EPUB 3 export using the shared HTML renderer and Python's standard library."""

from __future__ import annotations

import base64
import hashlib
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote_to_bytes
from zipfile import ZIP_STORED, ZipFile

from opendoc_model import ConversionReport, DocumentModel, IssueSeverity, PreservationState, get_integration

from opendoc_formats.support.io import atomic_write_bytes
from opendoc_formats.writers.html_resources import document_images
from opendoc_formats.writers.html_writer import write_html_model

_XHTML = "http://www.w3.org/1999/xhtml"
_OPF = "http://www.idpf.org/2007/opf"
_DC = "http://purl.org/dc/elements/1.1/"
_SVG = "http://www.w3.org/2000/svg"
_MATH = "http://www.w3.org/1998/Math/MathML"
_EPUB = "http://www.idpf.org/2007/ops"
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_IMAGES = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/svg+xml": "svg"}
_MAX_BYTES = 64 * 1024 * 1024
_SVG_CASE = {name.lower(): name for name in ("viewBox", "preserveAspectRatio", "gradientUnits", "gradientTransform")}


def _xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


class _Xhtml(HTMLParser):
    """Convert only our generated, balanced HTML, without a third-party parser."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: ET.Element | None = None
        self.stack: list[tuple[str, ET.Element, str]] = []
        self.assets: dict[str, tuple[str, bytes]] = {}
        self.count = 0
        self.byte_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.count += 1
        if self.count > 100_000 or len(self.stack) >= 128:
            raise ValueError("EPUB XHTML structure exceeds limits")
        namespace = self.stack[-1][2] if self.stack else _XHTML
        if tag == "svg":
            namespace = _SVG
        elif tag == "math":
            namespace = _MATH
        attributes = {
            _SVG_CASE.get(key, key) if namespace == _SVG else key: value or ""
            for key, value in attrs if key != "xmlns"
        }
        if "xml:lang" in attributes:
            attributes["{http://www.w3.org/XML/1998/namespace}lang"] = attributes.pop("xml:lang")
        if tag == "img":
            attributes["src"] = self._image(attributes.get("src", ""))
        if not self.stack or namespace != self.stack[-1][2]:
            attributes["xmlns"] = namespace
        element = ET.Element(tag, attributes)
        if self.stack:
            self.stack[-1][1].append(element)
        elif self.root is None:
            self.root = element
        else:
            raise ValueError("Multiple EPUB XHTML roots")
        if tag not in _VOID:
            self.stack.append((tag, element, namespace))

    def _image(self, uri: str) -> str:
        header, separator, payload = uri.partition(",")
        media = header.removeprefix("data:").split(";", 1)[0]
        if not separator or not uri.startswith("data:") or media not in _IMAGES:
            raise ValueError("EPUB image requires embedded PNG, JPEG, GIF or SVG")
        raw = base64.b64decode(payload, validate=True) if header.endswith(";base64") else unquote_to_bytes(payload)
        name = "assets/" + hashlib.sha256(raw).hexdigest() + "." + _IMAGES[media]
        if name not in self.assets:
            self.byte_count += len(raw)
            if self.byte_count > _MAX_BYTES:
                raise ValueError("EPUB resources exceed 64 MiB")
            self.assets[name] = (media, raw)
        return name

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            raise ValueError("Unbalanced generated EPUB XHTML")
        self.stack.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.stack:
            parent = self.stack[-1][1]
            if len(parent):
                parent[-1].tail = (parent[-1].tail or "") + data
            else:
                parent.text = (parent.text or "") + data


def _navigation(chapter: ET.Element, title: str, language: str) -> ET.Element:
    root = ET.Element("html", {"xmlns": _XHTML, "lang": language})
    head = ET.SubElement(root, "head")
    ET.SubElement(head, "title").text = title
    body = ET.SubElement(root, "body")
    nav = ET.SubElement(body, "nav", {f"{{{_EPUB}}}type": "toc", "id": "toc"})
    ET.SubElement(nav, "h1").text = title
    listing = ET.SubElement(nav, "ol")
    headings = [node for node in chapter.iter() if node.tag in {f"h{i}" for i in range(1, 7)}]
    used = {node.get("id") for node in chapter.iter() if node.get("id")}
    for index, heading in enumerate(headings):
        anchor = heading.get("id")
        if not anchor:
            anchor = f"epub-heading-{index}"
            while anchor in used:
                anchor += "-"
            heading.set("id", anchor)
            used.add(anchor)
        item = ET.SubElement(listing, "li")
        ET.SubElement(item, "a", {"href": "chapter.xhtml#" + anchor}).text = "".join(heading.itertext()) or title
    if not headings:
        item = ET.SubElement(listing, "li")
        ET.SubElement(item, "a", {"href": "chapter.xhtml"}).text = title
    return root


def write_epub_model(document: DocumentModel, output_path: str | Path) -> ConversionReport:
    """Write one XHTML spine item with TOC, tables, MathML and local image assets.

    This profile shares HTML diagnostics and presentation; it does not rebuild
    original EPUB packages, media playback or fixed-layout reading-system behavior.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = ConversionReport(output)
    try:
        with TemporaryDirectory(prefix=".opendoc-formats-epub-", dir=output.parent) as directory:
            html = Path(directory) / "chapter.html"
            rendered = write_html_model(document, html)
            report.issues.extend(rendered.issues)
            if not rendered.success:
                return report
            if html.stat().st_size > _MAX_BYTES:
                raise ValueError("EPUB XHTML exceeds 64 MiB")
            parser = _Xhtml()
            parser.feed(html.read_text(encoding="utf-8"))
            parser.close()
        chapter = parser.root
        if chapter is None or parser.stack:
            raise ValueError("Incomplete EPUB XHTML")
        title = str(document.metadata.get("title") or "Document")
        language = str(document.metadata.get("language") or "ru")
        nav = _navigation(chapter, title, language)
        package = ET.Element(f"{{{_OPF}}}package", {"version": "3.0", "unique-identifier": "book-id"})
        metadata = ET.SubElement(package, f"{{{_OPF}}}metadata")
        identifier = "urn:sha256:" + hashlib.sha256(_xml(chapter)).hexdigest()
        ET.SubElement(metadata, f"{{{_DC}}}identifier", {"id": "book-id"}).text = identifier
        ET.SubElement(metadata, f"{{{_DC}}}title").text = title
        ET.SubElement(metadata, f"{{{_DC}}}language").text = language
        ET.SubElement(metadata, f"{{{_OPF}}}meta", {"property": "dcterms:modified"}).text = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        manifest = ET.SubElement(package, f"{{{_OPF}}}manifest")
        properties = []
        if any(node.tag == "math" for node in chapter.iter()):
            properties.append("mathml")
        if any(node.tag == "svg" for node in chapter.iter()):
            properties.append("svg")
        ET.SubElement(manifest, f"{{{_OPF}}}item", {
            "id": "chapter", "href": "chapter.xhtml", "media-type": "application/xhtml+xml",
            **({"properties": " ".join(properties)} if properties else {}),
        })
        ET.SubElement(manifest, f"{{{_OPF}}}item", {
            "id": "nav", "href": "nav.xhtml", "media-type": "application/xhtml+xml", "properties": "nav",
        })
        for index, (name, (media, _)) in enumerate(parser.assets.items()):
            ET.SubElement(manifest, f"{{{_OPF}}}item", {"id": f"asset-{index}", "href": name, "media-type": media})
        spine = ET.SubElement(package, f"{{{_OPF}}}spine")
        ET.SubElement(spine, f"{{{_OPF}}}itemref", {"idref": "chapter"})
        container_ns = "urn:oasis:names:tc:opendocument:xmlns:container"
        container = ET.Element(f"{{{container_ns}}}container", {"version": "1.0"})
        roots = ET.SubElement(container, f"{{{container_ns}}}rootfiles")
        ET.SubElement(roots, f"{{{container_ns}}}rootfile", {
            "full-path": "OPS/book.opf", "media-type": "application/oebps-package+xml",
        })
        buffer = io.BytesIO()
        # Stored entries avoid creating archives our own compression-ratio guard rejects.
        with ZipFile(buffer, "w", compression=ZIP_STORED) as archive:
            archive.writestr("mimetype", b"application/epub+zip")
            archive.writestr("META-INF/container.xml", _xml(container))
            archive.writestr("OPS/book.opf", _xml(package))
            archive.writestr("OPS/chapter.xhtml", _xml(chapter))
            archive.writestr("OPS/nav.xhtml", _xml(nav))
            for name, (_, raw) in parser.assets.items():
                archive.writestr("OPS/" + name, raw)
        if buffer.tell() > _MAX_BYTES:
            raise ValueError("EPUB output exceeds 64 MiB")
        integration = get_integration(document)
        if integration is not None:
            for record in integration.preservation:
                if (
                    record.state is not PreservationState.SEMANTIC
                    and not record.issue.code.startswith(("html-", "html.", "epub."))
                ):
                    report.add(IssueSeverity.LOSS, "epub.source-feature", record.issue.message, record.issue.location)
        image_ids = {image.resource_id for image, _ in document_images(document)}
        for resource_id in document.resources.keys() - image_ids:
            report.add(
                IssueSeverity.LOSS, "epub.unreferenced-resource",
                "Source resource is not reconstructed in the EPUB manifest", f"resources[{resource_id}]",
            )
        if document.package is not None:
            report.add(IssueSeverity.LOSS, "epub.source-package", "Original source package is not reconstructed")
        report.add(
            IssueSeverity.LOSS, "epub.layout-profile",
            "One XHTML spine item; reading systems may reflow the shared HTML presentation",
        )
        report.metrics.update({"epub_spine_items": 1, "epub_assets": len(parser.assets), "epub_bytes": buffer.tell()})
        atomic_write_bytes(output, buffer.getvalue())
    except (OSError, ValueError, ET.ParseError) as error:
        report.add(IssueSeverity.ERROR, "epub.write", str(error))
    return report
