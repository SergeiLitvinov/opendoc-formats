"""Shared font usage collection and deterministic OpenType subsetting."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from opendoc_model.document_model import Block, DocumentModel, Paragraph, Table, TextRun

from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.fonts.subset_cache import SubsetCache, SubsetKey
from opendoc_formats.support.cancellation import checkpoint

_SUBSET_CACHE = SubsetCache()


def _reset_subset_cache_after_fork() -> None:
    global _SUBSET_CACHE
    # A fork may inherit a cache lock held by a thread which does not exist in the child.
    _SUBSET_CACHE = SubsetCache(maximum_bytes=_SUBSET_CACHE.maximum_bytes,
                                maximum_entries=_SUBSET_CACHE.maximum_entries)


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_reset_subset_cache_after_fork)


@dataclass(frozen=True)
class FontUsage:
    family: str
    path: Path
    bold: bool
    italic: bool
    characters: frozenset[str]
    embeddable: bool
    subsettable: bool


def collect_font_usages(document: DocumentModel) -> list[FontUsage]:
    usages: dict[tuple[str, str, bool, bool], set[str]] = {}
    embeddable: dict[tuple[str, str, bool, bool], bool] = {}
    subsettable: dict[tuple[str, str, bool, bool], bool] = {}

    def collect(blocks: list[Block]) -> None:
        for block in blocks:
            checkpoint()
            if isinstance(block, Paragraph):
                for item in block.content:
                    checkpoint()
                    if not isinstance(item, TextRun):
                        continue
                    resolution = item.style.properties.get("font_resolution")
                    if not isinstance(resolution, dict) or not resolution.get("path"):
                        continue
                    key = (
                        str(resolution.get("resolved") or item.style.font_family or "Font"),
                        str(resolution["path"]),
                        bool(item.style.bold),
                        bool(item.style.italic),
                    )
                    usages.setdefault(key, set()).update(item.text)
                    embeddable[key] = bool(resolution.get("embeddable", False))
                    subsettable[key] = bool(resolution.get("subsettable", True))
            elif isinstance(block, Table):
                for row in block.rows:
                    checkpoint()
                    for cell in row.cells:
                        checkpoint()
                        collect(cell.blocks)

    for section in document.sections:
        checkpoint()
        for blocks in (
            section.blocks,
            section.headers,
            section.footers,
            section.first_page_headers,
            section.first_page_footers,
            section.even_page_headers,
            section.even_page_footers,
        ):
            collect(blocks)
    return [
        FontUsage(family, Path(path), bold, italic, frozenset(characters), embeddable[key], subsettable[key])
        for key, characters in sorted(usages.items())
        for family, path, bold, italic in (key,)
    ]


def subset_font(usage: FontUsage) -> bytes:
    """Return a deterministic glyph subset, falling back to the full font if unsupported."""
    checkpoint()
    source = usage.path.read_bytes()
    checkpoint()
    if not usage.characters or not usage.subsettable:
        return source
    cache_key: SubsetKey | None = None
    engine: tuple[object, ...] = ()
    inserted = False
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont

        options = subset.Options()
        options.recalc_timestamp = False
        options.canonical_order = True
        # Keep copyright, license/URL and localized notices with the program.
        options.name_IDs = ['*']
        options.name_languages = ['*']
        options.name_legacy = True
        characters = ''.join(sorted(usage.characters))
        engine = (TTFont, TTFont.__init__, TTFont.__enter__, TTFont.__exit__, TTFont.save, TTFont.close,
                  subset.Subsetter, subset.Subsetter.__init__, subset.Subsetter.populate, subset.Subsetter.subset,
                  subset.Options, subset.Options.__init__)
        try:
            settings = json.dumps(vars(options), sort_keys=True, ensure_ascii=True, allow_nan=False)
        except (TypeError, ValueError):
            settings = None  # Unfamiliar option objects still use the established engine, without caching.
        if settings is not None:
            cache_key = source, characters, settings
            cached = _SUBSET_CACHE.get(cache_key, engine)
            checkpoint()
            if cached is not None:
                return cached
        checkpoint()
        with TTFont(BytesIO(source), recalcTimestamp=False) as font:
            checkpoint()
            subsetter = subset.Subsetter(options=options)
            subsetter.populate(text=characters)
            checkpoint()
            subsetter.subset(font)
            checkpoint()
            output = BytesIO()
            font.save(output, reorderTables=True)
            checkpoint()
            result = output.getvalue()
        checkpoint()
        if cache_key is not None:
            inserted = _SUBSET_CACHE.put(cache_key, engine, result)
            checkpoint()
        return result
    except OperationCancelledError:
        if inserted and cache_key is not None:
            _SUBSET_CACHE.discard(cache_key, engine)
        raise
    except Exception:  # noqa: BLE001 - unsupported fonts remain embeddable without subsetting
        checkpoint()
        return source


__all__ = ["FontUsage", "collect_font_usages", "subset_font"]
