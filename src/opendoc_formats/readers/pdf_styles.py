"""Declared semantic style of an observed PDF text span."""

from __future__ import annotations

from opendoc_model import ColorValue, Length, TextStyle


def native_text_style(font: str, size: float, flags: int, color: int) -> TextStyle:
    """Keep the same source declarations in import and logical-binding verification."""
    return TextStyle(font_family=font or None, font_size=Length(size) if size else None,
                     bold=bool(flags & 16), italic=bool(flags & 2), superscript=bool(flags & 1),
                     color=ColorValue.from_pdf_srgb(color))
