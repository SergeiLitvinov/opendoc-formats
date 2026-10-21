"""Target-specific diagnostics for canonical color metadata."""

from __future__ import annotations

from collections.abc import Iterator

from opendoc_model.color import ColorValue
from opendoc_model.diagnostics import ConversionReport, IssueSeverity
from opendoc_model.document_model import Block, DocumentModel, Paragraph, Table, TextRun

from opendoc_formats.support.cancellation import checkpoint


def preflight_colors(document: DocumentModel, report: ConversionReport, *, target: str) -> None:
    """Report color metadata that the selected writer cannot faithfully apply."""
    supports_blend = target == "html"
    seen: set[tuple[str, str]] = set()
    for location, color in _document_colors(document):
        checkpoint()
        if color == 'auto':
            if target != 'docx':
                report.add(IssueSeverity.LOSS, 'color-auto',
                           f'{target.upper()} cannot preserve native automatic color semantics', location)
            continue
        if color.icc_profile and ("icc", color.icc_profile) not in seen:
            seen.add(("icc", color.icc_profile))
            report.add(
                IssueSeverity.LOSS,
                "color-icc",
                f"{target.upper()} export converts ICC color {color.icc_profile!r} to sRGB",
                location,
            )
        if color.blend_mode != "normal" and not supports_blend and ("blend", color.blend_mode) not in seen:
            seen.add(("blend", color.blend_mode))
            report.add(
                IssueSeverity.LOSS,
                "color-blend",
                f"{target.upper()} export cannot guarantee blend mode {color.blend_mode!r}",
                location,
            )


def _document_colors(document: DocumentModel) -> Iterator[tuple[str, ColorValue | str]]:
    for style_id, style in document.styles.items():
        checkpoint()
        for field in ("color", "background"):
            checkpoint()
            value = getattr(style, field)
            if isinstance(value, ColorValue) or value == 'auto':
                yield f"styles[{style_id!r}].{field}", value
    for section_index, section in enumerate(document.sections):
        checkpoint()
        for collection_name in (
            "blocks",
            "headers",
            "footers",
            "first_page_headers",
            "first_page_footers",
            "even_page_headers",
            "even_page_footers",
        ):
            checkpoint()
            blocks = getattr(section, collection_name)
            yield from _block_colors(blocks, f"sections[{section_index}].{collection_name}")


def _block_colors(blocks: list[Block], location: str) -> Iterator[tuple[str, ColorValue | str]]:
    for block_index, block in enumerate(blocks):
        checkpoint()
        block_location = f"{location}[{block_index}]"
        if isinstance(block, Paragraph):
            for inline_index, item in enumerate(block.content):
                checkpoint()
                if isinstance(item, TextRun):
                    for field in ("color", "background"):
                        checkpoint()
                        value = getattr(item.style, field)
                        if isinstance(value, ColorValue) or value == 'auto':
                            yield f"{block_location}.content[{inline_index}].style.{field}", value
        elif isinstance(block, Table):
            for row_index, row in enumerate(block.rows):
                checkpoint()
                for cell_index, cell in enumerate(row.cells):
                    checkpoint()
                    yield from _block_colors(
                        cell.blocks,
                        f"{block_location}.rows[{row_index}].cells[{cell_index}].blocks",
                    )


__all__ = ["preflight_colors"]
