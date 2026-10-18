"""Use document-owned font programs during Word export without shared installs."""

from __future__ import annotations

import hashlib
import re
from contextlib import contextmanager
from dataclasses import replace
from io import BytesIO
from typing import Any, Iterator

from opendoc_model import DocumentLimits, DocumentModel, IssueSeverity, ResourceKind, TextStyle, get_font_reference

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
    supports_resource_references = True

    def __init__(self, embedded: FontResolver, aliases: dict[str, str], system: FontResolver,
                 native_names: dict[str, str], bindings: dict[tuple[str, bool, bool], FontFace], *, strict: bool,
                 resource_faces: dict[str, FontFace] | None = None, ambiguous: set[str] | None = None,
                 report: Any = None, limits: DocumentLimits | None = None) -> None:
        super().__init__(system.faces)
        self.embedded = embedded
        self.aliases = aliases
        self.native_names = native_names
        self.bindings = bindings
        self.strict = strict
        self.resource_faces = resource_faces or {}
        self.ambiguous = ambiguous or set()
        self.report = report
        self.limits = limits

    def resolve_style(self, style: TextStyle, text: str = '') -> FontResolution:
        reference = get_font_reference(style, limits=self.limits)
        if reference is None:
            return super().resolve_style(style, text)
        face = self.resource_faces.get(reference.resource_id)
        # This finite profile supports standalone TTF/OTF, never a guessed collection face.
        if face is None or reference.face_index not in (None, 0):
            return FontResolution(style.font_family or '', style.font_family or '', None, False, 1.0,
                                  tuple(sorted(set(text))), False)
        resolution = FontResolver([face]).resolve(face.family, text, bold=bool(style.bold), italic=bool(style.italic))
        return replace(resolution, requested=style.font_family or face.family,
                       resolved=self.native_names.get(str(face.path), face.family))

    def resolve(self, family: str, text: str = '', *, bold: bool = False, italic: bool = False) -> FontResolution:
        actual = self.aliases.get(_plain_name(family), family)
        if actual in self.ambiguous:
            self.report.add(IssueSeverity.LOSS, 'font-resource-binding',
                            f'Ambiguous PDF font program {family!r} requires an explicit resource binding')
            return FontResolution(family, family, None, False, 1.0, tuple(sorted(set(text))), False)
        bound = self.bindings.get((_plain_name(family), bold, italic))
        registry = FontResolver([bound]) if bound else self.embedded
        resolution = registry.resolve(bound.family if bound else actual, text, bold=bold, italic=italic)
        if resolution.exact and (self.strict or (not resolution.missing_glyphs and resolution.embeddable)):
            native = self.native_names.get(str(resolution.path), resolution.resolved)
            return replace(resolution, requested=family, resolved=native)
        return super().resolve(actual, text, bold=bold, italic=italic)


@contextmanager
def document_font_resolver(document: DocumentModel, report: Any, *,
                           limits: DocumentLimits | None = None) -> Iterator[FontResolver]:
    fonts = [resource for resource in document.resources.values() if resource.kind is ResourceKind.FONT and resource.data]
    system = FontResolver.system()
    with ArtifactWorkspace(prefix='opendoc_formats_font_resources_') as workspace:
        faces = []
        aliases = {}
        native_names = {}
        bindings = {}
        variants = {}
        resource_faces = {}
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
                variants.setdefault(key, set()).add(digest)
                resource_faces[resource.id] = face
                native = resource.properties.get('docx_font_family')
                if pdf or not isinstance(native, str):
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
        ambiguous = {face.family for face in faces
                     if pdf and len(variants[(face.normalized_family, face.weight, face.italic)]) > 1}
        yield ResourceFontResolver(FontResolver(faces), aliases, system, native_names, bindings, strict=pdf,
                                   resource_faces=resource_faces, ambiguous=ambiguous, report=report, limits=limits)
