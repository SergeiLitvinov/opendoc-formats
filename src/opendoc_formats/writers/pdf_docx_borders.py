"""Project only proven complete PDF grid strokes into editable Word cell borders."""

from __future__ import annotations

from opendoc_model import Border, BorderSet, ColorValue, DocumentModel, Image, Paragraph, Section, Table, TextRun, set_borders

from opendoc_formats.support.cancellation import checkpoint


def project_table_borders(document: DocumentModel, section: Section) -> None:
    removed: set[int] = set()
    for table in (block for block in section.blocks if isinstance(block, Table)):
        checkpoint()
        local_removed: set[int] = set()
        strokes = []
        cells = [cell for row in table.rows for cell in row.cells]
        paint = [run.properties.get('pdf_paint_seq') for cell in cells for block in cell.blocks
                 if isinstance(block, Paragraph) for run in block.content if isinstance(run, TextRun) and run.text]
        if not paint or any(type(value) is not int for value in paint):
            continue
        sides: dict[int, dict] = {id(cell): {} for cell in cells}
        for block in section.blocks:
            checkpoint()
            if not isinstance(block, Paragraph) or len(block.content) != 1 or not isinstance(block.content[0], Image):
                continue
            image = block.content[0]
            resource = document.resources.get(image.resource_id)
            if resource is None or resource.media_type != 'application/pdf+vector':
                continue
            props = resource.properties
            if (image.box is None or image.box.rotation or len(props.get('bbox', [])) != 4
                    or any(abs(a - b) > .001 for a, b in zip(
                        (image.box.x, image.box.y, image.box.x + image.box.width, image.box.y + image.box.height),
                        props['bbox']))):
                continue
            sequence = image.properties.get('pdf_paint_seq')
            if (type(sequence) is not int or sequence >= min(paint) or props.get('fill') is not None
                    or props.get('stroke') is None or props.get('stroke_opacity') != 1
                    or props.get('clip_rects')
                    or (props.get('graphics_state_unsupported') and not props.get('neutral_page_group_only'))
                    or props.get('dashes') != '[] 0' or len(props.get('items', [])) != 1):
                continue
            command = props['items'][0]
            width = props.get('width', 0)
            if command[0] != 'l' or not 0 < width <= 12 or abs(width * 8 - round(width * 8)) > 1e-6:
                continue
            p, q = command[1:]
            axis = 0 if abs(p[1] - q[1]) < .001 else 1 if abs(p[0] - q[0]) < .001 else None
            if axis is None:
                continue
            coordinate, start, end = p[1 - axis], min(p[axis], q[axis]), max(p[axis], q[axis])
            matches = []
            for cell in cells:
                checkpoint()
                box = cell.properties.get('pdf_cell_bbox')
                if not box:
                    continue
                definitions = ({'top': (box[1], box[0], box[2]), 'bottom': (box[3], box[0], box[2])} if axis == 0
                               else {'left': (box[0], box[1], box[3]), 'right': (box[2], box[1], box[3])})
                for side, (position, first, last) in definitions.items():
                    if abs(position - coordinate) < .001 and start <= first + .001 and last <= end + .001:
                        matches.append((cell, side, first, last))
            if not _covered(start, end, [(first, last) for _, _, first, last in matches]):
                continue
            border = Border(style='solid', width_pt=width, color=ColorValue.from_dict(props['stroke']))
            for cell, side, _, _ in matches:
                sides[id(cell)][side] = border
            local_removed.add(id(block))
            strokes.append((min(p[0], q[0]) - width / 2, min(p[1], q[1]) - width / 2,
                            max(p[0], q[0]) + width / 2, max(p[1], q[1]) + width / 2))
        # Native table borders occupy the body plane. Keep separate vectors if
        # another graphic intersects this grid, rather than reorder its painting.
        if table.box is None or any(_intersects_foreign_graphic(block, local_removed, strokes) for block in section.blocks):
            continue
        for cell in cells:
            checkpoint()
            if sides[id(cell)]:
                set_borders(cell, BorderSet(sides[id(cell)]))
        removed.update(local_removed)
    section.blocks[:] = [block for block in section.blocks if id(block) not in removed]


def _intersects_foreign_graphic(block: object, known: set[int], strokes: list[tuple[float, ...]]) -> bool:
    if id(block) in known or not isinstance(block, Paragraph):
        return False
    for image in block.content:
        checkpoint()
        if not isinstance(image, Image) or image.box is None:
            continue
        b = image.box
        if any(x0 <= b.x + b.width and b.x <= x1 and y0 <= b.y + b.height and b.y <= y1
               for x0, y0, x1, y1 in strokes):
            return True
    return False


def _covered(start: float, end: float, intervals: list[tuple[float, float]]) -> bool:
    cursor = start
    for first, last in sorted(intervals):
        checkpoint()
        if first > cursor + .001:
            return False
        cursor = max(cursor, last)
    return cursor >= end - .001
