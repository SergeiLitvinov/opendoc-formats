"""OpenType baseline metrics used by the fixed-layout Word writer."""

from __future__ import annotations

from functools import lru_cache

from opendoc_model import TextStyle


@lru_cache(maxsize=256)
def _metrics(path: str) -> tuple[float, float] | None:
    try:
        from fontTools.ttLib import TTFont

        with TTFont(path, lazy=True) as font:
            units = font['head'].unitsPerEm
            horizontal = font['hhea']
            return (horizontal.ascent + horizontal.lineGap) / units, -horizontal.descent / units
    except Exception:  # noqa: BLE001 - unresolved font metrics must remain unknown
        return None


def word_line_ascent(style: TextStyle) -> float | None:
    resolution = style.properties.get('font_resolution')
    if not style.font_family or style.font_size is None or not isinstance(resolution, dict) or not resolution.get('path'):
        return None
    metrics = _metrics(str(resolution['path']))
    return metrics[0] * style.font_size.pt if metrics is not None else None


def word_line_descent(style: TextStyle) -> float | None:
    resolution = style.properties.get('font_resolution')
    if not style.font_family or style.font_size is None or not isinstance(resolution, dict) or not resolution.get('path'):
        return None
    metrics = _metrics(str(resolution['path']))
    return metrics[1] * style.font_size.pt if metrics is not None else None
