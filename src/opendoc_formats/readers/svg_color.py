"""Safe SVG color discovery for canonical resource metadata."""

from __future__ import annotations

import math
import re
from colorsys import hls_to_rgb
from xml.etree import ElementTree

from opendoc_model.color import ColorValue

_COLOR_ATTRIBUTES = frozenset({"fill", "stroke", "stop-color", "flood-color", "lighting-color", "color"})
_SVG_RGB_RE = re.compile(
    r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*(0(?:\.\d+)?|1(?:\.0+)?))?\s*\)$",
    re.IGNORECASE,
)
_CSS_HEX_RE = re.compile(r'#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})')
_CSS_NUMBER = r'[+-]?(?:[0-9]*\.[0-9]+|[0-9]+)(?:[eE][+-]?[0-9]+)?'
_CSS_WS = r'[ \t\r\n\f]*'
_CSS_RGB_CHANNEL = rf'({_CSS_NUMBER})(%?)'
_CSS_RGB_RE = re.compile(
    rf'rgba?\({_CSS_WS}{_CSS_RGB_CHANNEL}{_CSS_WS},{_CSS_WS}{_CSS_RGB_CHANNEL}{_CSS_WS},'
    rf'{_CSS_WS}{_CSS_RGB_CHANNEL}{_CSS_WS}(?:,{_CSS_WS}({_CSS_NUMBER}){_CSS_WS})?\)',
    re.ASCII | re.IGNORECASE,
)
_CSS_HSL_RE = re.compile(
    rf'hsla?\({_CSS_WS}({_CSS_NUMBER}){_CSS_WS},{_CSS_WS}({_CSS_NUMBER})%{_CSS_WS},'
    rf'{_CSS_WS}({_CSS_NUMBER})%{_CSS_WS}(?:,{_CSS_WS}({_CSS_NUMBER}){_CSS_WS})?\)',
    re.ASCII | re.IGNORECASE,
)
# CSS Color 3 sRGB keyword values: https://www.w3.org/TR/css-color-3/#svg-color
_NAMED_COLORS = {
    'aliceblue': '#f0f8ff', 'antiquewhite': '#faebd7', 'aqua': '#00ffff',
    'aquamarine': '#7fffd4', 'azure': '#f0ffff', 'beige': '#f5f5dc',
    'bisque': '#ffe4c4', 'black': '#000000', 'blanchedalmond': '#ffebcd',
    'blue': '#0000ff', 'blueviolet': '#8a2be2', 'brown': '#a52a2a',
    'burlywood': '#deb887', 'cadetblue': '#5f9ea0', 'chartreuse': '#7fff00',
    'chocolate': '#d2691e', 'coral': '#ff7f50', 'cornflowerblue': '#6495ed',
    'cornsilk': '#fff8dc', 'crimson': '#dc143c', 'cyan': '#00ffff',
    'darkblue': '#00008b', 'darkcyan': '#008b8b', 'darkgoldenrod': '#b8860b',
    'darkgray': '#a9a9a9', 'darkgreen': '#006400', 'darkgrey': '#a9a9a9',
    'darkkhaki': '#bdb76b', 'darkmagenta': '#8b008b', 'darkolivegreen': '#556b2f',
    'darkorange': '#ff8c00', 'darkorchid': '#9932cc', 'darkred': '#8b0000',
    'darksalmon': '#e9967a', 'darkseagreen': '#8fbc8f', 'darkslateblue': '#483d8b',
    'darkslategray': '#2f4f4f', 'darkslategrey': '#2f4f4f', 'darkturquoise': '#00ced1',
    'darkviolet': '#9400d3', 'deeppink': '#ff1493', 'deepskyblue': '#00bfff',
    'dimgray': '#696969', 'dimgrey': '#696969', 'dodgerblue': '#1e90ff',
    'firebrick': '#b22222', 'floralwhite': '#fffaf0', 'forestgreen': '#228b22',
    'fuchsia': '#ff00ff', 'gainsboro': '#dcdcdc', 'ghostwhite': '#f8f8ff',
    'gold': '#ffd700', 'goldenrod': '#daa520', 'gray': '#808080',
    'green': '#008000', 'greenyellow': '#adff2f', 'grey': '#808080',
    'honeydew': '#f0fff0', 'hotpink': '#ff69b4', 'indianred': '#cd5c5c',
    'indigo': '#4b0082', 'ivory': '#fffff0', 'khaki': '#f0e68c',
    'lavender': '#e6e6fa', 'lavenderblush': '#fff0f5', 'lawngreen': '#7cfc00',
    'lemonchiffon': '#fffacd', 'lightblue': '#add8e6', 'lightcoral': '#f08080',
    'lightcyan': '#e0ffff', 'lightgoldenrodyellow': '#fafad2', 'lightgray': '#d3d3d3',
    'lightgreen': '#90ee90', 'lightgrey': '#d3d3d3', 'lightpink': '#ffb6c1',
    'lightsalmon': '#ffa07a', 'lightseagreen': '#20b2aa', 'lightskyblue': '#87cefa',
    'lightslategray': '#778899', 'lightslategrey': '#778899', 'lightsteelblue': '#b0c4de',
    'lightyellow': '#ffffe0', 'lime': '#00ff00', 'limegreen': '#32cd32',
    'linen': '#faf0e6', 'magenta': '#ff00ff', 'maroon': '#800000',
    'mediumaquamarine': '#66cdaa', 'mediumblue': '#0000cd', 'mediumorchid': '#ba55d3',
    'mediumpurple': '#9370db', 'mediumseagreen': '#3cb371', 'mediumslateblue': '#7b68ee',
    'mediumspringgreen': '#00fa9a', 'mediumturquoise': '#48d1cc', 'mediumvioletred': '#c71585',
    'midnightblue': '#191970', 'mintcream': '#f5fffa', 'mistyrose': '#ffe4e1',
    'moccasin': '#ffe4b5', 'navajowhite': '#ffdead', 'navy': '#000080',
    'oldlace': '#fdf5e6', 'olive': '#808000', 'olivedrab': '#6b8e23',
    'orange': '#ffa500', 'orangered': '#ff4500', 'orchid': '#da70d6',
    'palegoldenrod': '#eee8aa', 'palegreen': '#98fb98', 'paleturquoise': '#afeeee',
    'palevioletred': '#db7093', 'papayawhip': '#ffefd5', 'peachpuff': '#ffdab9',
    'peru': '#cd853f', 'pink': '#ffc0cb', 'plum': '#dda0dd',
    'powderblue': '#b0e0e6', 'purple': '#800080', 'red': '#ff0000',
    'rosybrown': '#bc8f8f', 'royalblue': '#4169e1', 'saddlebrown': '#8b4513',
    'salmon': '#fa8072', 'sandybrown': '#f4a460', 'seagreen': '#2e8b57',
    'seashell': '#fff5ee', 'sienna': '#a0522d', 'silver': '#c0c0c0',
    'skyblue': '#87ceeb', 'slateblue': '#6a5acd', 'slategray': '#708090',
    'slategrey': '#708090', 'snow': '#fffafa', 'springgreen': '#00ff7f',
    'steelblue': '#4682b4', 'tan': '#d2b48c', 'teal': '#008080',
    'thistle': '#d8bfd8', 'tomato': '#ff6347', 'turquoise': '#40e0d0',
    'violet': '#ee82ee', 'wheat': '#f5deb3', 'white': '#ffffff',
    'whitesmoke': '#f5f5f5', 'yellow': '#ffff00', 'yellowgreen': '#9acd32',
}


def _rgb_components(match: re.Match[str]) -> ColorValue:
    red, green, blue = (min(255, int(match.group(index))) / 255.0 for index in range(1, 4))
    alpha = float(match.group(4)) if match.group(4) is not None else 1.0
    return ColorValue.from_srgb_components(red, green, blue, alpha=alpha)


def parse_static_css_color(token: str) -> ColorValue | None:
    """Decode the subset shared by the native HTML cascade and CSS Color 3."""
    if not token.isascii():
        return None
    lower = token.lower()
    if lower in _NAMED_COLORS:
        return ColorValue.from_hex(_NAMED_COLORS[lower])
    if lower == 'transparent':
        return ColorValue.from_srgb_components(0, 0, 0, alpha=0)
    if _CSS_HEX_RE.fullmatch(token):
        return ColorValue.from_hex(token)
    match = _CSS_RGB_RE.fullmatch(token)
    if match is not None and (match[7] is not None) == lower.startswith('rgba('):
        percentages = match[2] == match[4] == match[6] == '%'
        channels = match[1], match[3], match[5]
        if percentages or (not any(match[index] for index in (2, 4, 6))
                           and all(re.fullmatch(r'[+-]?[0-9]+', channel) for channel in channels)):
            maximum = 100 if percentages else 255
            red, green, blue = map(float, channels)
            alpha = float(match[7]) if match[7] is not None else 1.0
            if all(0 <= channel <= maximum for channel in (red, green, blue)) and math.isfinite(alpha):
                if not percentages:
                    red, green, blue = red + 0.0, green + 0.0, blue + 0.0
                return ColorValue.from_srgb_components(red/maximum, green/maximum, blue/maximum,
                                                       alpha=min(1.0, max(0.0, alpha)))
    hsl = _CSS_HSL_RE.fullmatch(token)
    if hsl is not None and (hsl[4] is not None) == lower.startswith('hsla('):
        hue, saturation, lightness = (float(hsl[index]) for index in (1, 2, 3))
        alpha = float(hsl[4]) if hsl[4] is not None else 1.0
        if math.isfinite(hue) and 0 <= saturation <= 100 and 0 <= lightness <= 100 and math.isfinite(alpha):
            rgb = hls_to_rgb(hue / 360, lightness / 100, saturation / 100)
            return ColorValue.from_srgb_components(*rgb, alpha=min(1.0, max(0.0, alpha)))
    return None


def parse_svg_color(value: str, *, opacity: float | None = None) -> ColorValue | None:
    token = value.strip()
    try:
        color = ColorValue.from_hex(token)
    except ValueError:
        match = _SVG_RGB_RE.fullmatch(token)
        if match is None:
            return None
        color = _rgb_components(match)
    if opacity is not None:
        color = color.transformed(alpha=color.alpha * max(0.0, min(1.0, opacity)))
    return color


def svg_color_catalog(data: bytes) -> list[dict[str, object]]:
    """Collect explicit SVG paint values without changing the source asset."""
    try:
        root = ElementTree.fromstring(data)
    except (ElementTree.ParseError, UnicodeDecodeError):
        return []
    result: list[dict[str, object]] = []
    for element in root.iter():
        declarations = _style_declarations(element.attrib.get("style", ""))
        for attribute in _COLOR_ATTRIBUTES:
            raw = element.attrib.get(attribute, declarations.get(attribute))
            if not raw:
                continue
            opacity_raw = element.attrib.get(f"{attribute}-opacity") or declarations.get(f"{attribute}-opacity")
            opacity = _opacity(opacity_raw)
            color = parse_svg_color(raw, opacity=opacity)
            if color is not None:
                result.append({"element": _local_name(element.tag), "attribute": attribute, "color": color.to_dict()})
    return result


def _style_declarations(value: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for declaration in value.split(";"):
        name, separator, raw = declaration.partition(":")
        if separator:
            declarations[name.strip().lower()] = raw.strip()
    return declarations


def _opacity(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip().removesuffix("%")) / (100.0 if value.strip().endswith("%") else 1.0)
    except ValueError:
        return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


__all__ = ["parse_svg_color", "svg_color_catalog"]
