"""Bridge explicit HTML table declarations to the common model contract."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from opendoc_model import (
    ArtifactLimitError,
    DocumentLimits,
    DocumentModel,
    Section,
    Table,
    TableCellSemantics,
    TableColumnGroup,
    TableRowGroup,
    TableRowSemantics,
    TableSemantics,
    set_table_cell_semantics,
    set_table_row_semantics,
    set_table_semantics,
)

SCOPE_TO_MODEL = {'row': 'row', 'col': 'column', 'rowgroup': 'row-group', 'colgroup': 'column-group'}
SCOPE_TO_HTML = {value: key for key, value in SCOPE_TO_MODEL.items()}
IMPORTED = 'html_table_semantics_imported'


def import_table_semantics(
    table: Table, *, identifier: Callable[[], str], resources: dict, styles: dict,
    ambiguous_ids: frozenset[str] = frozenset(),
) -> str | None:
    """Keep malformed declarations in the source profile rather than invent valid associations."""
    nodes: list[Any] = [table, *table.rows, *(cell for row in table.rows for cell in row.cells)]
    if table.properties.get('html_column_groups_invalid'):
        return 'Column group declarations are outside the bounded source profile'
    if any(node.properties.get('anchor_id') in ambiguous_ids for node in nodes):
        return 'Duplicate source IDs make table declarations ambiguous'
    previous = [(node, dict(node.properties)) for node in nodes]
    try:
        columns = tuple(TableColumnGroup(**value) for value in table.properties.get('html_column_groups', []))
        if any(group.id in ambiguous_ids for group in columns):
            raise ValueError('Duplicate source IDs make column groups ambiguous')
        groups = {}
        occupied = []
        work = 0
        for row_index, row in enumerate(table.rows):
            native_group = row.properties.get('html_row_group_id', 0)
            group_id = f'group-{native_group}'
            group_kind = {'thead': 'head', 'tbody': 'body', 'tfoot': 'foot'}[row.properties.get('html_row_group', 'tbody')]
            groups.setdefault(group_id, TableRowGroup(group_id, group_kind))
            set_table_row_semantics(row, TableRowSemantics(f'row-{row_index + 1}', group_id))
            occupied = [interval for interval in occupied if interval[2] > row_index]
            column = 0
            for cell in row.cells:
                while True:
                    blocking = None
                    for first, last, _ in occupied:
                        work += 1
                        if work > 100_000:
                            raise ArtifactLimitError('HTML table grid work exceeds 100000')
                        if first < column + cell.column_span and column < last:
                            blocking = last
                            break
                    if blocking is None:
                        break
                    column = blocking
                props = cell.properties
                cell_id = str(props.get('anchor_id') or identifier())
                scope = SCOPE_TO_MODEL.get(props.get('html_scope'))
                column_group = None
                if scope == 'column-group':
                    matches = [group.id for group in columns
                               if group.start <= column and column + cell.column_span <= group.start + group.span]
                    if len(matches) != 1:
                        raise ValueError('Column-group scope has no unambiguous containing group')
                    column_group = matches[0]
                set_table_cell_semantics(cell, TableCellSemantics(
                    cell_id, 'header' if props.get('html_cell_tag') == 'th' else 'data',
                    scope, tuple(str(props.get('html_headers', '')).split()), column_group,
                ))
                end = column + cell.column_span
                occupied.append((column, end, row_index + cell.row_span))
                column = end
        set_table_semantics(table, TableSemantics(row_groups=tuple(groups.values()), column_groups=columns))
        errors = DocumentModel(sections=[Section(blocks=[table])], resources=resources, styles=styles).validate()
        if errors:
            raise ValueError('; '.join(errors))
    except ArtifactLimitError:
        raise
    except (ValueError, TypeError, KeyError) as error:
        for node, properties in previous:
            node.properties.clear()
            node.properties.update(properties)
        return str(error)
    for node in nodes:
        node.properties[IMPORTED] = True
    return None


def migrate_html_tables(document: DocumentModel, *, limits: DocumentLimits | None = None) -> None:
    """Promote old explicit source declarations once, without resurrecting removed records."""
    from collections import Counter
    from dataclasses import replace

    from opendoc_model import (
        DiagnosticIssue,
        IssueSeverity,
        Paragraph,
        PreservationRecord,
        PreservationState,
        Provenance,
        TableCell,
        get_anchor,
        get_integration,
        set_integration,
        walk_model,
    )

    references = [reference for reference in walk_model(document, limits=limits)
                  if hasattr(reference.node, 'properties')]
    source_ids: Counter[str] = Counter()
    for reference in references:
        identifiers = set()
        if isinstance(value := reference.node.properties.get('anchor_id'), str):
            identifiers.add(value)
        if 'opendoc.anchor' in reference.node.properties and (anchor := get_anchor(reference.node)) is not None:
            identifiers.add(anchor.id)
        source_ids.update(identifiers)
    reserved = set(source_ids)
    ambiguous = frozenset(key for key, count in source_ids.items() if count > 1)
    count = 0

    def identifier() -> str:
        nonlocal count
        while True:
            count += 1
            value = f'opendoc-html-{count}'
            if value not in reserved:
                reserved.add(value)
                return value

    captions = {}
    for reference in references:
        owner = reference.node
        collections = [owner.blocks, owner.headers, owner.footers] if isinstance(owner, Section) else (
            [owner.blocks] if isinstance(owner, TableCell) else []
        )
        for blocks in collections:
            pending = []
            for block in blocks:
                if isinstance(block, Paragraph) and block.properties.get('html_table_caption'):
                    pending.append(block)
                else:
                    if isinstance(block, Table) and pending:
                        captions[id(block)] = pending
                    pending = []
    records = []
    for reference in references:
        table = reference.node
        if not isinstance(table, Table):
            continue
        nodes = [table, *table.rows, *(cell for row in table.rows for cell in row.cells)]
        if any(node.properties.get(IMPORTED) or node.properties.get('html_table_semantics_migration_attempted')
               or any(key.startswith('opendoc.table-') for key in node.properties) for node in nodes):
            continue
        if not any('html_cell_tag' in cell.properties for row in table.rows for cell in row.cells):
            continue
        error = import_table_semantics(
            table, identifier=identifier, resources=document.resources, styles=document.styles, ambiguous_ids=ambiguous,
        )
        if not error and id(table) in captions:
            error = import_caption_semantics(
                table, captions[id(table)], identifier=identifier, resources=document.resources,
                styles=document.styles, ambiguous_ids=ambiguous,
            )
        table.properties['html_table_semantics_migration_attempted'] = True
        if error:
            records.append(PreservationRecord(
                DiagnosticIssue('html-table-semantics', IssueSeverity.LOSS, error, reference.path,
                                reason='ambiguous-legacy-table'),
                PreservationState.LOST, provenance=Provenance('json', object_id=reference.path),
            ))
    if records:
        integration = get_integration(document, limits=limits)
        from opendoc_model import IntegrationModel

        integration = integration or IntegrationModel()
        set_integration(document, replace(integration, preservation=(*integration.preservation, *records),
                                         assessed_features=tuple(dict.fromkeys(
                                             (*integration.assessed_features, *(record.issue.code for record in records)),
                                         )), assessment_complete=False), limits=limits)


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
