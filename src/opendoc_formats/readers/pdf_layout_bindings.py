"""Exact source-observed Unicode groups to logical ranges; never reading-order inference."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from opendoc_model import (
    Anchor,
    ArtifactLimitError,
    DocumentLimits,
    DocumentModel,
    Formula,
    Image,
    IntegrationModel,
    Paragraph,
    Table,
    TextCluster,
    TextLayout,
    TextPosition,
    TextRange,
    TextRun,
    TextStyle,
    get_anchor,
    get_font_reference,
    set_anchor,
    set_font_reference,
    walk_model,
)

from opendoc_formats.pdf import PdfTextPlacement
from opendoc_formats.readers.pdf_styles import native_text_style
from opendoc_formats.support.cancellation import check_cancelled


def _unicode_groups(observation: PdfTextPlacement,
                    cancelled: Callable[[], bool] | None) -> tuple[str, list[tuple[int, int]]] | None:
    characters: list[str] = []
    offsets: list[tuple[int, int]] = []
    previous = None
    start = 0
    for glyph in observation.glyphs:
        check_cancelled(cancelled, 'PDF logical Unicode group')
        code = glyph.unicode
        if not 0 <= code <= 0x10ffff or 0xd800 <= code <= 0xdfff or code == 0xfffd:
            return None
        if glyph.glyph_id >= 0:
            if previous is not None:
                offsets.append((start, len(characters)))
            start = len(characters)
            previous = glyph
        elif glyph.glyph_id != -1 or previous is None or glyph.transform != previous.transform:
            return None
        characters.append(chr(code))
    if previous is None:
        return None
    offsets.append((start, len(characters)))
    return ''.join(characters), offsets


class LogicalBindings:
    def __init__(self, document: DocumentModel, integration: IntegrationModel, budget: DocumentLimits,
                 cancelled: Callable[[], bool] | None) -> None:
        self.budget, self.cancelled = budget, cancelled
        self.ranges = list(integration.ranges)
        self.used_ranges = {value.id for value in self.ranges}
        self.used_anchors: set[str] = set()
        self.owners: dict[int, tuple[TextRun, str]] = {}
        self.index: dict[tuple[int, tuple[float, float], str, str], list[TextRun]] = {}
        self.range_cache = {
            (value.start.node_id, value.start.offset, value.end.offset): value.id
            for value in self.ranges
            if value.id.startswith('pdf-text-layout-') and value.start.node_id == value.end.node_id
            and value.start.affinity == value.end.affinity == 'after'
        }
        self.verified: list[TextLayout] = []
        self.source_styles: dict[tuple[tuple[float, float], str, str], list[TextStyle]] = {}
        for location in walk_model(document, limits=budget):
            check_cancelled(cancelled, 'PDF logical anchor index')
            if isinstance(location.node, (Paragraph, Table, Formula, Image, TextRun)):
                anchor = get_anchor(location.node, limits=budget)
                if anchor is not None:
                    self.used_anchors.add(anchor.id)
        for page, section in enumerate(document.sections):
            for number, location in enumerate(walk_model(section, limits=budget)):
                check_cancelled(cancelled, 'PDF logical run index')
                run = location.node
                if not isinstance(run, TextRun) or not run.text:
                    continue
                font = get_font_reference(run.style, limits=budget)
                origin = run.properties.get('pdf_origin')
                if (font is None or font.face_index not in (None, 0) or not isinstance(origin, (list, tuple))
                        or len(origin) != 2
                        or any(type(value) not in (int, float) or not math.isfinite(value) for value in origin)):
                    continue
                point = float(origin[0]), float(origin[1])
                self.index.setdefault((page, point, font.resource_id, run.text), []).append(run)
                self.owners[id(run)] = run, f'pdf-layout-run-{page}-{number}'

    @staticmethod
    def _unique(base: str, used: set[str]) -> str:
        value, number = base, 1
        while value in used:
            value, number = f'{base}-{number}', number+1
        used.add(value)
        return value

    def read_source_styles(self, page: Any, engine: Any) -> None:
        """Inspect text-only style declarations from the same immutable source as the glyphs."""
        flags = engine.TEXTFLAGS_DICT & ~engine.TEXT_MEDIABOX_CLIP & ~engine.TEXT_PRESERVE_IMAGES
        raw = page.get_text('dict', sort=False, flags=flags, clip=engine.INFINITE_RECT())
        check_cancelled(self.cancelled, 'PDF logical source styles')
        self.source_styles = {}
        count = size = 0
        for block in raw.get('blocks', []):
            for line in block.get('lines', []):
                for span in line.get('spans', []):
                    check_cancelled(self.cancelled, 'PDF logical source style')
                    count += 1
                    size += len(json.dumps(span, ensure_ascii=False, allow_nan=False).encode('utf-8'))
                    if count > self.budget.max_nodes or size > self.budget.max_bytes:
                        nodes = count > self.budget.max_nodes
                        raise ArtifactLimitError('PDF logical source styles exceed budget', path='$.text_layouts.source_styles',
                                                 quota='nodes' if nodes else 'bytes',
                                                 maximum=self.budget.max_nodes if nodes else self.budget.max_bytes)
                    origin = tuple(span['origin'])
                    key = (origin[0], origin[1]), span['font'], span['text']
                    self.source_styles.setdefault(key, []).append(native_text_style(
                        span['font'], span['size'], int(span['flags']), int(span['color'])))

    def bind(self, layout: TextLayout, observation: PdfTextPlacement) -> TextLayout:
        check_cancelled(self.cancelled, 'PDF logical binding')
        if (layout.page_id is None or len(layout.fonts) != 1 or layout.fonts[0].face_index != 0
                or not layout.glyphs or any(row[1] is None for row in layout.glyphs)):
            return layout
        grouped = _unicode_groups(observation, self.cancelled)
        if grouped is None:
            return layout
        text, groups = grouped
        if len(groups) != len(layout.glyphs):
            return layout
        first = observation.glyphs[0]
        matches = self.index.get((observation.page_index, (first.transform[4], first.transform[5]),
                                  layout.fonts[0].resource_id, text), [])
        if len(matches) != 1:
            return layout
        run = matches[0]
        styles = self.source_styles.get(((first.transform[4], first.transform[5]), observation.font, text), [])
        if len(styles) != 1:
            return layout
        expected = replace(styles[0])
        set_font_reference(expected, get_font_reference(run.style, limits=self.budget), limits=self.budget)
        if expected != run.style:
            return layout
        anchor = get_anchor(run, limits=self.budget)
        if anchor is None:
            anchor = Anchor(self._unique(self.owners[id(run)][1], self.used_anchors))
            set_anchor(run, anchor, limits=self.budget)
        clusters = []
        for glyph, (start, end) in enumerate(groups):
            check_cancelled(self.cancelled, 'PDF logical range')
            key = anchor.id, start, end
            if key not in self.range_cache:
                identifier = self._unique(f'{layout.id}-range-{glyph}', self.used_ranges)
                self.ranges.append(TextRange(identifier, TextPosition(anchor.id, start), TextPosition(anchor.id, end)))
                self.range_cache[key] = identifier
            clusters.append(TextCluster((glyph,), (self.range_cache[key],)))
        result = replace(layout, clusters=tuple(clusters),
                         extra={**layout.extra, 'opendoc_formats.logical_mapping': 'exact-source-unicode-origin-program'})
        self.verified.append(result)
        return result
