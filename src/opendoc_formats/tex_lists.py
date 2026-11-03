"""Inert TeX paragraph identity comments, not an alternate document model."""

import base64
import json
import re

from opendoc_model import Anchor, ArtifactLimitError, DocumentLimits, ListItem

from opendoc_formats.errors import InvalidDocumentError

PREFIX = '% opendoc-par-v1:'
MARKER = re.compile(r'(?m)^% opendoc-par-v1:([^\r\n]*)\r?$')


def paragraph_marker(anchor: Anchor | None, item: ListItem | None) -> str:
    if anchor is None and item is None:
        return ''
    data = {'anchor': anchor.id if anchor else None}
    if item is not None:
        data.update(list_id=item.list_id, level=item.level, start=item.start, restart=item.restart)
    encoded = base64.urlsafe_b64encode(json.dumps(data, ensure_ascii=True, separators=(',', ':')).encode()).decode()
    if len(encoded) > 65_536:
        raise ValueError('TeX paragraph identity exceeds the native profile budget')
    return PREFIX+encoded+'\n'


def _marker_object(pairs: list[tuple[str, object]]) -> dict:
    if len(pairs) != len({key for key, _ in pairs}):
        raise ValueError('Duplicate native paragraph metadata key')
    return dict(pairs)


def paragraph_markers(text: str, *, limits: DocumentLimits | None = None) -> list[tuple[int, dict]]:
    result = []
    maximum = (limits or DocumentLimits()).max_nodes
    if any(not match.group().startswith(PREFIX) for match in re.finditer(r'(?m)^% opendoc-par-v[^\r\n]*', text)):
        raise InvalidDocumentError('Unsupported native paragraph metadata version')
    for match in MARKER.finditer(text):
        try:
            encoded = match.group(1)
            if len(encoded) > 65_536 or not re.fullmatch(r'[A-Za-z0-9_=-]+', encoded):
                raise ValueError('Invalid native paragraph identity')
            data = json.loads(base64.b64decode(encoded, altchars=b'-_', validate=True), object_pairs_hook=_marker_object)
            if (not isinstance(data, dict) or set(data)-{'anchor', 'list_id', 'level', 'start', 'restart'}
                    or not isinstance(data.get('anchor'), (str, type(None)))):
                raise ValueError('Invalid native paragraph identity')
            if data.get('anchor') is not None:
                Anchor(data['anchor'])
            if 'list_id' in data:
                ListItem(data['list_id'], data['level'], start=data['start'], restart=data['restart'])
            elif set(data) != {'anchor'}:
                raise ValueError('Incomplete native paragraph identity')
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError) as error:
            raise InvalidDocumentError('Invalid inert TeX paragraph metadata') from error
        result.append((match.end(), data))
        if len(result) > maximum:
            raise ArtifactLimitError('Native TeX paragraph metadata exceeds selected budget', path='$.latex.native-paragraphs',
                                     quota='nodes', maximum=maximum)
    return result
