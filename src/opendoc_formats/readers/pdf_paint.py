"""PDF paint evidence, independent of semantic reading order and Word layout."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from opendoc_model import DocumentLimits, DocumentModel, FontReference, Formula, Image, TextRun, set_font_reference, walk_model


def attach_text_paint(document: DocumentModel, path: str | Path, *, limits: DocumentLimits | None) -> None:
    from opendoc_formats.readers.pdf_content import content_only_pdf

    with content_only_pdf(path) as native:
        indices = []
        for page in native:
            from opendoc_formats.readers.pdf_graphics_state import native_paint_states

            evidence = native_paint_states(page, limits=limits)
            from opendoc_formats.readers.pdf_image_clips import image_clip_profiles
            from opendoc_formats.readers.pdf_images import _neutral_page_group

            graphics = page.get_drawings(extended=True)
            clips = sum(draw.get('type') == 'clip' for draw in graphics)
            unknown = (any(draw.get('type') == 'group' and not _neutral_page_group(page, draw) for draw in graphics)
                       or bool(clips and not (clips == 1 and len(image_clip_profiles(page)) == 1)))
            index: dict[tuple[float, float], list[tuple[dict[str, Any], int]]] = defaultdict(list)
            for trace in page.get_texttrace():
                for offset, character in enumerate(trace['chars']):
                    index[_point_key(character[2])].append((trace, offset))
            from opendoc_formats.readers.pdf_font_bindings import painted_font_programs

            programs = painted_font_programs(page, document.resources, set(index))
            indices.append((index, unknown, programs, evidence))
        for section, (index, unknown, programs, graphics) in zip(document.sections, indices, strict=True):
            section.properties['pdf_graphics'] = graphics
            for reference in walk_model(section, limits=limits):
                run = reference.node
                if isinstance(run, Image):
                    resource = document.resources.get(run.resource_id)
                    if resource is not None and resource.media_type == 'application/pdf+vector':
                        from opendoc_formats.pdf_graphics import paint_clips

                        try:
                            paint_clips(graphics, run.properties.get('pdf_paint_seq'), {'fill-path', 'stroke-path'},
                                        compositing=True)
                            resource.properties['pdf_docx_graphics_measured'] = True
                        except ValueError:
                            pass
                if isinstance(run, Formula):
                    for line in run.properties.get('pdf_native_lines', []):
                        for span in line:
                            span['paint'] = _evidence(span['text'], span['font'], span['origin'], index, programs)
                            span['paint']['pdf_graphics_state_unknown'] = unknown
                if not isinstance(run, TextRun) or not run.properties.get('pdf_origin'):
                    continue
                evidence = _evidence(run.text, run.style.font_family, run.properties['pdf_origin'], index, programs)
                identifier = evidence.pop('pdf_font_resource', None)
                if identifier is not None:
                    set_font_reference(run.style, FontReference(identifier), limits=limits)
                run.properties.update(evidence)
                run.properties['pdf_graphics_state_unknown'] = unknown


def _evidence(text: str, font: str, origin: Any, index: dict, programs: dict) -> dict:
    candidates = []
    for trace, offset in index.get(_point_key(origin), []):
        native_text = ''.join(chr(character[0]) for character in trace['chars'][offset:offset + len(text)])
        if native_text.startswith(text) and (trace['font'] == font or not trace['font']):
            candidates.append((trace, offset))
    if len(candidates) != 1:
        return {'pdf_paint_unknown': True}
    trace, offset = candidates[0]
    evidence = {'pdf_paint_seq': trace['seqno'], 'pdf_paint_type': trace['type'], 'pdf_paint_opacity': trace['opacity']}
    bindings = [programs.get((_point_key(char[2]), char[0]), set())
                for char in trace['chars'][offset:offset + len(text)]]
    if bindings and all(len(binding) == 1 and None not in binding for binding in bindings):
        identifiers = set.union(*bindings)
        if len(identifiers) == 1:
            evidence['pdf_font_resource'] = next(iter(identifiers))
    return evidence


def _point_key(point: Any) -> tuple[float, float]:
    return round(float(point[0]), 3), round(float(point[1]), 3)
