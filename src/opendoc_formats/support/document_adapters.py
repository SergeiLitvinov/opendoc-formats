"""Совместимые адаптеры между старым ``Text`` и богатым ``DocumentModel``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast

from opendoc_model import DocumentLimits, integration_from_dict, integration_to_dict, set_integration, walk_model
from opendoc_model.document_model import (
    Block as RichBlock,
)
from opendoc_model.document_model import (
    DocumentModel,
    Formula,
    Image,
    Paragraph,
    Section,
    TableCell,
    TableRow,
    TextRun,
)
from opendoc_model.document_model import (
    Table as RichTable,
)
from opendoc_model.properties import ParagraphProperties, TableProperties

from opendoc_formats.support.cancellation import cancellable_items, cancellation_scope, checkpoint
from opendoc_formats.support.text_projection import in_body, projection_losses
from opendoc_formats.types import Block, BlockType, DocFormat, Table, Text


def text_to_document(text: Text, *, limits: DocumentLimits | None = None,
                     cancelled: Callable[[], bool] | None = None) -> DocumentModel:
    """Поднять извлечённый ``Text`` в богатую модель без выдумывания оформления."""
    with cancellation_scope(cancelled, 'Legacy text to Model', inherit=True):
        return _text_to_document(text, limits=limits)


def _checked_rows(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        raise ValueError('Legacy table rows must be a list')
    for row in cancellable_items(value):
        if not isinstance(row, list) or any(not isinstance(cell, str) for cell in cancellable_items(row)):
            raise ValueError('Legacy table rows must contain lists of strings')
    return cast(list[list[str]], value)


def _rich_table(rows: list[list[str]], page: int, properties: dict[str, Any] | None = None) -> RichTable:
    rendered = [TableRow(cells=[TableCell(blocks=[Paragraph(content=[TextRun(cell)])])
                               for cell in cancellable_items(row)]) for row in cancellable_items(rows)]
    return RichTable(rows=rendered, properties=cast(TableProperties, {**(properties or {}), 'page': page}))


def _text_to_document(text: Text, *, limits: DocumentLimits | None) -> DocumentModel:
    blocks: list[RichBlock] = []
    consumed: set[int] = set()
    for block in cancellable_items(text.blocks):
        if block.type is BlockType.TABLE and ('rows' in block.meta or 'table_index' in block.meta):
            if 'table_index' in block.meta:
                index = block.meta['table_index']
                if type(index) is not int or not 0 <= index < len(text.tables) or index in consumed:
                    raise ValueError('Invalid or repeated legacy table_index')
                table = text.tables[index]
                rows = _checked_rows(table.rows)
                if table.page != block.page or ('rows' in block.meta and _checked_rows(block.meta['rows']) != rows):
                    raise ValueError('Conflicting linked legacy table data')
                consumed.add(index)
            else:
                rows = _checked_rows(block.meta['rows'])
            properties = {key: value for key, value in block.meta.items() if key not in {'rows', 'table_index'}}
            blocks.append(_rich_table(rows, block.page, properties))
            continue
        properties = {"legacy_type": block.type.value, "level": block.level, "page": block.page, **block.meta}
        style_id = f"heading-{block.level}" if block.type is BlockType.HEADING and block.level else None
        blocks.append(Paragraph(
            content=[TextRun(block.text)], style_id=style_id, properties=cast(ParagraphProperties, properties),
        ))
    for index, table in enumerate(cancellable_items(text.tables)):
        if index not in consumed:
            blocks.append(_rich_table(_checked_rows(table.rows), table.page))
    if not blocks and text.plain:
        blocks.append(Paragraph(content=[TextRun(text.plain)]))
    document = DocumentModel(
        sections=[Section(blocks=blocks)],
        metadata={
            "language": text.language,
            "engine": text.engine,
            "warnings": list(text.warnings),
            "pages": text.pages,
        },
        source_format=text.source_format.value,
    )
    if text.diagnostics is not None:
        set_integration(document, text.diagnostics, limits=limits)
    for _ in walk_model(document, limits=limits):
        checkpoint()
    return document


def document_to_text(document: DocumentModel, *, limits: DocumentLimits | None = None,
                     cancelled: Callable[[], bool] | None = None) -> Text:
    """Получить совместимый текстовый вид богатой модели для старого pipeline."""
    with cancellation_scope(cancelled, 'Model to legacy text', inherit=True):
        return _document_to_text(document, limits=limits)


def _document_to_text(document: DocumentModel, *, limits: DocumentLimits | None) -> Text:
    references = list(cancellable_items(walk_model(document, limits=limits)))
    blocks: list[Block] = []
    tables: list[Table] = []
    plain_parts: list[str] = []
    values: dict[str, str] = {}
    table_rows: dict[str, list[list[str]]] = {}
    for reference in reversed(references):
        checkpoint()
        if not in_body(reference):
            continue
        block, path = reference.node, reference.path
        if isinstance(block, Paragraph):
            parts = []
            for index, item in enumerate(cancellable_items(block.content)):
                if isinstance(item, TextRun):
                    parts.append(item.text)
                elif isinstance(item, (Formula, Image)):
                    parts.append(values.pop(f'{path}.content[{index}]'))
            values[path] = ''.join(parts)
        elif isinstance(block, Formula):
            values[path] = block.fallback_text or block.value
        elif isinstance(block, Image):
            values[path] = block.alt_text
        elif isinstance(block, RichTable):
            rows = []
            for row_index, row in enumerate(cancellable_items(block.rows)):
                cells = []
                for cell_index, cell in enumerate(cancellable_items(row.cells)):
                    cell_path = f'{path}.rows[{row_index}].cells[{cell_index}]'
                    cells.append('\n'.join(values.pop(f'{cell_path}.blocks[{index}]')
                                           for index, _ in enumerate(cancellable_items(cell.blocks))))
                rows.append(cells)
            if reference.parent is not None and isinstance(reference.parent.node, Section):
                table_rows[path] = rows
            values[path] = '\n'.join(' | '.join(row) for row in cancellable_items(rows))

    for reference in references:
        checkpoint()
        if reference.parent is None or not isinstance(reference.parent.node, Section) or reference.field != 'blocks':
            continue
        block, path = reference.node, reference.path
        text = values[path]
        if isinstance(block, Paragraph):
            legacy_type = block.properties.get("legacy_type", BlockType.PARAGRAPH.value)
            try:
                block_type = BlockType(legacy_type)
            except ValueError:
                block_type = BlockType.PARAGRAPH
            legacy = Block(
                type=block_type,
                text=text,
                level=int(block.properties.get("level", 0)),
                page=int(block.properties.get("page", 0)),
            )
            blocks.append(legacy)
            if text:
                plain_parts.append(text)
        elif isinstance(block, RichTable):
            rows = table_rows[path]
            page = int(block.properties.get('page', 0))
            blocks.append(Block(BlockType.TABLE, text=text, page=page,
                                meta={'rows': rows, 'table_index': len(tables)}))
            tables.append(Table(rows=rows, page=page))
            plain_parts.append(text)
        elif isinstance(block, Formula):
            value = block.fallback_text or block.value
            blocks.append(Block(type=BlockType.EQUATION, text=value))
            plain_parts.append(value)
        elif isinstance(block, Image) and block.alt_text:
            blocks.append(Block(type=BlockType.CAPTION, text=block.alt_text))
            plain_parts.append(block.alt_text)

    raw_format = document.source_format or DocFormat.UNKNOWN.value
    try:
        source_format = DocFormat(raw_format)
    except ValueError:
        source_format = DocFormat.UNKNOWN
    from opendoc_formats.support.text_diagnostics import ledger, source_diagnostics

    warnings, diagnostics = source_diagnostics(document, limits=limits)
    losses = projection_losses(document, references, limits=limits)
    if losses:
        bound = []
        for record in cancellable_items(losses):
            bound.append(replace(record, issue=replace(record.issue, measurement={
                **(record.issue.measurement or {}), 'legacy_warning_path': f'metadata.warnings[{len(warnings)}]',
            })))
            warnings.append(record.issue.message)
        combined = ledger((diagnostics.preservation if diagnostics else ())+tuple(bound),
                          extra=diagnostics.extra if diagnostics else None)
        diagnostics = integration_from_dict(integration_to_dict(combined, limits=limits), limits=limits)
    return Text(
        blocks=blocks,
        tables=tables,
        plain="\n".join(plain_parts),
        language=str(document.metadata.get("language", "und")),
        source_format=source_format,
        engine=str(document.metadata.get("engine", "document-model")),
        warnings=warnings,
        pages=int(document.metadata.get("pages", 0)),
        diagnostics=diagnostics,
    )


__all__ = ["document_to_text", "text_to_document"]
