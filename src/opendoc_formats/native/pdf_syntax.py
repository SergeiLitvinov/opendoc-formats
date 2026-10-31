"""Bounded PDF object syntax for source dictionaries, never execution or repair."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, NoReturn

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError
from opendoc_formats.support.cancellation import checkpoint

SPACE = b'\x00\t\n\x0c\r '
DELIMITERS = SPACE+b'()<>[]{}/%'
SKIP = re.compile(rb'[\x00\t\n\x0c\r ]+|%[^\r\n]*')
NUMBER = re.compile(rb'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z')


@dataclass(frozen=True)
class Name:
    value: str


@dataclass(frozen=True)
class Reference:
    object: int
    generation: int


@dataclass(frozen=True)
class Token:
    kind: str
    value: Any
    start: int
    end: int


@dataclass
class SyntaxBudget:
    maximum: int
    depth: int
    tokens: int = 0


class Parser:
    def __init__(self, data: bytes, start: int, window: int, budget: SyntaxBudget) -> None:
        self.data, self.pos, self.end = data, start, min(len(data), start+window)
        self.budget = budget
        self.buffer: list[Token] = []

    def error(self, message: str) -> NoReturn:
        raise InvalidDocumentError(f'pdf:byte={self.pos}: {message}')

    def bounded(self) -> None:
        if self.pos >= self.end:
            if self.end < len(self.data):
                raise ResourceLimitError(f'pdf:byte={self.pos}: max_part_bytes exceeded')
            self.error('unexpected end of source syntax')

    def skip(self) -> None:
        while True:
            checkpoint()
            match = SKIP.match(self.data, self.pos, self.end)
            if match is None:
                return
            self.pos = match.end()

    def _token(self) -> Token:
        checkpoint()
        self.budget.tokens += 1
        if self.budget.tokens > self.budget.maximum:
            raise ResourceLimitError(f'pdf:byte={self.pos}: max_pdf_tokens exceeded')
        self.skip()
        self.bounded()
        start, value = self.pos, self.data[self.pos]
        pair = self.data[self.pos:self.pos+2]
        if pair in (b'<<', b'>>'):
            self.pos += 2
            return Token(pair.decode(), None, start, self.pos)
        if value in b'[]':
            self.pos += 1
            return Token(chr(value), None, start, self.pos)
        if value == 40:
            self.pos += 1
            depth = 1
            while depth:
                self.bounded()
                if (self.pos-start) % 4096 == 0:
                    checkpoint()
                char = self.data[self.pos]
                self.pos += 1
                if char == 92:
                    self.bounded()
                    if self.data[self.pos:self.pos+2] == b'\r\n':
                        self.pos += 2
                    else:
                        self.pos += 1
                elif char == 40:
                    depth += 1
                    if depth > self.budget.depth:
                        raise ResourceLimitError(f'pdf:byte={self.pos}: max_pdf_depth exceeded')
                elif char == 41:
                    depth -= 1
            return Token('string', None, start, self.pos)
        if value == 60:
            self.pos += 1
            while True:
                self.bounded()
                if (self.pos-start) % 4096 == 0:
                    checkpoint()
                char = self.data[self.pos]
                self.pos += 1
                if char == 62:
                    break
                if char not in SPACE+b'0123456789abcdefABCDEF':
                    self.error('invalid hexadecimal string')
            return Token('string', None, start, self.pos)
        name = value == 47
        if name:
            self.pos += 1
        word_start = self.pos
        while self.pos < self.end and self.data[self.pos] not in DELIMITERS:
            if (self.pos-start) % 4096 == 0:
                checkpoint()
            self.pos += 1
        if self.pos == self.end and self.end < len(self.data):
            raise ResourceLimitError(f'pdf:byte={self.pos}: max_part_bytes exceeded')
        word = self.data[word_start:self.pos]
        if name:
            if re.search(rb'#(?![0-9a-fA-F]{2})', word):
                self.error('invalid PDF name escape')
            decoded = re.sub(rb'#([0-9a-fA-F]{2})', lambda m: bytes([int(m[1], 16)]), word)
            return Token('name', Name(decoded.decode('latin1')), start, self.pos)
        if not word:
            self.error('unexpected delimiter')
        if NUMBER.fullmatch(word):
            if len(word) > 128:
                raise ResourceLimitError(f'pdf:byte={start}: numeric token exceeds bounded profile')
            return Token('real' if b'.' in word else 'integer',
                         float(word) if b'.' in word else int(word), start, self.pos)
        return Token('keyword', word, start, self.pos)

    def peek(self, index: int = 0) -> Token:
        while len(self.buffer) <= index:
            self.buffer.append(self._token())
        return self.buffer[index]

    def take(self, kind: str | None = None) -> Token:
        token = self.buffer.pop(0) if self.buffer else self._token()
        if kind is not None and token.kind != kind:
            self.error('expected '+kind)
        return token

    def value(self, depth: int = 0) -> Any:
        if depth > self.budget.depth:
            raise ResourceLimitError(f'pdf:byte={self.pos}: max_pdf_depth exceeded')
        token = self.take()
        if token.kind == '<<':
            result = {}
            while self.peek().kind != '>>':
                key = self.take('name').value.value
                if key in result:
                    self.error('duplicate dictionary key /'+key)
                result[key] = self.value(depth+1)
            self.take('>>')
            return result
        if token.kind == '[':
            array = []
            while self.peek().kind != ']':
                array.append(self.value(depth+1))
            self.take(']')
            return array
        if token.kind == 'integer':
            if self.peek().kind == 'integer' and self.peek(1).value == b'R':
                generation = self.take().value
                self.take()
                if token.value < 0 or not 0 <= generation <= 65535:
                    self.error('invalid indirect reference')
                return Reference(token.value, generation)
            return token.value
        if token.kind in {'real', 'name', 'string'}:
            return token.value
        if token.kind == 'keyword' and token.value in {b'true', b'false', b'null'}:
            return {b'true': True, b'false': False, b'null': None}[token.value]
        self.error('unsupported object syntax in source dictionary')
