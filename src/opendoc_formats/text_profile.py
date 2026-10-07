"""Finite, dependency-free text encoding and newline policies."""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass
from typing import Any

_BOMS = {"utf-8": codecs.BOM_UTF8, "utf-16-le": codecs.BOM_UTF16_LE, "utf-16-be": codecs.BOM_UTF16_BE}
_NEWLINES = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}


@dataclass(frozen=True)
class TextProfile:
    encoding: str = "auto"
    bom: str = "auto"
    newline: str = "preserve"

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) for value in (self.encoding, self.bom, self.newline)):
            raise ValueError("Text profile fields must be strings")
        if self.encoding not in {"auto", "utf-8", "utf-16-le", "utf-16-be", "cp1251"}:
            raise ValueError("encoding must be auto, utf-8, utf-16-le, utf-16-be or cp1251")
        if self.bom not in {"auto", "require", "forbid"}:
            raise ValueError("bom must be auto, require or forbid")
        if self.newline not in {"preserve", "lf", "crlf", "cr"}:
            raise ValueError("newline must be preserve, lf, crlf or cr")
        if self.encoding == "cp1251" and self.bom == "require":
            raise ValueError("CP1251 has no BOM")


class TextEncodingError(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def decode_text(data: bytes, profile: TextProfile) -> tuple[str, str, bool]:
    if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        raise TextEncodingError("unsupported-encoding", "UTF-32 is outside the text profile")
    detected = next((encoding for encoding, bom in _BOMS.items() if data.startswith(bom)), None)
    if profile.bom == "require" and detected is None:
        raise TextEncodingError("missing-bom", "The selected text profile requires a BOM")
    if profile.bom == "forbid" and detected is not None:
        raise TextEncodingError("forbidden-bom", "The selected text profile forbids a BOM")
    if detected is not None and profile.encoding not in {"auto", detected}:
        raise TextEncodingError("conflicting-bom", "BOM conflicts with the selected encoding")
    encoding = detected or ("utf-8" if profile.encoding == "auto" else profile.encoding)
    payload = data[len(_BOMS[detected]):] if detected else data
    try:
        text = payload.decode(encoding, errors="strict")
    except UnicodeDecodeError as error:
        reason = "ambiguous-encoding" if profile.encoding == "auto" and detected is None else "invalid-encoding"
        raise TextEncodingError(
            reason, "Cannot decode text strictly; choose an explicit encoding for BOM-less legacy text",
        ) from error
    if "\x00" in text:
        raise TextEncodingError(
            "binary-or-ambiguous", "NUL text is outside the profile; UTF-16 without BOM requires explicit encoding",
        )
    return text, encoding, detected is not None


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def source_profile(text: str, encoding: str, bom: bool) -> dict[str, Any]:
    separators = re.findall(r"\r\n|\r|\n", text)
    return {"encoding": encoding, "bom": bom, "line_separators": separators, "line_separator": "\n"}


def encode_text(text: str, profile: TextProfile, original: dict[str, Any]) -> tuple[bytes, dict[str, Any], bool]:
    encoding = original.get("encoding", "utf-8") if profile.encoding == "auto" else profile.encoding
    if encoding not in {*_BOMS, "cp1251"}:
        raise ValueError("Invalid source text encoding")
    bom = original.get("bom", False) if profile.bom == "auto" else profile.bom == "require"
    if type(bom) is not bool or (bom and encoding == "cp1251"):
        raise ValueError("Invalid source BOM policy")
    text = normalize_newlines(text)
    changed = False
    if profile.newline == "preserve":
        separators = original.get("line_separators")
        if separators is None:
            separators = ["\n"] * text.count("\n")
        if not isinstance(separators, list) or any(item not in _NEWLINES.values() for item in separators):
            raise ValueError("Invalid source newline profile")
        if len(separators) != text.count("\n"):
            changed = True
            separators = ["\n"] * text.count("\n")
        lines = text.split("\n")
        rendered = "".join(line + separator for line, separator in zip(lines, separators, strict=False)) + lines[-1]
    else:
        rendered = text.replace("\n", _NEWLINES[profile.newline])
    data = rendered.encode(encoding, errors="strict")
    if bom:
        data = _BOMS[encoding] + data
    reopened, _, _ = decode_text(data, TextProfile(encoding, "require" if bom else "forbid"))
    if reopened != rendered:
        raise ValueError("Encoded text did not roundtrip under the selected profile")
    return data, {"encoding": encoding, "bom": bom, "newline": profile.newline}, changed
