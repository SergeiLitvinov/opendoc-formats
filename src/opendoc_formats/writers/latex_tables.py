"""Editable finite tabular output, without an Office intermediate or images."""

from collections.abc import Callable

from opendoc_model import ArtifactLimitError, DocumentLimits, Formula, Paragraph, Table

from opendoc_formats.support.cancellation import checkpoint
from opendoc_formats.tex_tables import KEY, MULTICOLUMN_KEY, TableProfileError, layout, multicolumn_layout


def table_tex(table: Table, render: Callable[[Paragraph], str | None], *, limits: DocumentLimits | None = None) -> str | None:
    """Return None for geometry, row spanning or content outside the accepted cell profile."""
    if (not table.rows or table.style_id or table.box or table.visual_surrogate or set(table.properties)-{KEY, 'source_span'}
            or not table.rows[0].cells):
        return None
    maximum = (limits or DocumentLimits()).max_nodes
    row_widths = []
    merged = False
    for row in table.rows:
        width = 0
        for cell in row.cells:
            checkpoint()
            width += cell.column_span
            merged |= cell.column_span != 1 or MULTICOLUMN_KEY in cell.properties
            if width > maximum:
                raise ArtifactLimitError('TeX logical column width exceeds native work budget',
                                         path='table.columns', quota='nodes', maximum=maximum)
        row_widths.append(width)
    columns = row_widths[0]
    if (merged or KEY in table.properties) and any(width != columns for width in row_widths):
        raise TableProfileError('Inconsistent logical row widths in native TeX table')
    if KEY in table.properties and table.properties[KEY] is None:
        raise TableProfileError('Invalid explicit tabular source layout')
    spec, rules, trailing = layout(table.properties.get(KEY), len(table.rows), columns)
    boundaries = []
    alignments = []
    boundary = ''
    for char in spec:
        checkpoint()
        if char == '|':
            boundary += char
        else:
            boundaries.append(boundary)
            alignments.append(char)
            boundary = ''
    boundaries.append(boundary)
    lines = [r'\begin{tabular}{'+spec+'}']

    def horizontal(boundary: list[list[int] | None]) -> None:
        for rule in boundary:
            checkpoint()
            lines.append(r'\hline' if rule is None else '\\cline{'+str(rule[0])+'-'+str(rule[1])+'}')

    for index, row in enumerate(table.rows):
        checkpoint()
        horizontal(rules[index])
        if row.properties or row_widths[index] != columns:
            return None
        values = []
        position = 0
        for cell in row.cells:
            checkpoint()
            if cell.row_span != 1 or set(cell.properties)-{MULTICOLUMN_KEY, 'source_span'} or len(cell.blocks) > 1:
                return None
            text: str | None = ''
            if cell.blocks:
                paragraph = cell.blocks[0]
                if (not isinstance(paragraph, Paragraph) or paragraph.style_id or paragraph.alignment
                        or paragraph.box or paragraph.visual_surrogate or set(paragraph.properties)-{'source_span'}
                        or any(isinstance(run, Formula) and run.display for run in paragraph.content)):
                    return None
                text = render(paragraph) if paragraph.content else ''
            if text is None:
                return None
            if MULTICOLUMN_KEY in cell.properties or cell.column_span != 1:
                override = (multicolumn_layout(cell.properties[MULTICOLUMN_KEY]) if MULTICOLUMN_KEY in cell.properties else
                            boundaries[position]+alignments[position]+boundaries[position+cell.column_span])
                text = '\\multicolumn{'+str(cell.column_span)+'}{'+override+'}{'+text+'}'
            values.append(text)
            position += cell.column_span
        lines.append(' & '.join(values)+(r' \\' if index+1 < len(table.rows) or trailing else ''))
    horizontal(rules[-1])
    lines.append(r'\end{tabular}')
    return '\n'.join(lines)
