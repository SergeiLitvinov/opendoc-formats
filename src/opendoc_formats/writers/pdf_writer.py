"""Экспорт DocumentModel в PDF через встроенный HTML-layout PyMuPDF."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from opendoc_model import ArtifactLimitError, DocumentLimits
from opendoc_model.diagnostics import ConversionReport, IssueSeverity
from opendoc_model.document_model import Block, DocumentModel, Formula, FormulaFormat, Paragraph, Section, Table

from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.fonts.html_embedding import archived_font_stylesheet
from opendoc_formats.writers.color_preflight import preflight_colors
from opendoc_formats.writers.font_preflight import prepare_fonts
from opendoc_formats.writers.html_writer import _HtmlRenderer
from opendoc_formats.writers.pdf_resources import PdfResourceStage
from opendoc_formats.writers.stages import StageContext


def write_pdf_model(
    document: DocumentModel, output_path: str | Path, *, cancelled: Callable[[], bool] | None = None,
    limits: DocumentLimits | None = None,
) -> ConversionReport:
    """Записать модель в PDF, сохранив размеры секций и многостраничный поток."""

    import fitz

    output = Path(output_path)
    report = ConversionReport(output)
    from opendoc_model import PreservationState, get_integration, get_page_geometry

    from opendoc_formats.support.object_mapping import PdfFallbackMapping, mapping_publication

    mapping = PdfFallbackMapping(report)
    outline_document = document
    integration = get_integration(document, limits=limits)
    if integration is not None:
        if any(scene.scope_version == 1 for scene in integration.scenes):
            report.add(IssueSeverity.ERROR, 'pdf.graphics-scopes', 'Native PDF projection of mixed scopes is not implemented')
            return report
        if integration.extra.get("pdf_outline") and not integration.extra.get("pdf_outline_imported"):
            report.add(IssueSeverity.LOSS, "pdf.outline", "Source outline is not recreated by the PDF layout writer")
        for record in integration.preservation:
            if record.state is not PreservationState.SEMANTIC:
                report.add(
                    IssueSeverity.LOSS, record.issue.code, "Opaque source feature is not recreated by the PDF layout writer",
                    record.issue.location,
                )
    from opendoc_formats.writers.pdf_vectors import draw_vectors, prepare_vectors

    check_cancelled = cancelled or (lambda: False)
    document, vectors = prepare_vectors(document, report, check_cancelled, mapping)
    if not report.success:
        mapping_publication(report, 'rejected', code='pdf.write-rejected', reason='preparation-failed')
        return report
    prepared = PdfResourceStage(mapping=mapping).execute(document, StageContext(output, check_cancelled))
    report.issues.extend(prepared.report.issues)
    report.metrics.update(prepared.report.metrics)
    if not report.success:
        mapping_publication(report, 'rejected', code='pdf.write-rejected', reason='preparation-failed')
        return report
    document = prepared.value
    from opendoc_formats.writers.pdf_rasters import draw_rasters, prepare_rasters

    document, rasters = prepare_rasters(document, report, check_cancelled, mapping, limits=limits)
    if not report.success:
        mapping_publication(report, 'rejected', code='pdf.write-rejected', reason='preparation-failed')
        return report
    try:
        mapping.prepare_story(document)
    except Exception as error:  # noqa: BLE001 - optional native backend has heterogeneous errors
        report.add(IssueSeverity.ERROR, 'pdf.svg-preparation', str(error))
        mapping_publication(report, 'rejected', code='pdf.write-rejected', reason='preparation-failed')
        return report
    document = prepare_fonts(document, report, limits=limits)
    if not report.success:
        mapping_publication(report, 'rejected', code='pdf.font-preparation-rejected', reason='preparation-failed')
        return report
    from opendoc_formats.writers.color_inheritance import materialize_docx_colors

    document = materialize_docx_colors(document, limits=limits)
    preflight_colors(document, report, target="pdf")
    target = fitz.open()
    totals = {"paragraphs": 0, "tables": 0, "images": 0, "formulas": 0, "pages": 0}
    outline_pages: dict[str, tuple[int, tuple[float, float], bool]] = {}
    ambiguous_pages: set[str] = set()
    outline_anchors: dict[str, tuple[int, tuple[float, float]]] = {}
    outline_source_origins: dict[int, tuple[float, float]] = {}
    used_geometry_ids: set[str] = set()

    try:
        for section_index, section in enumerate(document.sections or [Section()]):
            pdf_profile = section.properties.get("pdf", {})
            if not isinstance(pdf_profile, dict):
                raise ValueError("Invalid PDF section profile")
            rotation = pdf_profile.get("source_rotation", 0)
            source_page_id = pdf_profile.get("page_id")
            source_page = next((p for p in integration.pages if p.id == source_page_id), None) if integration else None
            page_geometry = get_page_geometry(source_page) if source_page else None
            if page_geometry is not None:
                rotation = page_geometry.rotation
            elif source_page and source_page.extra.get("pdf_page_geometry_imported"):
                rotation = 0
            if type(rotation) is not int or rotation not in (0, 90, 180, 270):
                raise ValueError("Invalid PDF source page rotation")
            flow_positions: dict[tuple[str, int], tuple[float, ...]] = {}
            anchor_positions: dict[str, tuple[int, tuple[float, float]]] = {}
            flow_ids = {r.location: r.flow_id for r in rasters[section_index] if r.flow_id is not None}
            section_pdf, renderer = _render_section(document, section, section_index, report, flow_positions, flow_ids,
                                                    anchor_positions, mapping, limits=limits, cancelled=check_cancelled)
            from opendoc_formats.writers.pdf_text_verify import verify_section_text

            try:
                from opendoc_formats.writers.pdf_unicode import restore_ligature_unicode

                restore_ligature_unicode(section_pdf, report, f'sections[{section_index}]')
                verify_section_text(section_pdf, section, report, f'sections[{section_index}]')
            except Exception:
                section_pdf.close()
                raise
            if not report.success:
                section_pdf.close()
                mapping_publication(report, 'rejected', code='pdf.text-rejected', reason='text-validation-failed')
                return report
            if page_geometry is not None:
                used_geometry_ids.add(source_page_id)
                if section_pdf.page_count != 1:
                    report.add(IssueSeverity.LOSS, "pdf.page-geometry-pagination",
                               "Source page was repaginated; regions apply to each output page", f"sections[{section_index}]")
            if source_page_id:
                if source_page_id in outline_pages:
                    ambiguous_pages.add(source_page_id)
                origin = pdf_profile.get("crop_origin", [0, 0])
                if (not isinstance(origin, (list, tuple)) or len(origin) != 2
                        or any(type(v) not in (int, float) or not math.isfinite(v) for v in origin)):
                    section_pdf.close()
                    raise ValueError("Invalid PDF outline crop origin")
                if page_geometry is not None:
                    area = page_geometry.crop_box or page_geometry.media_box
                    outline_origin = area.x, area.y
                    source_width, source_height = area.width, area.height
                else:
                    outline_origin = tuple(origin)
                    source_width, source_height = (source_page.width, source_page.height) if source_page else (0, 0)
                stable = (section_pdf.page_count == 1 and source_page is not None
                          and (page_geometry is not None
                               or (math.isclose(source_width, section.page.width.pt, abs_tol=0.01)
                                   and math.isclose(source_height, section.page.height.pt, abs_tol=0.01))))
                outline_pages[source_page_id] = target.page_count, outline_origin, stable
            for identifier, (number, position) in anchor_positions.items():
                outline_anchors.setdefault(identifier, (target.page_count + number, position))
            section_vectors = vectors[section_index] if section_index < len(vectors) else []
            if section_vectors and rasters[section_index]:
                report.add(IssueSeverity.LOSS, "pdf-raster-compositing", "Source raster/vector paint order is not reconstructed",
                           f"sections[{section_index}]")
            try:
                mapping.resolve_story(section_pdf, target.page_count)
                for page_number, page in enumerate(section_pdf):
                    placed_rasters = [r for r in rasters[section_index]
                                      if r.flow_id is None
                                      and (page_number == 0 or ".headers[" in r.location or ".footers[" in r.location)]
                    for raster in rasters[section_index]:
                        if raster.flow_id is None:
                            continue
                        if not any(token == raster.flow_id for token, _ in flow_positions):
                            raise ValueError(f"Missing inline raster placement at {raster.location}")
                        position = flow_positions.get((raster.flow_id, page_number))
                        if position is not None:
                            x0, y0, x1, y1 = position
                            box = raster.image.box
                            assert box is not None
                            angle = math.radians(box.rotation % 360)
                            expected_width = abs(box.width * math.cos(angle)) + abs(box.height * math.sin(angle))
                            expected_height = abs(box.width * math.sin(angle)) + abs(box.height * math.cos(angle))
                            if not (math.isclose(x1-x0, expected_width, abs_tol=0.01)
                                    and math.isclose(y1-y0, expected_height, abs_tol=0.01)):
                                raise ValueError(f"Inline raster placeholder was resized or split at {raster.location}")
                            frame = flow_positions.get((raster.flow_id + "-frame", page_number))
                            if frame is None:
                                raise ValueError(f"Missing inline raster container at {raster.location}")
                            if raster.flow_alignment == "center":
                                x0 = (frame[0] + frame[2] - expected_width) / 2
                                x1 = x0 + expected_width
                            elif raster.flow_alignment == "right":
                                x1 = frame[2]
                                x0 = x1 - expected_width
                            placed_box = replace(box, x=(x0 + x1 - box.width) / 2, y=(y0 + y1 - box.height) / 2)
                            placed_rasters.append(replace(raster, image=replace(raster.image, box=placed_box)))
                    draw_rasters(page, placed_rasters, check_cancelled, mapping=mapping,
                                 page_index=target.page_count + page_number)
                    placed = [v for v in section_vectors
                              if page_number == 0 or ".headers[" in v.location or ".footers[" in v.location]
                    draw_vectors(page, placed, check_cancelled)
            except Exception:
                section_pdf.close()
                raise
            totals["pages"] += section_pdf.page_count
            for key in ("paragraphs", "tables", "images", "formulas"):
                totals[key] += renderer.metrics[key]
            totals["images"] += len(section_vectors)
            totals["images"] += len(rasters[section_index])
            from opendoc_formats.pdf_page_geometry import apply_page_geometry, translate_generated_links

            placements = {}
            generated_links = {}
            for page_number, page in enumerate(section_pdf):
                if page_geometry is not None:
                    generated_links[page.xref] = [int(link["xref"]) for link in page.get_links() if link.get("xref")]
                    origin = pdf_profile.get("crop_origin", (page_geometry.media_box.x, page_geometry.media_box.y))
                    outline_source_origins[target.page_count + page_number] = tuple(origin)
                    placements[page.xref] = apply_page_geometry(page, page_geometry, tuple(origin))
                else:
                    page.set_rotation(rotation)
            translate_generated_links(section_pdf, placements, generated_links)
            target.insert_pdf(section_pdf)
            section_pdf.close()
        from opendoc_formats.writers.pdf_interactive import write_interactions
        from opendoc_formats.writers.pdf_outline import write_outline

        write_interactions(target, outline_document, report, outline_pages, check_cancelled, limits=limits)
        if not report.success:
            mapping_publication(report, 'rejected', code='pdf.interactions-rejected', reason='interaction-failed')
            return report

        if integration:
            for source_page in integration.pages:
                if get_page_geometry(source_page) is not None and source_page.id not in used_geometry_ids:
                    report.add(IssueSeverity.LOSS, "pdf.page-geometry",
                               "Page geometry has no explicit section binding", f"pages[{source_page.id}]")
        for identifier in ambiguous_pages:
            outline_pages.pop(identifier, None)
        write_outline(target, outline_document, report, outline_pages, outline_anchors, outline_source_origins, limits=limits)
        _set_metadata(target, document.metadata)
        from opendoc_formats.support.artifacts import ArtifactWorkspace
        from opendoc_formats.support.io import atomic_copy

        with ArtifactWorkspace(prefix="opendoc_formats_pdf_writer_") as workspace:
            staged = workspace.artifact_path("output.pdf")
            mapping.embed(target)
            target.save(staged, garbage=4, deflate=True)
            workspace.validate_artifact(staged)
            with fitz.open(staged) as check:
                if check.page_count != totals['pages'] or check.page_count == 0:
                    raise ValueError('Written PDF has an invalid page count')
                _verify_pdf_font_embedding(check, document, report)
            if not report.success:
                mapping_publication(report, 'rejected', code='pdf.validation-rejected', reason='validation-failed')
                return report
            mapping.materialize(staged)
            if check_cancelled():
                raise ValueError("PDF export cancelled before publication")
            atomic_copy(staged, output)
            mapping_publication(report, 'published')
    except ArtifactLimitError:
        raise
    except OperationCancelledError:
        raise
    except Exception as error:  # noqa: BLE001 - backend failures must be represented in the report
        report.add(IssueSeverity.ERROR, "pdf-write", str(error))
        mapping_publication(report, 'rejected', code='pdf.write-rejected', reason='write-failed')
        return report
    finally:
        target.close()

    report.metrics.update(totals)
    report.metrics["sections"] = len(document.sections or [Section()])
    report.metrics["resources"] = len(document.resources)
    return report


def _render_section(
    document: DocumentModel,
    section: Section,
    section_index: int,
    report: ConversionReport,
    flow_positions: dict[tuple[str, int], tuple[float, ...]],
    flow_ids: dict[str, str],
    anchor_positions: dict[str, tuple[int, tuple[float, float]]],
    mapping: Any = None,
    *, limits: DocumentLimits | None = None, cancelled: Callable[[], bool] | None = None,
) -> tuple[Any, _HtmlRenderer]:
    import fitz

    section_model = DocumentModel(
        sections=[section],
        resources=document.resources,
        styles=document.styles,
        metadata=document.metadata,
        mode=document.mode,
        source_format=document.source_format,
        version=document.version,
    )
    from opendoc_formats.support.cancellation import check_cancelled
    from opendoc_formats.writers.pdf_flow import PdfFlowRenderer, next_flow_break, record_position

    renderer = PdfFlowRenderer(section_model, report, flow_ids, mapping, limits=limits)
    main_html = renderer._blocks(section.blocks, f"sections[{section_index}].blocks")
    header_html = renderer._blocks(section.headers, f"sections[{section_index}].headers")
    footer_html = renderer._blocks(section.footers, f"sections[{section_index}].footers")
    _report_mathml_fallback(section.blocks, report, f"sections[{section_index}].blocks")
    _report_mathml_fallback(section.headers, report, f"sections[{section_index}].headers")
    _report_mathml_fallback(section.footers, report, f"sections[{section_index}].footers")

    page = section.page
    media_box = fitz.Rect(0, 0, page.width.pt, page.height.pt)
    content_box = fitz.Rect(
        page.margin_left.pt,
        page.margin_top.pt,
        page.width.pt - page.margin_right.pt,
        page.height.pt - page.margin_bottom.pt,
    )

    def rect_function(_rect_number: int, _filled: Any) -> tuple[Any, Any, Any]:
        return media_box, content_box, fitz.Identity

    from opendoc_formats.support.artifacts import ArtifactWorkspace

    with ArtifactWorkspace(prefix="opendoc_formats_pdf_fonts_") as font_workspace:
        font_styles = archived_font_stylesheet(document, font_workspace, report)
        css = (
            font_styles
            + "\n"
            + renderer.stylesheet(include_page_rules=False)
            + "\nhtml, body { background: transparent; } body { margin: 0; }"
        )
        archive = fitz.Archive(str(font_workspace.path))
        trial_positions: dict[tuple[str, int], tuple[float, ...]] = {}
        trial_anchors: dict[str, tuple[int, tuple[float, float]]] = {}

        def page_function(_page_number: int, _mediabox: Any, device: Any, after: int) -> None:
            if after:
                return
            if header_html:
                header_box = fitz.Rect(
                    page.margin_left.pt,
                    max(2, page.margin_top.pt * 0.15),
                    page.width.pt - page.margin_right.pt,
                    max(4, page.margin_top.pt - 4),
                )
                _draw_fixed_story(header_html, css, header_box, device, report, "header", archive=archive,
                                  flow_positions=trial_positions, page_number=_page_number - 1)
            if footer_html:
                footer_box = fitz.Rect(
                    page.margin_left.pt,
                    min(page.height.pt - 4, page.height.pt - page.margin_bottom.pt + 4),
                    page.width.pt - page.margin_right.pt,
                    page.height.pt - 2,
                )
                _draw_fixed_story(footer_html, css, footer_box, device, report, "footer", archive=archive,
                                  flow_positions=trial_positions, page_number=_page_number - 1)

        def position_function(position: Any) -> None:
            record_position(trial_positions, position)
            if position.id and position.open_close & 1:
                trial_anchors.setdefault(position.id, (position.page_num - 1, (position.rect[0], position.rect[1])))

        forced: set[str] = set()
        trial_issue_start = len(report.issues)
        for attempt in range(33):
            check_cancelled(cancelled, 'PDF pagination')
            trial_positions.clear()
            trial_anchors.clear()
            story = fitz.Story(html=main_html or "<p></p>", user_css=css, archive=archive)
            section_pdf = story.write_with_links(rect_function, pagefn=page_function, positionfn=position_function)
            if not isinstance(section_pdf, fitz.Document):
                section_pdf = fitz.open(stream=section_pdf.read(), filetype="pdf")
            try:
                retry = next_flow_break(main_html, trial_positions, content_box.y1, forced)
                if retry is None:
                    flow_positions.update(trial_positions)
                    anchor_positions.update(trial_anchors)
                    if forced:
                        report.metrics.setdefault('pdf_flow_page_breaks', []).extend(
                            location for location, token in flow_ids.items() if token in forced
                        )
                    break
                if attempt == 32:
                    raise ValueError('PDF inline raster pagination exceeds 32 retries')
                main_html, token = retry
                forced.add(token)
            except Exception:
                section_pdf.close()
                raise
            section_pdf.close()
            del report.issues[trial_issue_start:]
    return section_pdf, renderer


def _verify_pdf_font_embedding(pdf: Any, document: DocumentModel, report: ConversionReport) -> None:
    from opendoc_formats.fonts.embedding import collect_font_usages

    expected = [usage for usage in collect_font_usages(document) if usage.embeddable]
    observed: set[str] = set()
    for page in pdf:
        for font in page.get_fonts(full=True):
            if font and int(font[0]) > 0:
                observed.update(_font_token(str(value)) for value in font[3:5] if value)
    verified = 0
    for usage in expected:
        requested = _font_token(usage.family)
        if any(requested in name or name in requested for name in observed if name):
            verified += 1
        else:
            report.add(
                IssueSeverity.LOSS,
                "font-embedding",
                f"PDF output does not contain the requested embedded font {usage.family!r}",
            )
    metrics = report.metrics.setdefault("font_embedding", {"target": "pdf"})
    metrics["verified_faces"] = verified
    metrics["pdf_fonts"] = sorted(observed)


def _font_token(value: str) -> str:
    token = value.split("+", 1)[-1]
    return "".join(character for character in token.casefold() if character.isalnum())


def _draw_fixed_story(
    html: str,
    css: str,
    rectangle: Any,
    device: Any,
    report: ConversionReport,
    feature: str,
    *,
    archive: Any = None,
    flow_positions: dict[tuple[str, int], tuple[float, ...]] | None = None,
    page_number: int = 0,
) -> None:
    import fitz

    story = fitz.Story(html=html, user_css=css, archive=archive)
    more, _filled = story.place(rectangle)
    if flow_positions is not None:
        from opendoc_formats.writers.pdf_flow import record_position

        story.element_positions(lambda position: record_position(flow_positions, position), {"page_num": page_number + 1})
    story.draw(device)
    if more:
        report.add(IssueSeverity.LOSS, feature, f"{feature} content was clipped because it exceeds the page margin")


def _report_mathml_fallback(blocks: list[Block], report: ConversionReport, location: str) -> None:
    for index, block in enumerate(blocks):
        block_location = f"{location}[{index}]"
        if isinstance(block, Formula) and block.format is FormulaFormat.MATHML:
            report.add(
                IssueSeverity.LOSS,
                "formula",
                "MathML is flattened by the PDF HTML backend; exact mathematical layout is not guaranteed",
                block_location,
            )
        elif isinstance(block, Paragraph):
            for inline_index, item in enumerate(block.content):
                if isinstance(item, Formula) and item.format is FormulaFormat.MATHML:
                    report.add(
                        IssueSeverity.LOSS,
                        "formula",
                        "MathML is flattened by the PDF HTML backend; exact mathematical layout is not guaranteed",
                        f"{block_location}.content[{inline_index}]",
                    )
        elif isinstance(block, Table):
            for row_index, row in enumerate(block.rows):
                for cell_index, cell in enumerate(row.cells):
                    _report_mathml_fallback(
                        cell.blocks,
                        report,
                        f"{block_location}.rows[{row_index}].cells[{cell_index}].blocks",
                    )


def _set_metadata(document: Any, metadata: dict[str, Any]) -> None:
    current = document.metadata
    for name in ("title", "author", "subject", "keywords", "creator", "producer"):
        value = metadata.get(name)
        if value is not None:
            current[name] = str(value)
    current.setdefault("producer", "OpenDoc Formats / PyMuPDF")
    document.set_metadata(current)


__all__ = ["write_pdf_model"]
