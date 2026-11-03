"""Cross-platform font registry and metric-aware deterministic substitutions."""

from __future__ import annotations

import copy
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Iterable

import opendoc_model as od
from opendoc_model.document_model import DocumentModel, Paragraph, Table, TextRun, TextStyle

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.fonts.sfnt_cmap import read_unicode_coverage
from opendoc_formats.fonts.sfnt_names import read_program_names
from opendoc_formats.native.common import read_source
from opendoc_formats.native.sfnt import SfntLimits, read_face_metrics
from opendoc_formats.support.cancellation import cancellable_items, cancellation_requested, checkpoint


@dataclass(frozen=True)
class FontFace:
    family: str
    path: Path
    weight: int = 400
    italic: bool = False
    width_class: int = 5
    units_per_em: int = 1000
    average_width: float = 500.0
    glyphs: frozenset[int] = frozenset()
    embeddable: bool = True
    subsettable: bool = True

    @property
    def normalized_family(self) -> str:
        return _normalize_family(self.family)


@dataclass(frozen=True)
class FontResolution:
    requested: str
    resolved: str
    path: Path | None
    exact: bool
    metric_distance: float
    missing_glyphs: tuple[str, ...] = ()
    embeddable: bool = False
    subsettable: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "resolved": self.resolved,
            "path": str(self.path) if self.path else None,
            "exact": self.exact,
            "metric_distance": round(self.metric_distance, 4),
            "missing_glyphs": list(self.missing_glyphs),
            "embeddable": self.embeddable,
            "subsettable": self.subsettable,
        }


@dataclass
class FontResolutionReport:
    resolutions: dict[str, FontResolution] = field(default_factory=dict)

    @property
    def substitutions(self) -> list[FontResolution]:
        return [item for item in cancellable_items(self.resolutions.values()) if not item.exact]

    @property
    def missing_glyphs(self) -> dict[str, tuple[str, ...]]:
        return {name: item.missing_glyphs for name, item in cancellable_items(self.resolutions.items()) if item.missing_glyphs}

    def to_dict(self) -> dict[str, object]:
        return {
            "resolutions": {name: item.to_dict() for name, item in cancellable_items(sorted(self.resolutions.items()))},
            "substitution_count": len(self.substitutions),
            "fonts_with_missing_glyphs": len(self.missing_glyphs),
        }


class FontResolver:
    """Immutable registry whose ordering and tie-breaking are platform-stable."""

    supports_resource_references = False

    def __init__(self, faces: Iterable[FontFace] = ()) -> None:
        self._faces = tuple(sorted(faces, key=lambda item: (item.normalized_family, str(item.path).casefold())))

    @classmethod
    def system(cls, search_paths: Iterable[str | Path] | None = None) -> FontResolver:
        paths = (
            tuple(Path(path) for path in cancellable_items(search_paths)) if search_paths is not None else _system_font_paths()
        )
        return cls(_load_faces(tuple(str(path.resolve()) for path in cancellable_items(paths))))

    @property
    def faces(self) -> tuple[FontFace, ...]:
        return self._faces

    def resolve_style(self, style: TextStyle, text: str = '') -> FontResolution:
        return self.resolve(style.font_family or '', text, bold=bool(style.bold), italic=bool(style.italic))

    def resolve(self, family: str, text: str = "", *, bold: bool = False, italic: bool = False) -> FontResolution:
        requested = family.strip() or "sans-serif"
        normalized = _normalize_family(requested)
        exact_faces = [face for face in cancellable_items(self._faces) if face.normalized_family == normalized]
        candidates = exact_faces or list(self._faces)
        if not candidates:
            return FontResolution(requested, requested, None, False, 1.0, tuple(sorted(set(text))), False)
        target_weight = 700 if bold else 400
        requested_class = _generic_class(requested)

        def rank(face: FontFace) -> tuple[float, str, str]:
            metric = abs(face.weight - target_weight) / 500 + abs(face.width_class - 5) / 8
            metric += 0.35 if face.italic != italic else 0
            metric += 0.45 if requested_class != _generic_class(face.family) else 0
            coverage = _missing(face, text)
            metric += min(2.0, len(coverage) / max(1, len(set(text))))
            return metric, face.normalized_family, str(face.path).casefold()

        face = min(candidates, key=rank)
        missing = tuple(sorted(_missing(face, text)))
        return FontResolution(
            requested=requested,
            resolved=face.family,
            path=face.path,
            exact=face.normalized_family == normalized,
            metric_distance=rank(face)[0],
            missing_glyphs=missing,
            embeddable=face.embeddable,
            subsettable=face.subsettable,
        )


@lru_cache(maxsize=8)
def _load_faces(search_paths: tuple[str, ...]) -> tuple[FontFace, ...]:
    paths = tuple(Path(path) for path in cancellable_items(search_paths))
    extensions = ("*.ttf", "*.otf")
    files = sorted(
        {
            file.resolve()
            for root in cancellable_items(paths)
            if root.is_dir()
            for pattern in cancellable_items(extensions)
            for file in cancellable_items(root.rglob(pattern))
        },
        key=lambda item: str(item).casefold(),
    )
    return tuple(face for path in cancellable_items(files) if (face := _read_face(path)) is not None)


def prepare_document_fonts(
    document: DocumentModel,
    resolver: FontResolver | None = None,
    *, limits: od.DocumentLimits | None = None,
) -> tuple[DocumentModel, FontResolutionReport]:
    """Resolve fonts in a deep copy, preserving the caller's canonical model."""
    prepared = copy.deepcopy(document)
    registry = resolver or FontResolver.system()
    # Resolve only font bindings in the private renderer view through the SDK cascade.
    if registry.supports_resource_references and next(od.iter_font_references(prepared, limits=limits), None) is not None:
        context = DocumentModel(styles=prepared.styles, resources=prepared.resources)
        for style in prepared.styles.values():
            checkpoint()
            effective = od.resolve_style(context, style, limits=limits)
            reference = od.get_font_reference(effective, limits=limits)
            if reference is not None:
                od.set_font_reference(style, reference, limits=limits)
                if style.font_family is None:
                    style.font_family = effective.font_family
        for location in od.walk_model(prepared, limits=limits):
            checkpoint()
            paragraph = location.node
            if not isinstance(paragraph, Paragraph):
                continue
            for run in paragraph.content:
                checkpoint()
                if not isinstance(run, TextRun):
                    continue
                if od.get_font_reference(run.style, limits=limits) is not None:
                    continue
                # Exporters also accept native built-in labels without a Model style declaration.
                identifier = paragraph.style_id if paragraph.style_id in context.styles else None
                if identifier is None and not run.style.properties.base_style_id:
                    continue
                effective = od.resolve_style(context, identifier, overrides=run.style, limits=limits)
                reference = od.get_font_reference(effective, limits=limits)
                if reference is not None:
                    od.set_font_reference(run.style, reference, limits=limits)
                    if run.style.font_family is None:
                        run.style.font_family = effective.font_family
    report = FontResolutionReport()
    usages: dict[str, dict[str, object]] = {}

    def collect_style(style: TextStyle, text: str) -> None:
        reference = od.get_font_reference(style, limits=limits) if registry.supports_resource_references else None
        if not style.font_family and reference is None:
            return
        key = f"{style.font_family}"
        if reference is not None:
            key += f'|resource={reference.resource_id!r}|face={reference.face_index!r}'
        # Existing consumers read the final two fields as weight and slant.
        key += f'|{int(bool(style.bold))}|{int(bool(style.italic))}'
        usage = usages.setdefault(key, {"styles": [], "style_ids": set(), "text": []})
        style_ids = usage["style_ids"]
        if isinstance(style_ids, set) and id(style) not in style_ids:
            style_ids.add(id(style))
            styles = usage["styles"]
            if isinstance(styles, list):
                styles.append(style)
        texts = usage["text"]
        if isinstance(texts, list):
            texts.append(text)

    for style in prepared.styles.values():
        checkpoint()
        collect_style(style, "")
    for section in prepared.sections:
        checkpoint()
        for collection in (
            section.headers,
            section.first_page_headers,
            section.even_page_headers,
            section.blocks,
            section.footers,
            section.first_page_footers,
            section.even_page_footers,
        ):
            checkpoint()
            for block in collection:
                checkpoint()
                _resolve_block_fonts(block, collect_style)

    for key, usage in sorted(usages.items()):
        checkpoint()
        styles = usage["styles"]
        texts = usage["text"]
        if not isinstance(styles, list) or not styles or not isinstance(texts, list):
            continue
        style = styles[0]
        text = "".join(str(value) for value in cancellable_items(texts))
        resolution = registry.resolve_style(style, text)
        report.resolutions[key] = resolution
        for used_style in styles:
            checkpoint()
            used_style.font_family = resolution.resolved
            used_style.properties["font_resolution"] = resolution.to_dict()
    prepared.metadata["font_resolution"] = report.to_dict()
    return prepared, report


def _resolve_block_fonts(block: od.Block, resolve_style: Callable[[od.TextStyle, str], None]) -> None:
    if isinstance(block, Paragraph):
        for item in block.content:
            checkpoint()
            if isinstance(item, TextRun):
                resolve_style(item.style, item.text)
    elif isinstance(block, Table):
        for row in block.rows:
            checkpoint()
            for cell in row.cells:
                checkpoint()
                for child in cell.blocks:
                    checkpoint()
                    _resolve_block_fonts(child, resolve_style)


def _read_face(path: Path) -> FontFace | None:
    try:
        try:
            data = read_source(path, SfntLimits().max_input_bytes, cancellation_requested)
        except (InvalidDocumentError, ResourceLimitError):
            data = None  # Keep the established lazy-file profile for larger/unreadable native snapshots.
        if data is not None:
            try:
                face_index = 0 if data.startswith(b'ttcf') else None
                metrics = read_face_metrics(data, cancelled=cancellation_requested,
                                            default_variations=True, face_index=face_index)
                names = read_program_names(data, face_index=face_index)
                glyphs = read_unicode_coverage(data, face_index=face_index)
                checkpoint()
                return FontFace(
                    family=names.get(16) or names.get(1) or path.stem, path=path, weight=metrics.weight,
                    italic=metrics.italic, width_class=metrics.width_class, units_per_em=metrics.units_per_em,
                    average_width=float(metrics.average_width or 500), glyphs=glyphs,
                    embeddable=not bool(metrics.fs_type & (0x0002 | 0x0200)),
                    subsettable=not bool(metrics.fs_type & 0x0100),
                )
            except (InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError):
                checkpoint()
        from fontTools.ttLib import TTFont

        with TTFont(BytesIO(data) if data is not None else path, lazy=True, fontNumber=0) as font:
            names = font["name"]
            family = names.getDebugName(16) or names.getDebugName(1) or path.stem
            os2 = font.get("OS/2")
            head = font.get("head")
            try:
                if data is None:
                    raise UnsupportedDocumentError('No bounded native font snapshot')
                glyphs = read_unicode_coverage(data)
            except (InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError):
                checkpoint()
                glyphs = frozenset((font.getBestCmap() or {}).keys())
            fs_type = int(getattr(os2, "fsType", 0))
            face = FontFace(
                family=family,
                path=path,
                weight=int(getattr(os2, "usWeightClass", 400)),
                italic=bool(getattr(font.get("post"), "italicAngle", 0)),
                width_class=int(getattr(os2, "usWidthClass", 5)),
                units_per_em=int(getattr(head, "unitsPerEm", 1000)),
                average_width=float(getattr(os2, "xAvgCharWidth", 500) or 500),
                glyphs=glyphs,
                embeddable=not bool(fs_type & (0x0002 | 0x0200)),
                subsettable=not bool(fs_type & 0x0100),
            )
            checkpoint()
            return face
    except OperationCancelledError:
        raise
    except Exception:  # noqa: BLE001 - malformed/system fonts are skipped independently
        return None


def _missing(face: FontFace, text: str) -> set[str]:
    return {character for character in cancellable_items(text) if not character.isspace() and ord(character) not in face.glyphs}


def _normalize_family(name: str) -> str:
    return "".join(character for character in cancellable_items(name.casefold()) if character.isalnum())


def _generic_class(name: str) -> str:
    normalized = _normalize_family(name)
    if any(token in normalized for token in ("mono", "courier", "consol", "code")):
        return "mono"
    if any(token in normalized for token in ("serif", "times", "georgia", "cambria")) and "sans" not in normalized:
        return "serif"
    return "sans"


def _system_font_paths() -> tuple[Path, ...]:
    candidates = []
    windows = os.environ.get("WINDIR")
    if windows:
        candidates.append(Path(windows) / "Fonts")
    candidates.extend(
        (
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".fonts",
            Path.home() / "Library/Fonts",
        )
    )
    return tuple(dict.fromkeys(candidates))


__all__ = ["FontFace", "FontResolution", "FontResolutionReport", "FontResolver", "prepare_document_fonts"]
