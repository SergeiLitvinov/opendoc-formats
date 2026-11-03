"""Editable background gradient using a bounded native hint and current visible stops."""

from __future__ import annotations

from typing import Any

from opendoc_formats.ooxml.pptx_gradient import KEY, A, gradient_xml
from opendoc_formats.support.cancellation import checkpoint

P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'


def write_gradient(slide: Any, properties: dict[str, Any]) -> bool:
    stops = properties.get('background_gradient_colors')
    if not stops or properties.get('background_fill') == 'none' or KEY not in properties:
        return False
    root = gradient_xml(stops, properties[KEY])
    slide.background.fill.solid()
    target = slide._element.find(P+'cSld/'+P+'bg/'+P+'bgPr')
    for child in list(target):
        checkpoint()
        if child.tag in {A+name for name in ('solidFill', 'noFill', 'gradFill', 'blipFill', 'pattFill', 'grpFill')}:
            target.remove(child)
    target.insert(0, root)
    return True
