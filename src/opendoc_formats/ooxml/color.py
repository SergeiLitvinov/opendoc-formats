"""Shared OOXML DrawingML color resolution."""

from __future__ import annotations

from collections.abc import Mapping
from colorsys import hls_to_rgb, rgb_to_hls
from math import floor
from typing import Any

from opendoc_model.color import ColorSpace, ColorValue

from opendoc_formats.support.cancellation import checkpoint

_COLOR_NODES = frozenset({"srgbClr", "schemeClr", "sysClr"})
_MODIFIERS = {
    "tint": "tint",
    "shade": "shade",
    "lumMod": "luminance_mod",
    "lumOff": "luminance_offset",
    "alpha": "alpha",
}


def resolve_drawingml_color(
    node: Any,
    theme_colors: Mapping[str, str],
) -> tuple[ColorValue | None, dict[str, Any]]:
    """Resolve a DrawingML color container and retain its source metadata."""
    if node is None:
        return None, {}
    color_node = (
        node
        if _local_name(node.tag) in _COLOR_NODES
        else next(
            (child for child in node if _local_name(child.tag) in _COLOR_NODES),
            None,
        )
    )
    if color_node is None:
        return None, {}
    kind = _local_name(color_node.tag)
    theme = color_node.get("val") if kind == "schemeClr" else None
    raw = theme_colors.get(theme or "") if theme else color_node.get("val") or color_node.get("lastClr")
    if not raw:
        return None, {}
    try:
        color = ColorValue.from_hex("#" + raw)
    except ValueError:
        return None, {}
    modifiers: dict[str, float] = {}
    linear_rgb: tuple[float, ...] | None = None
    last_luminance = False
    for child in color_node:
        checkpoint()
        target = _MODIFIERS.get(_local_name(child.tag))
        if target and child.get("val") is not None:
            raw_value = child.get('val')
            value = (_luminance_percentage(raw_value) if target.startswith('luminance_') else
                     max(0.0, min(1.0, float(raw_value)/100000)))
            modifiers[target] = value
            if target in ('tint', 'shade'):
                last_luminance = False
                if linear_rgb is None:
                    linear_rgb = tuple(component/12.92 if component <= 0.04045 else
                                       ((component+0.055)/1.055)**2.4 for component in color.components)
                linear_rgb = tuple(component*value+(1-value if target == 'tint' else 0) for component in linear_rgb)
            elif target == 'alpha':
                color = ColorValue(color.space, color.components, alpha=value)
            else:
                last_luminance = True
                if linear_rgb is not None:
                    color = _encoded(color, linear_rgb)
                    linear_rgb = None
                hue, luminance, saturation = rgb_to_hls(color.components[0], color.components[1], color.components[2])
                luminance = luminance*value if target == 'luminance_mod' else luminance+value
                rgb = hls_to_rgb(hue, max(0.0, min(1.0, luminance)), saturation)
                color = ColorValue(ColorSpace.SRGB, rgb, alpha=color.alpha)
    if linear_rgb is not None:
        color = _encoded(color, linear_rgb)
    if last_luminance and len(set(color.components)) == 1:
        # Office truncates the final achromatic HSL projection, rather than rounding half upward.
        color = ColorValue(ColorSpace.SRGB, tuple(floor(channel*255)/255 for channel in color.components), alpha=color.alpha)
    properties: dict[str, Any] = {"color_source": kind}
    if theme:
        properties["color_theme"] = theme
    if modifiers:
        properties["color_modifiers"] = modifiers
    return color, properties


def _encoded(color: ColorValue, rgb: tuple[float, ...]) -> ColorValue:
    components = (12.92*value if value <= 0.0031308 else 1.055*value**(1/2.4)-0.055 for value in rgb)
    return ColorValue(ColorSpace.SRGB, tuple(min(1.0, max(0.0, value)) for value in components), alpha=color.alpha)


def _luminance_percentage(raw: str) -> float:
    raw = raw.strip()
    digits = raw[1:] if raw[:1] in ('+', '-') else raw
    if not digits.isascii() or not digits.isdecimal():
        raise ValueError('DrawingML luminance requires an integer percentage')
    digits = digits.lstrip('0') or '0'
    if len(digits) > 10:
        raise ValueError('DrawingML luminance percentage exceeds signed int32')
    value = int(digits)*(-1 if raw.startswith('-') else 1)
    if not -2147483648 <= value <= 2147483647:
        raise ValueError('DrawingML luminance percentage exceeds signed int32')
    return value/100000


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


__all__ = ["resolve_drawingml_color"]
