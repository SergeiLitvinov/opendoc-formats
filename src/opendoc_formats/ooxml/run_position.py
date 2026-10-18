"""Direct native Word baseline shifts in half-point units."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
KEY = 'docx_run_position_pt'


def import_run_position(run: Any, properties: Any) -> None:
    nodes = run._r.xpath('./w:rPr/w:position')
    if not nodes:
        return
    raw = nodes[0].get(W + 'val', '')
    if (len(nodes) == 1 and not len(nodes[0]) and set(nodes[0].attrib) == {W + 'val'}
            and raw.lstrip('-').isdigit() and len(raw) <= 10 and abs(int(raw)) < 2**31):
        properties[KEY] = int(raw) / 2
    else:
        properties['docx_run_position_unsupported'] = True


def native_position(properties: Mapping[str, Any]) -> int | None:
    if properties.get('docx_run_position_unsupported') and KEY not in properties:
        raise ValueError('Unknown run baseline requires an explicit replacement or None')
    value = properties.get(KEY)
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value * 2) >= 2**31:
        raise ValueError('Run baseline must be finite signed half-points')
    raw = round(value * 2)
    if not math.isclose(value * 2, raw, rel_tol=0, abs_tol=1e-7):
        raise ValueError('Run baseline cannot be represented exactly in half-points')
    return raw


def export_run_position(properties: Mapping[str, Any], owner: Any) -> None:
    raw = native_position(properties)
    if raw is None:
        return
    from docx.oxml import OxmlElement

    for old in owner.findall(W + 'position'):
        owner.remove(old)
    node = OxmlElement('w:position')
    node.set(W + 'val', str(raw))
    owner.insert_element_before(node, 'w:sz', 'w:szCs', 'w:highlight', 'w:u', 'w:vertAlign')
