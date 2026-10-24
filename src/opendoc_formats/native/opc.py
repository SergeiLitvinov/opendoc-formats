"""OPC content-type declarations over bounded XML inventories; no Office backend."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.package_resources import _part_name
from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import XmlNodeInfo

CONTENT_TYPES = '{http://schemas.openxmlformats.org/package/2006/content-types}'


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
