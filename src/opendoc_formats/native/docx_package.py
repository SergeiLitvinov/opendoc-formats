"""Private ZIP/XML implementation of immutable DOCX snapshots and patches."""

from __future__ import annotations

import copy
import hashlib
import io
import re
import stat
import zipfile
import zlib
from collections import defaultdict
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote

from opendoc_formats.docx import (
    BodyItem,
    CellSnapshot,
    DocxLimits,
    DocxPackageInfo,
    DocxPatch,
    InsertParagraph,
    InsertTableRow,
    PackagePartInfo,
    ParagraphSnapshot,
    PartRole,
    ReplaceTextSpan,
    RowSnapshot,
    RunSnapshot,
    RunStyle,
    SetParagraphText,
    SetTableRowText,
    TableSnapshot,
)
from opendoc_formats.errors import (
    DocumentClosedError,
    EncryptedDocumentError,
    InvalidDocumentError,
    PatchConflictError,
    ResourceLimitError,
    UnsupportedDocumentError,
)
from opendoc_formats.native.common import Cancellation, Source, backend, check_cancel, read_source

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
SPACE = "{http://www.w3.org/XML/1998/namespace}space"
OFFICE_DOCUMENT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
_ROLES: dict[str, PartRole] = {
    "document": "body",
    "hdr": "header",
    "ftr": "footer",
    "footnotes": "footnote",
    "endnotes": "endnote",
}
_PATCH_TYPES = (ReplaceTextSpan, SetParagraphText, InsertParagraph, InsertTableRow, SetTableRowText)


def parse_xml(data: bytes, engine: Any) -> Any:
    try:
        parser = engine.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False, recover=False)
        root = engine.fromstring(data, parser)
        if root.getroottree().docinfo.doctype or any(isinstance(item, engine._Entity) for item in root.iter()):
            raise UnsupportedDocumentError("DTD and entities are not accepted in document XML")
        return root
    except engine.XMLSyntaxError as error:
        raise InvalidDocumentError(f"Invalid document XML: {error}") from error


def _text_tokens(paragraph: Any) -> list[Any]:
    return [
        item
        for item in paragraph.iter()
        if item.tag in {W + "t", W + "tab", W + "br", W + "cr"} and next(item.iterancestors(W + "p"), None) is paragraph
    ]


def _token_text(token: Any) -> str:
    if token.tag == W + "t":
        return str(token.text or "")
    return "\t" if token.tag == W + "tab" else "\n"


def _text(paragraph: Any) -> str:
    return "".join(_token_text(item) for item in _text_tokens(paragraph))


def _all_text(node: Any) -> str:
    return "".join(_text(p) for p in node.iter(W + "p"))


def _val(node: Any, tag: str) -> str | None:
    child = node.find(W + tag) if node is not None else None
    return child.get(W + "val") if child is not None else None


def _on_off(node: Any, tag: str) -> bool | None:
    child = node.find(W + tag) if node is not None else None
    return None if child is None else child.get(W + "val", "1") not in {"0", "false", "off", "none"}


def _run_style(run: Any) -> RunStyle:
    props = run.find(W + "rPr") if run is not None else None
    fonts = props.find(W + "rFonts") if props is not None else None
    size = _val(props, "sz")
    try:
        font_size = float(size) / 2 if size is not None else None
    except ValueError:
        font_size = None
    return RunStyle(
        _on_off(props, "b"),
        _on_off(props, "i"),
        _on_off(props, "u"),
        fonts.get(W + "ascii") if fonts is not None else None,
        font_size,
        _val(props, "rStyle"),
    )


def _runs(paragraph: Any) -> tuple[RunSnapshot, ...]:
    groups: list[tuple[Any, list[str]]] = []
    for token in _text_tokens(paragraph):
        run = next(token.iterancestors(W + "r"), None)
        text = _token_text(token)
        if groups and groups[-1][0] is run:
            groups[-1][1].append(text)
        else:
            groups.append((run, [text]))
    result = []
    offset = 0
    for run, tokens in groups:
        text = "".join(tokens)
        result.append(RunSnapshot(offset, offset + len(text), text, _run_style(run)))
        offset += len(text)
    return tuple(result)


def _contains(node: Any, tags: set[str]) -> bool:
    return any(item.tag in tags for item in node.iter())


def _safe_rewrite(paragraph: Any) -> bool:
    for child in paragraph:
        if child.tag == W + "pPr":
            continue
        if child.tag != W + "r" or any(item.tag not in {W + v for v in ("rPr", "t", "tab", "br", "cr")} for item in child):
            return False
    return True


class NativePackage:
    def __init__(self, source: Source, limits: DocxLimits, allow_macros: bool, cancelled: Cancellation | None) -> None:
        self.limits = limits
        self.allow_macros = allow_macros
        self.cancelled = cancelled
        self.closed = False
        self._data = read_source(source, limits.max_input_bytes, cancelled)
        self._engine = backend("lxml.etree", "docx")
        self._roots: dict[str, Any] = {}
        self._entries: list[tuple[zipfile.ZipInfo, bytes]] = []
        self._comment = b""
        self._load()
        self._snapshot()
        check_cancel(cancelled)

    def check_open(self) -> None:
        if self.closed:
            raise DocumentClosedError("DOCX context is closed")
        check_cancel(self.cancelled)

    def close(self) -> None:
        self.closed = True
        self._roots.clear()
        self._entries.clear()
        self._data = b""
        self._paragraph_nodes.clear()
        self._row_nodes.clear()
        self.paragraphs = ()
        self.tables = ()
        self.body = ()

    def _load(self) -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(self._data)) as archive:
                infos = archive.infolist()
                if len(infos) > self.limits.max_entries:
                    raise ResourceLimitError("DOCX entry count exceeds limit")
                seen: set[str] = set()
                total = 0
                for info in infos:
                    check_cancel(self.cancelled)
                    name = info.filename
                    if (
                        name in seen
                        or not name
                        or "\\" in name
                        or name.startswith("/")
                        or ":" in name
                        or ".." in PurePosixPath(name).parts
                        or "\x00" in name
                        or stat.S_ISLNK(info.external_attr >> 16)
                    ):
                        raise InvalidDocumentError(f"Unsafe or duplicate package entry: {name!r}")
                    seen.add(name)
                    if info.flag_bits & 1:
                        raise EncryptedDocumentError("Encrypted DOCX ZIP is not accepted")
                    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                        raise UnsupportedDocumentError("DOCX requires stored or deflated ZIP entries")
                    total += info.file_size
                    if info.file_size > self.limits.max_part_bytes or total > self.limits.max_uncompressed_bytes:
                        raise ResourceLimitError("DOCX expanded parts exceed limits")
                    if info.file_size > max(1, info.compress_size) * self.limits.max_compression_ratio:
                        raise ResourceLimitError("DOCX compression ratio exceeds limit")
                self._comment = archive.comment
                for info in infos:
                    check_cancel(self.cancelled)
                    data = archive.read(info)
                    if len(data) != info.file_size:
                        raise InvalidDocumentError("DOCX ZIP size mismatch")
                    self._entries.append((copy.copy(info), data))
                    if info.filename.endswith((".xml", ".rels")):
                        self._roots[info.filename] = parse_xml(data, self._engine)
        except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, zlib.error, EOFError, UnicodeError) as error:
            raise InvalidDocumentError(f"Cannot read DOCX ZIP: {error}") from error
        self._check_package()

    def _check_package(self) -> None:
        content_types = self._roots.get("[Content_Types].xml")
        root_rels = self._roots.get("_rels/.rels")
        if (
            content_types is None
            or content_types.tag != CT + "Types"
            or root_rels is None
            or root_rels.tag != PR + "Relationships"
        ):
            raise InvalidDocumentError("Missing OPC content types or package relationships")
        main_rels = [item for item in root_rels if item.get("Type") == OFFICE_DOCUMENT]
        if len(main_rels) != 1 or main_rels[0].get("TargetMode") == "External":
            raise InvalidDocumentError("DOCX must have one internal main document relationship")
        target = main_rels[0].get("Target", "").lstrip("/")
        root = self._roots.get(target)
        if root is None or root.tag != W + "document" or root.find(W + "body") is None:
            raise InvalidDocumentError("Missing DOCX main document/body")
        self._main = target
        overrides = {
            item.get("PartName", "").lstrip("/"): item.get("ContentType", "")
            for item in content_types
            if item.tag == CT + "Override"
        }
        if overrides.get(target, "") not in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
            "application/vnd.ms-word.document.macroEnabled.main+xml",
            "application/vnd.ms-word.template.macroEnabledTemplate.main+xml",
        }:
            raise InvalidDocumentError("Main part does not declare a DOCX/DOTX content type")
        self._validate_relationships()
        content = " ".join(item.get("ContentType", "") for item in content_types)
        has_macros = "macroenabled" in content.lower() or any("vbaproject" in info.filename.lower() for info, _ in self._entries)
        has_signatures = "digital-signature" in content.lower() or any(
            info.filename.lower().startswith("_xmlsignatures/") for info, _ in self._entries
        )
        if has_macros and not self.allow_macros:
            raise UnsupportedDocumentError("Macros require allow_macros=True; they are never executed")
        self.info = DocxPackageInfo(
            hashlib.sha256(self._data).hexdigest(),
            tuple(
                PackagePartInfo(name, self._role(name), len(data), hashlib.sha256(data).hexdigest())
                for name, data in ((info.filename, value) for info, value in self._entries)
            ),
            has_macros,
            has_signatures,
        )

    def _validate_relationships(self) -> None:
        names = {info.filename for info, _ in self._entries}
        for name, root in self._roots.items():
            if not name.endswith(".rels"):
                continue
            if root.tag != PR + "Relationships":
                raise InvalidDocumentError("Invalid package relationships namespace")
            if name == "_rels/.rels":
                base = []
            else:
                parent = PurePosixPath(name).parent
                if parent.name != "_rels":
                    raise InvalidDocumentError("Invalid relationship part location")
                source = (parent.parent / PurePosixPath(name).name.removesuffix(".rels")).as_posix()
                if source not in names:
                    raise InvalidDocumentError("Relationships refer to a missing source part")
                base = list(PurePosixPath(source).parent.parts)
                if base == ["."]:
                    base = []
            seen = set()
            for relationship in root:
                if relationship.tag != PR + "Relationship":
                    continue
                key, kind, destination = (relationship.get(field) for field in ("Id", "Type", "Target"))
                if not key or not kind or not destination or key in seen:
                    raise InvalidDocumentError("Invalid or duplicate package relationship")
                seen.add(key)
                mode = relationship.get("TargetMode", "Internal")
                if mode == "External":
                    continue  # Preserve opaque metadata, never fetch or open external targets.
                if mode != "Internal":
                    raise InvalidDocumentError("Invalid relationship target mode")
                decoded = unquote(destination)
                if "\\" in decoded or ":" in decoded or "\x00" in decoded:
                    raise InvalidDocumentError("Unsafe internal relationship target")
                resolved = [] if decoded.startswith("/") else list(base)
                for piece in decoded.split("/"):
                    if piece in {"", "."}:
                        continue
                    if piece == "..":
                        if not resolved:
                            raise InvalidDocumentError("Relationship escapes the package")
                        resolved.pop()
                    else:
                        resolved.append(piece)
                if "/".join(resolved) not in names:
                    # Encoded OPC names may remain escaped in a producer's ZIP directory.
                    encoded = (PurePosixPath("/" + "/".join(base)) / destination).as_posix().lstrip("/")
                    if encoded not in names:
                        raise InvalidDocumentError("Internal relationship refers to a missing package part")

    def _role(self, name: str) -> PartRole:
        root = self._roots.get(name)
        if name == self._main:
            return "body"
        return _ROLES.get(root.tag.removeprefix(W), "other") if root is not None and isinstance(root.tag, str) else "other"

    def _snapshot(self) -> None:
        self._paragraph_nodes: dict[str, Any] = {}
        self._row_nodes: dict[str, Any] = {}
        table_ids: dict[Any, str] = {}
        cell_ids: dict[Any, str] = {}
        paragraph_ids: dict[Any, str] = {}
        field_paragraphs: set[Any] = set()
        table_nodes: list[tuple[str, int, Any]] = []
        for part, root in self._roots.items():
            field_depth = 0
            for node in root.iter():
                if node.tag == W + "p" and field_depth:
                    field_paragraphs.add(node)
                if node.tag == W + "fldChar":
                    paragraph = next(node.iterancestors(W + "p"), None)
                    if paragraph is not None:
                        field_paragraphs.add(paragraph)
                    field_kind = node.get(W + "fldCharType")
                    if field_kind == "begin":
                        field_depth += 1
                    elif field_kind == "end":
                        field_depth = max(0, field_depth - 1)
            for index, table in enumerate(root.iter(W + "tbl")):
                table_id = f"{part}:table:{index}"
                table_ids[table] = table_id
                table_nodes.append((part, index, table))
                for row_index, row in enumerate(table.findall(W + "tr")):
                    row_id = f"{table_id}:row:{row_index}"
                    self._row_nodes[row_id] = row
                    for cell_index, cell in enumerate(row.findall(W + "tc")):
                        cell_ids[cell] = f"{row_id}:cell:{cell_index}"
            for index, paragraph in enumerate(root.iter(W + "p")):
                if len(paragraph_ids) >= self.limits.max_paragraphs:
                    raise ResourceLimitError("DOCX paragraph count exceeds limit")
                key = f"{part}:{index}"
                paragraph_ids[paragraph] = key
                self._paragraph_nodes[key] = paragraph
        if len(paragraph_ids) > self.limits.max_paragraphs:
            raise ResourceLimitError("DOCX paragraph count exceeds limit")
        paragraphs = []
        total_chars = 0
        for node, key in paragraph_ids.items():
            check_cancel(self.cancelled)
            part, index_text = key.rsplit(":", 1)
            parent_cell = next(node.iterancestors(W + "tc"), None)
            parent_table = next(node.iterancestors(W + "tbl"), None)
            text = _text(node)
            total_chars += len(text)
            if total_chars > self.limits.max_text_chars:
                raise ResourceLimitError("DOCX snapshot text exceeds character limit")
            paragraphs.append(
                ParagraphSnapshot(
                    key,
                    part,
                    self._role(part),
                    int(index_text),
                    text,
                    _runs(node),
                    part == self._main and node.getparent().tag == W + "body",
                    table_ids.get(parent_table),
                    cell_ids.get(parent_cell),
                    _contains(node, {W + "drawing", W + "pict"}),
                    _contains(node, {W + "sectPr"}),
                    any(True for _ in node.iterdescendants(W + "p")),
                    node in field_paragraphs or _contains(node, {W + "fldSimple", W + "fldChar", W + "instrText"}),
                    _contains(node, {W + "ins", W + "del", W + "moveFrom", W + "moveTo"})
                    or any(p.tag in {W + "ins", W + "del", W + "moveFrom", W + "moveTo"} for p in node.iterancestors()),
                    _contains(
                        node, {W + "object", M + "oMath", M + "oMathPara", W + "footnoteReference", W + "endnoteReference"}
                    ),
                    _val(node.find(W + "pPr"), "pStyle"),
                )
            )
        self.paragraphs = tuple(paragraphs)
        tables = []
        for part, index, table in table_nodes:
            columns = len(table.findall("./" + W + "tblGrid/" + W + "gridCol"))
            rows = []
            for row_index, row in enumerate(table.findall(W + "tr")):
                row_id = f"{table_ids[table]}:row:{row_index}"
                cells = []
                for cell_index, cell in enumerate(row.findall(W + "tc")):
                    props = cell.find(W + "tcPr")
                    try:
                        span = int(_val(props, "gridSpan") or 1)
                    except ValueError as error:
                        raise InvalidDocumentError("Invalid DOCX table grid span") from error
                    if span < 1:
                        raise InvalidDocumentError("Invalid DOCX table grid span")
                    cells.append(
                        CellSnapshot(
                            cell_ids[cell],
                            cell_index,
                            _all_text(cell),
                            tuple(paragraph_ids[p] for p in cell.iter(W + "p")),
                            span,
                            _contains(cell, {W + "vMerge"}),
                            _contains(cell, {W + "hMerge"}),
                            any(True for _ in cell.iter(W + "tbl")),
                        )
                    )
                merged = any(c.grid_span > 1 or c.vertical_merge or c.horizontal_merge for c in cells)
                nested = any(c.has_nested_tables for c in cells)
                section = _contains(row, {W + "sectPr"})
                rows.append(
                    RowSnapshot(
                        row_id,
                        row_index,
                        tuple(cells),
                        _all_text(row),
                        tuple(paragraph_ids[p] for p in row.iter(W + "p")),
                        merged,
                        nested,
                        section,
                        columns > 0 and len(cells) == columns and not (merged or nested or section),
                    )
                )
            parent_cell = next(table.iterancestors(W + "tc"), None)
            tables.append(
                TableSnapshot(
                    table_ids[table],
                    part,
                    self._role(part),
                    index,
                    columns,
                    tuple(rows),
                    part == self._main and table.getparent().tag == W + "body",
                    cell_ids.get(parent_cell),
                )
            )
        self.tables = tuple(tables)
        body = self._roots[self._main].find(W + "body")
        self.body = tuple(
            BodyItem(
                index,
                "paragraph"
                if node.tag == W + "p"
                else "table"
                if node.tag == W + "tbl"
                else "section"
                if node.tag == W + "sectPr"
                else "other",
                paragraph_ids.get(node),
                table_ids.get(node),
                _text(node) if node.tag == W + "p" else _all_text(node),
            )
            for index, node in enumerate(body)
        )

    def _plan(self, patches: Sequence[DocxPatch]) -> tuple[dict[str, list[ReplaceTextSpan]], set[str]]:
        if len(patches) > self.limits.max_patches:
            raise ResourceLimitError("DOCX patch count exceeds limit")
        if self.info.has_signatures and patches:
            raise UnsupportedDocumentError("Editing digitally signed DOCX would invalidate signatures")
        spans: dict[str, list[ReplaceTextSpan]] = defaultdict(list)
        whole: set[str] = set()
        insertions: set[tuple[str, str]] = set()
        changed: set[str] = set()
        snapshots = {p.id: p for p in self.paragraphs}
        row_tables = {row.id: table for table in self.tables for row in table.rows}
        replacement_chars = 0
        for patch in patches:
            check_cancel(self.cancelled)
            if not isinstance(patch, _PATCH_TYPES):
                raise TypeError("Unknown DOCX patch type")
            if not isinstance(patch.text, str):
                raise TypeError("Patch text must be a string")
            _validate_text(patch.text)
            replacement_chars += len(patch.text)
            if replacement_chars > self.limits.max_text_chars:
                raise ResourceLimitError("DOCX replacement text exceeds character limit")
            if isinstance(patch, (ReplaceTextSpan, SetParagraphText)):
                key = patch.paragraph_id
                if key not in snapshots:
                    raise PatchConflictError(f"Unknown paragraph ID: {key}")
                snapshot = snapshots[key]
                if isinstance(patch, ReplaceTextSpan):
                    if any(isinstance(v, bool) or not isinstance(v, int) for v in (patch.start, patch.end)):
                        raise TypeError("Span offsets must be integers")
                    if not 0 <= patch.start <= patch.end <= len(snapshot.text):
                        raise PatchConflictError("Span is outside the original paragraph text")
                    if snapshot.has_nested_paragraphs or snapshot.has_fields or snapshot.has_revisions:
                        raise UnsupportedDocumentError("Text spans in nested/field/revision markup cannot safely be edited")
                    spans[key].append(patch)
                else:
                    if not isinstance(patch.append, bool):
                        raise TypeError("append must be bool")
                    if (
                        snapshot.has_nested_paragraphs
                        or snapshot.has_fields
                        or snapshot.has_revisions
                        or (not patch.append and not _safe_rewrite(self._paragraph_nodes[key]))
                    ):
                        raise UnsupportedDocumentError("Replacing complex paragraph content would lose native markup")
                    if key in whole:
                        raise PatchConflictError("Multiple whole-paragraph patches")
                    whole.add(key)
                changed.add(snapshot.part)
            elif isinstance(patch, InsertParagraph):
                snapshot = snapshots.get(patch.anchor_id)
                if snapshot is None or not snapshot.is_body:
                    raise PatchConflictError("InsertParagraph requires an original body paragraph")
                _position(patch.position)
                location = (patch.anchor_id, patch.position)
                if location in insertions:
                    raise PatchConflictError("Multiple insertions at the same anchor/position")
                insertions.add(location)
                changed.add(snapshot.part)
            else:
                key = patch.anchor_row_id if isinstance(patch, InsertTableRow) else patch.row_id
                if key not in self._row_nodes:
                    raise PatchConflictError(f"Unknown table row ID: {key}")
                table = row_tables[key]
                if table.grid_columns < 1:
                    raise UnsupportedDocumentError("Table has no usable column grid")
                if isinstance(patch, InsertTableRow):
                    _position(patch.position)
                    location = (key, patch.position)
                    if location in insertions:
                        raise PatchConflictError("Multiple row insertions at the same anchor/position")
                    insertions.add(location)
                else:
                    row = next(r for r in table.rows if r.id == key)
                    if len(row.cells) != 1 or len(row.paragraph_ids) != 1 or row.has_nested_tables or row.has_section_break:
                        raise UnsupportedDocumentError("SetTableRowText requires one plain paragraph in one spanning cell")
                    cell = row.cells[0]
                    if cell.vertical_merge or cell.horizontal_merge or cell.grid_span != table.grid_columns:
                        raise UnsupportedDocumentError("Row does not span the full table grid")
                    paragraph_key = row.paragraph_ids[0]
                    if snapshots[paragraph_key].has_fields or not _safe_rewrite(self._paragraph_nodes[paragraph_key]):
                        raise UnsupportedDocumentError("Table marker row contains complex native markup")
                    if paragraph_key in whole:
                        raise PatchConflictError("Conflicting whole-row/paragraph patches")
                    whole.add(paragraph_key)
                changed.add(table.part)
        if whole.intersection(spans):
            raise PatchConflictError("Span and whole-paragraph patches conflict")
        for group in spans.values():
            ordered = sorted(group, key=lambda p: (p.start, p.end))
            for left, right in zip(ordered, ordered[1:]):
                if (
                    left.end > right.start
                    or (left.start == left.end and left.end == right.start)
                    or (right.start == right.end and right.start == left.end)
                ):
                    raise PatchConflictError("Text patches overlap or have an ambiguous insertion boundary")
        return spans, changed

    def edit(self, patches: Sequence[DocxPatch]) -> tuple[bytes, tuple[str, ...]]:
        self.check_open()
        if not isinstance(patches, Sequence):
            raise TypeError("patches must be a finite sequence")
        if len(patches) > self.limits.max_patches:
            raise ResourceLimitError("DOCX patch count exceeds limit")
        patches = tuple(patches)
        spans, changed = self._plan(patches)
        if not patches:
            if len(self._data) > self.limits.max_output_bytes:
                raise ResourceLimitError("DOCX output exceeds limit")
            return self._data, ()
        roots = {name: copy.deepcopy(self._roots[name]) for name in changed}
        paragraphs: dict[str, Any] = {}
        rows: dict[str, Any] = {}
        for part, root in roots.items():
            for index, node in enumerate(root.iter(W + "p")):
                paragraphs[f"{part}:{index}"] = node
            for index, table in enumerate(root.iter(W + "tbl")):
                for row_index, row in enumerate(table.findall(W + "tr")):
                    rows[f"{part}:table:{index}:row:{row_index}"] = row
        for key, group in spans.items():
            for patch in sorted(group, key=lambda p: (p.start, p.end), reverse=True):
                check_cancel(self.cancelled)
                _replace_span(paragraphs[key], patch.start, patch.end, patch.text, self._engine)
        for patch in patches:
            check_cancel(self.cancelled)
            if isinstance(patch, SetParagraphText):
                _set_paragraph(paragraphs[patch.paragraph_id], patch.text, patch.append, self._engine)
            elif isinstance(patch, InsertParagraph):
                _insert(paragraphs[patch.anchor_id], _new_paragraph(patch.text, self._engine), patch.position)
            elif isinstance(patch, InsertTableRow):
                row = rows[patch.anchor_row_id]
                columns = len(row.getparent().findall("./" + W + "tblGrid/" + W + "gridCol"))
                new_row = self._engine.Element(W + "tr")
                cell = self._engine.SubElement(new_row, W + "tc")
                props = self._engine.SubElement(cell, W + "tcPr")
                self._engine.SubElement(props, W + "gridSpan").set(W + "val", str(columns))
                cell.append(_new_paragraph(patch.text, self._engine))
                _insert(row, new_row, patch.position)
            elif isinstance(patch, SetTableRowText):
                _set_paragraph(next(rows[patch.row_id].iter(W + "p")), patch.text, False, self._engine)
        updated = {
            name: self._engine.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            for name, root in roots.items()
        }
        for data in updated.values():
            if len(data) > self.limits.max_part_bytes:
                raise ResourceLimitError("Edited DOCX part exceeds limit")
            parse_xml(data, self._engine)
        buffer = io.BytesIO()
        actual_changes = []
        with zipfile.ZipFile(buffer, "w") as target:
            target.comment = self._comment
            for info, original in self._entries:
                check_cancel(self.cancelled)
                content = updated.get(info.filename, original)
                if content != original:
                    actual_changes.append(info.filename)
                target.writestr(copy.copy(info), content)
                if buffer.tell() > self.limits.max_output_bytes:
                    raise ResourceLimitError("DOCX output exceeds limit")
        data = buffer.getvalue()
        if len(data) > self.limits.max_output_bytes:
            raise ResourceLimitError("DOCX output exceeds limit")
        # Validate staged package, XML, ZIP CRC, macros policy and resulting snapshot limits before publication.
        staged = NativePackage.__new__(NativePackage)
        staged.limits = self.limits
        staged.allow_macros = self.allow_macros
        staged.cancelled = self.cancelled
        staged.closed = False
        staged._data = data
        staged._engine = self._engine
        staged._roots = {}
        staged._entries = []
        staged._comment = b""
        staged._load()
        staged._snapshot()
        staged.close()
        check_cancel(self.cancelled)
        return data, tuple(sorted(actual_changes))


def _position(position: str) -> None:
    if position not in {"before", "after"}:
        raise ValueError("position must be before or after")


def _validate_text(text: str) -> None:
    if any(
        not (char in "\t\n\r" or 0x20 <= ord(char) <= 0xD7FF or 0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF)
        for char in text
    ):
        raise ValueError("Patch contains characters invalid in XML 1.0")


def _text_children(text: str, engine: Any) -> list[Any]:
    nodes = []
    for item in re.split(r"([\n\t])", text.replace("\r\n", "\n").replace("\r", "\n")):
        if item in {"\n", "\t"}:
            node = engine.Element(W + ("br" if item == "\n" else "tab"))
        else:
            node = engine.Element(W + "t")
            node.set(SPACE, "preserve")
            node.text = item
        nodes.append(node)
    return nodes


def _first_style(paragraph: Any) -> Any:
    run = next((r for r in paragraph.iter(W + "r") if next(r.iterancestors(W + "p"), None) is paragraph), None)
    props = run.find(W + "rPr") if run is not None else None
    return copy.deepcopy(props) if props is not None else None


def _append_run(paragraph: Any, text: str, engine: Any, style: Any = None) -> None:
    run = engine.SubElement(paragraph, W + "r")
    if style is not None:
        run.append(style)
    run.extend(_text_children(text, engine))


def _set_paragraph(paragraph: Any, text: str, append: bool, engine: Any) -> None:
    style = _first_style(paragraph)
    if not append:
        for child in list(paragraph):
            if child.tag != W + "pPr":
                paragraph.remove(child)
    _append_run(paragraph, text, engine, style)


def _new_paragraph(text: str, engine: Any) -> Any:
    paragraph = engine.Element(W + "p")
    _append_run(paragraph, text, engine)
    return paragraph


def _insert(anchor: Any, node: Any, position: str) -> None:
    if position == "before":
        anchor.addprevious(node)
    else:
        anchor.addnext(node)


def _set_token(token: Any, text: str, engine: Any) -> None:
    parent = token.getparent()
    offset = parent.index(token)
    replacements = _text_children(text, engine)
    replacements[-1].tail = token.tail
    parent.remove(token)
    for index, item in enumerate(replacements):
        parent.insert(offset + index, item)


def _replace_span(paragraph: Any, start: int, end: int, text: str, engine: Any) -> None:
    tokens = _text_tokens(paragraph)
    if not tokens:
        if text:
            _append_run(paragraph, text, engine, _first_style(paragraph))
        return
    offset = 0
    inserted = False
    for index, token in enumerate(tokens):
        value = _token_text(token)
        right = offset + len(value)
        if start == end:
            if not inserted and (offset <= start < right or index == len(tokens) - 1 and start == right):
                local = start - offset
                _set_token(token, value[:local] + text + value[local:], engine)
                inserted = True
        elif right > start and offset < end:
            prefix = value[: max(0, start - offset)]
            suffix = value[max(0, end - offset) :]
            replacement = text if not inserted else ""
            _set_token(token, prefix + replacement + suffix, engine)
            inserted = True
        offset = right
