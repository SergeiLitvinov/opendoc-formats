"""Explicit PPTX policy: generated slides or bound source text edits."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PptxProfile:
    layout: str = 'rebuild'

    def __post_init__(self) -> None:
        if not isinstance(self.layout, str) or self.layout not in {'rebuild', 'source'}:
            raise ValueError('PPTX layout must be rebuild or source')
