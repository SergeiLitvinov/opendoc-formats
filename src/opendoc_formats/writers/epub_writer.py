"""Finite EPUB 3 export using the shared HTML renderer and Python's standard library."""

from __future__ import annotations

import base64
import hashlib
import io
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, unquote, unquote_to_bytes
from zipfile import ZIP_STORED, ZipFile

from opendoc_model import ConversionReport, DocumentModel, IssueSeverity, PreservationState, get_integration

from opendoc_formats.epub_metadata import export_dc_values
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


def _chapters(root: ET.Element, report: ConversionReport) -> list[tuple[str, ET.Element]]:
    body = root.find("body")
    if body is None:
        raise ValueError("EPUB XHTML has no body")
    sections = list(body)
    chapters = []
    for index, section in enumerate(sections):
        chapter = ET.Element(root.tag, dict(root.attrib))
        head = root.find("head")
        if head is not None:
            chapter.append(head)
        target = ET.SubElement(chapter, "body", dict(body.attrib))
        target.append(deepcopy(section))
        name = "chapter.xhtml" if index == 0 else f"chapter-{index + 1}.xhtml"
        chapters.append((name, chapter))
    if not chapters:
        chapters = [("chapter.xhtml", root)]
    targets: dict[str, list[str]] = {}
    for name, chapter in chapters:
        for node in chapter.iter():
            if node.get("id"):
                targets.setdefault(node.attrib["id"], []).append(name)
    for name, chapter in chapters:
        for node in chapter.iter("a"):
            href = node.get("href", "")
            if not href.startswith("#"):
                continue
            anchor = unquote(href[1:])
            owners = targets.get(anchor, [])
            if len(owners) != 1:
                node.attrib.pop("href", None)
                report.add(IssueSeverity.LOSS, "epub.internal-link", "Missing or ambiguous internal target", f"{name}:{href}")
            else:
                node.set("href", (owners[0] if owners[0] != name else "") + "#" + quote(anchor, safe=""))
    return chapters


def _navigation(chapters: list[tuple[str, ET.Element]], title: str, language: str) -> ET.Element:
    root = ET.Element("html", {"xmlns": _XHTML, "lang": language})
    head = ET.SubElement(root, "head")
    ET.SubElement(head, "title").text = title
    body = ET.SubElement(root, "body")
    nav = ET.SubElement(body, "nav", {f"{{{_EPUB}}}type": "toc", "id": "toc"})
    ET.SubElement(nav, "h1").text = title
    listing = ET.SubElement(nav, "ol")
    for chapter_index, (name, chapter) in enumerate(chapters):
        headings = [node for node in chapter.iter() if node.tag in {f"h{i}" for i in range(1, 7)}]
        used = {node.get("id") for node in chapter.iter() if node.get("id")}
        parents: list[tuple[int, ET.Element]] = []
        for index, heading in enumerate(headings):
            anchor = heading.get("id")
            if not anchor:
                anchor = f"epub-heading-{index}"
                while anchor in used:
                    anchor += "-"
                heading.set("id", anchor)
                used.add(anchor)
            level = int(heading.tag[1])
            while parents and parents[-1][0] >= level:
                parents.pop()
            target_list = listing
            if parents:
                target_list = parents[-1][1].find("ol")
                if target_list is None:
                    target_list = ET.SubElement(parents[-1][1], "ol")
            item = ET.SubElement(target_list, "li")
            parents.append((level, item))
            ET.SubElement(item, "a", {"href": name + "#" + quote(anchor, safe="")}).text = "".join(heading.itertext()) or title
        if not headings:
            item = ET.SubElement(listing, "li")
            ET.SubElement(item, "a", {"href": name}).text = f"{title} — {chapter_index + 1}" if len(chapters) > 1 else title
    return root


def write_epub_model(document: DocumentModel, output_path: str | Path) -> ConversionReport:
    """Write one XHTML spine item per section, with TOC, MathML and local assets.

    This profile shares HTML diagnostics and presentation; it does not rebuild
    original EPUB packages, media playback or fixed-layout reading-system behavior.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = ConversionReport(output)
    try:
        dc = export_dc_values(document.metadata, {"title": "Document", "language": "ru"}, report)
        title, language = dc["title"][0], dc["language"][0]
        rendered_document = replace(document, metadata={**document.metadata, "title": title, "language": language})
        requested = {image.resource_id for image, _ in document_images(document)}
        image_bytes = 0
        for resource_id in requested:
            resource = document.resources.get(resource_id)
            if resource is not None:
                if resource.data is not None:
                    image_bytes += len(resource.data)
                elif resource.source is not None:
                    image_bytes += Path(resource.source).stat().st_size
            if image_bytes > _MAX_BYTES:
                raise ValueError("EPUB input images exceed 64 MiB")
        with TemporaryDirectory(prefix=".opendoc-formats-epub-", dir=output.parent) as directory:
            html = Path(directory) / "chapter.html"
            rendered = write_html_model(rendered_document, html)
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
        chapters = _chapters(chapter, report)
        nav = _navigation(chapters, title, language)
        chapter_bytes = {}
        total_chapter_bytes = 0
        for name, content in chapters:
            data = _xml(content)
            total_chapter_bytes += len(data)
            if total_chapter_bytes > _MAX_BYTES:
                raise ValueError("EPUB chapters exceed 64 MiB")
            chapter_bytes[name] = data
        package = ET.Element(f"{{{_OPF}}}package", {"version": "3.0", "unique-identifier": "book-id"})
        metadata = ET.SubElement(package, f"{{{_OPF}}}metadata")
        identifier = "urn:sha256:" + hashlib.sha256(b"".join(chapter_bytes.values())).hexdigest()
        dc.setdefault("identifier", (identifier,))
        for name, values in dc.items():
            for index, value in enumerate(values):
                attributes = {"id": "book-id"} if name == "identifier" and index == 0 else {}
                ET.SubElement(metadata, f"{{{_DC}}}{name}", attributes).text = value
        ET.SubElement(metadata, f"{{{_OPF}}}meta", {"property": "dcterms:modified"}).text = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        manifest = ET.SubElement(package, f"{{{_OPF}}}manifest")
        for index, (name, content) in enumerate(chapters):
            properties = [tag for tag, name_tag in (("mathml", "math"), ("svg", "svg"))
                          if any(node.tag == name_tag for node in content.iter())]
            ET.SubElement(manifest, f"{{{_OPF}}}item", {
                "id": "chapter" if index == 0 else f"chapter-{index + 1}", "href": name,
                "media-type": "application/xhtml+xml",
                **({"properties": " ".join(properties)} if properties else {}),
            })
        ET.SubElement(manifest, f"{{{_OPF}}}item", {
            "id": "nav", "href": "nav.xhtml", "media-type": "application/xhtml+xml", "properties": "nav",
        })
        for index, (name, (media, _)) in enumerate(parser.assets.items()):
            ET.SubElement(manifest, f"{{{_OPF}}}item", {"id": f"asset-{index}", "href": name, "media-type": media})
        spine = ET.SubElement(package, f"{{{_OPF}}}spine")
        for index in range(len(chapters)):
            ET.SubElement(spine, f"{{{_OPF}}}itemref", {"idref": "chapter" if index == 0 else f"chapter-{index + 1}"})
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
            for name, data in chapter_bytes.items():
                archive.writestr("OPS/" + name, data)
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
            "Reading systems may reflow the shared HTML presentation",
        )
        report.metrics.update({"epub_spine_items": len(chapters), "epub_assets": len(parser.assets), "epub_bytes": buffer.tell()})
        atomic_write_bytes(output, buffer.getvalue())
    except (OSError, ValueError, ET.ParseError) as error:
        report.add(IssueSeverity.ERROR, "epub.write", str(error))
    return report
