"""Resolve nearest PPTX background through its actual theme style matrix and color map."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from opendoc_model import ColorValue

from opendoc_formats.ooxml.color import _luminance_percentage, resolve_drawingml_color
from opendoc_formats.support.cancellation import checkpoint

A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
_COLORS = {A+name for name in ('srgbClr', 'schemeClr', 'sysClr')}
_TRANSFORMS = {A+name for name in ('tint', 'shade', 'lumMod', 'lumOff', 'alpha')}


def _native_color(node: Any, palette: dict[str, str]) -> ColorValue | None:
    """DrawingML tint/shade mix linear light, keeping precision across consecutive modifiers."""
    source = node if node.tag in _COLORS else next((child for child in node if child.tag in _COLORS), None)
    if source is None:
        return None
    for modifier in source:
        checkpoint()
        raw = modifier.get('val', '')
        if modifier.tag in (A+'lumMod', A+'lumOff'):
            _luminance_percentage(raw)
            continue
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 6 or int(raw) > 100000:
            raise ValueError('Unsupported color modifier percentage')
    return resolve_drawingml_color(source, palette)[0]



def background_style(slide: Any, diagnostics: Any = None, *, work_state: Any = None
                     ) -> tuple[ColorValue | None, list[dict[str, Any]], bool, dict[str, Any] | None]:
    from opendoc_formats.readers.pptx_theme_colors import charge_theme, theme_context

    layout, master = slide.slide_layout, slide.slide_layout.slide_master
    bg = None
    owner = slide
    for owner in (slide, layout, master):
        checkpoint()
        bg = owner._element.find(P+'cSld/'+P+'bg')
        if bg is not None:
            break
    if bg is None:
        return None, [], False, None

    def unsupported(reason: str) -> tuple[None, list[dict[str, Any]], bool, None]:
        if diagnostics is not None:
            previous, consumer = diagnostics.part, diagnostics.consumer_part
            try:
                diagnostics.part = str(owner.part.partname)
                diagnostics.consumer_part = str(slide.part.partname)
                diagnostics.record('pptx.background', 'unsupported-background-style', reason, bg)
            finally:
                diagnostics.part, diagnostics.consumer_part = previous, consumer
        return None, [], False, None

    palette, matrix = theme_context(slide, work_state)

    reference = bg.find(P+'bgRef')
    properties = bg.find(P+'bgPr')
    if (reference is None) == (properties is None):
        return unsupported('Background must have exactly one bgPr or p:bgRef')
    placeholder = None
    if reference is not None:
        raw = reference.get('idx', '')
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 10:
            return unsupported('Background style index is not a supported unsigned integer')
        index = int(raw)
        if index in (0, 1000):
            return None, [], True, None
        name, position = ('fillStyleLst', index-1) if index < 1000 else ('bgFillStyleLst', index-1001)
        styles = matrix.find(A+name) if matrix is not None else None
        if styles is None or position >= len(styles):
            return unsupported('Background style index is outside its actual theme list')
        fill = styles[position]
        placeholder = next((child for child in reference if child.tag in _COLORS), None)
    else:
        fills = [child for child in properties if child.tag in {A+name for name in
                 ('solidFill', 'gradFill', 'noFill', 'pattFill', 'blipFill', 'grpFill')}]
        if len(fills) != 1:
            return unsupported('Background has no unique supported fill')
        fill = fills[0]
    if fill.tag == A+'noFill':
        return None, [], True, None
    if fill.tag not in (A+'solidFill', A+'gradFill'):
        return unsupported('Background fill is outside the solid/gradient projection')
    # Copy only the selected style. The original package and shared theme remain untouched.
    charge_theme(fill, work_state, str(owner.part.partname))
    fill = deepcopy(fill)
    for color in list(fill.iter()):
        checkpoint()
        if color.tag == A+'schemeClr' and color.get('val') == 'phClr':
            if placeholder is None or placeholder.get('val') == 'phClr':
                return unsupported('Background phClr has no concrete reference color')
            replacement = deepcopy(placeholder)
            replacement.extend(deepcopy(child) for child in color)
            color.getparent().replace(color, replacement)
    for node in fill.iter():
        checkpoint()
        if node.tag in _COLORS and any(child.tag not in _TRANSFORMS for child in node):
            return unsupported('Background color transform is outside the accepted profile')
    try:
        if fill.tag == A+'solidFill':
            color = _native_color(fill, palette)
            return (color, [], False, None) if color is not None else unsupported('Background color cannot be resolved')
        stops = []
        for stop in fill.findall(A+'gsLst/'+A+'gs'):
            checkpoint()
            color = _native_color(stop, palette)
            if color is None:
                return unsupported('Background gradient color cannot be resolved')
            _, metadata = resolve_drawingml_color(stop, palette)
            stops.append({'position': float(stop.get('pos', '0'))/100000,
                          'color': color.to_dict(), 'source': metadata})
        if not stops:
            return unsupported('Background gradient colors cannot be resolved')
        color = _native_color(fill.find(A+'gsLst/'+A+'gs'), palette)
        from opendoc_formats.ooxml.pptx_gradient import capture_gradient

        try:
            effects = properties is not None and any(len(node) for node in properties
                                                     if node.tag in (A+'effectLst', A+'effectDag'))
            if properties is not None and (properties.get('shadeToTitle', '0') not in ('0', 'false') or effects):
                raise ValueError('Background effects/title shading are outside the gradient profile')
            hint = capture_gradient(fill, palette, stops)
        except ValueError:
            unsupported('Background gradient geometry is outside the accepted native profile')
            hint = None
        return color, stops, False, hint
    except ValueError:
        return unsupported('Background color or transform value is outside the accepted profile')
