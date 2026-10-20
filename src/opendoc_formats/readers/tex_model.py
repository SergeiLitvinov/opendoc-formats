"""Finite source LaTeX parsing into OpenDoc, with inert original bytes and located losses."""

from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from opendoc_model import (
    Anchor,
    DiagnosticIssue,
    DocumentLimits,
    DocumentModel,
    Formula,
    FormulaFormat,
    Heading,
    IntegrationModel,
    IssueSeverity,
    ListItem,
    Paragraph,
    PreservationRecord,
    PreservationState,
    Provenance,
    Resource,
    ResourceKind,
    Section,
    TextRun,
    TextStyle,
    get_anchor,
    get_list_item,
    iter_list_numbers,
    set_anchor,
    set_heading,
    set_integration,
    set_list_item,
)

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError
from opendoc_formats.readers.tex_source import TexToken, load_tex_source
from opendoc_formats.tex_lists import paragraph_markers

_HEADINGS = {"section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4, "subparagraph": 5, "chapter": 1}
_STYLES = {"textbf": "bold", "textit": "italic", "emph": "italic", "underline": "underline", "texttt": "monospace"}
_ACCENTS = {
    "'": "\u0301",
    "`": "\u0300",
    '"': "\u0308",
    "^": "\u0302",
    "~": "\u0303",
    "c": "\u0327",
    "v": "\u030c",
    "H": "\u030b",
    "u": "\u0306",
    "=": "\u0304",
    ".": "\u0307",
}
_LITERALS = {
    "\n": " ",
    "\r": " ",
    "\r\n": " ",
    "%": "%",
    "$": "$",
    "&": "&",
    "#": "#",
    "_": "_",
    "{": "{",
    "}": "}",
    " ": " ",
    "textbackslash": "\\",
    "textasciitilde": "~",
    "textasciicircum": "^",
    "dots": "…",
    "ldots": "…",
    "LaTeX": "LaTeX",
    "TeX": "TeX",
    "ss": "ß",
    "ae": "æ",
    "AE": "Æ",
    "oe": "œ",
    "OE": "Œ",
}
_BLOCKED = {
    "input",
    "include",
    "includegraphics",
    "bibliography",
    "addbibresource",
    "write",
    "openin",
    "openout",
    "read",
    "usepackage",
    "catcode",
    "def",
    "edef",
    "gdef",
    "xdef",
    "csname",
    "directlua",
    "special",
}


@dataclass
class _ListFrame:
    kind: str
    identifier: str
    item: TexToken | None = None
    paragraphs: int = 0
    primary: Paragraph | None = None
    parent: str | None = None
    counter: int = 0
    item_number: int = 0
    start: int | None = None
    level: int = 0
    restart: int | None = None
    role: ListItem | None = None
    marker: dict | None = None
    par_before: bool = False


class _Parser:
    def __init__(self, path: Path, text: str, tokens: list[TexToken], cancelled: Callable[[], bool] | None,
                 limits: DocumentLimits | None) -> None:
        self.path, self.text, self.tokens, self.cancelled = path, text, tokens, cancelled
        self.index = 0
        self.blocks: list[Paragraph] = []
        self.current: list[TextRun | Formula] = []
        self.properties: dict = {}
        self.metadata: dict = {}
        self.records: list[PreservationRecord] = []
        self.labels: set[str] = set()
        self.lines = [0, *[match.end() for match in re.finditer("\n", text)]]
        self.list_stack: list[_ListFrame] = []
        self.body = not any(t.kind == "command" and t.value == "documentclass" for t in tokens)
        self.paragraph_start: TexToken | None = None
        self.paragraph_end = 0
        self.limits = limits
        self.markers = paragraph_markers(text, limits=limits)
        self.marker_index = 0
        self.current_marker: dict | None = None
        self.list_numbers: dict[str, int] = {}
        self.after_list: bool | None = None

    def adjacent_par(self, *, before: bool) -> bool:
        index, step = (self.index-2, -1) if before else (self.index, 1)
        spaces = []
        while 0 <= index < len(self.tokens) and self.tokens[index].kind == 'space':
            spaces.append(self.tokens[index].value)
            index += step
        return bool(re.search(r'\n[ \t\r]*\n', ''.join(spaces))
                    or 0 <= index < len(self.tokens) and self.tokens[index].kind == 'command'
                    and self.tokens[index].value == 'par')

    def take_marker(self, position: int) -> dict | None:
        found = []
        while self.marker_index < len(self.markers) and self.markers[self.marker_index][0] <= position:
            found.append(self.markers[self.marker_index][1])
            self.marker_index += 1
        if len(found) > 1:
            raise InvalidDocumentError('Multiple native paragraph identities before one paragraph')
        return found[0] if found else None

    def span(self, token: TexToken) -> dict:
        line = bisect.bisect_right(self.lines, token.start)
        return {
            "source": str(self.path),
            "start": token.start,
            "end": token.end,
            "line": line,
            "column": token.start - self.lines[line - 1] + 1,
            "unit": "unicode-character",
        }

    def provenance(self, token: TexToken) -> Provenance:
        span = self.span(token)
        return Provenance("latex", str(self.path), object_id=f"chars:{token.start}:{token.end}:line:{span['line']}")

    def warn(self, token: TexToken, reason: str, message: str) -> None:
        if len(self.records) >= 10_000:
            raise ResourceLimitError("LaTeX diagnostics exceed profile limit")
        span = self.span(token)
        self.records.append(
            PreservationRecord(
                issue=DiagnosticIssue(
                    "latex.source", IssueSeverity.LOSS, message, f"{self.path}:{span['line']}:{span['column']}", reason=reason
                ),
                state=PreservationState.OPAQUE,
                provenance=self.provenance(token),
                extra={"resource_id": "latex-original-source", "source_span": span},
            )
        )

    def skip_space(self) -> None:
        while self.index < len(self.tokens) and self.tokens[self.index].kind == "space":
            self.index += 1

    def group(self, opening: str = "{", closing: str = "}") -> tuple[str, TexToken]:
        self.skip_space()
        if self.index >= len(self.tokens) or self.tokens[self.index].value != opening:
            raise InvalidDocumentError(f"LaTeX command requires {opening} argument")
        first = self.tokens[self.index]
        self.index += 1
        depth = 1
        start = first.end
        while self.index < len(self.tokens):
            token = self.tokens[self.index]
            self.index += 1
            if token.kind == "symbol" and token.value == opening:
                depth += 1
                if depth > 64:
                    raise ResourceLimitError("LaTeX group exceeds depth limit")
            elif token.kind == "symbol" and token.value == closing:
                depth -= 1
                if not depth:
                    return self.text[start : token.start], TexToken("group", "", first.start, token.end)
        raise InvalidDocumentError("Unclosed LaTeX argument")

    def optional(self) -> None:
        self.skip_space()
        if self.index < len(self.tokens) and self.tokens[self.index].value == "[":
            self.group("[", "]")

    def append(
        self, value: str, token: TexToken, style: TextStyle, *, link: str | None = None, properties: dict | None = None
    ) -> None:
        if not self.body or not value:
            return
        if not self.current:
            self.current_marker = self.take_marker(token.start)
            if self.after_list is not None:
                self.properties['latex_par_after_list'] = self.after_list
                self.after_list = None
        self.paragraph_start = self.paragraph_start or token
        self.paragraph_end = token.end
        self.current.append(
            TextRun(
                value,
                replace(style),
                link=link,
                properties={"source_span": self.span(token), **(properties or {})},
                provenance=self.provenance(token),
            )
        )

    def flush(self) -> None:
        if self.current:
            if isinstance(self.current[0], TextRun):
                self.current[0].text = self.current[0].text.lstrip(" ")
            if isinstance(self.current[-1], TextRun):
                self.current[-1].text = self.current[-1].text.rstrip(" ")
            token = self.paragraph_start
            assert token is not None
            if self.list_stack:
                frame = self.list_stack[-1]
                self.properties.update(list_kind=frame.kind, list_level=len(self.list_stack) - 1, latex_list_id=frame.identifier)
                self.properties['latex_list_par_before'] = frame.par_before
                if frame.item is None:
                    self.warn(token, 'list-missing-item', 'List content before the first item has no item membership')
            token = TexToken("paragraph", "", token.start, self.paragraph_end)
            block = Paragraph(
                    self.current,
                    properties={**self.properties, "source_span": self.span(token)},
                    provenance=self.provenance(token),
                )
            self.bind_list(block, token, self.current_marker)
            self.blocks.append(block)
        self.current, self.properties, self.paragraph_start = [], {}, None
        self.current_marker = None

    def bind_list(self, block: Paragraph, token: TexToken, marker: dict | None) -> None:
        frame = self.list_stack[-1] if self.list_stack else None
        if frame and frame.item and frame.role:
            if frame.primary is None:
                marker = frame.marker or marker
                role = frame.role
            else:
                role = replace(frame.role, continuation_of=get_anchor(frame.primary, limits=self.limits).id, restart=None)
                if marker and 'list_id' in marker and any(marker[key] != getattr(role, key)
                                                        for key in ('list_id', 'level', 'start', 'restart')):
                    raise InvalidDocumentError('Continuation metadata contradicts its native item')
            anchor = Anchor((marker or {}).get('anchor') or f'tex-list-node-{token.start}')
            set_anchor(block, anchor, limits=self.limits)
            set_list_item(block, role, limits=self.limits)
            block.properties['latex_list_imported'] = True
            if frame.primary is None:
                frame.primary = block
                if frame.kind == 'number':
                    self.list_numbers[anchor.id] = frame.item_number
            frame.paragraphs += 1
        elif marker:
            if 'list_id' in marker:
                raise InvalidDocumentError('List metadata has no containing native item')
            if marker.get('anchor'):
                set_anchor(block, Anchor(marker['anchor']), limits=self.limits)

    def finish_list_item(self) -> None:
        frame = self.list_stack[-1]
        if frame.item is not None and not frame.paragraphs:
            block = Paragraph(properties={'source_span': self.span(frame.item), 'list_kind': frame.kind,
                              'list_level': len(self.list_stack)-1, 'latex_list_id': frame.identifier,
                              'latex_list_par_before': frame.par_before},
                              provenance=self.provenance(frame.item))
            self.bind_list(block, frame.item, None)
            self.blocks.append(block)

    def start_list_item(self, token: TexToken) -> None:
        self.finish_list_item()
        frame = self.list_stack[-1]
        frame.item, frame.primary, frame.paragraphs = token, None, 0
        frame.marker = self.take_marker(token.start)
        frame.counter += 1
        frame.item_number = frame.counter
        marker = frame.marker or {}
        level = marker.get('level', min(len(self.list_stack)-1, 8))
        first = frame.start is None
        start = marker.get('start', frame.start if frame.start is not None else frame.counter)
        identifier = marker.get('list_id', frame.identifier)
        if frame.start is not None and (frame.start != start or frame.identifier != identifier or frame.level != level):
            raise InvalidDocumentError('Native list changes its semantic group configuration')
        frame.start, frame.identifier, frame.level = start, identifier, level
        restart = marker.get('restart', None if first else frame.restart)
        frame.role = ListItem(identifier, level, 'ordered' if frame.kind == 'number' else 'unordered',
                              start if frame.kind == 'number' else 1,
                              restart if frame.kind == 'number' else None, parent_id=frame.parent)
        frame.restart = None

    def math(self, token: TexToken, closing: str, style: TextStyle, display: bool) -> None:
        start = token.end
        if token.value == "$" and display:
            start = self.tokens[self.index].end
            self.index += 1
        while self.index < len(self.tokens):
            last = self.tokens[self.index]
            self.index += 1
            if last.value == closing and ((closing == "$" and last.kind == "symbol") or last.kind == "command"):
                if closing == "$" and display:
                    if self.index >= len(self.tokens) or self.tokens[self.index].value != "$":
                        continue
                    self.index += 1
                if not self.body:
                    return
                if display:
                    self.flush()
                self.paragraph_start = self.paragraph_start or token
                raw = self.text[start : last.start]
                self.current.append(
                    Formula(
                        raw,
                        FormulaFormat.LATEX,
                        display=display,
                        fallback_text=raw,
                        properties={"source_span": self.span(TexToken("math", "", token.start, self.tokens[self.index - 1].end))},
                        provenance=self.provenance(TexToken("math", "", token.start, self.tokens[self.index - 1].end)),
                    )
                )
                self.paragraph_end = self.tokens[self.index - 1].end
                if display:
                    self.flush()
                return
        raise InvalidDocumentError("Unclosed LaTeX math delimiter")

    def walk(
        self, style: TextStyle | None = None, *, group: bool = False, environment: str | None = None, depth: int = 0
    ) -> None:
        if depth > 64:
            raise ResourceLimitError("LaTeX syntax exceeds depth limit")
        style = style or TextStyle()
        while self.index < len(self.tokens):
            if self.cancelled and self.cancelled():
                raise OperationCancelledError("LaTeX import cancelled")
            token = self.tokens[self.index]
            self.index += 1
            if token.kind == "space":
                if re.search(r"\n[ \t\r]*\n", token.value):
                    self.flush()
                elif self.current and not (isinstance(self.current[-1], TextRun) and self.current[-1].text.endswith(" ")):
                    self.append(" ", token, style)
            elif token.kind == "text":
                self.append(token.value, token, style)
            elif token.kind == "symbol":
                if token.value == "}":
                    if group:
                        return
                    raise InvalidDocumentError("Unexpected closing LaTeX group")
                if token.value == "{":
                    self.walk(style, group=True, depth=depth + 1)
                elif token.value == "$":
                    display = self.index < len(self.tokens) and self.tokens[self.index].value == "$"
                    self.math(token, "$", style, display)
                else:
                    self.append("\u00a0" if token.value == "~" else token.value, token, style)
                    if token.value in {"&", "#"}:
                        self.warn(token, "unsupported-symbol", "Alignment/parameter syntax is not modeled here")
            else:
                name = token.value
                if name == "end":
                    target, _ = self.group()
                    if target != environment:
                        raise InvalidDocumentError("Mismatched LaTeX environment")
                    self.flush()
                    if target in {'itemize', 'enumerate'}:
                        self.finish_list_item()
                        if self.list_stack[-1].item is None:
                            self.warn(token, 'list-empty-environment', 'List has no item')
                        self.after_list = self.adjacent_par(before=False)
                    if target == "document":
                        self.body = False
                    return
                if name == "begin":
                    par_before = self.adjacent_par(before=True)
                    target, _ = self.group()
                    self.flush()
                    if target == "document":
                        self.body = True
                    elif target in {"itemize", "enumerate"}:
                        parent = None
                        if self.list_stack:
                            self.finish_list_item()
                            primary = self.list_stack[-1].primary
                            if primary is None:
                                self.warn(token, 'list-missing-item', 'Nested list has no parent item')
                            else:
                                parent = get_anchor(primary, limits=self.limits).id
                        if len(self.list_stack) >= 6 or sum(frame.kind == (
                                'number' if target == 'enumerate' else 'bullet') for frame in self.list_stack) >= 4:
                            self.warn(token, 'list-depth', 'List exceeds the native TeX environment profile')
                        self.list_stack.append(_ListFrame("bullet" if target == "itemize" else "number",
                                                         f"list-{token.start}", parent=parent, par_before=par_before))
                        self.after_list = None
                    else:
                        self.warn(token, "unsupported-environment", f"Environment {target!r} has no semantic layout profile")
                    self.walk(style, environment=target, depth=depth + 1)
                    if target in {"itemize", "enumerate"}:
                        self.list_stack.pop()
                elif name in _STYLES:
                    self.skip_space()
                    if self.index >= len(self.tokens) or self.tokens[self.index].value != "{":
                        raise InvalidDocumentError("Styled LaTeX text requires a group")
                    self.index += 1
                    changed = (
                        replace(style, font_family="monospace") if name == "texttt" else replace(style, **{_STYLES[name]: True})
                    )
                    self.walk(changed, group=True, depth=depth + 1)
                elif name in {"bfseries", "itshape", "normalfont"}:
                    style = (
                        TextStyle()
                        if name == "normalfont"
                        else replace(style, **{"bold" if name == "bfseries" else "italic": True})
                    )
                elif name in {"(", "["}:
                    self.math(token, ")" if name == "(" else "]", style, name == "[")
                elif name in _HEADINGS:
                    self.flush()
                    self.skip_space()
                    starred = False
                    if self.index < len(self.tokens) and self.tokens[self.index].value == "*":
                        self.index += 1
                        starred = True
                    self.skip_space()
                    if self.index < len(self.tokens) and self.tokens[self.index].value == '[':
                        self.group('[', ']')
                        self.warn(token, 'heading-short-title', 'Heading short title has no semantic export profile')
                    self.skip_space()
                    if self.index >= len(self.tokens) or self.tokens[self.index].value != "{":
                        raise InvalidDocumentError("LaTeX heading requires a group")
                    self.index += 1
                    self.walk(style, group=True, depth=depth + 1)
                    self.properties["latex_heading_level"] = _HEADINGS[name]
                    self.properties.update(latex_heading_command=name, latex_heading_starred=starred, latex_heading_imported=True)
                    self.flush()
                elif name == "label":
                    value, _ = self.group()
                    if value in self.labels:
                        self.warn(token, "duplicate-label", "Duplicate LaTeX label")
                    self.labels.add(value)
                    if not self.current and self.blocks:
                        self.blocks[-1].properties["anchor_id"] = value
                    else:
                        self.properties["anchor_id"] = value
                elif name in {"ref", "pageref", "eqref", "cite"}:
                    self.optional()
                    value, span = self.group()
                    self.append(
                        value,
                        span,
                        style,
                        link="#" + value if name != "cite" else None,
                        properties={"latex_reference": name, "latex_target": value},
                    )
                    if name != "ref":
                        self.warn(token, "reference-fallback", "Reference rendering/bibliography is not resolved")
                elif name in {"title", "author", "date", "documentclass"}:
                    self.optional()
                    value, _ = self.group()
                    self.metadata[name] = value
                elif name == "newcommand" or name == "renewcommand":
                    self.group()
                    self.optional()
                    self.optional()
                    self.group()
                    self.warn(token, "unexpanded-macro", "User macros are retained in the source but not expanded")
                elif name in _BLOCKED:
                    self.optional()
                    self.skip_space()
                    if self.index < len(self.tokens) and self.tokens[self.index].value == "{":
                        self.group()
                    self.warn(token, "inactive-command", f"Command {name!r} is not executed or followed")
                elif name in _ACCENTS:
                    self.skip_space()
                    if self.index < len(self.tokens) and self.tokens[self.index].value == "{":
                        value, span = self.group()
                    elif self.index < len(self.tokens):
                        span = self.tokens[self.index]
                        value = span.value[0]
                        self.index += 1
                        if len(span.value) > 1:
                            self.tokens.insert(self.index, TexToken(span.kind, span.value[1:], span.start + 1, span.end))
                        span = TexToken(span.kind, value, span.start, span.start + 1)
                    else:
                        raise InvalidDocumentError("LaTeX accent requires text")
                    self.append(unicodedata.normalize("NFC", value + _ACCENTS[name]), span, style)
                elif name in _LITERALS:
                    self.append(_LITERALS[name], token, style)
                    if name.isalpha() and self.index < len(self.tokens) and self.tokens[self.index].kind == "space":
                        if not re.search(r"\n[ \t\r]*\n", self.tokens[self.index].value):
                            self.index += 1
                elif name == 'setcounter':
                    counter, _ = self.group()
                    value, _ = self.group()
                    depth = sum(frame.kind == 'number' for frame in self.list_stack)
                    expected = ('enumi', 'enumii', 'enumiii', 'enumiv')[depth-1] if 1 <= depth <= 4 else None
                    if (not self.list_stack or self.list_stack[-1].kind != 'number' or counter != expected
                            or not re.fullmatch(r'[0-9]{1,10}', value) or int(value) >= 2**31-1):
                        self.warn(token, 'list-counter', 'Counter command is outside the finite list profile')
                    else:
                        self.list_stack[-1].counter = int(value)
                        self.list_stack[-1].restart = int(value)+1
                elif name in {"par", "item"}:
                    self.flush()
                    if name == "item":
                        if self.list_stack:
                            self.start_list_item(token)
                        else:
                            self.warn(token, 'list-orphan-item', 'Item command has no containing supported list')
                        self.skip_space()
                        if self.index < len(self.tokens) and self.tokens[self.index].value == '[':
                            self.group('[', ']')
                            self.warn(token, 'list-item-label', 'Custom item label is retained only in the inert original source')
                elif name == "\\":
                    self.append("\n", token, style)
                elif name == "maketitle":
                    self.flush()
                    self.append(str(self.metadata.get("title", "")), token, style)
                    self.flush()
                else:
                    self.warn(token, "unknown-command", f"Command {name!r} has no semantic profile")
        if group or environment:
            raise InvalidDocumentError("Unclosed LaTeX group or environment")


def read_tex_model(
    path: str | Path, *, max_input_bytes: int = 10 * 1024 * 1024, cancelled: Callable[[], bool] | None = None,
    limits: DocumentLimits | None = None,
) -> DocumentModel:
    """Read the first finite LaTeX source profile without executing commands or reading includes."""
    source = Path(path)
    if type(max_input_bytes) is not int or max_input_bytes < 1:
        raise ValueError("max_input_bytes must be a positive integer")
    if cancelled is not None and not callable(cancelled):
        raise ValueError("cancelled must be callable")
    if cancelled and cancelled():
        raise OperationCancelledError("LaTeX import cancelled before reading")
    data, text, tokens = load_tex_source(source, max_input_bytes)
    parser = _Parser(source, text, tokens, cancelled, limits)
    parser.walk()
    parser.flush()
    if parser.marker_index != len(parser.markers):
        raise InvalidDocumentError('Unattached native paragraph metadata')
    for block in parser.blocks:
        for item in block.content:
            if isinstance(item, TextRun) and item.properties.get("latex_reference") == "ref":
                if item.properties["latex_target"] not in parser.labels:
                    span = item.properties["source_span"]
                    parser.warn(TexToken("ref", "", span["start"], span["end"]), "missing-reference", "Label target is missing")
    document = DocumentModel(
        sections=[Section(blocks=parser.blocks)],
        resources={
            "latex-original-source": Resource("latex-original-source", ResourceKind.ATTACHMENT, "application/x-tex", data=data)
        },
        metadata={**parser.metadata, "latex": {"profile": "source-v1", "encoding": "utf-8"}},
        source_format="latex",
    )
    for block in parser.blocks:
        if "latex_heading_level" in block.properties:
            key = f"Heading {block.properties['latex_heading_level']}"
            block.style_id = key
            document.styles[key] = TextStyle()
            set_heading(block, Heading(block.properties['latex_heading_level']), limits=limits)
    unsafe_lists = any((record.issue.reason or '').startswith('list-') for record in parser.records)
    if unsafe_lists:
        for block in parser.blocks:
            if get_list_item(block, limits=limits) is not None:
                set_list_item(block, None, limits=limits)
                block.properties['latex_list_imported'] = False
    else:
        for entry in iter_list_numbers(document, limits=limits):
            anchor = get_anchor(entry.location.node, limits=limits)
            if entry.number is not None and entry.number != parser.list_numbers[anchor.id]:
                raise InvalidDocumentError('Semantic list annotation contradicts native TeX counters')
    parser.warn(
        TexToken("source", "", 0, len(text)), "inert-original-source", "Original LaTeX bytes retained as an inert attachment"
    )
    set_integration(
        document,
        IntegrationModel(preservation=tuple(parser.records), assessed_features=("latex.source",), assessment_complete=False),
        limits=limits,
    )
    return document
