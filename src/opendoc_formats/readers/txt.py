"""TXT и DjVu → Text."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Union

from opendoc_formats.readers._txt_model import read_txt_model as read_txt_model
from opendoc_formats.text_profile import TextProfile, decode_text, normalize_newlines
from opendoc_formats.types import Block, BlockType, DocFormat, Text


def read_txt(path: Union[str, Path], *, profile: TextProfile | None = None) -> Text:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    profile = TextProfile() if profile is None else profile
    if not isinstance(profile, TextProfile):
        raise ValueError("profile must be TextProfile")
    text, enc, _ = decode_text(p.read_bytes(), profile)
    if profile.newline != "preserve":
        separator = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}[profile.newline]
        text = normalize_newlines(text).replace("\n", separator)
    return Text(
        blocks=[Block(type=BlockType.PARAGRAPH, text=text)],
        plain=text,
        source_format=DocFormat.TXT,
        engine=enc,
    )


def read_djvu(
    path: Union[str, Path], *, timeout: float = 30,
    max_output_bytes: int = 10 * 1024 * 1024,
    cancelled: Callable[[], bool] | None = None,
) -> Text:
    """Read the UTF-8 hidden text layer with bounded, cancellable DjVuLibre."""
    from opendoc_formats.readers._djvu_text import extract_djvu_text

    return extract_djvu_text(path, timeout=timeout, max_output_bytes=max_output_bytes, cancelled=cancelled)


__all__ = ["read_txt", "read_txt_model", "read_djvu"]
