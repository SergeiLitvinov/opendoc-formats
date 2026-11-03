"""PDF paint evidence, independent of semantic reading order and Word layout."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from opendoc_model import (
    ArtifactLimitError,
    DocumentLimits,
    DocumentModel,
    FontReference,
    Formula,
    Image,
    TextRun,
    set_font_reference,
    walk_model,
)

from opendoc_formats.errors import ResourceLimitError
from opendoc_formats.pdf import PdfLimits, PdfTextSpan
from opendoc_formats.support.cancellation import cancellation_requested, check_cancelled

PaintIndex = dict[tuple[float, float], list[tuple[PdfTextSpan, int]]]
ProgramIndex = dict[tuple[tuple[float, float], int], set[str | None]]
PaintEvidence = dict[str, Any]
_PAINT_KEYS = {'pdf_paint_seq', 'pdf_paint_type', 'pdf_paint_opacity', 'pdf_paint_unknown', 'pdf_paint_unknown_reason'}


def _text_spans(page: Any, limits: DocumentLimits | None, cancelled: Callable[[], bool] | None) -> tuple[PdfTextSpan, ...]:
    from opendoc_formats.native.pdf_text import text_spans

    budget = limits or DocumentLimits()
    raw = page.get_texttrace()
    check_cancelled(cancelled, 'PDF paint native text trace')
    address = f'$.sections[{page.number}].pdf_text_paint'
    if isinstance(raw, (list, tuple)) and len(raw) > budget.max_nodes:
        raise ArtifactLimitError('Too many native PDF text spans', path=address, quota='nodes', maximum=budget.max_nodes)
    if raw and budget.max_bytes == 0:
        raise ArtifactLimitError('Native PDF text exceeds byte budget', path=address, quota='bytes', maximum=0)
    native = PdfLimits(max_text_spans=budget.max_nodes, max_text_chars=max(1, budget.max_bytes),
                       max_text_metadata_bytes=max(1, budget.max_bytes))
    try:
        return text_spans(raw, page.number, native, cancelled)
    except ResourceLimitError as error:
        raise ArtifactLimitError(str(error), path=address, quota='bytes', maximum=budget.max_bytes) from error


def attach_text_paint(document: DocumentModel, path: str | Path, *, limits: DocumentLimits | None,
                      cancelled: Callable[[], bool] | None = None) -> None:
    from opendoc_formats.readers.pdf_content import content_only_pdf

    cancelled = cancelled or cancellation_requested
    with content_only_pdf(path, cancelled=cancelled) as native:
        indices = []
        for page in native:
            check_cancelled(cancelled, 'PDF paint page')
            from opendoc_formats.readers.pdf_graphics_state import native_paint_states

            evidence = native_paint_states(page, limits=limits)
            from opendoc_formats.readers.pdf_image_clips import image_clip_profiles
            from opendoc_formats.readers.pdf_images import _neutral_page_group

            graphics = page.get_drawings(extended=True)
            clips = sum(draw.get('type') == 'clip' for draw in graphics)
            unknown = (any(draw.get('type') == 'group' and not _neutral_page_group(page, draw) for draw in graphics)
                       or bool(clips and not (clips == 1 and len(image_clip_profiles(page)) == 1)))
            index: PaintIndex = defaultdict(list)
            for trace in _text_spans(page, limits, cancelled):
                check_cancelled(cancelled, 'PDF paint text trace')
                for offset, character in enumerate(trace.glyphs):
                    check_cancelled(cancelled, 'PDF paint glyph index')
                    index[_point_key(character.origin)].append((trace, offset))
            from opendoc_formats.readers.pdf_font_bindings import painted_font_programs

            programs = painted_font_programs(page, document.resources, set(index), limits=limits, cancelled=cancelled)
            indices.append((index, unknown, programs, evidence))
        for section, (index, unknown, programs, graphics) in zip(document.sections, indices, strict=True):
            check_cancelled(cancelled, 'PDF paint model section')
            section.properties['pdf_graphics'] = graphics
            for reference in walk_model(section, limits=limits):
                check_cancelled(cancelled, 'PDF paint model node')
                run = reference.node
                if isinstance(run, Image):
                    resource = document.resources.get(run.resource_id)
                    if resource is not None and resource.media_type == 'application/pdf+vector':
                        from opendoc_formats.pdf_graphics import paint_clips

                        try:
                            sequence = run.properties.get('pdf_paint_seq')
                            if type(sequence) is not int:
                                raise ValueError('Missing native PDF paint occurrence')
                            paint_clips(graphics, sequence, {'fill-path', 'stroke-path'},
                                        compositing=True)
                            resource.properties['pdf_docx_graphics_measured'] = True
                        except ValueError:
                            pass
                if isinstance(run, Formula):
                    for line in run.properties.get('pdf_native_lines', []):
                        for span in line:
                            span['paint'] = _evidence(span['text'], span['font'], span['origin'], index, programs,
                                                      cancelled=cancelled)
                            span['paint']['pdf_graphics_state_unknown'] = unknown
                if not isinstance(run, TextRun) or not run.properties.get('pdf_origin'):
                    continue
                evidence = _evidence(run.text, run.style.font_family, run.properties['pdf_origin'], index, programs,
                                     cancelled=cancelled)
                identifier = evidence.pop('pdf_font_resource', None)
                if identifier is not None:
                    set_font_reference(run.style, FontReference(identifier), limits=limits)
                for key in _PAINT_KEYS:
                    run.properties.pop(key, None)
                run.properties.update(evidence)
                run.properties['pdf_graphics_state_unknown'] = unknown


def _evidence(text: str, font: str | None, origin: Any, index: PaintIndex, programs: ProgramIndex,
              *, cancelled: Callable[[], bool] | None = None) -> PaintEvidence:
    def unknown(reason: str) -> PaintEvidence:
        return {'pdf_paint_unknown': True, 'pdf_paint_unknown_reason': reason}

    if not text:
        return unknown('empty-semantic-text')
    candidates = []
    for trace, offset in index.get(_point_key(origin), []):
        check_cancelled(cancelled, 'PDF paint candidate')
        if (trace.font != font and trace.font) or offset+len(text) > len(trace.glyphs):
            continue
        glyphs = trace.glyphs[offset:offset+len(text)]
        matched = True
        for character, glyph in zip(text, glyphs, strict=True):
            check_cancelled(cancelled, 'PDF paint Unicode match')
            code = glyph.unicode
            if not 0 <= code <= 0x10ffff or 0xd800 <= code <= 0xdfff or code == 0xfffd:
                return unknown('unmapped-native-unicode')
            if ord(character) != code:
                matched = False
                break
        if matched:
            candidates.append((trace, offset))
            if len(candidates) > 1:
                return unknown('ambiguous-native-match')
    if len(candidates) != 1:
        return unknown('no-exact-native-match')
    trace, offset = candidates[0]
    evidence: PaintEvidence = {
        'pdf_paint_seq': trace.seqno, 'pdf_paint_type': trace.paint_type, 'pdf_paint_opacity': trace.opacity,
    }
    bindings = []
    for glyph in trace.glyphs[offset:offset+len(text)]:
        check_cancelled(cancelled, 'PDF paint font binding')
        bindings.append(programs.get((_point_key(glyph.origin), glyph.unicode), set()))
    if bindings and all(len(binding) == 1 and None not in binding for binding in bindings):
        identifiers = set.union(*bindings)
        if len(identifiers) == 1:
            evidence['pdf_font_resource'] = next(iter(identifiers))
    return evidence


def _point_key(point: Any) -> tuple[float, float]:
    return round(float(point[0]), 3), round(float(point[1]), 3)
