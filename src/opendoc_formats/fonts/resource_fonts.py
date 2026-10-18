"""Use document-owned font programs during Word export without shared installs."""

from __future__ import annotations

import hashlib
import re
from contextlib import contextmanager
from dataclasses import replace
from io import BytesIO
from typing import Any, Iterator

from opendoc_model import DocumentModel, IssueSeverity, ResourceKind

from opendoc_formats.fonts.resolver import FontFace, FontResolution, FontResolver, _read_face
from opendoc_formats.support.artifacts import ArtifactWorkspace


def _plain_name(name: str) -> str:
    return re.sub(r'^[A-Z]{6}\+', '', name).casefold()


def font_program_names(data: bytes) -> tuple[str, tuple[str, ...]]:
    from fontTools.ttLib import TTFont

    with TTFont(BytesIO(data), lazy=True) as native:
        names = native['name']
        family = names.getDebugName(16) or names.getDebugName(1)
        if not family:
            raise ValueError('Font program has no family name')
        if not names.getDebugName(4):
            raise ValueError('Word font program requires a full font name')
        aliases = tuple(name for identifier in (1, 4, 6, 16) if (name := names.getDebugName(identifier)))
        return family, aliases


class ResourceFontResolver(FontResolver):
    def __init__(self, embedded: FontResolver, aliases: dict[str, str], system: FontResolver,
                 native_names: dict[str, str], bindings: dict[tuple[str, bool, bool], FontFace], *, strict: bool) -> None:
        super().__init__(system.faces)
        self.embedded = embedded
        self.aliases = aliases
        self.native_names = native_names
        self.bindings = bindings
        self.strict = strict

    def resolve(self, family: str, text: str = '', *, bold: bool = False, italic: bool = False) -> FontResolution:
        actual = self.aliases.get(_plain_name(family), family)
        bound = self.bindings.get((_plain_name(family), bold, italic))
        registry = FontResolver([bound]) if bound else self.embedded
        resolution = registry.resolve(bound.family if bound else actual, text, bold=bold, italic=italic)
        if resolution.exact and (self.strict or (not resolution.missing_glyphs and resolution.embeddable)):
            native = self.native_names.get(str(resolution.path), resolution.resolved)
            return replace(resolution, requested=family, resolved=native)
        return super().resolve(actual, text, bold=bold, italic=italic)


@contextmanager
def document_font_resolver(document: DocumentModel, report: Any) -> Iterator[FontResolver]:
    fonts = [resource for resource in document.resources.values() if resource.kind is ResourceKind.FONT and resource.data]
    system = FontResolver.system()
    if not fonts:
        yield system
        return
    with ArtifactWorkspace(prefix='opendoc_formats_font_resources_') as workspace:
        faces = []
        aliases = {}
        native_names = {}
        bindings = {}
        variants = {}
        pdf = document.metadata.get('pdf_docx_layout') is not None
        for index, resource in enumerate(fonts):
            location = f'resources[{resource.id!r}]'
            if resource.media_type not in {'font/ttf', 'font/otf'}:
                report.add(IssueSeverity.LOSS, 'font-resource', 'Word cannot embed this font program profile', location)
                continue
            try:
                family, names = font_program_names(resource.data)
                for name in names:
                    aliases[_plain_name(name)] = family
                path = workspace.write_bytes(f'font-{index}.ttf', resource.data)
                face = _read_face(path)
                if face is None:
                    raise ValueError('Font program cannot be inspected')
                if not face.embeddable:
                    report.add(IssueSeverity.LOSS, 'font-resource',
                               'Source font embedding is restricted; installed font fallback requires verification', location)
                digest = hashlib.sha256(resource.data).hexdigest()
                key = (face.normalized_family, face.weight, face.italic)
                if pdf and key in variants and variants[key] != digest:
                    report.add(IssueSeverity.LOSS, 'font-resource-binding',
                               'Different PDF font programs share a family/variant; an explicit run resource binding is required',
                               location)
                variants[key] = digest
                native = resource.properties.get('docx_font_family')
                if pdf:
                    native = 'ODF Embedded ' + digest[:12]
                if isinstance(native, str):
                    native_names[str(path)] = native
                    aliases[_plain_name(native)] = family
                    variant = resource.properties.get('docx_font_variant')
                    bold = variant in {'embedBold', 'embedBoldItalic'} if variant else face.weight >= 600
                    italic = variant in {'embedItalic', 'embedBoldItalic'} if variant else face.italic
                    bindings[(_plain_name(native), bold, italic)] = face
                faces.append(face)
            except Exception as error:  # noqa: BLE001 - untrusted font programs need located diagnostics
                report.add(IssueSeverity.LOSS, 'font-resource', f'Embedded font could not be used: {error}', location)
        yield ResourceFontResolver(FontResolver(faces), aliases, system, native_names, bindings, strict=pdf)
