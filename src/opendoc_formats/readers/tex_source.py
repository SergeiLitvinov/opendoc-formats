"""Bounded lexical LaTeX source reader; no TeX engine, file commands or macro execution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError

_TOKEN = re.compile(r"\\(?:[A-Za-z@]+|\r\n|[\s\S])|[{}$&\[\]#~]|[ \t\r\n]+|[^\\{}$&\[\]#~%\s]+")


@dataclass(frozen=True)
class TexToken:
    kind: str
    value: str
    start: int
    end: int


def tokenize_tex(text: str, *, max_tokens: int = 250_000) -> list[TexToken]:
    """Tokenize a finite UTF-8 source profile, retaining Unicode character offsets."""
    result = []
    index = 0
    while index < len(text):
        if text[index] == "%":
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline + 1
            continue
        match = _TOKEN.match(text, index)
        if match is None:
            raise InvalidDocumentError(f"Invalid LaTeX token at character {index}")
        value = match.group()
        kind = (
            "command" if value.startswith("\\") else "space" if value.isspace() else "symbol" if value in "{}$&[]#~" else "text"
        )
        result.append(TexToken(kind, value[1:] if kind == "command" else value, index, match.end()))
        if len(result) > max_tokens:
            raise ResourceLimitError("LaTeX source exceeds token limit")
        index = match.end()
    return result


def load_tex_source(path: Path, max_bytes: int) -> tuple[bytes, str, list[TexToken]]:
    with path.open("rb") as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ResourceLimitError("LaTeX source exceeds input byte limit")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as error:
        raise InvalidDocumentError("LaTeX profile requires UTF-8 source") from error
    return data, text, tokenize_tex(text)
