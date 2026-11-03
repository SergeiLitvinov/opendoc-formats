"""Direct OOXML borders through the common model, with inert native extras."""

from __future__ import annotations

from collections import Counter
from typing import Any

from opendoc_model import ArtifactLimitError, Border, BorderSet, ColorValue, Table, TableCell, get_borders, set_borders

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SIDES = {'top': 'top', 'right': 'right', 'bottom': 'bottom', 'left': 'left',
         'insideH': 'inside-horizontal', 'insideV': 'inside-vertical',
         'tl2br': 'diagonal-down', 'tr2bl': 'diagonal-up'}
STYLES = {'single': 'solid', 'dashed': 'dashed', 'dotted': 'dotted', 'double': 'double',
          'dotDash': 'dash-dot', 'dotDotDash': 'dash-dot-dot'}


def _snapshot(border: Border) -> dict:
    return {'kind': border.kind, 'style': border.style, 'color': border.color.to_dict() if border.color else None,
            'width_pt': border.width_pt, 'offset_pt': border.offset_pt}


def _points(value: str | None, factor: int, maximum: int) -> float | None:
    if value is not None and len(value) <= 3 and value.isascii() and value.isdecimal() and 0 <= int(value) <= maximum:
        return int(value) / factor
    return None


def native_only(node: Any) -> bool:
    """Identify declarations beyond the finite semantic border profile."""
    allowed_sides = set(SIDES) - ({'tl2br', 'tr2bl'} if node.tag == W + 'tblBorders' else {'insideH', 'insideV'})
    seen = set()
    if node.attrib:
        return True
    for child in node:
        name = str(child.tag).removeprefix(W)
        if name not in allowed_sides or name in seen or len(child):
            return True
        seen.add(name)
        attrs = child.attrib
        if any(key not in {W + value for value in ('val', 'color', 'sz', 'space')} for key in attrs):
            return True
        if attrs.get(W + 'val') not in {*STYLES, 'none', 'nil'}:
            return True
        if W + 'sz' in attrs and _points(attrs[W + 'sz'], 8, 96) is None:
            return True
        if W + 'space' in attrs and _points(attrs[W + 'space'], 1, 31) is None:
            return True
        color = attrs.get(W + 'color')
        if color not in (None, 'auto'):
            if len(color) != 6:
                return True
            try:
                ColorValue.from_hex(color)
            except ValueError:
                return True
    return False


def import_borders(source: Table | TableCell, owner: Any) -> None:
    """Retain explicit declarations, never materialise inherited style defaults."""
    tag = 'tblBorders' if isinstance(source, Table) else 'tcBorders'
    groups = owner.findall(W + tag) if owner is not None else []
    if not groups:
        return
    node = groups[0]
    if len(node) > 64:
        raise ArtifactLimitError('DOCX border declarations exceed 64')
    if len(groups) != 1:
        raise ValueError('Duplicate border containers are outside the DOCX profile')
    allowed = set(SIDES) - ({'tl2br', 'tr2bl'} if isinstance(source, Table) else {'insideH', 'insideV'})
    names = [str(child.tag).removeprefix(W) for child in node]
    counts = Counter(names)
    declarations = {}
    opaque = []
    from lxml import etree

    for child, name in zip(node, names, strict=True):
        if name not in allowed or counts[name] != 1 or len(child):
            opaque.append(etree.tostring(child, encoding='unicode'))
            continue
        attrs = dict(child.attrib)
        val = attrs.get(W + 'val')
        kind = val if val in ('none', 'nil') else 'line'
        color = None
        if kind == 'line' and not any(key.startswith(W + 'theme') for key in attrs):
            try:
                color = ColorValue.from_hex(attrs[W + 'color']) if len(attrs.get(W + 'color', '')) == 6 else None
            except ValueError:
                pass
        border = Border(kind=kind, style=STYLES.get(val) if kind == 'line' else None, color=color,
                        width_pt=_points(attrs.get(W + 'sz'), 8, 96) if kind == 'line' else None,
                        offset_pt=_points(attrs.get(W + 'space'), 1, 31) if kind == 'line' else None)
        from dataclasses import replace

        declarations[SIDES[name]] = replace(border, extra={'docx_native': {'attributes': attrs, 'baseline': _snapshot(border)}})
    set_borders(source, BorderSet(declarations, extra={'docx_native': {'attributes': dict(node.attrib), 'children': opaque}}))


def _native_attributes(border: Border) -> dict:
    raw = border.extra.get('docx_native', {})
    if not isinstance(raw, dict):
        raise ValueError('Invalid native border metadata')
    baseline = raw.get('baseline', {})
    attrs = dict(raw.get('attributes', {})) if border.kind == baseline.get('kind') else {}
    current = _snapshot(border)
    if border.kind != 'line':
        attrs[W + 'val'] = border.kind
        return attrs
    for field, attribute in (('style', 'val'), ('color', 'color'), ('width_pt', 'sz'), ('offset_pt', 'space')):
        if baseline and current[field] == baseline.get(field):
            continue
        attrs.pop(W + attribute, None)
        value = current[field]
        if field == 'color':
            for key in list(attrs):
                if key.startswith(W + 'theme'):
                    attrs.pop(key)
        if value is None:
            continue
        if field == 'style':
            attrs[W + attribute] = {value: key for key, value in STYLES.items()}[value]
        elif field == 'color':
            attrs[W + attribute] = border.color.to_hex().removeprefix('#')[:6].upper()
        else:
            number = value * (8 if field == 'width_pt' else 1)
            if number != int(number) or not 0 <= number <= (96 if field == 'width_pt' else 31):
                raise ValueError('Border measurement cannot be represented exactly in DOCX')
            attrs[W + attribute] = str(int(number))
    if W + 'val' not in attrs:
        raise ValueError('Unknown border style has no native declaration')
    return attrs


def export_borders(source: Table | TableCell, owner: Any, report: Any, location: str) -> None:
    """Typed edits/removal override inert native declarations; errors stay atomic."""
    from docx.oxml import OxmlElement
    from lxml import etree
    from opendoc_model import IssueSeverity

    tag = 'tblBorders' if isinstance(source, Table) else 'tcBorders'
    for previous in list(owner.findall(W + tag)):
        owner.remove(previous)
    record = get_borders(source)
    if record is None:
        return
    try:
        node = OxmlElement('w:' + tag)
        raw = record.extra.get('docx_native', {})
        node.attrib.update(raw.get('attributes', {}))
        parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
        fragments = raw.get('children', [])
        if not isinstance(fragments, list) or len(fragments) > 64:
            raise ValueError('Invalid native border children')
        for fragment in fragments:
            if not isinstance(fragment, str) or len(fragment.encode()) > 65536:
                raise ValueError('Native border child exceeds 64 KiB')
            child = etree.fromstring(fragment.encode(), parser)
            if SIDES.get(str(child.tag).removeprefix(W)) not in record.sides:
                node.append(child)
        for side, border in record.sides.items():
            child = OxmlElement('w:' + {value: key for key, value in SIDES.items()}[side])
            child.attrib.update(_native_attributes(border))
            node.append(child)
            color = border.color
            if color is not None and (color.alpha != 1 or color.icc_profile or color.blend_mode != 'normal'):
                report.add(IssueSeverity.LOSS, 'docx-border-color', 'Border color effects converted to opaque sRGB', location)
        if native_only(node):
            report.add(IssueSeverity.LOSS, 'docx.table-borders',
                       'Native border details retained without full semantic support', location)
        owner.insert_element_before(node, *(['w:shd', 'w:tblLayout', 'w:tblCellMar', 'w:tblLook'] if tag == 'tblBorders'
                                          else ['w:shd', 'w:noWrap', 'w:tcMar', 'w:textDirection', 'w:vAlign']))
    except (ValueError, TypeError, KeyError, AttributeError, etree.XMLSyntaxError) as error:
        report.add(IssueSeverity.ERROR, 'docx-table-borders', str(error), location)
