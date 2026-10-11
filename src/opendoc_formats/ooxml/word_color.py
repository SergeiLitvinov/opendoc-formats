"""Own direct Word color declarations without flattening the style cascade."""

from __future__ import annotations

from typing import Any

from opendoc_model.color import ColorValue
from opendoc_model.document_model import TextStyle


def color_record(style: TextStyle) -> Any:
    return style.color.to_dict() if isinstance(style.color, ColorValue) else style.color


def color_needs_patch(style: TextStyle) -> bool:
    return ('docx_color_imported_value' in style.properties
            and color_record(style) != style.properties['docx_color_imported_value'])


def default_color_owner(root: Any) -> Any:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    parent = root
    for name in ('docDefaults', 'rPrDefault', 'rPr'):
        child = parent.find(qn('w:' + name))
        if child is None:
            child = OxmlElement('w:' + name)
            parent.insert(0, child)
        parent = child
    return parent


def apply_color(owner: Any, style: TextStyle) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    for existing in owner.findall(qn('w:color')):
        owner.remove(existing)
    if style.color is None:
        return
    node = OxmlElement('w:color')
    unchanged = ('docx_color_imported_value' in style.properties
                 and color_record(style) == style.properties['docx_color_imported_value'])
    raw = (style.color.to_hex().removeprefix('#') if isinstance(style.color, ColorValue)
           else style.color.removeprefix('#'))
    if unchanged:
        raw = style.properties.get('color_native_value') or raw
    node.set(qn('w:val'), raw)
    if style.properties.get('color_theme') and (unchanged or 'docx_color_imported_value' not in style.properties):
        node.set(qn('w:themeColor'), str(style.properties['color_theme']))
        for key, attribute in (('tint', 'themeTint'), ('shade', 'themeShade')):
            value = (style.properties.get('color_modifiers') or {}).get(key)
            if isinstance(value, (int, float)):
                node.set(qn('w:' + attribute), f'{round(max(0.0, min(1.0, value)) * 255):02X}')
    owner.insert_element_before(node, 'w:spacing', 'w:w', 'w:kern', 'w:position', 'w:sz', 'w:szCs',
                               'w:highlight', 'w:u', 'w:effect', 'w:bdr', 'w:shd', 'w:fitText', 'w:vertAlign',
                               'w:rtl', 'w:cs', 'w:em', 'w:lang', 'w:eastAsianLayout', 'w:specVanish', 'w:oMath')
