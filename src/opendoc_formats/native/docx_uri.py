"""Finite native DOCX URI-to-ZIP bindings; never lossy decoding or an alias guess."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import unquote

from opendoc_formats.errors import InvalidDocumentError, UnsupportedDocumentError
from opendoc_formats.native.common import Cancellation, check_cancel


def candidates(source: str | None, target: str, location: str,
               cancelled: Cancellation | None = None) -> tuple[str, str]:
    check_cancel(cancelled)
    if not target:
        raise InvalidDocumentError(location+': missing internal target')
    if re.search(r'%(?![0-9a-fA-F]{2})', target):
        raise InvalidDocumentError(location+': malformed percent escape')
    try:
        decoded = unquote(target, errors='strict')
    except UnicodeDecodeError as error:
        raise UnsupportedDocumentError(location+': internal target is outside the UTF-8 URI profile') from error
    if '\\' in decoded or ':' in decoded or any(ord(char) < 32 or ord(char) == 127 for char in decoded):
        raise InvalidDocumentError(location+': unsafe internal relationship target')
    if re.search(r'%(?:2[fF]|5[cC])', target):
        raise UnsupportedDocumentError(location+': encoded separator outside native URI profile')
    base = list(PurePosixPath(source).parent.parts) if source is not None else []
    if base == ['.']:
        base = []

    def normalized(value: str) -> str:
        parts = [] if value.startswith('/') else list(base)
        for piece in value.split('/'):
            check_cancel(cancelled)
            if piece in ('', '.'):
                continue
            if piece == '..':
                if not parts:
                    raise InvalidDocumentError(location+': relationship escapes the package')
                parts.pop()
            else:
                parts.append(piece)
        return '/'.join(parts)

    return normalized(decoded), normalized(target)


def bind(source: str | None, target: str, names: set[str], location: str,
         cancelled: Cancellation | None = None) -> str:
    possible = {name for name in candidates(source, target, location, cancelled) if name in names}
    if len(possible) > 1:
        raise UnsupportedDocumentError(location+': ambiguous escaped/unescaped ZIP part aliases')
    if not possible:
        raise InvalidDocumentError(location+': internal relationship refers to a missing package part')
    return possible.pop()
