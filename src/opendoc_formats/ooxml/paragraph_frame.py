"""Finite page-anchored editable paragraph frames for fixed-layout conversion."""

from __future__ import annotations

import math
from typing import Any

from opendoc_model import Box, IssueSeverity, Paragraph, TextRun

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MARKER = 'docx_page_frame'
_ALLOWED = {'x', 'y', 'w', 'h', 'hRule', 'hAnchor', 'vAnchor', 'wrap', 'anchorLock'}


def import_frame(source: Any, target: Paragraph) -> None:
    nodes = source._p.xpath('./w:pPr/w:framePr')
    if not nodes:
        return
    node = nodes[0]
    try:
        if (len(nodes) != 1 or len(node) or not set(node.attrib) <= {W + name for name in _ALLOWED}
                or node.get(W + 'hAnchor') != 'page' or node.get(W + 'vAnchor') != 'page'
                or node.get(W + 'wrap', 'auto') != 'none' or node.get(W + 'hRule', 'auto') != 'atLeast'):
            raise ValueError('Unsupported native paragraph frame')
        values = [int(node.get(W + name, '')) for name in ('x', 'y', 'w', 'h')]
        if any(abs(value) >= 2**31 for value in values) or min(values[2:]) <= 0:
            raise ValueError('Invalid native paragraph frame')
        target.box = Box(*[value / 20 for value in values])
        target.properties[MARKER] = True
    except (ValueError, TypeError):
        target.properties['docx_page_frame_unsupported'] = True


def export_frame(source: Paragraph, target: Any, report: Any, location: str, *, pdf: bool = False) -> None:
    if source.properties.get('docx_page_frame_unsupported'):
        report.add(IssueSeverity.ERROR, 'docx.paragraph-frame',
                   'Unknown native paragraph frame requires native resolution', location)
        return
    if not source.properties.get(MARKER) and not (pdf and source.box is not None):
        return
    try:
        box = source.box
        if box is None or box.rotation or min(box.width, box.height) <= 0:
            raise ValueError('Page frame requires a positive unrotated Box')
        values = [box.x, box.y, box.width, box.height]
        origin = source.properties.get('pdf_text_origin')
        if pdf and origin is not None:
            from opendoc_formats.fonts.word_metrics import word_line_ascent

            runs = [item for item in source.content if isinstance(item, TextRun) and item.text]
            ascents = [word_line_ascent(run.style) for run in runs]
            ascent = (max(value + run.style.properties.get('docx_run_position_pt', 0) for run, value in zip(runs, ascents))
                      if ascents and all(value is not None for value in ascents) else None)
            if not isinstance(origin, list) or len(origin) != 2 or ascent is None:
                raise ValueError('PDF text baseline requires resolved Word font metrics')
            values[0], values[1] = origin[0], origin[1] - ascent
            # A PDF ink box is not a Word line container: leave room for the
            # native paragraph end marker and font advance rounding.
            values[2] += 2 * max(run.style.font_size.pt for run in runs if run.style.font_size is not None)
        if any(type(value) not in (int, float) or not math.isfinite(value) or abs(value * 20) >= 2**31 for value in values):
            raise ValueError('Page frame exceeds native coordinate limits')
        from docx.oxml import OxmlElement

        owner = target._p.get_or_add_pPr()
        for old in owner.findall(W + 'framePr'):
            owner.remove(old)
        node = OxmlElement('w:framePr')
        for name, value in zip(('x', 'y', 'w', 'h'), values):
            node.set(W + name, str(round(value * 20)))
        for name, value in [('hAnchor', 'page'), ('vAnchor', 'page'), ('wrap', 'none'), ('hRule', 'atLeast')]:
            node.set(W + name, value)
        owner.insert_element_before(node, 'w:widowControl', 'w:numPr', 'w:pBdr', 'w:tabs', 'w:spacing', 'w:ind', 'w:jc')
    except (ValueError, TypeError, OverflowError) as error:
        report.add(IssueSeverity.ERROR, 'docx.paragraph-frame', str(error), location)
