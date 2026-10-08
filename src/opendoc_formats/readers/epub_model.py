"""Rich EPUB spine importer with links, media, and a small deterministic CSS cascade."""

from __future__ import annotations

import hashlib
import posixpath
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import opendoc_model as od
from opendoc_model.document_model import (
    DocumentModel,
    Image,
    Length,
    Paragraph,
    Provenance,
    Resource,
    ResourceKind,
    Section,
    TextRun,
    TextStyle,
)

_DECLARATION = re.compile(r"([\w-]+)\s*:\s*([^;]+)")
_SIZE = re.compile(r"^((?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))(pt|px|em|rem|%)$")
_CSS_PROPERTIES = {
    "font-family",
    "font-size",
    "font-weight",
    "font-style",
    "text-decoration",
    "vertical-align",
    "color",
    "background-color",
}
_BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "figcaption"}


def read_epub_model(path: str | Path, *, backend: str = "native", include_nonlinear: bool = False) -> DocumentModel:
    from bs4 import BeautifulSoup

    from opendoc_formats.readers.epub_diagnostics import EpubDiagnostics
    from opendoc_formats.readers.epub_package import read_ebooklib_package, read_epub_package

    source = Path(path)
    if type(include_nonlinear) is not bool:
        raise ValueError("include_nonlinear must be boolean")
    if not source.is_file():
        raise FileNotFoundError(source)
    if backend not in {"native", "ebooklib"}:
        raise ValueError("EPUB backend must be native or ebooklib")
    book = read_epub_package(source) if backend == "native" else read_ebooklib_package(source)
    resources, item_names = _resources(book, source)
    diagnostics = EpubDiagnostics(source, book.root_directory, resources)
    source_resources = {}
    for index, (part, payload) in enumerate(book.source_parts.items(), 1):
        resource_id = f"epub-source-xml-{index}"
        while resource_id in resources:
            resource_id += "-source"
        resources[resource_id] = Resource(
            resource_id,
            ResourceKind.ATTACHMENT,
            "application/xml",
            data=payload,
            filename=posixpath.basename(part),
            provenance=_provenance(source, part),
        )
        source_resources[part] = resource_id
        diagnostics.opaque(
            "epub.package",
            "source-package-xml",
            "Original package/navigation XML retained; partial semantic model",
            posixpath.relpath(part, book.root_directory or "."),
            resource_id,
        )
    for item in book.items.values():
        if item.media_type.startswith(("font/", "audio/", "video/")) or item.media_type in {
            "application/vnd.ms-opentype",
            "application/font-sfnt",
            "application/font-woff",
        }:
            diagnostics.opaque(
                "epub.asset",
                "inert-asset",
                "Original font/media bytes retained; no font activation or media playback",
                item.name,
                f"epub-{item.id}",
            )
    titles = book.titles
    sections, warnings, styles = [], [], {}
    for idref, linear in book.spine:
        item = book.items.get(idref)
        if str(linear).lower() == "no" and not include_nonlinear:
            diagnostics.lost("epub.spine", "nonlinear-spine", "Nonlinear spine item is skipped", item.name if item else idref)
            continue
        if item is None or item.media_type != "application/xhtml+xml" or "nav" in item.properties:
            diagnostics.lost(
                "epub.spine",
                "unsupported-spine-item",
                "Spine item has no content section",
                item.name if item else idref,
            )
            continue
        soup = BeautifulSoup(item.content, "html.parser")
        rules = _chapter_rules(book, item, soup, diagnostics)
        body = soup.body or soup
        diagnostics.chapter(body, item.name, _BLOCKS | {"table"})
        blocks = _chapter_blocks(body, rules, item.name, item_names, diagnostics, styles)
        sections.append(
            Section(
                blocks=blocks,
                properties={
                    "anchor_id": _anchor_id(item.name),
                    "epub": {
                        "id": idref,
                        "href": item.name,
                        "linear": str(linear),
                        "title": titles.get(posixpath.normpath(item.name))
                        or (blocks[0].plain_text if blocks and isinstance(blocks[0], Paragraph) and blocks[0].style_id else ""),
                    },
                },
                provenance=_provenance(source, item.name, root_directory=book.root_directory),
            )
        )
    metadata = {
        "title": book.metadata["title"],
        "language": book.metadata["language"],
        "identifier": book.metadata["identifier"],
        "engine": book.engine,
        "source_name": source.name,
        "epub": {
            "spine": [section.properties["epub"]["href"] for section in sections],
            "warnings": warnings,
            "include_nonlinear": include_nonlinear,
            "source_xml_resources": source_resources,
            "metadata_entries": list(book.metadata_entries),
            "package_properties": book.package_properties,
            "source_spine": [
                {"idref": idref, "linear": str(linear), "href": book.items[idref].name if idref in book.items else None}
                for idref, linear in book.spine
            ],
        },
    }
    document = DocumentModel(sections=sections, resources=resources, styles=styles, metadata=metadata, source_format="epub")
    diagnostics.attach(document)
    return document


def _chapter_blocks(
    root: Any,
    rules: Any,
    chapter: str,
    names: dict[str, str],
    diagnostics: Any,
    styles: dict[str, TextStyle],
    depth: int = 0,
    *,
    include_root: bool = False,
) -> list[od.Block]:
    if depth > 16:
        raise ValueError("EPUB table nesting exceeds profile limit")
    blocks = []
    candidates = _BLOCKS | {"table", "math", "img", "svg"}
    for tag in [root] if include_root else root.find_all(candidates):
        ancestors = []
        for parent in () if tag is root else tag.parents:
            if parent is root:
                break
            ancestors.append(parent.name)
        if any(name in candidates for name in ancestors):
            continue
        if tag.name == "table":
            caption = tag.find("caption", recursive=False)
            if caption is not None:
                blocks.append(_paragraph(caption, rules, chapter, names, diagnostics, styles))
            rows, count = [], 0
            for row in tag.find_all("tr"):
                if row.find_parent("table") is not tag:
                    continue
                cells = []
                for cell in row.find_all(["td", "th"], recursive=False):
                    count += 1
                    if count > 10_000:
                        raise ValueError("EPUB table cells exceed profile limit")
                    spans = []
                    for key in ("rowspan", "colspan"):
                        try:
                            span = int(cell.get(key, 1))
                            if not 1 <= span <= 100:
                                raise ValueError
                        except ValueError:
                            span = 1
                            diagnostics.lost("epub.table", "invalid-cell-span", f"Invalid {key} replaced by one", chapter, cell)
                        spans.append(span)
                    child_blocks = _cell_blocks(cell, rules, chapter, names, diagnostics, styles, depth + 1)
                    cells.append(od.TableCell(child_blocks, row_span=spans[0], column_span=spans[1]))
                rows.append(od.TableRow(cells))
            blocks.append(
                od.Table(
                    rows,
                    properties={"anchor_id": _anchor_id(chapter, tag["id"])} if tag.get("id") else {},
                    provenance=_provenance(diagnostics.source, chapter, tag.get("id"), diagnostics.root_directory),
                )
            )
        else:
            paragraph = _paragraph(tag, rules, chapter, names, diagnostics, styles)
            if paragraph.content or tag.name in {"p", "li"}:
                blocks.append(paragraph)
    return blocks


def _cell_blocks(
    cell: Any, rules: Any, chapter: str, names: dict[str, str], diagnostics: Any, styles: dict[str, TextStyle], depth: int
) -> list[od.Block]:
    blocks, pending = [], []
    structural = _BLOCKS | {"table"}

    def flush() -> None:
        if pending:
            paragraph = _paragraph(cell, rules, chapter, names, diagnostics, styles, nodes=list(pending))
            if paragraph.content:
                blocks.append(paragraph)
            pending.clear()

    def visit(node: Any, level: int = 0) -> None:
        if level > 64:
            raise ValueError("EPUB cell container nesting exceeds profile limit")
        if getattr(node, "name", None) in structural:
            flush()
            blocks.extend(_chapter_blocks(node, rules, chapter, names, diagnostics, styles, depth, include_root=True))
        elif getattr(node, "name", None) and node.find(structural):
            for child in node.children:
                visit(child, level + 1)
        else:
            pending.append(node)

    for child in cell.children:
        visit(child)
    flush()
    return blocks or [Paragraph()]


def _paragraph(
    tag: Any,
    rules: Any,
    chapter: str,
    names: dict[str, str],
    diagnostics: Any,
    styles: dict[str, TextStyle],
    *,
    nodes: Any = None,
) -> Paragraph:
    properties = {"epub": {"tag": tag.name}}
    if tag.get("id"):
        properties["anchor_id"] = _anchor_id(chapter, tag["id"])
    if tag.name == "li":
        properties["list_level"] = len(tag.find_parents(["ul", "ol"])) - 1
        parent = tag.find_parent(["ul", "ol"])
        properties["list_kind"] = "ordered" if parent and parent.name == "ol" else "unordered"
    heading = f"Heading{tag.name[1:]}" if tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"} else None
    if heading:
        styles.setdefault(heading, TextStyle(properties={"style_type": "paragraph"}))
    return Paragraph(
        _inline_content(tag, rules, chapter, names, diagnostics, nodes=nodes),
        style_id=heading,
        properties=properties,
        provenance=_provenance(diagnostics.source, chapter, tag.get("id"), diagnostics.root_directory),
    )


def _resources(book: Any, source: Path) -> tuple[dict[str, od.Resource], dict[str, str]]:
    resources, names = {}, {}
    for item in book.items.values():
        media_type = item.media_type or "application/octet-stream"
        if media_type.startswith("image/"):
            kind = ResourceKind.VECTOR_IMAGE if media_type == "image/svg+xml" else ResourceKind.RASTER_IMAGE
        elif media_type == "text/css":
            kind = ResourceKind.ATTACHMENT
        elif media_type.startswith(("font/", "audio/", "video/")) or media_type in {
            "application/vnd.ms-opentype",
            "application/font-sfnt",
            "application/font-woff",
        }:
            kind = ResourceKind.ATTACHMENT
        else:
            continue
        resource_id = f"epub-{item.id}"
        name = posixpath.normpath(item.name)
        if media_type.startswith("image/"):
            names[name] = resource_id
        resources[resource_id] = Resource(
            resource_id,
            kind,
            media_type,
            data=item.content,
            filename=posixpath.basename(name),
            properties={"epub": {"href": name, "item_id": item.id}},
            provenance=_provenance(source, name, item.id, book.root_directory),
        )
    return resources, names


def _chapter_rules(book: Any, item: Any, soup: Any, diagnostics: Any) -> list[tuple[str, dict[str, str], int]]:
    css = []
    for link in soup.find_all("link", href=True):
        if "stylesheet" not in [str(value).lower() for value in link.get("rel", [])]:
            continue
        href = link["href"]
        if urlsplit(href).scheme or urlsplit(href).netloc:
            diagnostics.lost("epub.css", "external-stylesheet", "External stylesheet is not loaded", item.name, link)
            continue
        name = _resolve(item.name, href)
        linked = next((entry for entry in book.items.values() if posixpath.normpath(entry.name) == name), None)
        if linked is not None and linked.media_type == "text/css":
            css.append((linked.content.decode("utf-8", errors="replace"), linked.name, f"epub-{linked.id}", None))
        else:
            diagnostics.lost(
                "epub.css", "missing-stylesheet", "Local stylesheet is missing or has another media type", item.name, link
            )
    css.extend((style.get_text(), item.name, None, style) for style in soup.find_all("style"))
    rules = []
    order = 0
    for text, part, resource_id, node in css:

        def warn(reason: str, message: str) -> None:
            if resource_id:
                diagnostics.opaque("epub.css", reason, message, part, resource_id)
            else:
                diagnostics.lost("epub.css", reason, message, part, node)

        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        for selector_text, declaration_text in _css_rules(text, warn):
            declarations = _declarations(declaration_text, warn)
            for selector in selector_text.split(","):
                selector = selector.strip()
                if selector and re.fullmatch(r"(?:[a-zA-Z][\w-]*)?(?:\.[\w-]+|#[\w-]+)?", selector):
                    rules.append((selector, declarations, order))
                    order += 1
                else:
                    warn("unsupported-selector", f"CSS selector is outside the profile: {selector[:160]}")
    return rules


def _css_rules(text: str, warn: Any) -> Iterator[tuple[str, str]]:
    start, opening, depth = 0, 0, 0
    quote, escaped = "", False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
        elif char == "{":
            if depth == 0:
                opening = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                selector, body = text[start:opening].strip(), text[opening + 1 : index]
                if selector.startswith("@") or "{" in body:
                    warn("complex-stylesheet", "At-rules or nested CSS are outside the profile")
                else:
                    yield selector, body
                start = index + 1
            elif depth < 0:
                warn("malformed-stylesheet", "Unmatched CSS closing brace")
                depth, start = 0, index + 1
        elif char == ";" and depth == 0:
            if text[start:index].strip():
                warn("complex-stylesheet", "Top-level CSS statement is outside the profile")
            start = index + 1
    if depth or quote or text[start:].strip():
        warn("malformed-stylesheet", "Incomplete or unparsed CSS source")


def _inline_content(
    root: Any,
    rules: list[tuple[str, dict[str, str], int]],
    chapter_name: str,
    item_names: dict[str, str],
    diagnostics: Any,
    *,
    nodes: Any = None,
) -> list[od.Inline]:
    from bs4 import Comment, NavigableString, Tag

    result = []

    def visit(node: Any, inherited: dict[str, str], link: str | None = None) -> None:
        if isinstance(node, Comment):
            return
        if isinstance(node, NavigableString):
            value = str(node)
            if value.strip() or value == " ":
                result.append(TextRun(value, _text_style(inherited), link=link))
            return
        if not isinstance(node, Tag):
            return
        if node.name in {"script", "style", "iframe", "object", "embed"}:
            return
        style = dict(inherited)
        for _, declarations, _ in sorted(_matching_rules(node, rules), key=lambda value: (value[0], value[2])):
            style.update(declarations)

        def css_warn(reason: str, message: str) -> None:
            diagnostics.lost("epub.css", reason, message, chapter_name, node)

        style.update(_declarations(node.get("style", ""), css_warn))
        _semantic_style(node.name, style)
        child_link = _resolve_link(chapter_name, node.get("href")) if node.name == "a" else link
        if node.name in {"math", "svg"}:
            from opendoc_formats.readers.html_resources import clean_xml

            def warn(feature: str, message: str) -> None:
                diagnostics.lost(
                    "epub.math" if node.name == "math" else "epub.inline-svg",
                    f"{node.name}-profile-sanitized",
                    message,
                    chapter_name,
                    node,
                )

            safe = clean_xml(str(node), node.name, warn)
            if safe and node.name == "svg":
                payload = safe.encode("utf-8")
                resource_id = "epub-inline-svg-" + hashlib.sha256(payload).hexdigest()
                base_id, suffix = resource_id, 0
                while resource_id in diagnostics.resources and (
                    diagnostics.resources[resource_id].data != payload
                    or diagnostics.resources[resource_id].kind is not ResourceKind.VECTOR_IMAGE
                    or diagnostics.resources[resource_id].media_type != "image/svg+xml"
                ):
                    suffix += 1
                    resource_id = f"{base_id}-{suffix}"
                diagnostics.resources.setdefault(
                    resource_id,
                    Resource(
                        resource_id,
                        ResourceKind.VECTOR_IMAGE,
                        "image/svg+xml",
                        data=payload,
                        filename="inline.svg",
                        provenance=_provenance(diagnostics.source, chapter_name, node.get("id"), diagnostics.root_directory),
                    ),
                )
                result.append(
                    Image(
                        resource_id,
                        alt_text=node.get("aria-label", ""),
                        provenance=_provenance(diagnostics.source, chapter_name, node.get("id"), diagnostics.root_directory),
                    )
                )
                diagnostics.opaque(
                    "epub.inline-svg",
                    "svg-resource",
                    "SVG retained as vector image; editable shapes are not modeled",
                    chapter_name,
                    resource_id,
                    node,
                )
            elif safe:
                import xml.etree.ElementTree as ET

                result.append(
                    od.Formula(
                        safe,
                        od.FormulaFormat.MATHML,
                        display=node.get("display") == "block",
                        fallback_text="".join(ET.fromstring(safe).itertext()),
                        provenance=_provenance(diagnostics.source, chapter_name, node.get("id"), diagnostics.root_directory),
                    )
                )
        elif node.name == "br":
            result.append(TextRun("\n", _text_style(style), link=child_link))
        elif node.name == "img":
            href = node.get("src", "")
            name = _resolve(chapter_name, href)
            split = urlsplit(href)
            resource_id = item_names.get(name) if not split.scheme and not split.netloc else None
            if resource_id:
                result.append(
                    Image(
                        resource_id,
                        alt_text=node.get("alt", ""),
                        provenance=_provenance(diagnostics.source, chapter_name, node.get("id"), diagnostics.root_directory),
                    )
                )
            else:
                diagnostics.lost("epub.image", "missing-image", f"missing image: {name}", chapter_name, node)
                if node.get("alt"):
                    result.append(TextRun(node["alt"], _text_style(style), link=child_link))
        else:
            for child in nodes if node is root and nodes is not None else node.children:
                visit(child, style, child_link)

    visit(root, {})
    return result


def _matching_rules(tag: Any, rules: list[tuple[str, dict[str, str], int]]) -> Iterator[tuple[int, dict[str, str], int]]:
    for selector, declarations, order in rules:
        element = selector.split(".", 1)[0].split("#", 1)[0]
        matches = not element or tag.name == element.lower()
        specificity = int(bool(element))
        if "#" in selector:
            matches &= tag.get("id") == selector.split("#", 1)[1]
            specificity += 100
        if "." in selector:
            matches &= selector.split(".", 1)[1] in tag.get("class", [])
            specificity += 10
        if matches:
            yield specificity, declarations, order


def _declarations(value: str, warn: Any = None) -> dict[str, str]:
    result = {}
    for name, content in _DECLARATION.findall(value):
        name, content = name.lower(), content.strip()
        reason = None
        if name not in _CSS_PROPERTIES:
            reason = "unsupported-declaration"
        elif "!" in content or re.search(r"(?:var|calc|url)\s*\(", content, re.I):
            reason = "unsupported-css-value"
        elif name == "font-size" and not _SIZE.fullmatch(content):
            reason = "invalid-font-size"
        if reason:
            if warn:
                warn(reason, f"CSS declaration is outside the profile: {name}: {content[:160]}")
            continue
        result[name] = content
    return result


def _semantic_style(name: str, style: dict[str, str]) -> None:
    if name in {"b", "strong", "th"}:
        style["font-weight"] = "bold"
    elif name in {"i", "em"}:
        style["font-style"] = "italic"
    elif name == "u":
        style["text-decoration"] = "underline"
    elif name == "sup":
        style["vertical-align"] = "super"
    elif name == "sub":
        style["vertical-align"] = "sub"


def _text_style(css: dict[str, str]) -> od.TextStyle:
    size = _css_size(css.get("font-size"))
    decoration = css.get("text-decoration", "")
    return TextStyle(
        font_family=css.get("font-family", "").split(",")[0].strip(" '\"") or None,
        font_size=Length(size) if size is not None else None,
        bold=css.get("font-weight") in {"bold", "600", "700", "800", "900"} or None,
        italic=css.get("font-style") in {"italic", "oblique"} or None,
        underline="underline" in decoration or None,
        superscript=css.get("vertical-align") == "super" or None,
        subscript=css.get("vertical-align") == "sub" or None,
        color=css.get("color"),
        background=css.get("background-color"),
    )


def _css_size(value: str | None) -> float | None:
    match = _SIZE.match(value or "")
    if not match:
        return None
    number, unit = float(match.group(1)), match.group(2)
    return number if unit == "pt" else number * 0.75 if unit == "px" else number * 12 if unit in {"em", "rem"} else number * 0.12


def _resolve(chapter: str, href: str | None) -> str:
    path = unquote(urlsplit(href).path)
    return posixpath.normpath(posixpath.join(posixpath.dirname(chapter), path))


def _resolve_link(chapter: str, href: str | None) -> str | None:
    if not href or urlsplit(href).scheme:
        return href
    split = urlsplit(href)
    resolved = _resolve(chapter, href) if split.path else posixpath.normpath(chapter)
    return "#" + _anchor_id(resolved, split.fragment)


def _anchor_id(chapter: str, fragment: str = "") -> str:
    value = posixpath.normpath(chapter) + ("--" + fragment if fragment else "")
    return "epub-" + re.sub(r"[^a-zA-Z0-9_.:-]+", "-", value).strip("-")


def _provenance(source: Path, part: str, object_id: str | None = None, root_directory: str = "") -> od.Provenance:
    part = posixpath.normpath(posixpath.join(root_directory, part))
    return Provenance("epub", str(source), object_id=object_id, package_part="/" + part.lstrip("/"))
