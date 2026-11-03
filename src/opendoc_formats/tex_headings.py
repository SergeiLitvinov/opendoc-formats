"""Finite standard TeX heading hierarchies; source classes are never executable paths."""

from __future__ import annotations

import re
from collections.abc import Mapping

from opendoc_formats.support.latex import PREAMBLE

CLASS_OPTIONS_KEY = 'opendoc_formats.latex_documentclass_options'
_LEGACY = object()
_OPTIONS = frozenset(('10pt', '11pt', '12pt', 'a4paper', 'a5paper', 'b5paper', 'letterpaper', 'legalpaper',
                      'executivepaper', 'landscape', 'oneside', 'twoside', 'onecolumn', 'twocolumn',
                      'openright', 'openany', 'titlepage', 'notitlepage', 'draft', 'final', 'leqno', 'fleqn'))
_HEADER = re.compile(rb'\\documentclass(?:\[([^\]]{0,2048})\])?\{(article|book|report)\}\r?\n')


class PreambleProfileError(ValueError):
    """Explicit source preamble data cannot be projected through the finite native route."""


def class_options(carrier: object) -> str | None:
    if (type(carrier) is not dict or set(carrier) != {'version', 'source'}
            or type(carrier.get('version')) is not int or carrier['version'] != 1):
        raise PreambleProfileError('Invalid or unsupported documentclass options carrier')
    raw = carrier['source']
    if raw is None:
        return None
    if (type(raw) is not str or len(raw) > 2048 or re.fullmatch(r'[a-z0-9, \t\r\n]*', raw) is None
            or raw.strip() and any(part.strip() not in _OPTIONS for part in raw.split(','))):
        raise PreambleProfileError('Documentclass options are outside the native literal profile')
    return raw


def heading_commands(document_class: object = None) -> dict[int, str]:
    commands: tuple[str, ...] = ('section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph')
    if type(document_class) is str and document_class in ('book', 'report'):
        commands = ('chapter', *commands)
    return dict(enumerate(commands, 1))


def heading_preamble(document_class: object = None, *, options: object = _LEGACY) -> str:
    """Emit literal source options; absence of a carrier preserves the legacy generated default."""
    selected = document_class if type(document_class) is str and document_class in ('book', 'report') else 'article'
    raw = '12pt,a4paper' if options is _LEGACY else class_options(options)
    argument = '' if raw is None else '[' + raw + ']'
    return '\\documentclass' + argument + '{' + selected + '}\n' + PREAMBLE.split('\n', 1)[1]


def metadata_preamble(metadata: Mapping[str, object]) -> str:
    return heading_preamble(metadata.get('documentclass'), options=metadata.get(CLASS_OPTIONS_KEY, _LEGACY))


def known_preamble_length(data: bytes) -> int:
    """Recognize only a complete generated prefix; source evidence never chooses edited options."""
    start = 3 if data.startswith(b'\xef\xbb\xbf') else 0
    match = _HEADER.match(data, start, min(len(data), start + 4096))
    if match is None:
        return 0
    try:
        raw = match[1].decode('ascii') if match[1] is not None else None
        expected = heading_preamble(match[2].decode('ascii'), options={'version': 1, 'source': raw})
    except (UnicodeError, PreambleProfileError):
        return 0
    for prefix in (expected, expected.replace('\r\n', '\n').replace('\n', '\r\n')):
        encoded = prefix.encode('utf-8')
        if data.startswith(encoded, start):
            return len(encoded)  # Generated prefix is ASCII; source character offsets exclude the UTF-8 BOM.
    return 0
