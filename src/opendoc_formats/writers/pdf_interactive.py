"""Bounded native PDF interactions; source actions are never executed."""

from __future__ import annotations

import math
from typing import Any, Callable

from opendoc_model import ConversionReport, DocumentModel, IssueSeverity, get_integration
from opendoc_model.limits import DocumentLimits

from opendoc_formats.writers.pdf_outline import _safe_uri


def write_interactions(
    pdf: Any, document: DocumentModel, report: ConversionReport,
    pages: dict[str, tuple[int, tuple[float, float], bool]], cancelled: Callable[[], bool],
    *, limits: DocumentLimits | None = None,
) -> None:
    rotations = [page.rotation for page in pdf]
    try:
        for page in pdf:
            page.set_rotation(0)
            pdf.reload_page(page)
        _write_interactions(pdf, document, report, pages, cancelled, limits=limits)
    finally:
        for index, rotation in enumerate(rotations):
            pdf[index].set_rotation(rotation)


def _write_interactions(
    pdf: Any, document: DocumentModel, report: ConversionReport,
    pages: dict[str, tuple[int, tuple[float, float], bool]], cancelled: Callable[[], bool],
    *, limits: DocumentLimits | None = None,
) -> None:
    import pymupdf as fitz

    integration = get_integration(document, limits=limits)
    if integration is None:
        return
    if len(integration.annotations) + len(integration.forms) > 10_000:
        report.add(IssueSeverity.ERROR, 'pdf.interaction-limit', 'Interactive objects exceed the finite profile', 'integration')
        return
    names: dict[str, tuple[str, int, str | None]] = {}
    for group, values in (('annotations', integration.annotations), ('forms', integration.forms)):
        for item in values:
            location = f'integration.{group}[{item.id}]'
            if cancelled():
                report.add(IssueSeverity.ERROR, 'pdf.interaction-cancelled', 'Export cancelled', location)
                return
            binding = pages.get(item.page_id)
            if binding is None or not binding[2]:
                report.add(IssueSeverity.LOSS, 'pdf.interaction-geometry', 'No confirmed one-page source geometry', location)
                continue
            box = item.box
            if box is None or box.rotation != 0 or any(
                not math.isfinite(v) or abs(v) > 1_000_000 for v in (box.x, box.y, box.width, box.height)
            ) or box.width <= 0 or box.height <= 0:
                report.add(IssueSeverity.ERROR, 'pdf.interaction-geometry', 'Invalid native interaction rectangle', location)
                return
            page = pdf[binding[0]]
            rect = fitz.Rect(box.x, box.y, box.x + box.width, box.y + box.height)
            if group == 'forms':
                if item.kind != 'text':
                    report.add(IssueSeverity.LOSS, 'pdf.form-type', 'Only native text fields are supported', location)
                    continue
                name, flags = item.extra.get('field_name', ''), item.extra.get('field_flags', 0)
                if not isinstance(name, str) or not name or len(name) > 65_536 or len(item.value) > 65_536:
                    report.add(IssueSeverity.ERROR, 'pdf.form-value', 'Invalid or excessive field name/value', location)
                    return
                if type(flags) is not int or not 0 <= flags <= 0x7fffffff:
                    report.add(IssueSeverity.ERROR, 'pdf.form-flags', 'Invalid field flags', location)
                    return
                default = item.extra.get('pdf_default_value')
                if default is not None and (not isinstance(default, str) or len(default) > 65_536):
                    report.add(IssueSeverity.ERROR, 'pdf.form-default', 'Invalid or excessive default value', location)
                    return
                if name in names and names[name] != (item.value, flags, default):
                    report.add(IssueSeverity.ERROR, 'pdf.form-conflict', 'Shared widgets have conflicting values/flags', location)
                    return
                names[name] = item.value, flags, default
                widget = fitz.Widget()
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                widget.field_name, widget.field_value, widget.field_flags = name, item.value, flags
                widget.field_label, widget.rect = item.extra.get('field_label', ''), rect
                for key, value in item.extra.get('pdf_widget_appearance', {}).items():
                    if key in _APPEARANCE:
                        setattr(widget, key, value)
                action = item.action
                supported = not action or (set(action).issubset({'A', 'script'})
                    and item.extra.get('pdf_action_profile') == 'javascript-A-v1'
                    and action.get('A') == item.extra.get('pdf_source_action'))
                if not supported:
                    report.add(IssueSeverity.LOSS, 'pdf.form-action', 'Unsupported actions are not recreated', location)
                if supported and action.get('script'):
                    script = action['script']
                    if not isinstance(script, str) or len(script) > 65_536:
                        report.add(IssueSeverity.ERROR, 'pdf.interaction-limit', 'Invalid or excessive script data', location)
                        return
                    widget.script = script
                created = page.add_widget(widget)
                # Distinct page occurrences must not be merged by save(garbage=4).
                pdf.xref_set_key(created.xref, 'P', f'{page.xref} 0 R')
                if default is not None:
                    pdf.xref_set_key(created.xref, 'DV', fitz.get_pdf_str(default))
            elif item.kind == 'link':
                if not _safe_uri(item.target):
                    report.add(IssueSeverity.LOSS, 'pdf.link-action', 'Only safe URI destinations are supported', location)
                    continue
                if set(item.action).difference({'destination', 'A'}) or (
                    item.action.get('A') and not item.extra.get('pdf_uri_action_complete')
                ):
                    report.add(IssueSeverity.LOSS, 'pdf.link-action', 'Additional native actions are not recreated', location)
                page.insert_link({'kind': fitz.LINK_URI, 'from': rect, 'uri': item.target})
            elif item.kind in {'note', 'highlight'}:
                if item.action:
                    report.add(IssueSeverity.LOSS, 'pdf.annotation-action', 'Annotation actions are not recreated', location)
                if len(item.text) > 65_536:
                    report.add(IssueSeverity.ERROR, 'pdf.interaction-limit', 'Annotation text exceeds the profile', location)
                    return
                if item.kind == 'note' and item.extra.get('pdf_type', fitz.PDF_ANNOT_TEXT) == fitz.PDF_ANNOT_TEXT:
                    annotation = page.add_text_annot(rect.tl, item.text)
                    annotation.set_rect(rect)
                elif item.kind == 'highlight':
                    vertices, baseline = item.extra.get('vertices', []), item.extra.get('pdf_source_box')
                    if not vertices or len(vertices) % 4 or len(vertices) > 4096 or baseline is None:
                        report.add(IssueSeverity.LOSS, 'pdf.highlight-geometry', 'No confirmed quadrilaterals', location)
                        continue
                    x, y, width, height = baseline
                    if width <= 0 or height <= 0:
                        report.add(IssueSeverity.ERROR, 'pdf.highlight-geometry', 'Invalid source highlight rectangle', location)
                        return
                    points = []
                    for point in vertices:
                        if len(point) != 2 or any(not math.isfinite(v) or abs(v) > 1_000_000 for v in point):
                            report.add(IssueSeverity.ERROR, 'pdf.highlight-geometry', 'Invalid highlight vertex', location)
                            return
                        points.append(fitz.Point(box.x + (point[0]-x)*box.width/width,
                                                box.y + (point[1]-y)*box.height/height))
                    annotation = page.add_highlight_annot([fitz.Quad(points[i:i+4]) for i in range(0, len(points), 4)])
                else:
                    report.add(IssueSeverity.LOSS, 'pdf.annotation-type', 'Unsupported note subtype', location)
                    continue
                info = item.extra.get('info', {})
                annotation.set_info(content=item.text, title=info.get('title', ''), subject=info.get('subject', ''))
                annotation.set_flags(item.extra.get('flags', 0))
                colors = item.extra.get('colors', {})
                if colors:
                    annotation.set_colors(stroke=colors.get('stroke'), fill=colors.get('fill'))
                annotation.set_opacity(item.extra.get('opacity', 1))
                annotation.update()
            else:
                report.add(IssueSeverity.LOSS, 'pdf.annotation-type', 'Unsupported interaction type', location)


_APPEARANCE = ('border_color', 'border_style', 'border_width', 'border_dashes', 'fill_color',
               'text_color', 'text_font', 'text_fontsize', 'text_maxlen')
