"""Bounded check of rendered plain text before PDF publication."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from typing import Any

from opendoc_model import ConversionReport, IssueSeverity, Paragraph, Section, Table, TextRun


def _normalized(text: str) -> str:
    return ''.join(unicodedata.normalize('NFKC', text).split()).replace('\u00ad', '')


def _runs(blocks: list, location: str) -> Iterator[tuple[str, str]]:
    for index, block in enumerate(blocks):
        block_location = f'{location}[{index}]'
        if isinstance(block, Paragraph):
            pptx = block.properties.get('pptx')
            if isinstance(pptx, dict) and isinstance(pptx.get('chart'), dict):
                continue  # Chart labels are handled by the chart renderer's own diagnostics.
            text, start = '', 0
            for number, inline in enumerate(block.content):
                if isinstance(inline, TextRun):
                    if not text:
                        start = number
                    text += inline.text
                elif text:
                    yield text, f'{block_location}.content[{start}]'
                    text = ''
            if text:
                yield text, f'{block_location}.content[{start}]'
        elif isinstance(block, Table):
            for row_index, row in enumerate(block.rows):
                for cell_index, cell in enumerate(row.cells):
                    yield from _runs(cell.blocks, f'{block_location}.rows[{row_index}].cells[{cell_index}].blocks')


def verify_section_text(pdf: Any, section: Section, report: ConversionReport, location: str) -> None:
    """Require each plain text occurrence, allowing whitespace/ligature normalization.

    This detects omissions; it does not prove placement, reading order or glyph fidelity.
    Formula, image and chart representations retain their separate diagnostics.
    """
    expected = []
    characters = 0
    for field in ('blocks', 'headers', 'footers'):
        for text, source in _runs(getattr(section, field), location + '.' + field):
            characters += len(text)
            if characters > 2_000_000 or len(expected) >= 100_000:
                report.add(IssueSeverity.ERROR, 'pdf-text-limit', 'Text verification exceeds its finite profile', source)
                return
            normalized = _normalized(text)
            if normalized:
                expected.append((normalized, source, field))
    if not expected:
        return
    extracted: dict[str, list[str]] = {field: [] for field in ('blocks', 'headers', 'footers')}
    characters = 0
    for page in pdf:
        settings = section.page
        if section.headers or section.footers:
            regions = {
                'blocks': (settings.margin_left.pt, settings.margin_top.pt,
                           settings.width.pt - settings.margin_right.pt, settings.height.pt - settings.margin_bottom.pt),
                'headers': (settings.margin_left.pt, max(2, settings.margin_top.pt * .15),
                            settings.width.pt - settings.margin_right.pt, max(4, settings.margin_top.pt - 4)),
                'footers': (settings.margin_left.pt, min(settings.height.pt - 4, settings.height.pt-settings.margin_bottom.pt+4),
                            settings.width.pt - settings.margin_right.pt, settings.height.pt - 2),
            }
        else:
            regions = {'blocks': tuple(page.rect)}
        for field, rectangle in regions.items():
            text = page.get_text(clip=rectangle)
            characters += len(text)
            if characters > 4_000_000:
                report.add(IssueSeverity.ERROR, 'pdf-text-limit', 'Rendered text exceeds the verification profile', location)
                return
            extracted[field].append(text)
    available_by_field = {field: _normalized(''.join(texts)) for field, texts in extracted.items()}
    work = 0
    checked = 0
    for text, source, field in expected:
        available = available_by_field[field]
        work += len(available)
        if work > 100_000_000:
            report.add(IssueSeverity.ERROR, 'pdf-text-limit', 'Text verification work exceeds the profile', source)
            return
        position = available.find(text)
        if position < 0:
            report.add(IssueSeverity.ERROR, 'pdf-text-content',
                       'PDF layout did not preserve a plain text occurrence; output was not published', source)
        else:
            available_by_field[field] = available[:position] + available[position + len(text):]
            checked += 1
    report.metrics['pdf_text_checked_runs'] = report.metrics.get('pdf_text_checked_runs', 0) + checked
