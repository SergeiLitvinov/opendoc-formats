"""Inert, bounded data-URI font-face bindings for the static HTML profile."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from collections.abc import Callable
from typing import Any

from opendoc_model import ArtifactLimitError, DocumentLimits, FontReference, Resource, ResourceKind, TextStyle, set_font_reference

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.sfnt import inspect_sfnt
from opendoc_formats.support.cancellation import check_cancelled


def _tokens(values: Any) -> list[Any]:
    return [token for token in values if token.type not in {'whitespace', 'comment'}]


class FontFaces:
    def __init__(self, resources: dict[str, Resource], warn: Callable[..., None], *, limits: DocumentLimits | None = None,
                 cancelled: Callable[[], bool] | None = None) -> None:
        self.resources, self.warn, self.cancelled = resources, warn, cancelled
        self.maximum = (limits or DocumentLimits()).max_embedded_bytes
        self.bytes = self.count = 0
        self.faces: dict[tuple[str, bool, bool], set[str]] = {}
        self.blocked: set[str] = set()
        self.families: set[str] = set()
        self.payloads: dict[str, str] = {}

    def read(self, rule: Any, node: Any) -> None:
        import tinycss2

        check_cancelled(self.cancelled, 'HTML font-face')
        self.count += 1
        if self.count > 1024:
            raise ResourceLimitError('HTML font-face rule budget exceeded')
        family = None
        try:
            if _tokens(rule.prelude) or rule.content is None:
                raise ValueError('font-face requires an empty prelude and a declaration block')
            descriptors = {}
            invalid = False
            for item in tinycss2.parse_declaration_list(rule.content, skip_comments=True, skip_whitespace=True):
                check_cancelled(self.cancelled, 'HTML font descriptor')
                if item.type != 'declaration' or item.important:
                    invalid = True
                    continue
                if item.lower_name in descriptors:
                    invalid = True
                descriptors[item.lower_name] = _tokens(item.value)
            names = descriptors.get('font-family', [])
            if len(names) != 1 or names[0].type != 'string' or not names[0].value.strip():
                raise ValueError('font-family requires one quoted family')
            family = names[0].value
            if re.search(r'[\x00-\x1f\x7f,;{}()<>\\]', family):
                raise ValueError('font-family outside static profile')
            self.families.add(family.casefold())
            if invalid or set(descriptors)-{'font-family', 'src', 'font-weight', 'font-style'}:
                raise ValueError('font descriptors outside static profile')
            weight = self._value(descriptors, 'font-weight', 'normal')
            slant = self._value(descriptors, 'font-style', 'normal')
            if weight not in {'normal', 'bold', '400', '700'} or slant not in {'normal', 'italic'}:
                raise ValueError('font weight/style outside static profile')
            source = descriptors.get('src', [])
            if not source or len(source) > 2:
                raise ValueError('src requires one data URL with an optional format')
            url = source[0]
            if url.type == 'url':
                uri = url.value
            elif url.type == 'function' and url.lower_name == 'url':
                arguments = _tokens(url.arguments)
                if len(arguments) != 1 or arguments[0].type != 'string':
                    raise ValueError('unsupported font URL')
                uri = arguments[0].value
            else:
                raise ValueError('local and external font sources are not loaded')
            if len(source) == 2:
                hint = source[1]
                if hint.type != 'function' or hint.lower_name != 'format':
                    raise ValueError('unsupported font source hint')
                arguments = _tokens(hint.arguments)
                if (len(arguments) != 1 or arguments[0].type not in {'string', 'ident'}
                        or arguments[0].value not in {'truetype', 'opentype'}):
                    raise ValueError('unsupported font format hint')
            identifier = self._program(uri)
            self.faces.setdefault((family.casefold(), weight in {'bold', '700'}, slant == 'italic'), set()).add(identifier)
        except (ArtifactLimitError, ResourceLimitError):
            raise
        except (ValueError, InvalidDocumentError, UnsupportedDocumentError) as error:
            if family is not None:
                self.blocked.add(family.casefold())
            self.warn('html-font', f'Font-face not bound: {error}', node)

    @staticmethod
    def _value(descriptors: dict[str, Any], name: str, default: str) -> str:
        tokens = descriptors.get(name)
        if tokens is None:
            return default
        if len(tokens) != 1 or tokens[0].type not in {'ident', 'number'}:
            raise ValueError('font descriptor requires one value')
        token = tokens[0]
        return str(token.value).lower() if token.type == 'ident' else str(token.representation)

    def _program(self, uri: str) -> str:
        check_cancelled(self.cancelled, 'HTML font program')
        if uri in self.payloads:
            return self.payloads[uri]
        match = re.fullmatch(r'data:(font/(?:ttf|otf));base64,([A-Za-z0-9+/]*={0,2})', uri)
        if match is None:
            raise ValueError('only base64 font/ttf and font/otf data URLs are loaded')
        media, payload = match.groups()
        if len(payload) % 4:
            raise ValueError('invalid base64 font payload length')
        size = len(payload)//4*3 - (len(payload)-len(payload.rstrip('=')))
        if self.bytes+size > self.maximum:
            raise ArtifactLimitError('HTML font programs exceed embedded-byte budget', path='$.html.font-face.src',
                                     quota='embedded bytes', maximum=self.maximum)
        try:
            data = base64.b64decode(payload, validate=True)
        except binascii.Error as error:
            raise ValueError('invalid base64 font payload') from error
        check_cancelled(self.cancelled, 'HTML font program decoding')
        if not data.startswith(b'OTTO' if media == 'font/otf' else b'\0\1\0\0'):
            raise ValueError('font wrapper does not match declared media type')
        inventory = inspect_sfnt(data, cancelled=self.cancelled)
        if any(table.tag in {'fvar', 'CFF2'} for table in inventory.tables):
            raise UnsupportedDocumentError('variable/CFF2 font programs require a separate binding profile')
        identifier = 'html-font-'+hashlib.sha256(data).hexdigest()
        if identifier not in self.resources:
            self.resources[identifier] = Resource(identifier, ResourceKind.FONT, media, data=data)
            self.bytes += len(data)
        self.payloads[uri] = identifier
        return identifier

    def bind(self, style: TextStyle, node: Any) -> None:
        check_cancelled(self.cancelled, 'HTML font binding')
        family = (style.font_family or '').casefold()
        if family not in self.families:
            return
        bindings = self.faces.get((family, bool(style.bold), bool(style.italic)), set())
        if family in self.blocked or len(bindings) != 1:
            self.warn('html-font', 'Font family/variant has no unambiguous static program binding', node)
            return
        set_font_reference(style, FontReference(next(iter(bindings)), 0))
