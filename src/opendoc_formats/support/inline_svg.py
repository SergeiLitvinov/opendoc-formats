"""Finite inert SVG profile for exposing shape anchors in HTML and EPUB."""

import re
from xml.etree import ElementTree as ET

from opendoc_formats.support.cancellation import checkpoint

_SVG = 'http://www.w3.org/2000/svg'
SVG_TAG_CASE = {'lineargradient': 'linearGradient', 'radialgradient': 'radialGradient'}
_GRADIENTS = set(SVG_TAG_CASE.values())
_SHAPES = {'rect', 'circle', 'ellipse', 'line', 'path', 'polyline', 'polygon'}
_USE_TARGETS = _SHAPES | {'g', 'use', 'symbol'}
_TAGS = {'svg', 'title', 'desc', 'defs', 'stop'} | _GRADIENTS | _USE_TARGETS
_ATTRIBUTES = {
    'id', 'aria-label', 'viewBox', 'preserveAspectRatio', 'x', 'y', 'x1', 'y1', 'x2', 'y2', 'width', 'height',
    'cx', 'cy', 'rx', 'ry', 'r', 'd', 'points', 'transform', 'fill', 'stroke', 'fill-rule',
    'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit', 'stroke-dasharray',
    'stroke-dashoffset', 'opacity', 'fill-opacity', 'stroke-opacity',
    'gradientUnits', 'gradientTransform', 'spreadMethod', 'fx', 'fy', 'fr', 'offset', 'stop-color', 'stop-opacity',
}
_PAINT = re.compile(r'#[0-9a-fA-F]{3,8}|[A-Za-z]+')
_LOCAL_PAINT = re.compile(r'url\(#([A-Za-z0-9_.:-]+)\)')
_LOCAL_HREF = re.compile(r'#([A-Za-z0-9_.:-]+)')
_XLINK_HREF = '{http://www.w3.org/1999/xlink}href'
_MAX_EXPANDED_NODES = 100_000
_MAX_EXPANDED_DEPTH = 64


def inline_svg_tree(value: str) -> ET.Element:
    """Validate an SVG before placing it in an XHTML document as active markup."""
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', value, re.I):
        raise ValueError('DTD and entities are not accepted in inline SVG')
    try:
        root = ET.fromstring(value)
    except ET.ParseError as error:
        raise ValueError('Invalid inline SVG XML') from error
    if root.tag != f'{{{_SVG}}}svg':
        raise ValueError('Inline SVG requires an SVG namespace and root')
    gradients: set[str] = set()
    reusable_shapes: dict[str, ET.Element] = {}
    shape_references: dict[ET.Element, str] = {}
    referenced: set[str] = set()
    seen: set[str] = set()
    inheritance: dict[str, str] = {}
    for node in root.iter():
        checkpoint()
        name = node.tag.removeprefix(f'{{{_SVG}}}')
        if name == node.tag:
            raise ValueError('Inline SVG element has a foreign namespace')
        name = SVG_TAG_CASE.get(name, name)
        if name not in _TAGS:
            raise ValueError('Inline SVG element is outside the static shape profile')
        node.tag = f'{{{_SVG}}}{name}'
        identifier = node.get('id')
        legacy_href = node.attrib.pop(_XLINK_HREF, None)
        if legacy_href is not None:
            if node.get('href', legacy_href) != legacy_href:
                raise ValueError('Conflicting inline SVG references')
            node.set('href', legacy_href)
        if identifier:
            if identifier in seen:
                raise ValueError('Duplicate inline SVG identifier')
            seen.add(identifier)
            if name in _GRADIENTS:
                gradients.add(identifier)
            if name in _USE_TARGETS:
                reusable_shapes[identifier] = node
        if name == 'use':
            match = _LOCAL_HREF.fullmatch(node.get('href', ''))
            if match is None:
                raise ValueError('Inline SVG use requires a local fragment')
            shape_references[node] = match[1]
        for key, val in node.attrib.items():
            if key == 'href' and name == 'use':
                continue
            if key == 'href' and name in _GRADIENTS:
                match = _LOCAL_HREF.fullmatch(val)
                if match is None:
                    raise ValueError('SVG gradient inheritance requires a local fragment')
                referenced.add(match[1])
                if identifier:
                    inheritance[identifier] = match[1]
                continue
            if key not in _ATTRIBUTES:
                raise ValueError('Inline SVG attribute is outside the static shape profile')
            if key in {'fill', 'stroke', 'stop-color'} and not _PAINT.fullmatch(val.strip()):
                match = _LOCAL_PAINT.fullmatch(val.strip()) if key != 'stop-color' else None
                if match is None:
                    raise ValueError('Inline SVG paint is outside the static shape profile')
                referenced.add(match[1])
    if referenced - gradients:
        raise ValueError('Inline SVG paint and inheritance must point to a local gradient')
    if set(shape_references.values()) - reusable_shapes.keys():
        raise ValueError('Inline SVG use target is outside the local static profile')
    if shape_references:
        _check_use_expansion(root, {node: reusable_shapes[target] for node, target in shape_references.items()})
    checked: set[str] = set()
    for start in inheritance:
        chain: set[str] = set()
        current = start
        while current in inheritance and current not in checked:
            checkpoint()
            if current in chain:
                raise ValueError('Cyclic inline SVG gradient inheritance')
            chain.add(current)
            current = inheritance[current]
        checked.update(chain)
    return root


def _check_use_expansion(root: ET.Element, references: dict[ET.Element, ET.Element]) -> None:
    """Measure the expanded tree without cloning referenced subtrees."""
    active: set[ET.Element] = set()
    measured: dict[ET.Element, tuple[int, int]] = {}
    stack = [(root, False)]
    while stack:
        checkpoint()
        node, leaving = stack.pop()
        if node in measured:
            continue
        children = list(node)
        if node in references:
            children.append(references[node])
        if not leaving:
            if node in active:
                raise ValueError('Cyclic inline SVG use reference')
            active.add(node)
            if len(active) > _MAX_EXPANDED_DEPTH:
                raise ValueError('Inline SVG use expansion exceeds depth limit')
            stack.append((node, True))
            stack.extend((child, False) for child in reversed(children))
            continue
        size = 1 + sum(measured[child][0] for child in children)
        depth = 1 + max((measured[child][1] for child in children), default=0)
        if size > _MAX_EXPANDED_NODES or depth > _MAX_EXPANDED_DEPTH:
            raise ValueError('Inline SVG use expansion exceeds size or depth limit')
        measured[node] = size, depth
        active.remove(node)


def remap_svg_paint(root: ET.Element, identifiers: dict[str, str]) -> None:
    for node in root.iter():
        checkpoint()
        for attribute in ('fill', 'stroke'):
            match = _LOCAL_PAINT.fullmatch(node.get(attribute, '').strip())
            if match:
                node.set(attribute, f'url(#{identifiers[match[1]]})')


def serialize_inline_svg(root: ET.Element) -> str:
    for node in root.iter():
        checkpoint()
        node.tag = node.tag.split('}', 1)[1]
    root.set('xmlns', _SVG)
    return ET.tostring(root, encoding='unicode', short_empty_elements=False)
