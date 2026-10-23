"""PDF → модель OpenDoc: геометрия, семантические блоки и внедряемый OCR."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from opendoc_model import ArtifactLimitError, DocumentLimits
from opendoc_model.color import ColorValue
from opendoc_model.document_model import (
    Block as RichBlock,
)
from opendoc_model.document_model import (
    Box,
    ConversionMode,
    DocumentModel,
    Formula,
    FormulaFormat,
    Length,
    PageSettings,
    Paragraph,
    Provenance,
    ProvenanceEvent,
    Resource,
    ResourceKind,
    Section,
    TextRun,
    TextStyle,
)
from opendoc_model.document_model import (
    Image as RichImage,
)
from opendoc_model.document_model import (
    Table as RichTable,
)
from opendoc_model.units import canonical_coordinate_contract

from opendoc_formats.errors import BackendUnavailableError, OperationCancelledError, ResourceLimitError
from opendoc_formats.support.cancellation import check_cancelled
from opendoc_formats.types import BlockType, DocFormat


def read_pdf_model(
    *,
    path: str | Path,
    use_ocr: bool = False,
    ocr_backend: str = "",
    handwriting: bool = False,
    use_gpu: bool = False,
    mode: str | None = None,
    ocr_engine_factory: Callable[..., Any] | None = None,
    limits: DocumentLimits | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> DocumentModel:
    """Извлечь PDF в богатую модель с текстом, таблицами и изображениями.

    Единый сценарий «text layer + OCR» задаётся ``mode``:
    ``fast`` — только текстовый слой; ``structure`` — text layer + OCR-слияние;
    ``scan`` — только OCR. При отсутствии ``mode`` поведение определяется
    ``use_ocr`` (backward compatibility).

    Args:
        path: Путь к PDF.
        use_ocr: Включить OCR-слияние с текстовым слоем (⇒ mode ``structure``).
        ocr_backend: Имя OCR-бэкенда (tesseract/easyocr/paddle).
        handwriting: Режим распознавания рукописного текста.
        use_gpu: Использовать GPU для OCR.
        mode: Стратегия обработки: ``fast`` / ``structure`` / ``scan``.

    Returns:
        ``DocumentModel`` с текстом, таблицами и изображениями.
    """
    from opendoc_formats.readers.pdf_ocr_merge import (
        PDF_SCENARIO_FAST,
        PDF_SCENARIO_MODES,
        PDF_SCENARIO_SCAN,
        PDF_SCENARIO_STRUCTURE,
    )

    scenario = mode if mode is not None else (PDF_SCENARIO_STRUCTURE if use_ocr else PDF_SCENARIO_FAST)
    if scenario not in PDF_SCENARIO_MODES:
        raise ValueError(f"unknown PDF scenario mode {scenario!r}; expected one of {PDF_SCENARIO_MODES}")

    from opendoc_formats.readers.pdf_geometry import extract_pdf_geometry
    from opendoc_formats.readers.pdf_images import (
        enrich_geometry_with_images,
        extract_pdf_images,
        extract_pdf_vector_drawings,
    )

    check_cancelled(cancelled, 'PDF import')
    path = str(path)
    geometry = extract_pdf_geometry(path, exclude_interactions=True, cancelled=cancelled)
    engine = f"pymupdf+{scenario}+document-model"
    ocr_pages = None
    ocr_failures: list[tuple[str, str, int]] = []

    # OCR-слияние для structure/scan сценариев.
    if scenario in (PDF_SCENARIO_STRUCTURE, PDF_SCENARIO_SCAN):
        ocr_engine = (
            ocr_engine_factory(
                backend=ocr_backend if ocr_backend else "auto",
                use_gpu=use_gpu,
            )
            if ocr_engine_factory is not None
            else None
        )
        check_cancelled(cancelled, 'PDF OCR initialization')
        if ocr_engine is not None and ocr_engine.is_available:
            try:
                ocr_pages = ocr_engine.recognize_pdf_geometry(path, handwriting=handwriting)
                if geometry.pages and not ocr_pages:
                    geometry.warnings.append('OCR engine returned no page results')
                    ocr_failures.append(('pdf.ocr-empty', 'ocr-no-page-results', len(geometry.warnings)-1))
            except (OperationCancelledError, ArtifactLimitError, ResourceLimitError):
                raise
            except BackendUnavailableError as exc:
                geometry.warnings.append(f'OCR backend unavailable: {exc}')
                ocr_failures.append(('pdf.ocr-unavailable', 'ocr-provider-unavailable', len(geometry.warnings)-1))
            except Exception as exc:  # noqa: BLE001
                geometry.warnings.append(f"OCR failed: {exc}")
                ocr_failures.append(('pdf.ocr-failed', 'ocr-provider-failed', len(geometry.warnings)-1))
        else:
            geometry.warnings.append("OCR engine requested but none available")
            ocr_failures.append(('pdf.ocr-unavailable', 'ocr-provider-unavailable', len(geometry.warnings)-1))

    check_cancelled(cancelled, 'PDF OCR')
    image_diagnostics, vector_diagnostics, cell_diagnostics = [], [], []
    images, img_warnings = extract_pdf_images(path, cancelled=cancelled, diagnostics=image_diagnostics)
    vectors, vec_warnings = extract_pdf_vector_drawings(path, cancelled=cancelled, diagnostics=vector_diagnostics)
    geometry = enrich_geometry_with_images(geometry, images, vectors, cancelled=cancelled)

    from opendoc_formats.readers.pdf_ocr_merge import merge_pdf_with_ocr

    semantic = merge_pdf_with_ocr(geometry, ocr_pages, use_text_layer=(scenario != PDF_SCENARIO_SCAN), cancelled=cancelled)

    all_warnings: list[str] = list(semantic.warnings) + img_warnings + vec_warnings
    from opendoc_formats.readers.pdf_diagnostics import bind_warning_records

    geometry.diagnostics.extend(bind_warning_records(image_diagnostics, len(semantic.warnings), cancelled=cancelled))
    geometry.diagnostics.extend(bind_warning_records(
        vector_diagnostics, len(semantic.warnings)+len(img_warnings), cancelled=cancelled,
    ))

    from opendoc_formats.support.pdf_mapping_history import HISTORY_KEY, attach_history_map, load_history

    history_routes, history_issues = load_history(path)
    check_cancelled(cancelled, 'PDF mapping history')
    from opendoc_model import Anchor, set_anchor

    from opendoc_formats.support.object_mapping import _result_id

    source_identity = _result_id(Path(path)).removeprefix('sha256:')
    matched_history = []
    sections: list[Section] = []
    resources: dict[str, Resource] = {}
    from opendoc_formats.readers.pdf_fonts import extract_pdf_fonts

    resources.update(extract_pdf_fonts(path, limits=limits, cancelled=cancelled))

    for page in geometry.pages:
        check_cancelled(cancelled, 'PDF model page')
        blocks: list[RichBlock] = []
        headers: list[RichBlock] = []
        footers: list[RichBlock] = []
        source_blocks = {block.number: block for block in page.text_blocks}

        def origin(object_id: str, *, detail: str, fallback_reason: str | None = None) -> Provenance:
            return Provenance(
                source_format=DocFormat.PDF.value,
                source_path=path,
                page=page.number,
                object_id=object_id,
                events=[ProvenanceEvent(f"extract.pdf.{scenario}", detail, fallback_reason)],
            )

        for semantic_block in (block for block in semantic.blocks if block.page == page.number):
            check_cancelled(cancelled, 'PDF model block')
            box = _pdf_box(semantic_block.meta.get("bbox"))
            properties = {
                "legacy_type": semantic_block.type.value,
                "page": page.number,
                **semantic_block.meta,
            }
            if semantic_block.type is BlockType.TABLE:
                from opendoc_formats.readers.pdf_table_model import pdf_table_rows

                rows = pdf_table_rows(page, semantic_block.meta, _pdf_text_runs, all_warnings,
                                      diagnostics=cell_diagnostics, source_path=path,
                                      location=f'sections[{len(sections)}].blocks[{len(blocks)}]', cancelled=cancelled)
                native_table = next((table for table in page.tables
                                     if table.number == semantic_block.meta.get('source_table')), None)
                blocks.append(
                    RichTable(
                        rows=rows,
                        box=box,
                        properties={"pdf": properties,
                                    'pdf_column_edges': list(native_table.column_edges) if native_table else [],
                                    'pdf_row_edges': list(native_table.row_edges) if native_table else []},
                        provenance=origin(
                            f"semantic-{semantic_block.meta.get('source_block', 'table')}",
                            detail="reconstructed semantic table",
                            fallback_reason="table inferred from PDF geometry",
                        ),
                    )
                )
                continue

            source_number = semantic_block.meta.get("source_block")
            source_block = source_blocks.get(int(source_number)) if source_number is not None else None
            if source_block is not None:
                properties['pdf_line_boxes'] = [list(line.bbox) for line in source_block.lines]
                properties['pdf_line_run_counts'] = [len(line.spans) for line in source_block.lines]
                properties['pdf_line_directions'] = [list(line.direction) for line in source_block.lines]
                properties['pdf_line_writing_modes'] = [line.writing_mode for line in source_block.lines]
                properties['pdf_line_quads'] = [[list(point) for point in line.quad] for line in source_block.lines]
                properties['pdf_line_origins'] = [list(line.spans[0].origin) if line.spans else None
                                                  for line in source_block.lines]
            runs = _pdf_text_runs(source_block, semantic_block.text, semantic_block.meta)
            if semantic_block.type is BlockType.EQUATION:
                if source_block is not None:
                    properties['pdf_native_lines'] = [
                        [{'text': span.text, 'font': span.font, 'size': span.size, 'flags': span.flags,
                          'color': span.color, 'origin': list(span.origin), 'bbox': list(span.bbox)} for span in line.spans]
                        for line in source_block.lines
                    ]
                rich_block: RichBlock = Formula(
                    value=semantic_block.text,
                    format=FormulaFormat.LATEX,
                    display=True,
                    fallback_text=semantic_block.text,
                    box=box,
                    properties=properties,
                    provenance=origin(
                        f"semantic-{source_number or 'equation'}",
                        detail="classified equation block",
                        fallback_reason="equation retained as LaTeX text without source math structure",
                    ),
                )
            else:
                merge_source = semantic_block.meta.get("source") or semantic_block.meta.get("origin") or "text-layer"
                rich_block = Paragraph(
                    content=runs,
                    box=box,
                    properties=properties,
                    provenance=origin(
                        f"semantic-{source_number or len(blocks)}",
                        detail=f"merged semantic block from {merge_source}",
                        fallback_reason="OCR supplied missing text" if "ocr" in str(merge_source).lower() else None,
                    ),
                )
            role = semantic_block.meta.get("semantic_role")
            if role == "header":
                headers.append(rich_block)
            elif role == "footer":
                footers.append(rich_block)
            else:
                blocks.append(rich_block)

        for img in page.extracted_images:
            resource_id = f"p{page.number}_img{img.xref}"
            if resource_id not in resources and img.data:
                resources[resource_id] = Resource(
                    id=resource_id,
                    kind=ResourceKind.RASTER_IMAGE,
                    media_type=img.media_type,
                    data=img.data,
                    filename=img.extension,
                    provenance=origin(f"image-xref-{img.xref}", detail="extracted embedded raster image"),
                )
            elif resource_id not in resources:
                continue
            bbox = img.bbox
            box = Box(x=bbox[0], y=bbox[1], width=bbox[2] - bbox[0], height=bbox[3] - bbox[1]) if len(bbox) == 4 else None
            image_origin = origin(f"image-xref-{img.xref}", detail="placed extracted raster image")
            image = RichImage(
                resource_id=resource_id, box=box, provenance=image_origin, crop=img.crop,
                properties={"pdf_image_transform": list(img.transform), 'pdf_paint_seq': img.paint_seq,
                            'pdf_source_image_transform': list(img.source_transform),
                            'pdf_graphics_state_unknown': img.graphics_state_unknown},
            )
            set_anchor(image, Anchor(f'pdf-image-{source_identity}-{page.number}-{img.number}'))
            route = history_routes.get((page.number - 1, img.number))
            if route is not None:
                image.properties[HISTORY_KEY] = route['history']
                image.properties['pdf_mapping_number'] = img.number
                matched_history.append((image, route))
            blocks.append(Paragraph(content=[image], provenance=image_origin))

        for vec in page.vector_drawings:
            resource_id = f"p{page.number}_vec{vec.number}"
            if resource_id not in resources:
                resources[resource_id] = Resource(
                    id=resource_id,
                    kind=ResourceKind.VECTOR_IMAGE,
                    media_type="application/pdf+vector",
                    data=b"",
                    properties={
                        "items": json.loads(json.dumps(vec.items, allow_nan=False)),
                        "fill": vec.fill.to_dict() if vec.fill else None,
                        "stroke": vec.stroke.to_dict() if vec.stroke else None,
                        "fill_opacity": vec.fill_opacity,
                        "stroke_opacity": vec.stroke_opacity,
                        "bbox": list(vec.bbox),
                        "width": vec.width,
                        "even_odd": vec.even_odd,
                        "close_path": vec.close_path,
                        "dashes": vec.dashes,
                        "line_join": vec.line_join,
                        "line_cap": vec.line_cap,
                        "clip_rects": [list(rectangle) for rectangle in vec.clip_rects],
                        "graphics_state_unsupported": vec.graphics_state_unsupported,
                        'neutral_page_group_only': vec.neutral_page_group_only,
                    },
                    provenance=origin(f"vector-{vec.number}", detail="extracted PDF drawing operators"),
                )
            bbox = vec.bbox
            box = Box(x=bbox[0], y=bbox[1], width=bbox[2] - bbox[0], height=bbox[3] - bbox[1]) if len(bbox) == 4 else None
            alt = f"Vector drawing {vec.number} on page {vec.page}"
            vector_origin = origin(f"vector-{vec.number}", detail="represented PDF drawing as editable vector resource")
            blocks.append(
                Paragraph(
                    content=[RichImage(resource_id=resource_id, box=box, alt_text=alt, provenance=vector_origin,
                                       properties={'pdf_paint_seq': vec.paint_seq})],
                    provenance=vector_origin,
                )
            )

        sections.append(
            Section(
                blocks=blocks,
                headers=headers,
                footers=footers,
                page=_pdf_page_settings(
                    page.height if page.rotation % 180 else page.width,
                    page.width if page.rotation % 180 else page.height,
                ),
                properties={"pdf": {"source_rotation": page.rotation, "coordinate_space": "pymupdf-unrotated",
                                    "page_id": f"pdf-page-{page.number}"}},
                provenance=origin(f"page-{page.number}", detail="created document section from PDF page"),
            )
        )

    geometry.diagnostics.extend(bind_warning_records(cell_diagnostics, cancelled=cancelled))
    metadata: dict[str, Any] = {
        "engine": engine,
        "pages": len(sections),
        "warnings": all_warnings,
        "coordinate_system": canonical_coordinate_contract(),
    }
    metadata.update(geometry.metadata)

    document = DocumentModel(
        sections=sections,
        resources=resources,
        metadata=metadata,
        source_format="pdf",
        mode=ConversionMode.BALANCED,
    )
    from opendoc_formats.readers.pdf_interactive import attach_pdf_interactions
    from opendoc_formats.readers.pdf_paint import attach_text_paint

    attach_text_paint(document, path, limits=limits, cancelled=cancelled)
    attach_pdf_interactions(document, path, limits=limits, cancelled=cancelled)
    from opendoc_formats.readers.pdf_scopes import attach_pdf_scopes

    attach_pdf_scopes(document, limits=limits, cancelled=cancelled)
    attach_history_map(document, path, matched_history, history_issues, limits=limits)
    from opendoc_formats.readers.pdf_diagnostics import attach_pdf_diagnostics

    attach_pdf_diagnostics(document, path, scenario, geometry, ocr_pages, ocr_failures,
                           limits=limits, cancelled=cancelled)
    check_cancelled(cancelled, 'PDF import completion')
    return document


def _pdf_page_settings(width: float, height: float) -> PageSettings:
    """Use inferred default margins without making small physical PDF pages invalid."""
    page = PageSettings(width=Length(width), height=Length(height))
    for field in ("margin_left", "margin_right"):
        setattr(page, field, Length(min(getattr(page, field).pt, width / 4)))
    for field in ("margin_top", "margin_bottom"):
        setattr(page, field, Length(min(getattr(page, field).pt, height / 4)))
    return page


def _pdf_box(value: Any) -> Box | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    x0, y0, x1, y1 = (float(item) for item in value)
    return Box(x=x0, y=y0, width=max(0.0, x1 - x0), height=max(0.0, y1 - y0))


def _pdf_text_runs(source_block: Any, fallback_text: str, meta: dict[str, Any]) -> list[TextRun]:
    if source_block is not None:
        runs: list[TextRun] = []
        for line_index, line in enumerate(source_block.lines):
            if line_index:
                runs.append(TextRun(text="\n"))
            for span in line.spans:
                flags = int(span.flags)
                color = ColorValue.from_pdf_srgb(span.color)
                runs.append(
                    TextRun(
                        text=span.text,
                        properties={'pdf_origin': list(span.origin), 'pdf_bbox': list(span.bbox)},
                        style=TextStyle(
                            font_family=span.font or None,
                            font_size=Length(span.size) if span.size else None,
                            bold=bool(flags & 16),
                            italic=bool(flags & 2),
                            superscript=bool(flags & 1),
                            color=color,
                        ),
                    )
                )
        if runs:
            return runs
    font_spans = meta.get("font_spans") or []
    first = font_spans[0] if font_spans else {}
    flags = int(first.get("flags", 0))
    color = ColorValue.from_pdf_srgb(int(first.get("color", 0)))
    style = TextStyle(
        font_family=first.get("font") or None,
        font_size=Length(float(first["size"])) if first.get("size") else None,
        bold=bool(flags & 16),
        italic=bool(flags & 2),
        superscript=bool(flags & 1),
        color=color,
    )
    return [TextRun(text=fallback_text, style=style)]
