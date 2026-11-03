"""Bounded native DrawingML gradient hint; visible stops remain authoritative."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from opendoc_model import ColorSpace, ColorValue

from opendoc_formats.ooxml.color import _luminance_percentage, resolve_drawingml_color
from opendoc_formats.support.cancellation import checkpoint

A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
KEY = 'opendoc_formats.pptx_background_gradient'
_MODIFIERS = {'tint', 'shade', 'lumMod', 'lumOff', 'alpha'}


def _integer(raw: str, minimum: int, maximum: int) -> int:
    value = _luminance_percentage(raw)*100000
    number = round(value)
    if not minimum <= number <= maximum:
        raise ValueError('Gradient integer outside native range')
    return number


def _attributes(node: Any, allowed: set[str]) -> None:
    if set(node.attrib)-allowed or node.text and node.text.strip() or node.tail and node.tail.strip():
        raise ValueError('Unsupported gradient attributes or content')


def _rectangle(node: Any) -> None:
    _attributes(node, {'l', 't', 'r', 'b'})
    if len(node):
        raise ValueError('Gradient rectangle has children')
    for value in node.attrib.values():
        _integer(value, -2147483648, 2147483647)


def _validate(root: Any) -> None:
    if root.tag != A+'gradFill':
        raise ValueError('Expected DrawingML gradFill')
    _attributes(root, {'flip', 'rotWithShape'})
    if root.get('flip', 'none') not in ('none', 'x', 'y', 'xy'):
        raise ValueError('Unsupported gradient flip')
    if root.get('rotWithShape', '1') not in ('0', '1', 'true', 'false'):
        raise ValueError('Unsupported gradient rotation boolean')
    for index, node in enumerate(root.iter()):
        checkpoint()
        if index >= 32768 or not isinstance(node.tag, str) or not node.tag.startswith(A):
            raise ValueError('Gradient node profile exceeded')
    children = [node.tag for node in root]
    if (children.count(A+'gsLst') != 1 or children.count(A+'lin')+children.count(A+'path') != 1
            or children.count(A+'tileRect') > 1 or set(children)-{A+'gsLst', A+'lin', A+'path', A+'tileRect'}):
        raise ValueError('Gradient requires one stop list and one shading geometry')
    order = [A+'gsLst', A+'lin' if A+'lin' in children else A+'path']
    if A+'tileRect' in children:
        order.append(A+'tileRect')
    if children != order:
        raise ValueError('Gradient child order is outside DrawingML profile')
    stops = root.find(A+'gsLst')
    _attributes(stops, set())
    if not 2 <= len(stops) <= 4096:
        raise ValueError('Gradient stop count outside profile')
    previous = -1
    for stop in stops:
        checkpoint()
        if stop.tag != A+'gs':
            raise ValueError('Unknown gradient stop')
        _attributes(stop, {'pos'})
        position = _integer(stop.get('pos', ''), 0, 100000)
        if position < previous or len(stop) != 1 or stop[0].tag != A+'srgbClr':
            raise ValueError('Gradient requires ordered stops with literal RGB bases')
        previous = position
        color = stop[0]
        _attributes(color, {'val'})
        raw = color.get('val', '')
        if len(raw) != 6 or any(char not in '0123456789abcdefABCDEF' for char in raw):
            raise ValueError('Invalid gradient RGB base')
        for modifier in color:
            name = modifier.tag[len(A):]
            _attributes(modifier, {'val'})
            if name not in _MODIFIERS or len(modifier):
                raise ValueError('Unsupported gradient color modifier')
            _integer(modifier.get('val', ''), -2147483648 if name in ('lumMod', 'lumOff') else 0,
                     2147483647 if name in ('lumMod', 'lumOff') else 100000)
    linear = root.find(A+'lin')
    if linear is not None:
        _attributes(linear, {'ang', 'scaled'})
        if len(linear) or linear.get('scaled', '1') not in ('0', '1', 'true', 'false'):
            raise ValueError('Unsupported linear gradient')
        _integer(linear.get('ang', '0'), 0, 21599999)
    path = root.find(A+'path')
    if path is not None:
        _attributes(path, {'path'})
        if path.get('path', 'shape') not in ('shape', 'circle', 'rect') or len(path) > 1:
            raise ValueError('Unsupported path gradient')
        for rectangle in path:
            if rectangle.tag != A+'fillToRect':
                raise ValueError('Unknown gradient path child')
            _rectangle(rectangle)
    tile = root.find(A+'tileRect')
    if tile is not None:
        _rectangle(tile)


def _parse(raw: object) -> Any:
    from lxml import etree

    if type(raw) is not str or len(raw) > 262144 or len(raw.encode('utf-8')) > 262144:
        raise ValueError('Gradient XML hint exceeds native profile')
    root = etree.fromstring(raw.encode('utf-8'), etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                                                              remove_comments=True, remove_pis=True))
    if root.getroottree().docinfo.doctype:
        raise ValueError('Gradient XML hint has a DTD')
    _validate(root)
    return root


def capture_gradient(fill: Any, palette: dict[str, str], stops: list[dict[str, Any]]) -> dict[str, Any]:
    from lxml import etree

    native = deepcopy(fill)
    for stop in native.findall(A+'gsLst/'+A+'gs'):
        checkpoint()
        for color in list(stop):
            if color.tag == A+'schemeClr':
                raw = palette.get(color.get('val', ''))
                if raw is None:
                    raise ValueError('Gradient theme base is unresolved')
                replacement = etree.Element(A+'srgbClr', val=raw)
                replacement.extend(deepcopy(child) for child in color)
                stop.replace(color, replacement)
    raw = etree.tostring(native, encoding='unicode')
    root = _parse(raw)
    original_stops = root.find(A+'gsLst')
    if len(original_stops) != len(stops):
        raise ValueError('Gradient stop projection is incomplete')
    for index, stop in enumerate(stops):
        stop['native_id'] = str(index)
    return {'format': 'drawingml-gradient', 'version': 1, 'xml': raw,
            'colors': [deepcopy(stop['color']) for stop in stops]}


def gradient_xml(stops: object, hint: object) -> Any:
    from lxml import etree

    if (type(hint) is not dict or set(hint) != {'format', 'version', 'xml', 'colors'}
            or hint['format'] != 'drawingml-gradient' or type(hint['version']) is not int or hint['version'] != 1):
        raise ValueError('Unsupported gradient hint version/schema')
    root = _parse(hint['xml'])
    original = list(root.find(A+'gsLst'))
    witnesses = hint['colors']
    if type(witnesses) is not list or len(witnesses) != len(original):
        raise ValueError('Gradient color witnesses do not match source')
    for node, value in zip(original, witnesses, strict=True):
        checkpoint()
        if type(value) is not dict or resolve_drawingml_color(node, {})[0] != ColorValue.from_dict(value):
            raise ValueError('Gradient source witness is inconsistent')
    if type(stops) is not list or not 2 <= len(stops) <= 4096:
        raise ValueError('Gradient requires at least two current stops')
    current = etree.Element(A+'gsLst')
    previous = -1
    for stop in stops:
        checkpoint()
        if (type(stop) is not dict or set(stop)-{'position', 'color', 'source', 'native_id'}
                or type(stop.get('position')) not in (int, float) or type(stop.get('color')) is not dict):
            raise ValueError('Invalid current gradient stop')
        position = stop['position']*100000
        if not 0 <= position <= 100000 or abs(position-round(position)) > 1e-6 or position < previous:
            raise ValueError('Gradient stop position is not ordered/native-representable')
        previous = position
        value = ColorValue.from_dict(stop['color'])
        identity = stop.get('native_id')
        original_index = (int(identity) if type(identity) is str and identity.isascii()
                          and identity.isdecimal() and len(identity) < 6 else -1)
        node = etree.SubElement(current, A+'gs', pos=str(round(position)))
        if 0 <= original_index < len(original) and value == ColorValue.from_dict(witnesses[original_index]):
            node.append(deepcopy(original[original_index][0]))
        else:
            if value.space is not ColorSpace.SRGB or value.icc_profile or value.blend_mode != 'normal':
                raise ValueError('Edited gradient color requires plain sRGB')
            if any(abs(component*255-round(component*255)) > 1e-8 for component in value.components):
                raise ValueError('Edited gradient color requires exact 8-bit RGB')
            color = etree.SubElement(node, A+'srgbClr', val=value.to_hex().lstrip('#'))
            if value.alpha != 1:
                alpha = value.alpha*100000
                if abs(alpha-round(alpha)) > 1e-6:
                    raise ValueError('Gradient alpha is not native-representable')
                etree.SubElement(color, A+'alpha', val=str(round(alpha)))
    old = root.find(A+'gsLst')
    root.replace(old, current)
    _validate(root)
    return root
