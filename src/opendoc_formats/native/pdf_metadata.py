"""Bounded fallback for xref-addressed PDF metadata and page trees."""

from __future__ import annotations

import re
from bisect import bisect_left
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from opendoc_formats.errors import EncryptedDocumentError, InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.common import Source, read_source
from opendoc_formats.native.pdf_object_streams import inspect_object_streams
from opendoc_formats.native.pdf_revisions import inspect_pdf_source
from opendoc_formats.native.pdf_stream_decode import decode
from opendoc_formats.native.pdf_syntax import SPACE, Name, Parser, Reference, SyntaxBudget, finish_stream
from opendoc_formats.support.cancellation import cancellation_scope, checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import AnatomyLimits, BinaryItem

_ESCAPE = re.compile(rb'\\(?:\r\n|[0-7]{1,3}|[\s\S])|\r\n?')
_ESCAPED_BYTES = {b'n': b'\n', b'r': b'\r', b't': b'\t', b'b': b'\b', b'f': b'\f'}
# ISO 32000-1 Annex D.3. Keep the existing literal-string control escapes.
_PDFDOC_TRANSLATION = {
    **dict.fromkeys(set(range(0x18)) - {8, 9, 10, 12, 13}, '\ufffd'),
    **dict(enumerate('˘ˇˆ˙˝˛˚˜', 0x18)),
    **dict(enumerate('•†‡…—–ƒ⁄‹›−‰„“”‘’‚™ﬁﬂŁŒŠŸŽıłœšž', 0x80)),
    0x7F: '\ufffd', 0x9F: '\ufffd', 0xA0: '€', 0xAD: '\ufffd',
}


def _unescape(match: re.Match[bytes]) -> bytes:
    checkpoint()
    raw = match[0]
    if raw.startswith(b'\r'):
        return b'\n'
    escaped = raw[1:]
    if escaped in {b'\r', b'\n', b'\r\n'}:
        return b''
    if b'0' <= escaped[:1] <= b'7':
        return bytes([int(escaped, 8) & 255])
    return _ESCAPED_BYTES.get(escaped, escaped)


def _text(raw: bytes) -> str:
    if raw.startswith(b'('):
        payload = _ESCAPE.sub(_unescape, raw[1:-1])
    else:
        digits = raw[1:-1].translate(None, SPACE)
        payload = bytes.fromhex((digits+b'0'*(len(digits) % 2)).decode('ascii'))
    try:
        if payload.startswith(b'\xfe\xff'):
            return payload[2:].decode('utf-16-be')
        if payload.startswith(b'\xef\xbb\xbf'):
            return payload[3:].decode('utf-8')
        return payload.decode('latin-1').translate(_PDFDOC_TRANSLATION)
    except UnicodeDecodeError:
        pass
    return ''


def _object_parser(data: bytes, offset: int, reference: Reference, window: int, budget: SyntaxBudget) -> Parser:
    if not 0 <= offset < len(data):
        raise InvalidDocumentError('PDF metadata object offset outside source')
    parser = Parser(data, offset, window, budget)
    first = parser.take('integer')
    if (first.start != offset or first.value != reference.object or parser.take('integer').value != reference.generation
            or parser.take().value != b'obj'):
        raise InvalidDocumentError('PDF metadata object header does not match xref')
    return parser


def _open_source(source: Source) -> tuple[
    bytes, AnatomyLimits, SyntaxBudget, tuple[BinaryItem, ...], dict[int, dict[str, Any]], dict[str, Any]
]:
    from opendoc_formats.anatomy import AnatomyLimits

    limits = AnatomyLimits()
    data = read_source(source, limits.max_input_bytes, None)
    budget = SyntaxBudget(limits.max_pdf_tokens, limits.max_pdf_depth)
    xrefs, report = inspect_pdf_source(data, limits, False, decode_streams=True, resolve_records=True, budget=budget)
    sections = {details['offset']: details for details in (dict(item.details) for item in xrefs)}
    if any(section['encrypted_declared'] for section in sections.values()):
        raise EncryptedDocumentError('Encrypted PDF requires a backend')
    return data, limits, budget, xrefs, sections, report


def _trailer_value(key: str, data: bytes, sections: dict[int, dict[str, Any]], report: dict[str, Any],
                   limits: AnatomyLimits, budget: SyntaxBudget) -> Any:
    for xref in report['xref_search_order']:
        if xref['role'] != 'primary':
            continue
        section = sections[xref['xref_offset']]
        parser = Parser(data, section['dictionary_start'], limits.max_part_bytes, budget,
                        stop=section['dictionary_end'])
        trailer = parser.value()
        if key in trailer:
            return trailer[key]
    return None


def _compressed_inventory(data: bytes, limits: AnatomyLimits, budget: SyntaxBudget, xrefs: tuple[BinaryItem, ...],
                          sections: dict[int, dict[str, Any]], report: dict[str, Any], *,
                          info_member: tuple[int, int, int] | None = None,
                          page_members: dict[str, Any] | None = None
                          ) -> tuple[tuple[BinaryItem, ...], dict[str, int]]:
    remaining_items = limits.max_items-len(xrefs)-len(report['effective_xref_entries'])-sum(
        len(section['entries']) for section in sections.values())
    remaining_bytes = limits.max_total_bytes-sum(item.size for item in xrefs)-report['xref_decode_work_bytes']
    items, links = inspect_object_streams(data, list(sections.values()), limits, False, budget,
                                          remaining_items, remaining_bytes, info_member=info_member,
                                          capture_scalar_members=page_members is None, page_members=page_members)
    selected = {row['member_locator']: row['object'] for row in links['compressed_object_current_links']
                if row['status'] == 'matched-declared-member'}
    return items, selected


def read_page_count(source: Source) -> int:
    """Count leaves of the selected page tree without reading page content."""
    data, limits, budget, xrefs, sections, report = _open_source(source)
    entries = {entry['object']: entry for entry in report['effective_xref_entries']}
    seen: set[Reference] = set()
    spans: list[tuple[int, int]] = []
    xref_starts: list[int] = []
    xref_ends = [0]
    compressed_nodes: dict[int, Any] | None = None
    loaded: dict[Reference, Any] = {}
    for start, end in sorted((section['offset'], section['end']) for section in sections.values()):
        xref_starts.append(start)
        xref_ends.append(max(xref_ends[-1], end))

    def load(reference: Reference) -> Any:
        nonlocal compressed_nodes
        checkpoint()
        if reference in loaded:
            return loaded[reference]
        target = entries.get(reference.object)
        if target is None or target['generation'] != reference.generation or target['state'] == 'free':
            raise InvalidDocumentError('PDF page-tree object missing from effective xref')
        if target['state'] == 'compressed':
            if compressed_nodes is None:
                page_members: dict[str, Any] = {}
                _, selected = _compressed_inventory(data, limits, budget, xrefs, sections, report,
                                                     page_members=page_members)
                compressed_nodes = {selected[locator]: value for locator, value in page_members.items()
                                    if locator in selected}
            value = compressed_nodes.get(reference.object)
            if value is None:
                raise InvalidDocumentError('Compressed PDF page-tree object does not match its xref record')
        elif target['state'] == 'uncompressed':
            offset = target['offset']
            parser = _object_parser(data, offset, reference, limits.max_part_bytes, budget)
            value = parser.value()
            closing = parser.take()
            if closing.value != b'endobj' or offset < xref_ends[bisect_left(xref_starts, closing.end)]:
                raise InvalidDocumentError('Invalid PDF page-tree object extent')
            spans.append((offset, closing.end))
        else:
            raise UnsupportedDocumentError('Unsupported PDF page-tree xref entry')
        loaded[reference] = value
        return value

    def dictionary(reference: Any) -> dict[str, Any]:
        if not isinstance(reference, Reference) or reference in seen:
            raise InvalidDocumentError('Invalid or repeated PDF page-tree reference')
        value = load(reference)
        if not isinstance(value, dict):
            raise InvalidDocumentError('Invalid PDF page-tree object dictionary')
        seen.add(reference)
        return value

    def field(value: Any) -> Any:
        return load(value) if isinstance(value, Reference) else value

    def count(reference: Any, parent: Reference | None, depth: int) -> int:
        if depth > limits.max_pdf_depth:
            raise ResourceLimitError('PDF page-tree depth budget exceeded')
        node = dictionary(reference)
        if (parent is None and 'Parent' in node) or (parent is not None and node.get('Parent') != parent):
            raise InvalidDocumentError('PDF page-tree Parent does not match its containing node')
        kind = node.get('Type')
        if kind == Name('Page') and parent is not None:
            return 1
        if kind != Name('Pages'):
            raise InvalidDocumentError('Invalid PDF page-tree node type')
        children, declared = field(node.get('Kids')), field(node.get('Count'))
        if not isinstance(children, list) or type(declared) is not int:
            raise InvalidDocumentError('Invalid PDF Pages node')
        actual = sum(count(child, reference, depth+1) for child in children)
        if actual != declared:
            raise InvalidDocumentError('PDF Pages Count does not match its descendants')
        return actual

    catalog = dictionary(_trailer_value('Root', data, sections, report, limits, budget))
    if catalog.get('Type') != Name('Catalog'):
        raise InvalidDocumentError('PDF Root is not a Catalog')
    result = count(catalog.get('Pages'), None, 0)
    spans.sort()
    if any(previous_end > start for (_, previous_end), (start, _) in zip(spans, spans[1:])):
        raise InvalidDocumentError('PDF page-tree objects overlap')
    return result


def read_pdf_xmp(path: str | Path, *, cancelled: Callable[[], bool] | None = None) -> bytes | None:
    """Read the document Catalog's XMP packet as inert bytes, without interpreting XML."""
    with cancellation_scope(cancelled, 'PDF XMP extraction', inherit=True):
        return _read_pdf_xmp(path)


def _read_pdf_xmp(path: str | Path) -> bytes | None:
    data, limits, budget, xrefs, sections, report = _open_source(path)
    entries: dict[int, dict[str, Any]] = {entry['object']: entry for entry in report['effective_xref_entries']}

    def entry(reference: Any) -> dict[str, Any]:
        if not isinstance(reference, Reference):
            raise InvalidDocumentError('PDF XMP requires an indirect object reference')
        target = entries.get(reference.object)
        if target is None or target['generation'] != reference.generation or target['state'] == 'free':
            raise InvalidDocumentError('PDF XMP reference does not match the current xref')
        return target

    def check_extent(start: int, end: int) -> None:
        if any(start < section['end'] and section['offset'] < end for section in sections.values()):
            raise InvalidDocumentError('PDF XMP object overlaps xref')

    occupied: list[tuple[int, int]] = []
    compressed: dict[int, Any] | None = None

    def scalar(reference: Any) -> Any:
        nonlocal compressed
        target = entry(reference)
        if target['state'] == 'compressed':
            if compressed is None:
                nodes: dict[str, Any] = {}
                items, selected = _compressed_inventory(data, limits, budget, xrefs, sections, report, page_members=nodes)
                compressed = {number: nodes[locator] for locator, number in selected.items() if locator in nodes}
                for item in items:
                    checkpoint()
                    if item.kind == 'pdf-object-stream':
                        details = dict(item.details)
                        occupied.append((details['offset'], details['end']))
            return compressed.get(reference.object)
        start = target['offset']
        scalar_parser = _object_parser(data, start, reference, limits.max_part_bytes, budget)
        value = scalar_parser.value()
        end = scalar_parser.take()
        if end.value != b'endobj':
            raise InvalidDocumentError('Invalid PDF XMP dependency extent')
        check_extent(start, end.end)
        occupied.append((start, end.end))
        return value

    catalog = scalar(_trailer_value('Root', data, sections, report, limits, budget))
    if not isinstance(catalog, dict) or catalog.get('Type') != Name('Catalog'):
        raise InvalidDocumentError('PDF Root is not a Catalog')
    reference = catalog.get('Metadata')
    if reference is None:
        return None
    target = entry(reference)
    if target['state'] != 'uncompressed':
        raise InvalidDocumentError('PDF Metadata stream cannot be a compressed object-stream member')
    start = target['offset']
    parser = _object_parser(data, start, reference, limits.max_part_bytes, budget)
    attributes = parser.value()
    if (not isinstance(attributes, dict) or attributes.get('Type') != Name('Metadata')
            or attributes.get('Subtype') != Name('XML') or parser.take().value != b'stream'):
        raise InvalidDocumentError('PDF Catalog Metadata is not an XML metadata stream')
    length = attributes.get('Length')
    if isinstance(length, Reference):
        length = scalar(length)
    if type(length) is not int or length < 0:
        raise InvalidDocumentError('Invalid PDF XMP stream Length')
    bounds = finish_stream(parser, length)
    check_extent(start, parser.pos)
    if any(start < other_end and other_start < parser.pos for other_start, other_end in occupied):
        raise InvalidDocumentError('PDF XMP stream overlaps a dependency or an object stream')
    if any(key in attributes for key in ('F', 'FFilter', 'FDecodeParms')):
        raise UnsupportedDocumentError('External data is outside the native PDF XMP profile')
    payload = memoryview(data)[bounds['encoded_start']:bounds['encoded_end']]
    decoded, details = decode(payload, attributes.get('Filter'), attributes.get('DecodeParms'),
                              source_start=bounds['encoded_start'], part_limit=limits.max_part_bytes,
                              byte_limit=limits.max_part_bytes, location='PDF XMP: ', budget=budget)
    if any(stage['trailing_input_bytes'] for stage in details['decode_stages']):
        raise InvalidDocumentError('Trailing input after PDF XMP filter data')
    return bytes(decoded)


def read_info(path: str | Path) -> dict[str, str]:
    """Read text entries in the Info dictionary selected by the source xref."""
    data, limits, budget, xrefs, sections, report = _open_source(path)
    result = {'title': '', 'author': '', 'subject': ''}
    reference = _trailer_value('Info', data, sections, report, limits, budget)
    if reference is None:
        return result
    if not isinstance(reference, Reference):
        raise InvalidDocumentError('PDF Info must be an indirect reference')
    entries = {entry['object']: entry for entry in report['effective_xref_entries']}

    def compressed_objects(info_member: tuple[int, int, int] | None = None) -> dict[int, bytes]:
        items, selected = _compressed_inventory(data, limits, budget, xrefs, sections, report, info_member=info_member)
        return {selected[item.locator]: item.payload for item in items
                if item.payload is not None and item.locator in selected}

    target = entries.get(reference.object)
    if target is None or target['generation'] != reference.generation or target['state'] not in {'compressed', 'uncompressed'}:
        raise UnsupportedDocumentError('PDF Info needs an in-use object selected by xref')
    compressed = target['state'] == 'compressed'
    payloads: dict[int, bytes] | None = None
    offset = 0
    if compressed:
        container = entries.get(target['object_stream'])
        if container is None or container['state'] != 'uncompressed' or container['generation'] != 0:
            raise InvalidDocumentError('Compressed PDF Info needs a selected ObjStm container')
        payloads = compressed_objects((container['offset'], target['index'], reference.object))
        info = payloads.get(reference.object)
        if info is None:
            raise InvalidDocumentError('Compressed PDF Info does not match the selected xref record')
        parser = Parser(info, 0, limits.max_part_bytes, budget, stop=len(info))
    else:
        offset = target['offset']
        parser = _object_parser(data, offset, reference, limits.max_part_bytes, budget)
    parser.take('<<')
    fields: dict[str, str | Reference | None] = {}
    conflicts: set[str] = set()
    while parser.peek().kind != '>>':
        key = parser.take('name').value.value
        token = parser.peek()
        value = parser.value()
        field = key.lower()
        if key in {'Title', 'Author', 'Subject'}:
            entry: str | Reference | None = None
            if token.kind == 'string':
                entry = _text(bytes(parser.data[token.start:token.end]))
            elif isinstance(value, Reference):
                entry = value
            if field in fields and fields[field] != entry:
                conflicts.add(field)
            fields[field] = entry
    parser.take('>>')
    closing = parser.take()
    if compressed:
        if closing.kind != 'eof':
            raise InvalidDocumentError('Extra syntax after compressed PDF Info')
    elif closing.value != b'endobj' or any(offset < section['end'] and section['offset'] < closing.end
                                          for section in sections.values()):
        raise InvalidDocumentError('PDF Info has an invalid end or overlaps xref')

    def resolve_text(reference: Reference) -> str:
        nonlocal payloads
        visited: set[Reference] = set()
        for _ in range(limits.max_pdf_depth):
            checkpoint()
            if reference in visited:
                return ''
            visited.add(reference)
            selected = entries.get(reference.object)
            if selected is None or selected['generation'] != reference.generation:
                return ''
            try:
                if selected['state'] == 'compressed':
                    if payloads is None:
                        try:
                            payloads = compressed_objects()
                        except (InvalidDocumentError, UnsupportedDocumentError):
                            payloads = {}
                    payload = payloads.get(reference.object)
                    if payload is None:
                        return ''
                    parser = Parser(payload, 0, limits.max_part_bytes, budget, stop=len(payload))
                elif selected['state'] == 'uncompressed':
                    parser = _object_parser(data, selected['offset'], reference, limits.max_part_bytes, budget)
                else:
                    return ''
                token = parser.peek()
                value = parser.value()
                closing = parser.take()
            except InvalidDocumentError:
                return ''
            if selected['state'] == 'compressed':
                if closing.kind != 'eof':
                    return ''
            elif closing.value != b'endobj' or any(selected['offset'] < section['end'] and section['offset'] < closing.end
                                                  for section in sections.values()):
                return ''
            if token.kind == 'string':
                return _text(bytes(parser.data[token.start:token.end]))
            if not isinstance(value, Reference):
                return ''
            reference = value
        return ''

    for field, entry in fields.items():
        if field not in conflicts:
            if isinstance(entry, Reference):
                result[field] = resolve_text(entry)
            elif entry is not None:
                result[field] = entry
    return result
