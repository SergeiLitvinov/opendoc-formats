"""Map measured PDF paint order to Word's drawing and body-text planes."""

from __future__ import annotations

from opendoc_model import Box, DocumentLimits, Image, Paragraph, Section, Table, TextRun, walk_model


def prepare_text_paint(paragraph: Paragraph) -> None:
    if paragraph.box is not None:
        box = paragraph.box
        paragraph.properties['pdf_paint_bbox'] = [box.x, box.y, box.x + box.width, box.y + box.height]
    runs = [run for run in paragraph.content if isinstance(run, TextRun) and run.properties.get('pdf_origin')]
    if not runs:
        return
    for run in runs:
        size = run.style.font_size.pt if run.style.font_size else 0
        if size <= 0 or round(size * 2) == 0 or abs(size * 2 - round(size * 2)) > .001:
            raise ValueError('PDF font size cannot be represented without rounding in native Word half-points')
        props = run.properties
        if (props.get('pdf_paint_unknown') or props.get('pdf_graphics_state_unknown')
                or type(props.get('pdf_paint_seq')) is not int
                or props.get('pdf_paint_type') != 0 or props.get('pdf_paint_opacity') != 1):
            raise ValueError('PDF text paint is unknown or outside the opaque filled-text Word profile')
    sequence = [run.properties['pdf_paint_seq'] for run in runs]
    paragraph.properties['pdf_paint_range'] = [min(sequence), max(sequence)]
    paragraph.properties['docx_drawing_relative_height'] = max(sequence) * 4 + 2


def _overlap(a: Box, b: Box) -> bool:
    # Axis-aligned source boxes, before private page rotation.
    return a.x <= b.x + b.width and b.x <= a.x + a.width and a.y <= b.y + b.height and b.y <= a.y + a.height


def prepare_page_paint(section: Section, *, limits: DocumentLimits | None) -> None:
    paragraphs, tables, images = [], [], []
    for reference in walk_model(section, limits=limits):
        node = reference.node
        if isinstance(node, Paragraph) and node.box is not None:
            paragraphs.append(node)
        elif isinstance(node, Table) and node.box is not None:
            tables.append(node)
        elif isinstance(node, Image) and node.box is not None:
            images.append(node)
    table_ranges = []
    for table in tables:
        for reference in walk_model(table, limits=limits):
            paragraph = reference.node
            if not isinstance(paragraph, Paragraph) or not paragraph.properties.get('pdf_paint_range'):
                continue
            boxes = [run.properties['pdf_bbox'] for run in paragraph.content
                     if isinstance(run, TextRun) and run.properties.get('pdf_bbox')]
            if boxes:
                x0, y0 = min(box[0] for box in boxes), min(box[1] for box in boxes)
                x1, y1 = max(box[2] for box in boxes), max(box[3] for box in boxes)
                table_ranges.append((Box(x0, y0, x1 - x0, y1 - y0), *paragraph.properties['pdf_paint_range']))
    for image in images:
        sequence = image.properties.get('pdf_paint_seq')
        if type(sequence) is not int or sequence < 0:
            raise ValueError('PDF image/vector paint order remains unknown')
        image.properties['relative_height'] = sequence * 4 + 2
        behind = front = False
        image_box = _paint_box(image)
        for box, first, last in table_ranges:
            if not _overlap(image_box, box):
                continue
            if first < sequence < last:
                raise ValueError('PDF graphic interleaves editable table text across Word drawing planes')
            if sequence < first:
                behind = True
            else:
                front = True
        if behind and front:
            raise ValueError('PDF graphic must lie both above and below overlapping native table text')
        for paragraph in paragraphs:
            paint = paragraph.properties.get('pdf_paint_range')
            if not paint or not _overlap(image_box, _paint_box(paragraph)):
                continue
            if paint[0] < sequence < paint[1] or (behind and sequence > paint[0]):
                raise ValueError('PDF graphic interleaves native text within a single Word text object')
        image.properties['behind_doc'] = behind


def _paint_box(node: Image | Paragraph) -> Box:
    values = node.properties.get('pdf_paint_bbox')
    if values:
        return Box(values[0], values[1], values[2] - values[0], values[3] - values[1])
    return node.box
