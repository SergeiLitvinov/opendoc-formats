"""Strict XHTML tree and compatibility recovery for EPUB chapters."""

from __future__ import annotations

import re
from bisect import bisect_right
from codecs import BOM_UTF8, BOM_UTF16_BE, BOM_UTF16_LE, BOM_UTF32_BE, BOM_UTF32_LE, lookup
from collections.abc import Callable, Collection, Iterator
from copy import copy
from html.entities import html5
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Literal
from xml.etree import ElementTree as ET
from xml.parsers.expat import ExpatError

from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.readers.epub_package import _xml, _XmlTarget
from opendoc_formats.support.cancellation import check_cancelled

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

_XHTML = 'http://www.w3.org/1999/xhtml'
_VOID = frozenset(
    'area base basefont bgsound br col command embed frame hr image img input isindex keygen link '
    'menuitem meta nextid param source spacer track wbr'.split()
)
_FOREIGN = frozenset({'math', 'svg'})
_XML_ENTITY = re.compile(
    r'<!--.*?(?:-->|\Z)|<!\[CDATA\[.*?(?:\]\]>|\Z)|<\?.*?(?:\?>|\Z)|&([A-Za-z][A-Za-z0-9]*;)',
    re.S,
)
_PREDEFINED_XML = frozenset({'amp;', 'lt;', 'gt;', 'quot;', 'apos;'})
_XML_ENCODING_PATTERN = r"""^<\?xml\s+[^?]*?\bencoding\s*=\s*(['"])([A-Za-z][A-Za-z0-9._-]*)\1"""
_XML_ENCODING = re.compile(_XML_ENCODING_PATTERN, re.I)
_XML_ENCODING_BYTES = re.compile(_XML_ENCODING_PATTERN.encode('ascii'), re.I)
_LEGACY_ENCODING = re.compile(r'(?:cp125[0-8]|iso8859-(?:[1-9]|1[0-6]))')
_BOM_ENCODINGS = (
    (BOM_UTF32_BE, 'utf-32', 'utf-32-be'), (BOM_UTF32_LE, 'utf-32', 'utf-32-le'),
    (BOM_UTF16_BE, 'utf-16', 'utf-16-be'), (BOM_UTF16_LE, 'utf-16', 'utf-16-le'),
    (BOM_UTF8, 'utf-8-sig', 'utf-8'),
)


class XhtmlTag:
    recovered = False

    def __init__(self, element: ET.Element, cancelled: Callable[[], bool] | None,
                 positions: dict[ET.Element, tuple[int, int]], parent: XhtmlTag | None = None) -> None:
        check_cancelled(cancelled, 'EPUB XHTML tree')
        self.element = element
        self.cancelled = cancelled
        self.name = element.tag.rsplit('}', 1)[-1].lower()
        self.sourceline, self.sourcepos = positions[element]
        self.attrs = {key: value.split() if key in {'class', 'rel'} else value for key, value in element.attrib.items()}
        self.parent = parent
        self.position = len(parent.children) if parent is not None else 0
        self.children: list[XhtmlTag | str] = []
        if element.text:
            self.children.append(element.text)
        for child in element:
            self.children.append(XhtmlTag(child, cancelled, positions, self))
            if child.tail:
                self.children.append(child.tail)

    @property
    def body(self) -> XhtmlTag | None:
        return self.find('body', recursive=False)

    @property
    def parents(self) -> Iterator[XhtmlTag]:
        parent = self.parent
        while parent is not None:
            yield parent
            parent = parent.parent

    @property
    def previous_siblings(self) -> Iterator[XhtmlTag | str]:
        if self.parent is not None:
            for index in range(self.position - 1, -1, -1):
                yield self.parent.children[index]

    @property
    def next_siblings(self) -> Iterator[XhtmlTag | str]:
        if self.parent is not None:
            for index in range(self.position + 1, len(self.parent.children)):
                yield self.parent.children[index]

    def __getitem__(self, name: str) -> str | list[str]:
        return self.attrs[name]

    def get(self, name: str, default: str | list[str] | None = None) -> str | list[str] | None:
        return self.attrs.get(name, default)

    def has_attr(self, name: str) -> bool:
        return name in self.attrs

    def _tags(self, recursive: bool) -> Iterator[XhtmlTag]:
        for child in self.children:
            check_cancelled(self.cancelled, 'EPUB XHTML traversal')
            if isinstance(child, XhtmlTag):
                yield child
                if recursive:
                    yield from child._tags(True)

    def find_all(self, names: str | Collection[str] | Literal[True], *,
                 recursive: bool = True, href: bool = False) -> Iterator[XhtmlTag]:
        for node in self._tags(recursive):
            matches = names is True or (node.name == names if isinstance(names, str) else node.name in names)
            if matches and (not href or node.has_attr('href')):
                yield node

    def find(self, names: str | Collection[str], *, recursive: bool = True) -> XhtmlTag | None:
        return next(self.find_all(names, recursive=recursive), None)

    def find_parents(self, names: str | Collection[str]) -> list[XhtmlTag]:
        return [node for node in self.parents if (node.name == names if isinstance(names, str) else node.name in names)]

    def find_parent(self, names: str | Collection[str]) -> XhtmlTag | None:
        return next(iter(self.find_parents(names)), None)

    def get_text(self) -> str:
        parts = []
        for text in self.element.itertext():
            check_cancelled(self.cancelled, 'EPUB XHTML text')
            parts.append(text)
        return ''.join(parts)

    def __str__(self) -> str:
        element = copy(self.element)
        element.tail = None
        return ET.tostring(element, encoding='unicode')


def parse_xhtml(payload: bytes, *, cancelled: Callable[[], bool] | None = None) -> XhtmlTag:
    positions: dict[ET.Element, tuple[int, int]] = {}
    try:
        root = _xml(payload, cancelled=cancelled, positions=positions)
    except ExpatError as error:
        raise InvalidDocumentError('EPUB chapter requires well-formed XHTML') from error
    if root.tag not in ('html', f'{{{_XHTML}}}html'):
        raise InvalidDocumentError('EPUB chapter requires an XHTML html root')
    return XhtmlTag(root, cancelled, positions)


def _foreign_entities(source: str, cancelled: Callable[[], bool] | None) -> tuple[str, dict[int, list[tuple[int, int]]]]:
    """Replace HTML-only names with XML character references and track column shifts."""
    shifts: dict[int, list[tuple[int, int]]] = {}
    row, previous = 1, 0
    line_start = changes = 0

    def substitute(match: re.Match[str]) -> str:
        nonlocal row, previous, line_start, changes
        check_cancelled(cancelled, 'EPUB foreign character references')
        name = match[1]
        if name is None or name in _PREDEFINED_XML or name not in html5:
            return match[0]
        start, end = match.span()
        breaks = source.count('\n', previous, start)
        if breaks:
            row += breaks
            line_start = source.rindex('\n', previous, start) + 1
        previous = end
        replacement = ''.join(f'&#{ord(char)};' for char in html5[name])
        if len(replacement) != end - start:
            changes += 1
            if changes > 100_000:
                raise InvalidDocumentError('Too many position shifts for native EPUB character reference recovery')
            entries = shifts.setdefault(row, [])
            delta = entries[-1][1] if entries else 0
            delta += len(replacement) - (end - start)
            entries.append((end - line_start + delta, delta))
        return replacement

    return _XML_ENTITY.sub(substitute, source), shifts


class _ChapterRecovery(HTMLParser):
    """Recover simple HTML-shaped chapters with the same tree limits as XHTML."""

    def __init__(self, source: str, cancelled: Callable[[], bool] | None) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.cancelled = cancelled
        self.target = _XmlTarget(cancelled)
        self.stack: list[str] = []
        self.positions: dict[ET.Element, tuple[int, int]] = {}
        self.seen_root = False
        self.foreign: tuple[str, int, int, int] | None = None
        self.foreign_depth = 0
        self.line = 1
        self.line_start = 0

    def _source_offset(self, line: int, column: int) -> int:
        while self.line < line:
            if self.line % 1024 == 0:
                check_cancelled(self.cancelled, 'EPUB foreign markup position')
            self.line_start = self.source.index('\n', self.line_start) + 1
            self.line += 1
        return self.line_start + column

    def _insert_foreign(self, start: int, end: int, line: int, column: int) -> None:
        positions: dict[ET.Element, tuple[int, int]] = {}
        source, shifts = _foreign_entities(self.source[start:end], self.cancelled)
        try:
            root = _xml(source.encode('utf-8'), cancelled=self.cancelled, positions=positions)
        except ExpatError as error:
            raise InvalidDocumentError('Foreign markup requires a complete XML subtree') from error

        def insert(element: ET.Element) -> None:
            row, offset = positions[element]
            if entries := shifts.get(row):
                index = bisect_right(entries, offset, key=lambda entry: entry[0])
                if index:
                    offset -= entries[index - 1][1]
            node = self.target.start(element.tag, element.attrib)
            self.positions[node] = (line + row - 1, column + offset if row == 1 else offset)
            if element.text:
                self.target.data(element.text)
            for child in element:
                insert(child)
                if child.tail:
                    self.target.data(child.tail)
            self.target.end(element.tag)

        insert(root)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.foreign is not None:
            if tag == self.foreign[0]:
                self.foreign_depth += 1
            return
        if tag in _FOREIGN and self.stack:
            line, column = self.getpos()
            self.foreign = tag, self._source_offset(line, column), line, column
            self.foreign_depth = 1
            return
        attributes = {name: value or '' for name, value in attrs}
        if (':' in tag
                or any(':' in name for name in attributes)
                or attributes.get('xmlns', _XHTML) != _XHTML):
            raise InvalidDocumentError('Namespaced markup requires XML or compatibility recovery')
        if not self.stack:
            if self.seen_root or tag != 'html':
                raise InvalidDocumentError('Recovery requires one html root')
            self.seen_root = True
        node = self.target.start(tag, attributes)
        self.positions[node] = self.getpos()
        if tag in _VOID:
            self.target.end(tag)
        else:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.foreign is not None:
            return
        if tag in _FOREIGN and self.stack:
            line, column = self.getpos()
            start = self._source_offset(line, column)
            self._insert_foreign(start, start + len(self.get_starttag_text()), line, column)
            return
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.target.end(self.stack.pop())

    def handle_endtag(self, tag: str) -> None:
        if self.foreign is not None:
            name, start, line, column = self.foreign
            if name == tag:
                self.foreign_depth -= 1
                if not self.foreign_depth:
                    close = self._source_offset(*self.getpos())
                    self._insert_foreign(start, self.source.index('>', close) + 1, line, column)
                    self.foreign = None
            return
        if tag not in self.stack:
            return
        while self.stack:
            current = self.stack.pop()
            self.target.end(current)
            if current == tag:
                break

    def handle_data(self, data: str) -> None:
        if self.foreign is not None:
            return
        if not self.stack and data.strip():
            raise InvalidDocumentError('Recovery found text outside the html root')
        self.target.data(data)

    def unknown_decl(self, data: str) -> None:
        if self.foreign is None:
            raise InvalidDocumentError('Recovery encountered an unsupported declaration')


def _decode_recovery_source(payload: bytes) -> str:
    for bom, codec, endian in _BOM_ENCODINGS:
        if payload.startswith(bom):
            source = payload.decode(codec)
            declaration = _XML_ENCODING.match(source)
            if declaration and lookup(declaration[2]).name not in {codec, endian}:
                raise InvalidDocumentError('EPUB chapter encoding declaration conflicts with its BOM')
            return source
    declaration_bytes = _XML_ENCODING_BYTES.match(payload)
    codec = lookup(declaration_bytes[2].decode('ascii')).name if declaration_bytes else 'utf-8'
    if codec not in {'utf-8', 'ascii'} and not _LEGACY_ENCODING.fullmatch(codec):
        raise InvalidDocumentError('EPUB chapter encoding is outside the native recovery profile')
    return payload.decode(codec)


def _recover_chapter(payload: bytes, cancelled: Callable[[], bool] | None) -> XhtmlTag:
    check_cancelled(cancelled, 'EPUB XHTML recovery decode')
    source = _decode_recovery_source(payload).replace('\r\n', '\n').replace('\r', '\n')
    if '\x00' in source:
        raise InvalidDocumentError('EPUB chapter contains a NUL character')
    parser = _ChapterRecovery(source, cancelled)
    for offset in range(0, len(source), 64 * 1024):
        check_cancelled(cancelled, 'EPUB XHTML recovery feed')
        parser.feed(source[offset:offset + 64 * 1024])
    check_cancelled(cancelled, 'EPUB XHTML recovery close')
    parser.close()
    if not parser.seen_root or parser.foreign is not None or (parser.stack and parser.stack[-1] in {'script', 'style'}):
        raise InvalidDocumentError('Recovery requires an html root and closed script/style elements')
    while parser.stack:
        parser.target.end(parser.stack.pop())
    root = XhtmlTag(parser.target.close(), cancelled, parser.positions)
    root.recovered = True
    return root


def parse_chapter(payload: bytes, *, cancelled: Callable[[], bool] | None = None) -> XhtmlTag | BeautifulSoup:
    """Parse XHTML natively and retain optional recovery for malformed markup."""
    try:
        return parse_xhtml(payload, cancelled=cancelled)
    except InvalidDocumentError as error:
        try:
            return _recover_chapter(payload, cancelled)
        except (AssertionError, InvalidDocumentError, LookupError, UnicodeDecodeError):
            pass
        try:
            import bs4
        except ModuleNotFoundError as missing:
            if missing.name != 'bs4':
                raise
            raise error from missing
        check_cancelled(cancelled, 'EPUB XHTML recovery')
        return bs4.BeautifulSoup(payload, "html.parser")
