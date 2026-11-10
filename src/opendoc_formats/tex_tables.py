"""Finite tabular layout and source boundaries; never TeX expansion or execution."""

import re
from dataclasses import dataclass
from typing import Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError
from opendoc_formats.readers.tex_source import TexToken
from opendoc_formats.support.cancellation import checkpoint

KEY = 'opendoc_formats.latex_tabular'
MULTICOLUMN_KEY = 'opendoc_formats.latex_multicolumn'
_COLUMN = re.compile(r'[lcr|]|p[ \t\r\n]*\{[ \t\r\n]*(\d{1,5}(?:\.\d{1,8})?|\.\d{1,8})'
                     r'[ \t\r\n]*(pt|mm|cm|in|bp)[ \t\r\n]*\}', re.ASCII)
_UNIT_PT = {'pt': 1, 'mm': 72.27/25.4, 'cm': 72.27/2.54, 'in': 72.27, 'bp': 72.27/72}


class TableProfileError(ValueError):
    """An explicit tabular declaration must not disappear through a fallback."""


def column_tokens(value: str) -> list[str] | None:
    """Finite literal columns and vertical rules, without interpreting TeX macros."""
    tokens = []
    index = 0
    while index < len(value):
        checkpoint()
        if value[index] in ' \t\r\n':
            index += 1
            continue
        match = _COLUMN.match(value, index)
        if match is None:
            return None
        width, unit = match.groups()
        if width is not None:
            points = float(width)*_UNIT_PT[unit]
            if not 1/65536 <= points < 16383:
                return None
            tokens.append('p{'+width+unit+'}')
        else:
            tokens.append(match[0])
        index = match.end()
    return tokens if any(token != '|' for token in tokens) else None


def column_spec(value: str) -> str | None:
    tokens = column_tokens(value)
    return ''.join(tokens) if tokens is not None else None


def column_count(value: str) -> int:
    return sum(token != '|' for token in column_tokens(value) or ())


def layout(value: Any, rows: int, columns: int) -> tuple[str, list[list[list[int] | None]], bool]:
    if value is None:
        return '|'+'l|'*columns, [[None] for _ in range(rows+1)], True
    if (not isinstance(value, dict) or set(value) != {'version', 'columns', 'rules', 'trailing_break'}
            or type(value['version']) is not int or value['version'] not in (1, 2)
            or not isinstance(value['columns'], str) or column_spec(value['columns']) != value['columns']
            or column_count(value['columns']) != columns
            or not isinstance(value['rules'], list) or len(value['rules']) != rows+1
            or type(value['trailing_break']) is not bool):
        raise TableProfileError('Invalid or unsupported '+KEY+' source layout')
    rules: list[list[list[int] | None]]
    if value['version'] == 1:
        if any(type(count) is not int or count < 0 for count in value['rules']) or sum(value['rules']) > 10_000:
            raise TableProfileError('Invalid horizontal rule counts')
        rules = [[None]*count for count in value['rules']]
    else:
        rules = value['rules']
        if any(type(boundary) is not list for boundary in rules) or sum(len(boundary) for boundary in rules) > 10_000:
            raise TableProfileError('Invalid horizontal rule sequences')
        for boundary in rules:
            for rule in boundary:
                checkpoint()
                if rule is not None and (type(rule) is not list or len(rule) != 2
                        or any(type(number) is not int for number in rule) or not 1 <= rule[0] <= rule[1] <= columns):
                    raise TableProfileError('Invalid partial horizontal rule range')
    if rules[-1] and not value['trailing_break']:
        raise TableProfileError('Trailing horizontal rules require a row break')
    return value['columns'], rules, value['trailing_break']


def multicolumn_layout(value: Any) -> str:
    if (not isinstance(value, dict) or set(value) != {'version', 'columns'}
            or type(value['version']) is not int or value['version'] != 1
            or not isinstance(value['columns'], str) or column_spec(value['columns']) != value['columns']
            or column_count(value['columns']) != 1):
        raise TableProfileError('Invalid or unsupported '+MULTICOLUMN_KEY+' source layout')
    return value['columns']


@dataclass(frozen=True)
class CellSpan:
    first: int
    stop: int
    start: int
    end: int


@dataclass(frozen=True)
class CellContent:
    span: CellSpan
    columns: str | None = None
    column_span: int = 1


def _group(tokens: list[TexToken], index: int, stop: int) -> tuple[CellSpan, int] | None:
    while index < stop and tokens[index].kind == 'space':
        checkpoint()
        index += 1
    if index >= stop or tokens[index].value != '{':
        return None
    first, start, depth = index+1, tokens[index].end, 1
    index += 1
    while index < stop:
        checkpoint()
        token = tokens[index]
        if token.kind == 'symbol' and token.value in {'{', '}'}:
            depth += 1 if token.value == '{' else -1
            if depth > 64:
                raise ResourceLimitError('LaTeX multicolumn group exceeds depth limit')
            if depth == 0:
                return CellSpan(first, index, start, token.start), index+1
        index += 1
    return None


def multicolumn(text: str, tokens: list[TexToken], span: CellSpan) -> CellContent | None:
    """Accept one complete literal multicolumn cell, never macros or partial overrides."""
    index = span.first
    while index < span.stop and tokens[index].kind == 'space':
        checkpoint()
        index += 1
    if index == span.stop or tokens[index].kind != 'command' or tokens[index].value != 'multicolumn':
        return CellContent(span)
    index += 1
    arguments = []
    for _ in range(3):
        group = _group(tokens, index, span.stop)
        if group is None:
            return None
        part, index = group
        arguments.append(part)
    if any(token.kind != 'space' for token in tokens[index:span.stop]):
        return None
    count = text[arguments[0].start:arguments[0].end].strip(' \t\r\n')
    if not re.fullmatch(r'[0-9]{1,9}', count) or int(count) < 1:
        return None
    columns = column_spec(text[arguments[1].start:arguments[1].end])
    if columns is None or column_count(columns) != 1:
        return None
    return CellContent(arguments[2], columns, int(count))


@dataclass(frozen=True)
class TabularSource:
    rows: list[list[CellSpan]]
    rules: list[list[list[int] | None]]
    trailing_break: bool
    stop: int
    end: int

    def declaration(self, columns: str) -> dict[str, Any]:
        partial = any(rule is not None for boundary in self.rules for rule in boundary)
        return {'version': 2 if partial else 1, 'columns': columns,
                'rules': self.rules if partial else [len(boundary) for boundary in self.rules],
                'trailing_break': self.trailing_break}


def _argument(tokens: list[TexToken], index: int) -> tuple[str, int, int]:
    while index < len(tokens) and tokens[index].kind == 'space':
        checkpoint()
        index += 1
    if index+2 >= len(tokens) or tokens[index].value != '{' or tokens[index+2].value != '}':
        raise InvalidDocumentError('Tabular environment requires a literal name')
    return tokens[index+1].value, index+3, tokens[index+2].end


def split_tabular(tokens: list[TexToken], index: int, start: int, columns: int, maximum: int) -> TabularSource | None:
    """Split only outer alignment tokens; math and braced text retain their own syntax."""
    rows: list[list[CellSpan]] = []
    cells: list[CellSpan] = []
    rules: list[list[list[int] | None]] = [[]]
    first, boundary, depth, count, rule_count = index, start, 0, 0, 0
    math: str | None = None
    content = False

    def cell(stop: int, end: int) -> None:
        nonlocal count
        checkpoint()
        count += 1
        if count > maximum:
            raise ResourceLimitError('LaTeX tabular cells exceed max_nodes work budget')
        cells.append(CellSpan(first, stop, boundary, end))

    while index < len(tokens):
        checkpoint()
        token = tokens[index]
        if math:
            if token.kind == 'symbol' and token.value == '$' and math in {'$', '$$'}:
                if math == '$$':
                    if index+1 >= len(tokens) or tokens[index+1].value != '$':
                        raise InvalidDocumentError('Mismatched tabular math delimiter')
                    index += 1
                math = None
            elif token.kind == 'command' and token.value == math:
                math = None
            index += 1
            continue
        if token.kind == 'symbol' and token.value == '$':
            math = '$'
            if index+1 < len(tokens) and tokens[index+1].value == '$':
                math = '$$'
                index += 1
            content = True
        elif token.kind == 'command' and token.value in {'(', '['}:
            math = ')' if token.value == '(' else ']'
            content = True
        elif token.kind == 'symbol' and token.value in {'{', '}'}:
            depth += 1 if token.value == '{' else -1
            if depth > 64:
                raise ResourceLimitError('LaTeX tabular group exceeds depth limit')
            if depth < 0:
                raise InvalidDocumentError('Unbalanced tabular text group')
            content = True
        elif depth == 0 and token.kind == 'symbol' and token.value == '&':
            cell(index, token.start)
            first, boundary, content = index+1, token.end, False
        elif depth == 0 and token.kind == 'command' and token.value == '\\':
            cell(index, token.start)
            if len(cells) > columns:
                return None
            rows.append(cells)
            cells = []
            rules.append([])
            first, boundary, content = index+1, token.end, False
            following = index+1
            while following < len(tokens) and tokens[following].kind == 'space':
                checkpoint()
                following += 1
            if following < len(tokens) and tokens[following].value in {'*', '['}:
                return None
        elif depth == 0 and token.kind == 'command' and token.value in {'hline', 'cline'}:
            if cells or content:
                return None
            rule = None
            if token.value == 'cline':
                group = _group(tokens, index+1, len(tokens))
                if group is None:
                    return None
                span, stop = group
                parts = tokens[span.first:span.stop]
                if any(part.kind == 'command' for part in parts):
                    return None
                match = re.fullmatch(r'[ \t\r\n]*([0-9]{1,9})[ \t\r\n]*-[ \t\r\n]*([0-9]{1,9})[ \t\r\n]*',
                                     ''.join(part.value for part in parts))
                if match is None or not 1 <= int(match[1]) <= int(match[2]) <= columns:
                    return None
                rule = [int(match[1]), int(match[2])]
                index = stop-1
            rules[-1].append(rule)
            rule_count += 1
            if rule_count > 10_000:
                raise ResourceLimitError('LaTeX tabular exceeds horizontal rule work limit')
            first, boundary = index+1, tokens[index].end
        elif depth == 0 and token.kind == 'command' and token.value in {'begin', 'end'}:
            target, stop, end = _argument(tokens, index+1)
            if token.value != 'end' or target != 'tabular':
                return None
            trailing = not (cells or content)
            if not trailing:
                cell(index, token.start)
                if len(cells) > columns:
                    return None
                rows.append(cells)
                rules.append([])
            return TabularSource(rows, rules, trailing, stop, end) if rows else None
        elif token.kind != 'space':
            content = True
        index += 1
    raise InvalidDocumentError('Unclosed tabular environment or math delimiter')
