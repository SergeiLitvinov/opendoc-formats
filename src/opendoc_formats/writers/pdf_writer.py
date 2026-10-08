"""Экспорт DocumentModel в PDF через встроенный HTML-layout PyMuPDF."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from opendoc_model.diagnostics import ConversionReport, IssueSeverity
from opendoc_model.document_model import Block, DocumentModel, Formula, FormulaFormat, Paragraph, Section, Table

from opendoc_formats.fonts.html_embedding import archived_font_stylesheet
from opendoc_formats.writers.color_preflight import preflight_colors
from opendoc_formats.writers.font_preflight import prepare_fonts
from opendoc_formats.writers.html_writer import _HtmlRenderer
from opendoc_formats.writers.pdf_resources import PdfResourceStage
from opendoc_formats.writers.stages import StageContext


def write_pdf_model(
    document: DocumentModel, output_path: str | Path, *, cancelled: Callable[[], bool] | None = None,
) -> ConversionReport:
    """Записать модель в PDF, сохранив размеры секций и многостраничный поток."""

    import fitz

    output = Path(output_path)
    report = ConversionReport(output)
    from opendoc_model import PreservationState, get_integration

    outline_document = document
    integration = get_integration(document)
    if integration is not None:
        for feature, values in (("pdf.annotations", integration.annotations), ("pdf.forms", integration.forms)):
            if values:
                report.add(IssueSeverity.LOSS, feature, "Interactive objects are not recreated by the PDF layout writer")
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
    document, vectors = prepare_vectors(document, report, check_cancelled)
    if not report.success:
        return report
    prepared = PdfResourceStage().execute(document, StageContext(output, check_cancelled))
    report.issues.extend(prepared.report.issues)
    report.metrics.update(prepared.report.metrics)
    if not report.success:
        return report
    document = prepared.value
    from opendoc_formats.writers.pdf_rasters import draw_rasters, prepare_rasters

    document, rasters = prepare_rasters(document, report, check_cancelled)
    if not report.success:
        return report
    document = prepare_fonts(document, report)
    preflight_colors(document, report, target="pdf")
    target = fitz.open()
    totals = {"paragraphs": 0, "tables": 0, "images": 0, "formulas": 0, "pages": 0}
    outline_pages: dict[str, tuple[int, tuple[float, float], bool]] = {}
    ambiguous_pages: set[str] = set()
    outline_anchors: dict[str, tuple[int, tuple[float, float]]] = {}

    try:
        for section_index, section in enumerate(document.sections or [Section()]):
            pdf_profile = section.properties.get("pdf", {})
            if not isinstance(pdf_profile, dict):
                raise ValueError("Invalid PDF section profile")
            rotation = pdf_profile.get("source_rotation", 0)
            if type(rotation) is not int or rotation not in (0, 90, 180, 270):
                raise ValueError("Invalid PDF source page rotation")
            flow_positions: dict[tuple[str, int], tuple[float, ...]] = {}
            anchor_positions: dict[str, tuple[int, tuple[float, float]]] = {}
            flow_ids = {r.location: r.flow_id for r in rasters[section_index] if r.flow_id is not None}
            section_pdf, renderer = _render_section(document, section, section_index, report, flow_positions, flow_ids,
                                                    anchor_positions)
            source_page_id = pdf_profile.get("page_id")
            if source_page_id:
                if source_page_id in outline_pages:
                    ambiguous_pages.add(source_page_id)
                origin = pdf_profile.get("crop_origin", [0, 0])
                if (not isinstance(origin, (list, tuple)) or len(origin) != 2
                        or any(type(v) not in (int, float) or not math.isfinite(v) for v in origin)):
                    section_pdf.close()
                    raise ValueError("Invalid PDF outline crop origin")
                source_page = next((p for p in integration.pages if p.id == source_page_id), None) if integration else None
                stable = (section_pdf.page_count == 1 and source_page is not None
                          and math.isclose(source_page.width, section.page.width.pt, abs_tol=0.01)
                          and math.isclose(source_page.height, section.page.height.pt, abs_tol=0.01))
                outline_pages[source_page_id] = target.page_count, tuple(origin), stable
            for identifier, (number, position) in anchor_positions.items():
                outline_anchors.setdefault(identifier, (target.page_count + number, position))
            section_vectors = vectors[section_index] if section_index < len(vectors) else []
            if section_vectors and rasters[section_index]:
                report.add(IssueSeverity.LOSS, "pdf-raster-compositing", "Source raster/vector paint order is not reconstructed",
                           f"sections[{section_index}]")
            try:
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
                    draw_rasters(page, placed_rasters, check_cancelled)
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
            for page in section_pdf:
                page.set_rotation(rotation)
            target.insert_pdf(section_pdf)
            section_pdf.close()
        from opendoc_formats.writers.pdf_outline import write_outline

        for identifier in ambiguous_pages:
            outline_pages.pop(identifier, None)
        write_outline(target, outline_document, report, outline_pages, outline_anchors)
        _set_metadata(target, document.metadata)
        from opendoc_formats.support.artifacts import ArtifactWorkspace
        from opendoc_formats.support.io import atomic_copy

        with ArtifactWorkspace(prefix="opendoc_formats_pdf_writer_") as workspace:
            staged = workspace.artifact_path("output.pdf")
            target.save(staged, garbage=4, deflate=True)
            workspace.validate_artifact(staged)
            if check_cancelled():
                raise ValueError("PDF export cancelled before publication")
            atomic_copy(staged, output)
    except Exception as error:  # noqa: BLE001 - backend failures must be represented in the report
        report.add(IssueSeverity.ERROR, "pdf-write", str(error))
        return report
    finally:
        target.close()

    try:
        with fitz.open(output) as check:
            if check.page_count != totals["pages"] or check.page_count == 0:
                report.add(IssueSeverity.ERROR, "pdf-validation", "written PDF has an invalid page count")
            _verify_pdf_font_embedding(check, document, report)
    except Exception as error:  # noqa: BLE001 - validation is part of the diagnostic boundary
        report.add(IssueSeverity.ERROR, "pdf-validation", str(error))
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
    from opendoc_formats.writers.pdf_flow import PdfFlowRenderer, record_position

    renderer = PdfFlowRenderer(section_model, report, flow_ids)
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
            + "\nhtml, body { background: white; } body { margin: 0; }"
        )
        archive = fitz.Archive(str(font_workspace.path))
        story = fitz.Story(html=main_html or "<p></p>", user_css=css, archive=archive)

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
                                  flow_positions=flow_positions, page_number=_page_number - 1)
            if footer_html:
                footer_box = fitz.Rect(
                    page.margin_left.pt,
                    min(page.height.pt - 4, page.height.pt - page.margin_bottom.pt + 4),
                    page.width.pt - page.margin_right.pt,
                    page.height.pt - 2,
                )
                _draw_fixed_story(footer_html, css, footer_box, device, report, "footer", archive=archive,
                                  flow_positions=flow_positions, page_number=_page_number - 1)

        def position_function(position: Any) -> None:
            record_position(flow_positions, position)
            if position.id and position.open_close & 1:
                anchor_positions.setdefault(position.id, (position.page_num - 1, (position.rect[0], position.rect[1])))

        section_pdf = story.write_with_links(rect_function, pagefn=page_function, positionfn=position_function)
    if isinstance(section_pdf, fitz.Document):
        return section_pdf, renderer
    return fitz.open(stream=section_pdf.read(), filetype="pdf"), renderer


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
