"""Finite OPC declarations and URI handling over bounded inventories; no Office backend."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.package_resources import _part_name
from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import XmlNodeInfo

CONTENT_TYPES = '{http://schemas.openxmlformats.org/package/2006/content-types}'
RELATIONSHIPS = '{http://schemas.openxmlformats.org/package/2006/relationships}'
RELATIONSHIPS_TYPE = 'application/vnd.openxmlformats-package.relationships+xml'


def relationship_owner(name: str) -> str | None:
    if name == '/_rels/.rels':
        return '/'
    path = PurePosixPath(name)
    if path.parent.name != '_rels' or not name.endswith('.rels') or path.name == '.rels':
        return None
    return str(path.parent.parent/path.name[:-5])


def resolve_target(owner: str, value: str) -> str:
    """Resolve the finite native internal-URI profile; never fetch an address."""
    if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise InvalidDocumentError(f'{owner}: invalid internal OPC target {value!r}')
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise InvalidDocumentError(f'{owner}: invalid internal OPC target {value!r}') from error
    if parsed.scheme or parsed.netloc or parsed.query:
        raise InvalidDocumentError(f'{owner}: invalid internal OPC target {value!r}')
    path = parsed.path
    if not path:
        return owner
    segments = [] if path.startswith('/') else owner.split('/')[1:-1]
    for segment in path.split('/'):
        checkpoint()
        if segment in ('', '.'):
            continue
        if segment == '..':
            if not segments:
                raise InvalidDocumentError(f'{owner}: OPC target escapes package root')
            segments.pop()
        else:
            decoded = unquote(segment)
            if decoded in ('.', '..') or '/' in decoded or '\\' in decoded:
                raise InvalidDocumentError(f'{owner}: ambiguous encoded OPC target')
            segments.append(segment)
    return part_name('/'+'/'.join(segments))


def part_name(value: str) -> str:
    value = _part_name(value)
    if any(segment in ('', '.', '..') for segment in value[1:].split('/')):
        raise InvalidDocumentError(f'Unnormalized OPC part name: {value!r}')
    return value


def content_types(nodes: Iterable[XmlNodeInfo]) -> tuple[dict[str, str], dict[str, str]]:
    """Read the finite Default/Override profile without reparsing or expanding XML."""
    entries = iter(nodes)
    root = next(entries, None)
    if root is None or root.tag != CONTENT_TYPES+'Types':
        raise InvalidDocumentError('Invalid OPC content-types root')
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for node in entries:
        checkpoint()
        if node.path.count('/') != 1:
            continue
        attributes = dict(node.attributes)
        if node.tag == CONTENT_TYPES+'Default':
            key, value = attributes.get('Extension'), attributes.get('ContentType')
            mapping = defaults
            key = key.lower() if key else key
        elif node.tag == CONTENT_TYPES+'Override':
            key, value = attributes.get('PartName'), attributes.get('ContentType')
            mapping = overrides
            key = part_name(key) if key else key
        else:
            continue
        if not key or not value or (key in mapping and mapping[key] != value):
            raise InvalidDocumentError('Invalid/conflicting OPC content-type declaration')
        mapping[key] = value
    return defaults, overrides


def xml_content_type(value: str) -> bool:
    media_type = value.partition(';')[0].strip().lower()
    return media_type in {'application/xml', 'text/xml'} or media_type.endswith('+xml')


def declared_content_type(name: str, defaults: Mapping[str, str], overrides: Mapping[str, str]) -> str | None:
    # OPC's root relationship name is '.rels'; pathlib deliberately treats it as extensionless.
    _, dot, extension = PurePosixPath(name).name.rpartition('.')
    return overrides.get(name) or (defaults.get(extension.lower()) if dot else None)
