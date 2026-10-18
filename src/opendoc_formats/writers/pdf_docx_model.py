"""Private fixed-layout Word view of the public PDF model; source stays unchanged."""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import replace

from opendoc_model import (
    Box,
    DocumentModel,
    Formula,
    Image,
    Paragraph,
    ResourceKind,
    Section,
    Table,
    TextRun,
    WidthMeasure,
    set_preferred_width,
    walk_model,
)
from opendoc_model.limits import DocumentLimits

_STANDARD_FONTS = {
    'Times-Roman': 'Times New Roman', 'Times-Bold': 'Times New Roman',
    'Times-Italic': 'Times New Roman', 'Times-BoldItalic': 'Times New Roman',
    'Helvetica': 'Arial', 'Helvetica-Bold': 'Arial', 'Helvetica-Oblique': 'Arial',
    'Helvetica-BoldOblique': 'Arial', 'Courier': 'Courier New', 'Courier-Bold': 'Courier New',
    'Courier-Oblique': 'Courier New', 'Courier-BoldOblique': 'Courier New',
}


def prepare_pdf_docx(document: DocumentModel, *, limits: DocumentLimits | None = None) -> DocumentModel:
    if document.source_format != 'pdf':
        raise ValueError('Fixed-layout PDF preparation requires a PDF model')
    prepared = deepcopy(document)
    from opendoc_formats.fonts.resource_fonts import _plain_name, font_program_names

    embedded_names = {_plain_name(resource.properties['pdf_font_name']) for resource in prepared.resources.values()
                      if resource.kind is ResourceKind.FONT and resource.data
                      and isinstance(resource.properties.get('pdf_font_name'), str)}
    for resource in prepared.resources.values():
        if resource.kind is ResourceKind.FONT and resource.data and resource.media_type in {'font/ttf', 'font/otf'}:
            try:
                _, names = font_program_names(resource.data)
                embedded_names.update(_plain_name(name) for name in names)
            except Exception:  # noqa: BLE001 - the font resource preflight reports the located failure
                pass
    for section in prepared.sections:
        from opendoc_formats.writers.pdf_docx_borders import project_table_borders

        project_table_borders(prepared, section)
        for name in ('blocks', 'headers', 'footers'):
            setattr(section, name, _split_lines(getattr(section, name)))
    for reference in walk_model(prepared, limits=limits):
        node = reference.node
        if isinstance(node, Paragraph):
            from opendoc_formats.writers.pdf_docx_paint import prepare_text_paint

            prepare_text_paint(node)
            node.properties.update({'space_before_pt': 0, 'space_after_pt': 0, 'keep_together': False,
                                    'keep_with_next': False, 'page_break_before': False, 'widow_control': False})
            if node.box is not None:
                _prepare_line_geometry(node)
                node.properties['docx_positioned_textbox'] = True
                origins = node.properties.get('pdf_line_origins')
                if isinstance(origins, list) and len(origins) == 1 and origins[0] is not None:
                    node.properties['pdf_text_origin'] = origins[0]
                _prepare_baselines(node)
            elif node.content and all(isinstance(item, Image) for item in node.content):
                node.properties.update({'line_spacing_pt': 1, 'docx_line_spacing_rule': 'exact'})
            if node.properties.get('pdf_cell_native_line'):
                _prepare_baselines(node)
                node.properties.update({'line_spacing': 1.0, 'docx_line_spacing_rule': 'auto'})
        elif isinstance(node, Image) and node.box is not None:
            from opendoc_formats.writers.pdf_docx_images import prepare_image_transform
            from opendoc_formats.writers.pdf_docx_vectors import convert_vector

            box = node.box
            node.properties['pdf_paint_bbox'] = [box.x, box.y, box.x + box.width, box.y + box.height]
            prepare_image_transform(node)
            convert_vector(prepared, node, reference.path)
            node.properties.update({'placement': 'anchor', 'horizontal_relative_from': 'page',
                                    'vertical_relative_from': 'page', 'wrap': 'none', 'allow_overlap': True})
        elif isinstance(node, TextRun):
            family = node.style.font_family
            if family in _STANDARD_FONTS and _plain_name(family) not in embedded_names:
                node.style.properties['pdf_source_font'] = family
                node.style.font_family = _STANDARD_FONTS[family]
        elif isinstance(node, Table):
            _prepare_table(node)
    prepared.metadata['pdf_docx_layout'] = {'version': 1, 'source_format': 'pdf'}
    for section in prepared.sections:
        from opendoc_formats.writers.pdf_docx_paint import prepare_page_paint

        prepare_page_paint(section, limits=limits)
        _rotate_page(section, limits=limits)
    prepared.validate(limits=limits)
    return prepared


def _rotate_page(section: Section, *, limits: DocumentLimits | None) -> None:
    rotation = section.properties.get('pdf', {}).get('source_rotation', 0)
    if rotation == 0:
        return
    if rotation not in {90, 180, 270}:
        raise ValueError('Unknown PDF page rotation')
    width, height = section.page.width.pt, section.page.height.pt

    def point(x: float, y: float) -> tuple[float, float]:
        if rotation == 90:
            return height - y, x
        if rotation == 180:
            return width - x, height - y
        return y, width - x

    for reference in walk_model(section, limits=limits):
        node = reference.node
        if isinstance(node, Table):
            raise ValueError('Rotated PDF tables require a verified editable Word representation')
        if not isinstance(node, (Paragraph, Image)) or node.box is None:
            continue
        box = node.box
        x, y = point(box.x + box.width / 2, box.y + box.height / 2)
        node.box = Box(x - box.width / 2, y - box.height / 2, box.width, box.height,
                       rotation=(box.rotation + rotation) % 360)
        if isinstance(node, Paragraph) and node.properties.get('pdf_text_origin') is not None:
            node.properties['pdf_text_origin'] = list(point(*node.properties['pdf_text_origin']))
    if rotation % 180:
        section.page.width, section.page.height = section.page.height, section.page.width


def _split_lines(blocks: list) -> list:
    result = []
    for block in blocks:
        if isinstance(block, Formula) and block.properties.get('pdf_native_lines'):
            from opendoc_formats.readers.pdf_geometry import PdfLineGeometry, PdfSpanGeometry, PdfTextBlockGeometry
            from opendoc_formats.readers.pdf_model import _pdf_text_runs

            lines = tuple(PdfLineGeometry(tuple(PdfSpanGeometry(**{key: value for key, value in span.items()
                                                                 if key != 'paint'}) for span in spans), tuple(box))
                          for spans, box in zip(block.properties['pdf_native_lines'], block.properties['pdf_line_boxes']))
            native = PdfTextBlockGeometry(lines, (block.box.x, block.box.y, block.box.x + block.box.width,
                                                  block.box.y + block.box.height), 0)
            properties = deepcopy(block.properties)
            properties['pdf_formula_text'] = block.value
            block = Paragraph(content=_pdf_text_runs(native, block.fallback_text or block.value, {}), box=block.box,
                              properties=properties, provenance=block.provenance)
            paints = iter(span.get('paint', {}) for spans in properties['pdf_native_lines'] for span in spans)
            for run in block.content:
                if isinstance(run, TextRun) and run.properties.get('pdf_origin'):
                    run.properties.update(next(paints))
        boxes = block.properties.get('pdf_line_boxes') if isinstance(block, Paragraph) else None
        counts = block.properties.get('pdf_line_run_counts') if isinstance(block, Paragraph) else None
        origins = block.properties.get('pdf_line_origins') if isinstance(block, Paragraph) else None
        if not isinstance(boxes, list) or not isinstance(counts, list) or len(boxes) < 2 or len(boxes) != len(counts):
            result.append(block)
            continue
        offset = 0
        for index, (box, count) in enumerate(zip(boxes, counts)):
            if index:
                offset += 1
            if (not isinstance(box, list) or len(box) != 4 or type(count) is not int or count < 0
                    or offset + count > len(block.content)):
                raise ValueError('Invalid PDF line geometry')
            properties = deepcopy(block.properties)
            properties.pop('pdf_line_boxes', None)
            properties.pop('pdf_line_run_counts', None)
            properties.pop('pdf_line_origins', None)
            for key in ('pdf_line_directions', 'pdf_line_writing_modes', 'pdf_line_quads'):
                values = properties.get(key)
                if isinstance(values, list) and len(values) == len(boxes):
                    properties[key] = [values[index]]
            properties['pdf_source_line'] = index
            if isinstance(origins, list) and len(origins) == len(boxes) and origins[index] is not None:
                properties['pdf_text_origin'] = origins[index]
            result.append(replace(block, content=block.content[offset:offset + count], properties=properties,
                                  box=Box(box[0], box[1], box[2] - box[0], box[3] - box[1])))
            offset += count
    return result


def _prepare_baselines(paragraph: Paragraph) -> None:
    runs = [item for item in paragraph.content if isinstance(item, TextRun) and item.properties.get('pdf_origin')]
    if not runs:
        return
    main = max(runs, key=lambda run: run.style.font_size.pt if run.style.font_size else 0)
    angle = math.radians(paragraph.box.rotation if paragraph.box else 0)
    normal = (-math.sin(angle), math.cos(angle))
    first_origin, main_origin = runs[0].properties['pdf_origin'], main.properties['pdf_origin']
    offset = sum((main_origin[index] - first_origin[index]) * normal[index] for index in (0, 1))
    base = [first_origin[index] + offset * normal[index] for index in (0, 1)]
    paragraph.properties['pdf_text_origin'] = base
    for run in runs:
        shift = sum((base[index] - run.properties['pdf_origin'][index]) * normal[index] for index in (0, 1))
        if abs(shift * 2 - round(shift * 2)) > .001:
            raise ValueError('PDF run baseline shift cannot be represented without rounding in native Word half-points')
        run.style.superscript = run.style.subscript = False
        run.style.properties['docx_run_position_pt'] = round(shift * 2) / 2


def _prepare_line_geometry(paragraph: Paragraph) -> None:
    directions = paragraph.properties.get('pdf_line_directions')
    modes = paragraph.properties.get('pdf_line_writing_modes')
    if modes and modes != [0]:
        raise ValueError('Vertical PDF writing mode is outside the measured Word text profile')
    if not directions or directions == [[1.0, 0.0]]:
        return
    quads = paragraph.properties.get('pdf_line_quads')
    if len(directions) != 1 or not quads or len(quads) != 1 or len(quads[0]) != 4:
        raise ValueError('Rotated PDF text requires a measured line quadrilateral')
    upper_left, upper_right, lower_left, _ = quads[0]
    width = math.dist(upper_left, upper_right)
    height = math.dist(upper_left, lower_left)
    angle = math.degrees(math.atan2(directions[0][1], directions[0][0]))
    paragraph.box = Box(upper_left[0], upper_left[1], width, height, rotation=angle)


def _prepare_table(table: Table) -> None:
    if table.box is None or not table.rows:
        raise ValueError('PDF table geometry remains unknown')
    table.properties['docx_page_table'] = True
    table.properties['autofit'] = False
    set_preferred_width(table, WidthMeasure('absolute', table.box.width, 'pt'))
    columns, bands = table.properties.get('pdf_column_edges'), table.properties.get('pdf_row_edges')
    grid = [round((right - left) * 20) for left, right in zip(columns, columns[1:])] if columns else []
    for row_index, row in enumerate(table.rows):
        boxes = [cell.properties.get('pdf_cell_bbox') for cell in row.cells]
        if any(not isinstance(box, list) or len(box) != 4 for box in boxes):
            raise ValueError(f'PDF table cell geometry unresolved at row {row_index}')
        row.properties['docx_height_twips'] = (round((bands[row_index + 1] - bands[row_index]) * 20)
                                                if bands and len(bands) == len(table.rows) + 1 else
                                                round((max(box[3] for box in boxes) - min(box[1] for box in boxes)) * 20))
        row.properties['docx_height_rule'] = 'exact'
        for cell, box in zip(row.cells, boxes):
            if cell.properties.get('pdf_cell_layout_uncertain'):
                raise ValueError(f'PDF table text placement unresolved at row {row_index}')
            if cell.properties.get('pdf_cell_rotated_text'):
                raise ValueError(f'PDF rotated cell text is outside the measured Word profile at row {row_index}')
            width = round((box[2] - box[0]) * 20)
            if row_index == 0 and not columns:
                grid.append(width)
            set_preferred_width(cell, WidthMeasure('absolute', width / 20, 'pt'))
            text = cell.properties.get('pdf_text_bbox') or box
            cell.properties['margins_twips'] = {'left': max(0, round((text[0] - box[0]) * 20)),
                                                'top': max(0, round((text[1] - box[1]) * 20)), 'right': 0, 'bottom': 0}
            cell.properties['vertical_alignment'] = 'top'
    table.properties['grid_widths_twips'] = grid
