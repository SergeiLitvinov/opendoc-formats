"""PDF paint evidence, independent of semantic reading order and Word layout."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from opendoc_model import DocumentLimits, DocumentModel, Formula, TextRun, walk_model


def attach_text_paint(document: DocumentModel, path: str | Path, *, limits: DocumentLimits | None) -> None:
    from opendoc_formats.readers.pdf_content import content_only_pdf

    with content_only_pdf(path) as native:
        indices = []
        for page in native:
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
            indices.append((index, unknown))
        for section, (index, unknown) in zip(document.sections, indices, strict=True):
            for reference in walk_model(section, limits=limits):
                run = reference.node
                if isinstance(run, Formula):
                    for line in run.properties.get('pdf_native_lines', []):
                        for span in line:
                            span['paint'] = _evidence(span['text'], span['font'], span['origin'], index)
                            span['paint']['pdf_graphics_state_unknown'] = unknown
                if not isinstance(run, TextRun) or not run.properties.get('pdf_origin'):
                    continue
                run.properties.update(_evidence(run.text, run.style.font_family, run.properties['pdf_origin'], index))
                run.properties['pdf_graphics_state_unknown'] = unknown


def _evidence(text: str, font: str, origin: Any, index: dict) -> dict:
    candidates = []
    for trace, offset in index.get(_point_key(origin), []):
        native_text = ''.join(chr(character[0]) for character in trace['chars'][offset:offset + len(text)])
        if native_text.startswith(text) and trace['font'] == font:
            candidates.append(trace)
    if len(candidates) != 1:
        return {'pdf_paint_unknown': True}
    trace = candidates[0]
    return {'pdf_paint_seq': trace['seqno'], 'pdf_paint_type': trace['type'], 'pdf_paint_opacity': trace['opacity']}


def _point_key(point: Any) -> tuple[float, float]:
    return round(float(point[0]), 3), round(float(point[1]), 3)
