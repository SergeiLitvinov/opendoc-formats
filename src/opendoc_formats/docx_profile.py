"""Explicit Word layout policy; preservation remains the default."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DocxProfile:
    layout: str = 'preserve'

    def __post_init__(self) -> None:
        if not isinstance(self.layout, str) or self.layout not in {'preserve', 'flow'}:
            raise ValueError('DOCX layout must be preserve or flow')
