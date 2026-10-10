"""Bridge explicit HTML table declarations to the common model contract."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from opendoc_model import (
    ArtifactLimitError,
    DocumentModel,
    Section,
    Table,
    TableCellSemantics,
    TableRowGroup,
    TableRowSemantics,
    TableSemantics,
    set_table_cell_semantics,
    set_table_row_semantics,
    set_table_semantics,
)

SCOPE_TO_MODEL = {'row': 'row', 'col': 'column', 'rowgroup': 'row-group'}
SCOPE_TO_HTML = {value: key for key, value in SCOPE_TO_MODEL.items()}
IMPORTED = 'html_table_semantics_imported'


def import_table_semantics(
    table: Table, *, identifier: Callable[[], str], resources: dict, styles: dict,
    ambiguous_ids: frozenset[str] = frozenset(),
) -> str | None:
    """Keep malformed declarations in the source profile rather than invent valid associations."""
    nodes: list[Any] = [table, *table.rows, *(cell for row in table.rows for cell in row.cells)]
    if any(node.properties.get('anchor_id') in ambiguous_ids for node in nodes):
        return 'Duplicate source IDs make table declarations ambiguous'
    previous = [(node, dict(node.properties)) for node in nodes]
    try:
        groups = {}
        for row_index, row in enumerate(table.rows):
            native_group = row.properties.get('html_row_group_id', 0)
            group_id = f'group-{native_group}'
            group_kind = {'thead': 'head', 'tbody': 'body', 'tfoot': 'foot'}[row.properties.get('html_row_group', 'tbody')]
            groups.setdefault(group_id, TableRowGroup(group_id, group_kind))
            set_table_row_semantics(row, TableRowSemantics(f'row-{row_index + 1}', group_id))
            for cell in row.cells:
                props = cell.properties
                cell_id = str(props.get('anchor_id') or identifier())
                set_table_cell_semantics(cell, TableCellSemantics(
                    cell_id, 'header' if props.get('html_cell_tag') == 'th' else 'data',
                    SCOPE_TO_MODEL.get(props.get('html_scope')), tuple(str(props.get('html_headers', '')).split()),
                ))
        set_table_semantics(table, TableSemantics(row_groups=tuple(groups.values())))
        errors = DocumentModel(sections=[Section(blocks=[table])], resources=resources, styles=styles).validate()
        if errors:
            raise ValueError('; '.join(errors))
    except ArtifactLimitError:
        raise
    except ValueError as error:
        for node, properties in previous:
            node.properties.clear()
            node.properties.update(properties)
        return str(error)
    for node in nodes:
        node.properties[IMPORTED] = True
    return None


def import_caption_semantics(
    table: Table, captions: list, *, identifier: Callable[[], str], resources: dict, styles: dict,
    ambiguous_ids: frozenset[str] = frozenset(),
) -> str | None:
    """Associate explicit caption paragraphs without changing their ownership or text."""
    from dataclasses import replace

    from opendoc_model import Anchor, Paragraph, get_anchor, get_table_semantics, set_anchor

    if not all(isinstance(node, Paragraph) for node in captions):
        return 'Caption contains blocks outside the common paragraph contract'
    semantics = get_table_semantics(table)
    if semantics is None:
        return 'Table declarations are outside the common contract'
    nodes = [table, *captions]
    if any(node.properties.get('anchor_id') in ambiguous_ids for node in nodes):
        return 'Duplicate source IDs make caption associations ambiguous'
    previous = [(node, dict(node.properties)) for node in nodes]
    try:
        ids = []
        for node in nodes:
            anchor = get_anchor(node)
            if anchor is None:
                anchor = Anchor(str(node.properties.get('anchor_id') or identifier()))
                set_anchor(node, anchor)
            node.properties['html_anchor_imported'] = True
            if node is not table:
                ids.append(anchor.id)
        set_table_semantics(table, replace(semantics, caption_ids=tuple(ids)))
        errors = DocumentModel(sections=[Section(blocks=[*captions, table])], resources=resources, styles=styles).validate()
        if errors:
            raise ValueError('; '.join(errors))
    except ArtifactLimitError:
        raise
    except ValueError as error:
        for node, properties in previous:
            node.properties.clear()
            node.properties.update(properties)
        return str(error)
    for node in nodes:
        node.properties['html_caption_semantics_imported'] = True
        node.properties['html_caption_owner'] = get_anchor(table).id
    return None
