"""Rich EPUB spine importer with links, media, and a small deterministic CSS cascade."""

from __future__ import annotations

import hashlib
import posixpath
import re
from collections.abc import Callable, Iterator
from math import isfinite
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

from opendoc_formats.native.epub import FONT_OBFUSCATION_PROPERTY, IDPF_EMBEDDING, xor_idpf_font
from opendoc_formats.readers.css_selectors import SELECTOR, Selector, Specificity, matches_selector, parse_selector
from opendoc_formats.readers.epub_anchors import EpubAnchors
from opendoc_formats.readers.epub_xhtml import XhtmlTag, parse_chapter
from opendoc_formats.readers.html_fonts import FontFaces, simple_font_face
from opendoc_formats.readers.svg_color import parse_static_css_color
from opendoc_formats.support.cancellation import check_cancelled

_DECLARATION = re.compile(r"([\w-]+)\s*:\s*(.+)", re.S)
_CSS_TOKEN = re.compile(
    r"""/\*[\s\S]*?(?:\*/|\Z)|"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'"""
    r"""|\\[\s\S]|[{}();"'\\]|[^/"'\\{}();]+|/"""
)
_NUMBER = r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
_SIZE = re.compile(rf"^({_NUMBER})(pt|px|em|rem|%)$")
_CSS_PROPERTIES = {
    "font-family",
    "font-size",
    "font-weight",
    "font-style",
    "text-decoration",
    "vertical-align",
    "color",
    "background-color",
    "text-align",
    "white-space",
    "margin",
    "line-height",
}
_ALIGNMENTS = {"left", "right", "center", "justify"}
_WHITE_SPACE = {"normal", "pre", "pre-wrap"}
_PARAGRAPH_LENGTHS = {
    "margin-left": "left_indent_pt", "margin-right": "right_indent_pt", "text-indent": "first_line_indent_pt",
    "margin-top": "space_before_pt", "margin-bottom": "space_after_pt",
}
_CSS_PROPERTIES.update(_PARAGRAPH_LENGTHS)
_MARGIN_SIDES = ("margin-top", "margin-right", "margin-bottom", "margin-left")
_BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "figcaption"}
_INERT_CONTAINERS = {"iframe", "object", "embed"}
_IMPORTANT = re.compile(r"\s*!\s*important\s*$", re.I)
_Declarations = dict[str, tuple[str, bool]]
_Rule = tuple[Selector, Specificity, _Declarations, int]


def read_epub_model(path: str | Path, *, backend: str = "native", include_nonlinear: bool = False,
                    limits: od.DocumentLimits | None = None, cancelled: Callable[[], bool] | None = None) -> DocumentModel:
    from opendoc_formats.readers.epub_diagnostics import EpubDiagnostics
    from opendoc_formats.readers.epub_package import read_epub_package

    check_cancelled(cancelled, 'EPUB import')
    source = Path(path)
    if type(include_nonlinear) is not bool:
        raise ValueError("include_nonlinear must be boolean")
    if not source.is_file():
        raise FileNotFoundError(source)
    if backend != "native":
        raise ValueError("EPUB supports backend='native' only; install opendoc-formats[epub]")
    book = read_epub_package(source, cancelled=cancelled)
    resources, item_names = _resources(book, source, cancelled=cancelled)
    diagnostics = EpubDiagnostics(source, book.root_directory, resources,
                                  source_chapters={item.name: item.content for item in book.items.values()
                                                   if item.media_type == 'application/xhtml+xml'},
                                  limits=limits, cancelled=cancelled)
    source_resources = {}
    for index, (part, payload) in enumerate(book.source_parts.items(), 1):
        diagnostics.checkpoint()
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
    titles = book.titles
    sections, warnings, styles = [], [], {}
    recovered = False
    for idref, linear in book.spine:
        diagnostics.checkpoint()
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
        diagnostics.anchors.begin_chapter(item.name)
        soup = parse_chapter(item.content, cancelled=diagnostics.cancelled)
        recovered |= not isinstance(soup, XhtmlTag)
        diagnostics.checkpoint()
        if isinstance(soup, XhtmlTag) and soup.recovered:
            resource_id = diagnostics.retain_chapter(item.name)
            if resource_id is not None:
                diagnostics.opaque("epub.xhtml", "recovered-markup",
                                   "Chapter markup recovered; original XHTML bytes retained", item.name, resource_id)
        rules = _chapter_rules(book, item, soup, diagnostics)
        body = soup.body or soup
        diagnostics.chapter(body, item.name, _BLOCKS | {"table"})
        blocks = _chapter_blocks(body, rules, item.name, item_names, diagnostics, styles)
        sections.append(
            Section(
                blocks=blocks,
                properties={
                    "anchor_id": diagnostics.anchors.get(item.name),
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
        "engine": book.engine if recovered else "native-epub-xhtml",
        "source_name": source.name,
        "epub": {
            "spine": [section.properties["epub"]["href"] for section in sections],
            "warnings": warnings,
            "include_nonlinear": include_nonlinear,
            "source_xml_resources": source_resources,
            "metadata_entries": list(book.metadata_entries),
            "dc": {name: list(values) for name, values in book.dc_values.items()},
            "package_properties": book.package_properties,
            "source_spine": [
                {"idref": idref, "linear": str(linear), "href": book.items[idref].name if idref in book.items else None}
                for idref, linear in book.spine
            ],
        },
    }
    for item in book.items.values():
        diagnostics.checkpoint()
        resource = resources.get(f"epub-{item.id}")
        if resource is not None and resource.kind is ResourceKind.ATTACHMENT and item.media_type != "text/css":
            diagnostics.opaque("epub.asset", "inert-asset", "Original font/media bytes retained as an inert attachment",
                               item.name, resource.id)
    document = DocumentModel(sections=sections, resources=resources, styles=styles, metadata=metadata, source_format="epub")
    diagnostics.attach(document, limits=limits)
    diagnostics.checkpoint()
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
    maximum_depth = min(16, diagnostics.limits.max_depth)
    if depth > maximum_depth:
        raise od.ArtifactLimitError('EPUB table nesting exceeds profile limit at '+chapter,
                                    path=f'epub.tables[{chapter!r}]', quota='table depth', maximum=maximum_depth)
    blocks = []
    candidates = _BLOCKS | {"table", "math", "img", "svg"}
    for tag in [root] if include_root else root.find_all(candidates | _INERT_CONTAINERS):
        diagnostics.checkpoint()
        ancestors = []
        for parent in () if tag is root else tag.parents:
            if parent is root:
                break
            ancestors.append(parent.name)
        if any(name in candidates and not (tag.name == 'li' and name == 'li') for name in ancestors):
            continue
        if tag.name in _INERT_CONTAINERS:
            if tag.get("id"):
                blocks.append(Paragraph(
                    properties={"anchor_id": diagnostics.anchors.get(chapter, tag["id"])},
                    provenance=_provenance(diagnostics.source, chapter, tag["id"], diagnostics.root_directory),
                ))
        elif tag.name == "table":
            caption = tag.find("caption", recursive=False)
            if caption is not None:
                blocks.append(_paragraph(caption, rules, chapter, names, diagnostics, styles))
            rows, count = [], 0
            for row in tag.find_all("tr"):
                diagnostics.checkpoint()
                if row.find_parent("table") is not tag:
                    continue
                cells = []
                for cell in row.find_all(["td", "th"], recursive=False):
                    diagnostics.checkpoint()
                    count += 1
                    if count > 10_000:
                        raise od.ArtifactLimitError('EPUB table cells exceed profile limit at '+chapter,
                                                    path=f'epub.tables[{chapter!r}].cells[{count-1}]',
                                                    quota='cells per table', maximum=10_000)
                    diagnostics.claim_table_cell(chapter)
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
                    cell_properties = {"anchor_id": diagnostics.anchors.get(chapter, cell["id"])} if cell.get("id") else {}
                    cells.append(od.TableCell(child_blocks, row_span=spans[0], column_span=spans[1],
                                              properties=cell_properties))
                row_properties = {"anchor_id": diagnostics.anchors.get(chapter, row["id"])} if row.get("id") else {}
                rows.append(od.TableRow(cells, properties=row_properties))
            blocks.append(
                od.Table(
                    rows,
                    properties={"anchor_id": diagnostics.anchors.get(chapter, tag["id"])} if tag.get("id") else {},
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
        diagnostics.checkpoint()
        if level > 64:
            raise od.ArtifactLimitError('EPUB cell container nesting exceeds profile limit at '+chapter,
                                        path=f'epub.cell_containers[{chapter!r}]',
                                        quota='cell wrapper depth', maximum=64)
        if getattr(node, "name", None) in structural:
            flush()
            blocks.extend(_chapter_blocks(node, rules, chapter, names, diagnostics, styles, depth, include_root=True))
        elif getattr(node, "name", None) and node.find(structural):
            if node.name in _INERT_CONTAINERS and node.get("id"):
                flush()
                blocks.extend(_chapter_blocks(node, rules, chapter, names, diagnostics, styles, depth, include_root=True))
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
    if tag.get("id") and tag.name not in {'math', 'svg', 'img', 'td', 'th'}:
        properties["anchor_id"] = diagnostics.anchors.get(chapter, tag["id"])
    if tag.name == "li":
        properties['legacy_type'] = 'list_item'
        properties["list_level"] = len(tag.find_parents(["ul", "ol"])) - 1
        properties['level'] = properties['list_level']
        parent = tag.find_parent(["ul", "ol"])
        properties["list_kind"] = "ordered" if parent and parent.name == "ol" else "unordered"
    heading = f"Heading{tag.name[1:]}" if tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"} else None
    if heading:
        properties['legacy_type'] = 'heading'
        properties['level'] = int(tag.name[1:])
        styles.setdefault(heading, TextStyle(properties={"style_type": "paragraph"}))
    content, alignment, whitespace, spacing = _inline_content(tag, rules, chapter, names, diagnostics, properties, nodes=nodes)
    if whitespace is not None:
        properties["epub_white_space"] = whitespace
    paragraph = Paragraph(
        content,
        style_id=heading,
        alignment=alignment,
        properties=properties,
        provenance=_provenance(diagnostics.source, chapter, tag.get("id"), diagnostics.root_directory),
    )
    if spacing is not None:
        od.set_line_spacing(paragraph, spacing, limits=diagnostics.limits)
    return paragraph


def _resources(book: Any, source: Path, *, cancelled: Callable[[], bool] | None = None
                ) -> tuple[dict[str, od.Resource], dict[str, str]]:
    resources, names = {}, {}
    for item in book.items.values():
        check_cancelled(cancelled, 'EPUB resource')
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


def _chapter_rules(book: Any, item: Any, soup: Any, diagnostics: Any) -> list[_Rule]:
    def font_warn(feature: str, message: str, owner: tuple[str, Any]) -> None:
        part, node = owner
        diagnostics.lost("epub.font", "font-face-unbound", message, part, node)

    fonts = FontFaces(diagnostics.resources, font_warn, limits=diagnostics.limits, cancelled=diagnostics.cancelled)
    diagnostics.font_faces = fonts
    manifest = {}
    for entry in book.items.values():
        diagnostics.checkpoint()
        manifest.setdefault(posixpath.normpath(entry.name), entry)
    css = []
    for node in soup.find_all(("link", "style")):
        diagnostics.checkpoint()
        if node.name == "link":
            relations = {str(value).lower() for value in node.get("rel", [])}
            if not node.has_attr("href") or "stylesheet" not in relations:
                continue
            if "alternate" in relations:
                diagnostics.lost("epub.css", "alternate-stylesheet", "Alternate stylesheet is not active",
                                 item.name, node, attribute="rel")
                continue
        media = node.get("media", "").strip().lower()
        if media and (not re.fullmatch(r"[a-z-]+(?:\s*,\s*[a-z-]+)*", media)
                      or not {"screen", "all"}.intersection(value.strip() for value in media.split(","))):
            diagnostics.lost("epub.css", "unsupported-stylesheet-media",
                             "Stylesheet media is outside the static screen profile", item.name, node,
                             measurement={"media": media}, attribute="media")
            continue
        if node.name == "style":
            css.append((node.get_text(), item.name, None, node))
            continue
        href = node["href"]
        try:
            split = urlsplit(href)
            name = None if split.scheme or split.netloc else _resolve(item.name, href)
        except ValueError as error:
            _uri_loss(diagnostics, item.name, node, 'href', href, error, 'epub.css')
            continue
        if split.scheme or split.netloc:
            diagnostics.lost("epub.css", "external-stylesheet", "External stylesheet is not loaded", item.name, node)
            continue
        linked = manifest.get(name)
        if linked is not None and linked.media_type == "text/css":
            css.append((linked.content.decode("utf-8", errors="replace"), linked.name, f"epub-{linked.id}", None))
        else:
            diagnostics.lost(
                "epub.css", "missing-stylesheet", "Local stylesheet is missing or has another media type", item.name, node
            )
    rules = []
    order = 0
    for text, part, resource_id, node in css:
        diagnostics.checkpoint()

        def warn(reason: str, message: str) -> None:
            if resource_id:
                diagnostics.opaque("epub.css", reason, message, part, resource_id)
            else:
                diagnostics.lost("epub.css", reason, message, part, node)

        for selector_text, declaration_text in _css_rules(text, warn, cancelled=diagnostics.cancelled):
            diagnostics.checkpoint()
            if selector_text.lower() == '@font-face':
                face = simple_font_face(selector_text + '{' + declaration_text, allow_local=True)
                if face is None:
                    warn("unsupported-font-face", "Font face is outside the static local TTF/OTF profile")
                    continue
                uri = face[1]
                if uri.startswith('data:'):
                    fonts.read_simple(face, (part, node))
                else:
                    try:
                        entry = manifest.get(_resolve(part, uri)) if not uri.startswith('/') else None
                    except ValueError:
                        entry = None
                    resource = _local_font_resource(book, entry, diagnostics)
                    fonts.read_local(face, resource, (part, node))
                    if resource is not None and resource.kind is ResourceKind.FONT and entry.id in book.obfuscated_fonts:
                        diagnostics.resources[resource.id] = resource
                        diagnostics.decoded_fonts[entry.id] = resource.id
                continue
            declarations = _declarations(declaration_text, warn, cancelled=diagnostics.cancelled)
            for selector in selector_text.split(","):
                diagnostics.checkpoint()
                selector = selector.strip()
                parsed = parse_selector(selector, compound=SELECTOR)
                if parsed is not None:
                    normalized, specificity = parsed
                    rules.append((normalized, specificity, declarations, order))
                    order += 1
                else:
                    warn("unsupported-selector", f"CSS selector is outside the profile: {selector[:160]}")
    return rules


def _local_font_resource(book: Any, entry: Any, diagnostics: Any) -> Resource | None:
    if entry is None:
        return None
    resource = diagnostics.resources.get(f"epub-{entry.id}")
    if entry.id not in book.obfuscated_fonts:
        return resource
    key = book.obfuscated_fonts[entry.id]
    if key is None or resource is None or resource.data is None or resource.media_type not in {"font/ttf", "font/otf"}:
        return None
    if entry.id in diagnostics.decoded_fonts:
        return diagnostics.resources[diagnostics.decoded_fonts[entry.id]]
    identifier = f"epub-decoded-font-{entry.id}"
    while identifier in diagnostics.resources:
        diagnostics.checkpoint()
        identifier += "-decoded"
    return Resource(identifier, ResourceKind.ATTACHMENT, resource.media_type,
                    data=xor_idpf_font(resource.data, key), filename=resource.filename, provenance=resource.provenance,
                    properties={FONT_OBFUSCATION_PROPERTY: IDPF_EMBEDDING})


def _css_without_comments(text: str, cancelled: Callable[[], bool] | None) -> str:
    pieces = []
    for match in _CSS_TOKEN.finditer(text):
        check_cancelled(cancelled, 'EPUB CSS parsing')
        token = match[0]
        if token.startswith("/*"):
            # Keep boundaries so two CSS tokens do not become a different token.
            pieces.append(" ")
        else:
            pieces.append(token)
    return "".join(pieces)


def _css_rules(text: str, warn: Any, *, cancelled: Callable[[], bool] | None = None) -> Iterator[tuple[str, str]]:
    text = _css_without_comments(text, cancelled)
    start, opening, depth = 0, 0, 0
    parentheses, nested = 0, False
    quote, escaped = "", False
    for index, char in enumerate(text):
        if cancelled is not None and index % 1024 == 0:
            check_cancelled(cancelled, 'EPUB CSS parsing')
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
        elif char == "(":
            parentheses += 1
        elif char == ")" and parentheses:
            parentheses -= 1
        elif parentheses:
            continue
        elif char == "{":
            if depth == 0:
                opening = index
                nested = False
            else:
                nested = True
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                selector, body = text[start:opening].strip(), text[opening + 1 : index]
                if (selector.startswith("@") and selector.lower() != "@font-face") or nested:
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
    if depth or quote or parentheses or text[start:].strip():
        warn("malformed-stylesheet", "Incomplete or unparsed CSS source")


def _inline_content(
    root: Any,
    rules: list[_Rule],
    chapter_name: str,
    item_names: dict[str, str],
    diagnostics: Any,
    paragraph_properties: dict[str, Any],
    *,
    nodes: Any = None,
) -> tuple[list[od.Inline], str | None, str | None, od.LineSpacing | None]:
    result = []

    def styled(css: dict[str, str], node: Any) -> TextStyle:
        style = _text_style(css)
        diagnostics.font_faces.bind(style, (chapter_name, node))
        return style

    def append_media(node: Any, item: od.Inline) -> None:
        if node.get('id'):
            od.set_anchor(item, od.Anchor(diagnostics.anchors.get(chapter_name, node['id'])))
        result.append(item)

    def retain_media_anchor(node: Any) -> None:
        if node.get('id'):
            append_media(node, TextRun(''))

    def cascade_for(node: Any, warn: Any = None, *, ancestor: bool = False) -> _Declarations:
        cascade: _Declarations = {}
        inherited_names = {'font-size', 'text-align', 'white-space', 'text-indent', 'line-height'}
        relevant = (rule for rule in rules if not ancestor or rule[2].keys() & inherited_names)
        for _, declarations, _ in sorted(_matching_rules(node, relevant, cancelled=diagnostics.cancelled),
                                        key=lambda value: (value[0], value[2])):
            _apply_declarations(cascade, declarations)
        _apply_declarations(cascade, _declarations(node.get("style", ""), warn, cancelled=diagnostics.cancelled))
        return cascade

    initial_size = 12.0
    root_size = initial_size
    ancestor_size = None
    alignment = None
    whitespace = None
    indent = None
    spacing = None
    for ancestor in reversed(list(root.parents)):
        diagnostics.checkpoint()
        if ancestor.name == '[document]':
            continue
        cascade = cascade_for(ancestor, ancestor=True)
        if 'text-align' in cascade:
            alignment = cascade['text-align'][0]
        if 'white-space' in cascade:
            whitespace = cascade['white-space'][0]
        declared = cascade.get('font-size')
        if declared is not None:
            size = _css_size(declared[0], parent=ancestor_size if ancestor_size is not None else initial_size, root=root_size)
            if size is not None:
                ancestor_size = size
        if ancestor.name == 'html' and ancestor_size is not None:
            root_size = ancestor_size
        if 'text-indent' in cascade:
            size = ancestor_size if ancestor_size is not None else initial_size
            indent = _paragraph_length(cascade['text-indent'][0], font_size=size, root_size=root_size)
        if 'line-height' in cascade:
            size = ancestor_size if ancestor_size is not None else initial_size
            spacing = _line_height(cascade['line-height'][0], font_size=size, root_size=root_size)

    def visit(node: Any, inherited: dict[str, str], link: str | None = None) -> None:
        nonlocal alignment, whitespace, spacing
        diagnostics.checkpoint()
        if isinstance(node, str):
            if getattr(node, 'PREFIX', '') == '<!--':
                return
            value = str(node)
            mode = inherited.get("white-space")
            if value.strip() or value == " " or mode in {"pre", "pre-wrap"}:
                properties = {"epub_white_space": mode} if mode is not None and mode != whitespace else {}
                result.append(TextRun(value, styled(inherited, getattr(node, 'parent', None) or root),
                                      link=link, properties=properties))
            return
        if not getattr(node, 'name', None):
            return
        if node.name in {"script", "style"} | _INERT_CONTAINERS:
            if node.name in _INERT_CONTAINERS:
                retain_media_anchor(node)
            return
        if root.name == 'li' and node.name in {'ul', 'ol'}:
            # Nested items are separate block occurrences, not repeated parent text.
            return
        if node is not root and node.name not in {'math', 'svg', 'img'} and node.get('id'):
            # The root already belongs to its paragraph; inline targets need a
            # separate, zero-width owner, including empty source elements.
            marker = TextRun('')
            od.set_anchor(marker, od.Anchor(diagnostics.anchors.get(chapter_name, node['id'])))
            result.append(marker)
        style = dict(inherited)
        _semantic_style(node.name, style)
        if node.name == 'pre':
            style['white-space'] = 'pre'
        def css_warn(reason: str, message: str) -> None:
            diagnostics.lost("epub.css", reason, message, chapter_name, node)

        cascade = cascade_for(node, css_warn)
        if node is root and 'text-align' in cascade:
            alignment = cascade['text-align'][0]
        style.update({name: value for name, (value, _) in cascade.items() if name not in {'font-size', 'text-align'}})
        if node is root:
            whitespace = style.get('white-space')
        if (declared := cascade.get('font-size')) is not None:
            parent_size = _css_size(inherited.get('font-size'))
            size = _css_size(declared[0], parent=parent_size if parent_size is not None else initial_size, root=root_size)
            if size is None:
                css_warn('invalid-font-size', 'Computed font size is outside the supported range')
            else:
                style['font-size'] = f'{size}pt'
        if node is root:
            if indent is not None:
                paragraph_properties['first_line_indent_pt'] = indent
            size = _css_size(style.get('font-size'))
            if 'line-height' in cascade:
                spacing = _line_height(cascade['line-height'][0], font_size=size if size is not None else initial_size,
                                       root_size=root_size)
            for name, property_name in _PARAGRAPH_LENGTHS.items():
                if name not in cascade or (node.name not in _BLOCKS and name != 'text-indent'):
                    continue
                value = _paragraph_length(cascade[name][0], font_size=size if size is not None else initial_size,
                                          root_size=root_size)
                if value is not None:
                    paragraph_properties[property_name] = value
        child_link = link
        if node.name == 'a':
            try:
                child_link = _resolve_link(chapter_name, node.get('href'), anchors=diagnostics.anchors)
                if child_link and child_link.startswith('#'):
                    diagnostics.internal_link(child_link[1:], chapter_name, node)
            except od.ArtifactLimitError:
                raise
            except ValueError as error:
                child_link = None
                _uri_loss(diagnostics, chapter_name, node, 'href', node.get('href'), error, 'epub.hyperlink')
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

            safe = clean_xml(str(node), node.name, warn, cancelled=diagnostics.cancelled)
            if safe and node.name == "svg":
                from opendoc_formats.support.inline_svg import inline_svg_tree, remap_svg_paint, serialize_inline_svg

                inline = False
                try:
                    svg = inline_svg_tree(safe)
                except ValueError:
                    pass
                else:
                    identifiers = diagnostics.bind_embedded_anchors(svg, chapter_name)
                    if identifiers:
                        inline = True
                        remap_svg_paint(svg, identifiers)
                        safe = serialize_inline_svg(svg)
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
                append_media(node,
                    Image(
                        resource_id,
                        alt_text=node.get("aria-label", ""),
                        properties={"epub_inline_svg": True} if inline else {},
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

                math = ET.fromstring(safe)
                fallback = "".join(math.itertext())
                if diagnostics.bind_mathml_anchors(math, chapter_name):
                    safe = ET.tostring(math, encoding="unicode")
                append_media(node,
                    od.Formula(
                        safe,
                        od.FormulaFormat.MATHML,
                        display=node.get("display") == "block",
                        fallback_text=fallback,
                        provenance=_provenance(diagnostics.source, chapter_name, node.get("id"), diagnostics.root_directory),
                    )
                )
            else:
                retain_media_anchor(node)
        elif node.name == "br":
            result.append(TextRun("\n", styled(style, node), link=child_link))
        elif node.name == "img":
            href = node.get("src", "")
            try:
                split = urlsplit(href)
                name = href if split.scheme or split.netloc else _resolve(chapter_name, href)
            except ValueError as error:
                _uri_loss(diagnostics, chapter_name, node, 'src', href, error, 'epub.image')
                if node.get('alt'):
                    append_media(node, TextRun(node['alt'], styled(style, node), link=child_link))
                else:
                    retain_media_anchor(node)
                return
            resource_id = item_names.get(name) if not split.scheme and not split.netloc else None
            if resource_id:
                append_media(node,
                    Image(
                        resource_id,
                        alt_text=node.get("alt", ""),
                        provenance=_provenance(diagnostics.source, chapter_name, node.get("id"), diagnostics.root_directory),
                    )
                )
            else:
                diagnostics.lost("epub.image", "missing-image", f"missing image: {name}", chapter_name, node)
                if node.get("alt"):
                    append_media(node, TextRun(node["alt"], styled(style, node), link=child_link))
                else:
                    retain_media_anchor(node)
        else:
            for child in nodes if node is root and nodes is not None else node.children:
                visit(child, style, child_link)

    inherited = {'font-size': f'{ancestor_size}pt'} if ancestor_size is not None else {}
    if whitespace is not None:
        inherited['white-space'] = whitespace
    visit(root, inherited)
    return result, alignment, whitespace, spacing


def _matching_rules(tag: Any, rules: Iterator[_Rule], *, cancelled: Callable[[], bool] | None = None
                      ) -> Iterator[tuple[Specificity, _Declarations, int]]:
    for selector, specificity, declarations, order in rules:
        check_cancelled(cancelled, 'EPUB CSS selector')
        if matches_selector(tag, selector, cancelled):
            yield specificity, declarations, order


def _apply_declarations(target: _Declarations, source: _Declarations) -> None:
    for name, declaration in source.items():
        _set_declaration(target, name, declaration)


def _set_declaration(target: _Declarations, name: str, declaration: tuple[str, bool]) -> None:
    if declaration[1] or name not in target or not target[name][1]:
        target[name] = declaration


def _declarations(value: str, warn: Any = None, *, cancelled: Callable[[], bool] | None = None) -> _Declarations:
    result: _Declarations = {}
    value = _css_without_comments(value, cancelled)
    start, depth = 0, 0
    for token in _CSS_TOKEN.finditer(value + ";"):
        check_cancelled(cancelled, 'EPUB CSS declaration')
        if token[0] == "(":
            depth += 1
            continue
        elif token[0] == ")" and depth:
            depth -= 1
            continue
        elif token[0] == ";" and not depth:
            segment = value[start:token.start()].strip()
            start = token.end()
            if not segment:
                continue
            match = _DECLARATION.fullmatch(segment)
            if match is None:
                if warn:
                    warn("malformed-declaration", f"Invalid CSS declaration: {segment[:160]}")
                continue
            name, content = match.groups()
        else:
            continue
        name, content = name.lower(), content.strip()
        important = _IMPORTANT.search(content)
        if important:
            content = content[:important.start()].rstrip()
        reason = None
        margins = ()
        if name not in _CSS_PROPERTIES:
            reason = "unsupported-declaration"
        elif not content or "!" in content or re.search(r"(?:var|calc|url)\s*\(", content, re.I):
            reason = "unsupported-css-value"
        elif name in {"color", "background-color"} and "(" in content and parse_static_css_color(content) is None:
            reason = "unsupported-css-value"
        elif name == "font-size" and _css_size(content) is None:
            reason = "invalid-font-size"
        elif name == "text-align":
            content = content.lower()
            if content not in _ALIGNMENTS:
                reason = "unsupported-css-value"
        elif name == "white-space":
            content = content.lower()
            if content not in _WHITE_SPACE:
                reason = "unsupported-css-value"
        elif name in _PARAGRAPH_LENGTHS and _paragraph_length(content) is None:
            reason = "unsupported-css-value"
        elif name == "line-height":
            content = content.lower()
            if content != "normal" and _line_height(content) is None:
                reason = "unsupported-css-value"
        elif name == "margin":
            lengths = re.split(r"[ \t\r\n\f]+", content, maxsplit=4)
            if not 1 <= len(lengths) <= 4 or any(_paragraph_length(length) is None for length in lengths):
                reason = "unsupported-css-value"
            else:
                top = lengths[0]
                right = lengths[1] if len(lengths) >= 2 else top
                bottom = lengths[2] if len(lengths) >= 3 else top
                left = lengths[3] if len(lengths) == 4 else right
                margins = top, right, bottom, left
        if reason:
            if warn:
                warn(reason, f"CSS declaration is outside the profile: {name}: {content[:160]}")
            continue
        if margins:
            for side, length in zip(_MARGIN_SIDES, margins, strict=True):
                _set_declaration(result, side, (length, important is not None))
        else:
            _set_declaration(result, name, (content, important is not None))
    if start <= len(value) and value[start:].strip() and warn:
        warn("malformed-declaration", "Incomplete CSS declaration")
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
        color=_epub_color(css.get("color")),
        background=_epub_color(css.get("background-color")),
    )


def _epub_color(value: str | None) -> od.ColorValue | str | None:
    if value is not None:
        if "(" in value:
            return parse_static_css_color(value)
        if value.isalpha():
            return parse_static_css_color(value) or value
    return value


def _css_size(value: str | None, *, parent: float = 12.0, root: float = 12.0) -> float | None:
    match = _SIZE.match(value or "")
    if not match:
        return None
    number, unit = float(match.group(1)), match.group(2)
    scale = {"pt": 1.0, "px": 0.75, "em": parent, "rem": root, "%": parent / 100}
    size = number * scale[unit]
    return size if isfinite(size) else None


def _paragraph_length(value: str, *, font_size: float = 12.0, root_size: float = 12.0) -> float | None:
    if value in {"0", "+0", "-0"}:
        return 0.0
    if value.endswith("%"):
        return None
    unsigned = value[1:] if value.startswith(("+", "-")) else value
    magnitude = _css_size(unsigned, parent=font_size, root=root_size)
    return -magnitude if magnitude is not None and value.startswith("-") else magnitude


def _line_height(value: str, *, font_size: float = 12.0, root_size: float = 12.0) -> od.LineSpacing | None:
    if re.fullmatch(_NUMBER, value):
        factor = float(value)
        return od.LineSpacing("relative", factor) if isfinite(factor) and factor > 0 else None
    points = _css_size(value, parent=font_size, root=root_size)
    return od.LineSpacing("minimum", points) if points is not None and points > 0 else None


def _resolve(chapter: str, href: str | None) -> str:
    path = unquote(urlsplit(href).path, errors='strict')
    return posixpath.normpath(posixpath.join(posixpath.dirname(chapter), path))


def _resolve_link(chapter: str, href: str | None, *, anchors: EpubAnchors) -> str | None:
    if not href:
        return href
    split = urlsplit(href)
    if split.scheme or split.netloc:
        return href
    resolved = _resolve(chapter, href) if split.path else posixpath.normpath(chapter)
    return "#" + anchors.get(resolved, unquote(split.fragment, errors='strict'))


def _uri_loss(diagnostics: Any, chapter: str, node: Any, attribute: str, value: Any,
               error: ValueError, feature: str) -> None:
    diagnostics.lost(feature, 'unresolved-reference-uri', 'Source URI cannot be bound without a lossy repair',
                     chapter, node, measurement={'attribute': attribute, 'value': value, 'error': str(error)},
                     attribute=attribute)


def _provenance(source: Path, part: str, object_id: str | None = None, root_directory: str = "") -> od.Provenance:
    part = posixpath.normpath(posixpath.join(root_directory, part))
    return Provenance("epub", str(source), object_id=object_id, package_part="/" + part.lstrip("/"))
