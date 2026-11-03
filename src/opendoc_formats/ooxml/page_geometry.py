"""Source DOCX page declarations and explicit edits, without treating defaults as evidence."""

from __future__ import annotations

import math
from typing import Any

from opendoc_model import PageSettings, Section

from opendoc_formats.support.cancellation import checkpoint

KEY = 'opendoc_formats.docx_page'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
GROUPS = {'size': {'width': 'w', 'height': 'h'},
          'margins': {'margin_top': 'top', 'margin_right': 'right', 'margin_bottom': 'bottom', 'margin_left': 'left',
                      'header_distance_pt': 'header', 'footer_distance_pt': 'footer', 'gutter_pt': 'gutter'}}
TAGS = {'size': 'pgSz', 'margins': 'pgMar'}
PAGE_FIELDS = ('width', 'height', 'margin_top', 'margin_right', 'margin_bottom', 'margin_left')
DISTANCES = ('header_distance_pt', 'footer_distance_pt', 'gutter_pt')


def values(section: Section) -> dict[str, float | None]:
    return {**{name: float(getattr(section.page, name).pt) for name in PAGE_FIELDS},
            **{name: section.properties.get(name) for name in DISTANCES}}


def source_geometry(native: Any, page: PageSettings, properties: dict[str, Any], *, section_present: bool) -> dict[str, Any]:
    from lxml import etree

    checkpoint()
    result: dict[str, Any] = {'format': KEY, 'version': 1, 'section_present': section_present,
                              'break_on_paragraph': section_present and native._sectPr.getparent().tag == W+'pPr'}
    missing = []
    for group, fields in GROUPS.items():
        nodes = native._sectPr.findall(W+TAGS[group]) if section_present else []
        if len(nodes) > 1:
            from opendoc_formats.errors import UnsupportedDocumentError

            raise UnsupportedDocumentError('DOCX '+str(native._document_part.partname)+': duplicate '
                                           +TAGS[group]+' page declarations')
        node = nodes[0] if nodes else None
        result[group] = etree.tostring(node, encoding='unicode', with_tail=False) if node is not None else None
        for field, attribute in fields.items():
            if field in PAGE_FIELDS and (node is None or node.get(W+attribute) is None):
                missing.append(field)
    result['projected'] = {**{name: float(getattr(page, name).pt) for name in PAGE_FIELDS},
                           **{name: properties.get(name) for name in DISTANCES}}
    result['unresolved'] = missing
    return result


def _state(section: Section) -> dict[str, Any] | None:
    state = section.properties.get(KEY)
    if state is None:
        return None
    if (not isinstance(state, dict) or state.get('format') != KEY or type(state.get('version')) is not int
            or state['version'] != 1 or type(state.get('section_present')) is not bool
            or type(state.get('break_on_paragraph')) is not bool
            or not isinstance(state.get('projected'), dict)
            or set(state['projected']) != set(PAGE_FIELDS+DISTANCES)
            or not isinstance(state.get('unresolved'), list)
            or any(field not in PAGE_FIELDS for field in state['unresolved'])):
        raise ValueError('Invalid or unsupported source page geometry profile')
    for name, value in state['projected'].items():
        if value is None and name in DISTANCES:
            continue
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Invalid projected page geometry value')
    if any(group not in state or (state[group] is not None and not isinstance(state[group], str)) for group in GROUPS):
        raise ValueError('Invalid source page XML')
    if not state['section_present'] and (state['break_on_paragraph'] or any(state[group] is not None for group in GROUPS)):
        raise ValueError('Absent section cannot declare page geometry')
    return state


def unresolved(section: Section) -> list[str]:
    state = _state(section)
    if state is None:
        return []
    current = values(section)
    return [name for name in state['unresolved'] if current[name] == state['projected'][name]]


def restore_geometry(native: Any, section: Section, *, limits: Any = None) -> None:
    """Run after common geometry/running content; unchanged fields retain source omission."""
    from docx.oxml import OxmlElement, parse_xml
    from opendoc_model import ArtifactLimitError, DocumentLimits

    from opendoc_formats.anatomy import AnatomyLimits, _Budget, _xml_nodes

    checkpoint()
    state = _state(section)
    if state is None:
        return
    budget = limits or DocumentLimits()
    maximum = min(AnatomyLimits().max_part_bytes, budget.max_bytes)
    xml_budget = _Budget(AnatomyLimits(max_part_bytes=maximum, max_xml_nodes=budget.max_nodes,
                                    max_xml_depth=budget.max_depth, max_xml_characters=budget.max_bytes))
    current, changed = values(section), False
    for group, fields in GROUPS.items():
        checkpoint()
        raw = state[group]
        node = None
        if raw is not None:
            data = raw.encode('utf-8')
            if len(data) > maximum:
                raise ArtifactLimitError('Source page XML exceeds byte budget', path=KEY+'.'+group,
                                         quota='bytes', maximum=maximum)
            _xml_nodes(data, KEY+'.'+group, xml_budget, count_markup=True)
            node = parse_xml(data)
            if node.tag != W+TAGS[group]:
                raise ValueError('Source page geometry has an unexpected XML root')
        generated = native._sectPr.find(W+TAGS[group])
        for field, attribute in fields.items():
            checkpoint()
            if current[field] == state['projected'][field]:
                continue
            changed = True
            if node is None:
                node = OxmlElement('w:'+TAGS[group])
            value = generated.get(W+attribute) if generated is not None and current[field] is not None else None
            if value is None:
                node.attrib.pop(W+attribute, None)
            else:
                node.set(W+attribute, value)
        if generated is not None:
            if node is None:
                native._sectPr.remove(generated)
            else:
                native._sectPr.replace(generated, node)
        elif node is not None:
            getattr(native._sectPr, '_insert_'+TAGS[group])(node)
    # With no source sectPr Word applies document/environment defaults, which
    # differ from an explicit empty sectPr. Do not introduce that section solely
    # for the template's otherwise unused columns/docGrid declarations.
    if (not state['section_present'] and not changed
            and all(node.tag in {W+'cols', W+'docGrid'} for node in native._sectPr)):
        native._sectPr.getparent().remove(native._sectPr)
