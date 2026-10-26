"""Explicit semantic Word flow, with verified finite PDF grid replacement."""

from __future__ import annotations

import hashlib
import math
import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from opendoc_model import (
    ArtifactLimitError,
    Border,
    BorderSet,
    ColorValue,
    ConversionReport,
    DiagnosticIssue,
    DocumentLimits,
    DocumentModel,
    Image,
    IssueSeverity,
    NativeObjectLocator,
    ObjectMapping,
    ObjectMappingEntry,
    ObjectOccurrence,
    Paragraph,
    PreservationState,
    Table,
    TextRun,
    WidthMeasure,
    get_borders,
    get_integration,
    get_preferred_width,
    object_mapping_from_dict,
    object_mapping_to_dict,
    set_borders,
    set_preferred_width,
    walk_model,
)

from opendoc_formats.support.cancellation import cancellable_items, checkpoint


class FlowProfileError(ValueError):
    def __init__(self, message: str, location: str) -> None:
        super().__init__(message)
        self.location = location


def _number(value: object) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1_000_000:
        raise ValueError('Invalid PDF grid coordinate')
    return float(value)


def _edges(value: object) -> list[float]:
    if not isinstance(value, list) or not 2 <= len(value) <= 256:
        raise ValueError('PDF grid requires 2..256 ordered edges per axis')
    result = [_number(item) for item in value]
    if any(a >= b for a, b in zip(result, result[1:])):
        raise ValueError('PDF grid edges must increase strictly')
    return result


def _same(left: tuple, right: tuple) -> bool:
    return len(left) == len(right) and all(abs(a-b) <= .0001 for a, b in zip(left, right))


def _fragment(line: tuple, expected: tuple) -> bool:
    vertical = expected[0] == expected[2]
    axis, fixed = (1, 0) if vertical else (0, 1)
    return (line[fixed] == line[fixed+2] and abs(line[fixed]-expected[fixed]) <= .0001
            and line[axis+2] > line[axis] and line[axis] >= expected[axis]-.0001
            and line[axis+2] <= expected[axis+2]+.0001)


def _complete_strokes(matches: list, segments: set) -> bool:
    grouped: dict[tuple, list[tuple]] = {}
    for line, _image, _location, _style, expected in matches:
        checkpoint()
        grouped.setdefault(expected, []).append(line)
    if grouped.keys() != segments:
        return False
    for expected, fragments in grouped.items():
        checkpoint()
        axis = 1 if expected[0] == expected[2] else 0
        cursor = expected[axis]
        discrepancy = 0.0
        for fragment in sorted(fragments, key=lambda item: item[axis]):
            checkpoint()
            discrepancy += abs(fragment[axis]-cursor)
            if discrepancy > .0001:
                return False  # Neither gaps nor overlapping paint may be merged away.
            cursor = fragment[axis+2]
        if discrepancy+abs(cursor-expected[axis+2]) > .0001:
            return False
    return True


def _visible_fragment(segment: tuple, bounds: tuple) -> bool:
    axis, fixed = (1, 0) if segment[0] == segment[2] else (0, 1)
    return (bounds[fixed]-.0001 <= segment[fixed] <= bounds[fixed+2]+.0001
            and max(segment[axis], bounds[axis]) < min(segment[axis+2], bounds[axis+2]))


def _border_styles(matches: list, bounds: tuple) -> dict:
    sides = ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')
    common = {item[3] for item in matches}
    if len(common) == 1:
        width, color = next(iter(common))
        return {side: {'width': width, 'color': color} for side in sides}
    grouped: dict[str, set] = {}
    for segment, _image, _location, style, _expected in matches:
        checkpoint()
        if not _visible_fragment(segment, bounds):
            continue
        vertical = segment[0] == segment[2]
        fixed, lower, upper = ((segment[0], bounds[0], bounds[2]) if vertical else
                               (segment[1], bounds[1], bounds[3]))
        if abs(fixed-lower) <= .0001:
            side = 'left' if vertical else 'top'
        elif abs(fixed-upper) <= .0001:
            side = 'right' if vertical else 'bottom'
        else:
            side = 'insideV' if vertical else 'insideH'
        grouped.setdefault(side, set()).add(style)
    if set(grouped) != set(sides) or any(len(values) != 1 for values in grouped.values()):
        return {}  # These measured differences require explicit cell borders.
    return {side: {'width': next(iter(values))[0], 'color': next(iter(values))[1]}
            for side, values in grouped.items()}


def _line(image: Image, document: DocumentModel) -> tuple | None:
    resource = document.resources.get(image.resource_id)
    if resource is None or resource.media_type != 'application/pdf+vector':
        return None
    from opendoc_formats.writers.pdf_vectors import _validate

    _validate(image, resource)
    props = resource.properties
    items = props.get('items', [])
    if len(items) != 1 or items[0][0] != 'l' or image.box is None or image.box.rotation:
        return None
    a, b = [tuple(map(_number, point)) for point in items[0][1:]]
    if a[0] != b[0] and a[1] != b[1]:
        return None
    segment = (*min(a, b), *max(a, b))
    bounds = (image.box.x, image.box.y, image.box.x+image.box.width, image.box.y+image.box.height)
    if not _same(bounds, segment):
        return None
    return segment


def _style(image: Image, document: DocumentModel) -> tuple[float, str]:
    props = document.resources[image.resource_id].properties
    color = ColorValue.from_dict(props.get('stroke'))
    width = _number(props.get('width'))
    if (props.get('fill') is not None or props.get('clip_rects') or props.get('dashes') not in ('[] 0', None, '')
            or props.get('line_cap', 0) != 0 or props.get('line_join', 0) != 0
            or props.get('stroke_opacity', 1) != 1 or color.alpha != 1 or color.blend_mode != 'normal'
            or color.icc_profile is not None or color.space != 'srgb'
            or width not in (.25, .5, .75, 1, 1.5, 2.25, 3, 4.5, 6)):
        raise ValueError('PDF grid stroke is outside the native Word border profile')
    return width, color.to_hex().removeprefix('#')[:6].upper()


def prepare_flow(document: DocumentModel, report: ConversionReport, *, limits: DocumentLimits | None) -> DocumentModel:
    if document.source_format != 'pdf' or document.metadata.get('pdf_docx_layout'):
        raise FlowProfileError('Flow requires a canonical PDF model, not a prepared positioned Word view', 'document')
    integration = get_integration(document, limits=limits)
    if integration and integration.scenes:
        raise FlowProfileError('Graphics groups require a separate flow projection', 'integration.scenes')
    result = deepcopy(document)
    sources, targets, entries = [], [], []
    location_map = {}
    table_number = comparisons = 0
    for section_index, section in enumerate(result.sections):
        checkpoint()
        specs = []
        vectors = []
        for index, block in enumerate(section.blocks):
            checkpoint()
            location = f'sections[{section_index}].blocks[{index}]'
            if isinstance(block, Table):
                columns = block.properties.get('pdf_column_edges')
                rows = block.properties.get('pdf_row_edges')
                if columns is not None or rows is not None:
                    try:
                        x, y = _edges(columns), _edges(rows)
                    except ValueError as error:
                        raise FlowProfileError(str(error), location) from error
                    segments = {(edge, y[0], edge, y[-1]) for edge in x}
                    segments.update((x[0], edge, x[-1], edge) for edge in y)
                    original_cells = block.properties.get('pdf_source_cell_bounds')
                    if original_cells is not None:
                        try:
                            segments, source_bounds = _source_segments(original_cells, x, y, limits)
                            _bounds, _widths, placements = _selected_grid(block, x, y, limits)
                            for _row, _column, cell in placements:
                                checkpoint()
                                if tuple(cell.properties['pdf_cell_bbox']) not in source_bounds:
                                    raise ValueError('Retained cell is not one complete measured source cell')
                        except ArtifactLimitError:
                            raise
                        except ValueError as error:
                            raise FlowProfileError(str(error), location) from error
                    elif any(cell.column_span > 1 or cell.row_span > 1 for row in block.rows for cell in row.cells):
                        try:
                            bounds, _widths, placements = _selected_grid(block, x, y, limits)
                            if bounds != (x[0], y[0], x[-1], y[-1]):
                                raise ValueError('Cropped merged grids need explicit original topology reconciliation')
                            segments = _merged_segments(placements)
                        except ArtifactLimitError:
                            raise
                        except ValueError as error:
                            raise FlowProfileError(str(error), location) from error
                    specs.append({'table': block, 'location': location, 'number': table_number,
                                  'segments': segments, 'matches': [], 'seen': set(), 'x': x, 'y': y})
                table_number += 1
            if isinstance(block, Paragraph):
                for offset, inline in enumerate(block.content):
                    checkpoint()
                    if isinstance(inline, Image):
                        resource = result.resources.get(inline.resource_id)
                        if resource and resource.media_type == 'application/pdf+vector':
                            vectors.append((index, inline, f'{location}.content[{offset}]', len(block.content)))
        consumed = set()
        for index, image, location, inline_count in vectors:
            checkpoint()
            try:
                line = _line(image, result)
                owners = []
                for spec in specs:
                    for expected in spec['segments']:
                        checkpoint()
                        comparisons += 1
                        if comparisons > 1_000_000:
                            raise ArtifactLimitError('Flow grid matching work exceeded', path=location,
                                                     quota='flow grid comparisons', maximum=1_000_000)
                        if line is not None and _fragment(line, expected):
                            owners.append((spec, expected))
                if len(owners) > 1:
                    raise ValueError('Grid occurrence belongs to more than one table')
                if owners:
                    if inline_count != 1:
                        raise ValueError('Grid occurrence in a mixed paragraph cannot be consumed')
                    spec, expected = owners[0]
                    if line in spec['seen']:
                        raise ValueError('Duplicate grid strokes require an explicit compositing profile')
                    spec['seen'].add(line)
                    spec['matches'].append((line, image, location, _style(image, result), expected))
                    consumed.add(index)
                else:
                    raise ValueError('PDF vector has no verified editable table-grid replacement')
            except ArtifactLimitError:
                raise
            except (ValueError, TypeError) as error:
                raise FlowProfileError(str(error), location) from error
        for spec in specs:
            checkpoint()
            matches = spec['matches']
            if not matches:
                continue
            table, location = spec['table'], spec['location']
            try:
                if not _complete_strokes(matches, spec['segments']):
                    raise ValueError('Table grid stroke coverage must be complete')
                bounds, widths, placements = _selected_grid(table, spec['x'], spec['y'], limits)
                width, color = matches[0][3]
                border_styles = _border_styles(matches, bounds)
                names = {'insideH': 'inside-horizontal', 'insideV': 'inside-vertical'}
                cell_borders = None
                if not border_styles:
                    from opendoc_formats.writers.docx_flow_borders import plan_cell_borders

                    cell_borders = plan_cell_borders(matches, placements, limits=limits)
                expected_borders = (BorderSet({side: Border(kind='none') for side in
                    ('top', 'left', 'bottom', 'right', 'inside-horizontal', 'inside-vertical')}) if cell_borders else
                    BorderSet({names.get(side, side): Border(kind='line', style='solid',
                            color=ColorValue.from_hex(style['color']), width_pt=style['width'])
                            for side, style in border_styles.items()}))
                declared_borders = get_borders(table, limits=limits)
                if declared_borders is not None and declared_borders != expected_borders:
                    raise ValueError('Edited border declarations need explicit source-grid reconciliation')
                if declared_borders is None:
                    set_borders(table, expected_borders, limits=limits)
                declared_widths = (get_preferred_width(table, limits=limits) is not None or any(
                    get_preferred_width(cell, limits=limits) is not None
                    for row in cancellable_items(table.rows) for cell in cancellable_items(row.cells)))
                if not declared_widths:
                    set_preferred_width(table, WidthMeasure('absolute', sum(widths), 'pt'), limits=limits)
                    table.properties['grid_widths_twips'] = [round(value*20) for value in widths]
                    for _row, column, cell in placements:
                        checkpoint()
                        set_preferred_width(cell, WidthMeasure('absolute', sum(widths[column:column+cell.column_span]), 'pt'),
                                            limits=limits)
                from opendoc_formats.ooxml.source_grid import capture_source_grid

                capture_source_grid(table)
                target_id = f'flow-table-{spec["number"]}'
                target_extra = {'body_table': spec['number'], 'width': width, 'color': color,
                                'border_styles': border_styles}
                if table.properties.get('docx_source_grid_identity') is not None:
                    target_extra['source_grid'] = table.properties['docx_source_grid_identity']
                if cell_borders is not None:
                    target_extra['cell_borders'] = cell_borders
                if cell_borders is not None or any(cell.row_span > 1 or cell.column_span > 1
                                                   for _row, _column, cell in placements):
                    target_extra['cell_topology'] = [[row, column, cell.row_span, cell.column_span]
                                                     for row, column, cell in placements]
                targets.append(ObjectOccurrence(target_id, extra=target_extra))
                for segment, image, source_location, _, _expected in matches:
                    checkpoint()
                    visible = _visible_fragment(segment, bounds)
                    source_id = f'flow-source-{len(sources)}'
                    sources.append(ObjectOccurrence(source_id, resource_id=image.resource_id,
                                                    provenance=deepcopy(image.provenance)))
                    entries.append(ObjectMappingEntry(
                        f'flow-entry-{len(entries)}', (source_id,),
                        PreservationState.VISUAL if visible else PreservationState.LOST,
                        DiagnosticIssue('docx.flow-grid', IssueSeverity.LOSS,
                                        'Source grid is replaced by editable table borders; '
                                        'portions outside the selected range are excluded',
                                        source_location, reason='explicit-table-grid-reflow'),
                        None,
                        extra={'table_location': location, 'selected_bounds': list(bounds),
                               'source_segment': list(segment), 'range_exclusion': not visible,
                               'planned_table_id': target_id},
                    ))
            except ArtifactLimitError:
                raise
            except (ValueError, TypeError) as error:
                raise FlowProfileError(str(error), location) from error
        retained = []
        for index, block in cancellable_items(enumerate(section.blocks)):
            if index not in consumed:
                location_map[f'sections[{section_index}].blocks[{len(retained)}]'] = f'sections[{section_index}].blocks[{index}]'
                retained.append(block)
        section.blocks = retained
    for reference in walk_model(result, limits=limits):
        checkpoint()
        node = reference.node
        match = re.match(r'^(sections\[\d+\]\.blocks\[\d+\])(?=\.|$)', reference.path)
        location = reference.path
        if match is not None and match[0] in location_map:
            location = location_map[match[0]]+location[len(match[0]):]
        if isinstance(node, TextRun):
            props = node.properties
            if any(key in props for key in ('pdf_origin', 'pdf_paint_type', 'pdf_paint_opacity',
                                            'pdf_paint_unknown', 'pdf_graphics_state_unknown')):
                if (props.get('pdf_paint_unknown') or props.get('pdf_graphics_state_unknown')
                        or props.get('pdf_paint_type') != 0 or props.get('pdf_paint_opacity') != 1):
                    raise FlowProfileError('PDF text paint is unknown or outside the opaque filled-text flow profile', location)
        if isinstance(node, Image):
            resource = result.resources.get(node.resource_id)
            if resource is not None and resource.media_type == 'application/pdf+vector':
                raise FlowProfileError('PDF vector has no verified editable table-grid replacement', location)
        if isinstance(node, (Paragraph, Table)):
            node.box = None
        if isinstance(node, Image) and node.box is not None:
            node.box = replace(node.box, x=0, y=0)
            node.properties['placement'] = 'inline'
        if isinstance(node, Table):
            for row in node.rows:
                checkpoint()
                for cell in row.cells:
                    checkpoint()
                    cell.properties.pop('pdf_text_origin', None)
    result.validate(limits=limits)
    if entries:
        report.metrics['docx_flow_grid_plan'] = [{'id': target.id, **target.extra} for target in targets]
        report.metrics['object_mapping'] = object_mapping_to_dict(ObjectMapping(
            sources=tuple(sources), entries=tuple(entries), publication='attempted', output_format='docx',
            extra={'profile': 'docx-flow-grid-v1', 'scope': 'declared-table-grid-occurrences'},
        ), limits=limits)
    report.metrics['docx_flow_profile'] = 'pdf-semantic-flow-v1'
    report.metrics['docx_flow_locations'] = location_map
    report.add(IssueSeverity.LOSS, 'docx.flow-layout',
               'Original PDF coordinates and pagination are discarded; '
               'source grid outside selected table ranges is excluded', 'document')
    return result


def remap_flow_issues(report: ConversionReport, start: int) -> None:
    # Also runs after a successful direct commit: never poll cancellation here.
    locations = report.metrics.get('docx_flow_locations', {})
    for index in range(start, len(report.issues)):
        issue = report.issues[index]
        match = re.match(r'^(sections\[\d+\]\.blocks\[\d+\])(?=\.|$)', issue.location)
        if match is not None and (source := locations.get(match[0])) is not None:
            report.issues[index] = replace(issue, location=source+issue.location[len(match[0]):])


def _selected_grid(table: Table, x: list[float], y: list[float], limits: DocumentLimits | None) -> tuple:
    from opendoc_formats.ooxml.table_grid import native_grid

    columns, placements = native_grid(table, limits=limits)
    widths = [None] * columns
    boxes = []
    occupied = set()
    origins = set()
    merged = False
    for native_row, column, cell in placements:
        checkpoint()
        raw = cell.properties.get('pdf_cell_bbox')
        if not isinstance(raw, list) or len(raw) != 4:
            raise ValueError('Grid replacement requires source bounds for each retained cell')
        a, b, c, d = map(_number, raw)
        if a not in x or c not in x or b not in y or d not in y or a >= c or b >= d:
            raise ValueError('Retained cell is not aligned to the original PDF grid')
        start, end, top, bottom = x.index(a), x.index(c), y.index(b), y.index(d)
        if cell.column_span != end-start or cell.row_span != bottom-top:
            raise ValueError('Cell spans disagree with measured PDF source bounds')
        origins.add((start-column, top-native_row))
        merged = merged or cell.column_span > 1 or cell.row_span > 1
        for row in range(y.index(b), y.index(d)):
            for col in range(x.index(a), x.index(c)):
                checkpoint()
                if (row, col) in occupied:
                    raise ValueError('Retained source cells overlap')
                occupied.add((row, col))
        for offset in range(cell.column_span):
            checkpoint()
            width = x[start+offset+1]-x[start+offset]
            if widths[column+offset] not in (None, width):
                raise ValueError('Retained cell widths disagree within a column')
            widths[column+offset] = width
        boxes.append((a, b, c, d))
    if merged and len(origins) != 1:
        raise ValueError('Merged cell placement disagrees with measured source topology')
    if not boxes or any(value is None for value in widths):
        raise ValueError('Selected grid is empty or incomplete')
    bounds = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    if sum((b[2]-b[0])*(b[3]-b[1]) for b in boxes) != (bounds[2]-bounds[0])*(bounds[3]-bounds[1]):
        raise ValueError('Selected cells do not form one contiguous rectangle')
    return bounds, widths, placements


def _merged_segments(placements: list) -> set:
    return _cell_segments([cell.properties['pdf_cell_bbox'] for _row, _column, cell in placements])


def _source_segments(raw: object, x: list[float], y: list[float], limits: DocumentLimits | None) -> tuple:
    maximum = (len(x)-1)*(len(y)-1)
    budget = limits or DocumentLimits()
    if maximum > budget.max_nodes:
        raise ArtifactLimitError('Source table grid exceeds selected node budget', path='table.pdf_source_cell_bounds',
                                 quota='flow source grid', maximum=budget.max_nodes)
    if not isinstance(raw, list) or not raw or len(raw) > maximum:
        raise ValueError('Invalid measured source cell inventory')
    xs, ys = {value: index for index, value in enumerate(x)}, {value: index for index, value in enumerate(y)}
    boxes, occupied = set(), set()
    for value in raw:
        checkpoint()
        if not isinstance(value, list) or len(value) != 4:
            raise ValueError('Invalid measured source cell bounds')
        a, b, c, d = map(_number, value)
        if a not in xs or c not in xs or b not in ys or d not in ys or a >= c or b >= d:
            raise ValueError('Source cell is not aligned to measured grid edges')
        for row in range(ys[b], ys[d]):
            for column in range(xs[a], xs[c]):
                checkpoint()
                if (row, column) in occupied:
                    raise ValueError('Measured source cells overlap')
                occupied.add((row, column))
        boxes.add((a, b, c, d))
    if len(occupied) != maximum:
        raise ValueError('Measured source grid is incomplete')
    return _cell_segments(boxes), boxes


def _cell_segments(boxes: list | set) -> set:
    groups: dict[tuple, set] = {}
    for a, b, c, d in boxes:
        checkpoint()
        for key, interval in (((0, a), (b, d)), ((0, c), (b, d)), ((1, b), (a, c)), ((1, d), (a, c))):
            groups.setdefault(key, set()).add(interval)
    segments = set()
    for (axis, fixed), intervals in groups.items():
        start = end = None
        for left, right in sorted(intervals):
            checkpoint()
            if end is not None and left > end:
                segments.add((fixed, start, fixed, end) if axis == 0 else (start, fixed, end, fixed))
                start = None
            start = left if start is None else start
            end = right if end is None else max(end, right)
        segments.add((fixed, start, fixed, end) if axis == 0 else (start, fixed, end, fixed))
    return segments


def _native_cell_topology(table: ET.Element) -> list:
    w = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    anchors: list[list[int]] = []
    active: dict[tuple[int, int], list[int]] = {}
    for row, native_row in enumerate(table.findall(w+'tr')):
        checkpoint()
        column = 0
        following = {}
        for cell in native_row.findall(w+'tc'):
            checkpoint()
            props = cell.find(w+'tcPr')
            span = props.find(w+'gridSpan') if props is not None else None
            width = int(span.get(w+'val')) if span is not None else 1
            merge = props.find(w+'vMerge') if props is not None else None
            if merge is not None and merge.get(w+'val', 'continue') == 'continue':
                if (column, width) not in active:
                    raise ValueError('Native Word merge continuation has no matching origin')
                anchor = active[column, width]
                anchor[2] += 1
                following[column, width] = anchor
            else:
                anchor = [row, column, 1, width]
                anchors.append(anchor)
                if merge is not None:
                    if merge.get(w+'val') != 'restart':
                        raise ValueError('Unknown native Word merge declaration')
                    following[column, width] = anchor
            column += width
        active = following
    return anchors


def finalize_flow_mapping(report: ConversionReport, path: Path, *, limits: DocumentLimits | None = None) -> None:
    raw = report.metrics.get('object_mapping')
    if raw is None:
        return
    mapping = object_mapping_from_dict(raw, limits=limits)
    w = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    with ZipFile(path) as package:
        root = ET.fromstring(package.read('word/document.xml'))
        for plan in report.metrics['docx_flow_grid_plan']:
            if 'source_grid' in plan:
                from opendoc_formats.ooxml.source_grid import verify_source_grid

                verify_source_grid(package, root, plan['body_table'], plan['source_grid'])
    tables = root.find(w+'body').findall(w+'tbl')
    targets = []
    for plan in report.metrics['docx_flow_grid_plan']:
        checkpoint()
        target = ObjectOccurrence(plan['id'], extra={key: value for key, value in plan.items() if key != 'id'})
        number = target.extra['body_table']
        if 'cell_topology' in target.extra and _native_cell_topology(tables[number]) != target.extra['cell_topology']:
            raise ValueError('Native Word merged-cell topology changed')
        borders = tables[number].find(w+'tblPr/'+w+'tblBorders')
        if borders is None or len(borders) != 6:
            raise ValueError('Native Word table border replacement was not written')
        if 'cell_borders' in target.extra:
            from opendoc_formats.writers.docx_flow_borders import verify_cell_borders

            if ({border.tag.removeprefix(w) for border in borders}
                    != {'top', 'left', 'bottom', 'right', 'insideH', 'insideV'}
                    or any(border.attrib != {w+'val': 'none'} for border in borders)):
                raise ValueError('Native Word cell-border table baseline changed')
            verify_cell_borders(tables[number], target.extra['cell_borders'])
            targets.append(replace(target, native_locator=NativeObjectLocator(
                'docx', f'word/document.xml#/w:document/w:body/w:tbl[{number+1}]')))
            continue
        styles = target.extra.get('border_styles') or {side: {'width': target.extra['width'], 'color': target.extra['color']}
                    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')}
        if {border.tag.removeprefix(w) for border in borders} != set(styles):
            raise ValueError('Native Word border roles changed')
        for border in borders:
            style = styles[border.tag.removeprefix(w)]
            if (border.get(w+'val') != 'single' or border.get(w+'color') != style['color']
                    or int(border.get(w+'sz', '-1')) != round(style['width']*8)):
                raise ValueError('Native Word table border replacement changed stroke')
        targets.append(replace(target, native_locator=NativeObjectLocator(
            'docx', f'word/document.xml#/w:document/w:body/w:tbl[{number+1}]'
                    +('' if 'cell_topology' in target.extra else '/w:tblPr/w:tblBorders'),
        )))
    grouped: dict[tuple[str, bool], list[ObjectMappingEntry]] = {}
    for entry in mapping.entries:
        grouped.setdefault((entry.extra['planned_table_id'], entry.extra['range_exclusion']), []).append(entry)
    entries = []
    for (target_id, excluded), group in grouped.items():
        entries.append(replace(
            group[0], id=f'flow-group-{len(entries)}',
            source_ids=tuple(source for entry in group for source in entry.source_ids),
            target_ids=None if excluded else (target_id,),
            extra={'source_grid_occurrences': [entry.extra for entry in group], 'range_exclusion': excluded},
        ))
    report.metrics['object_mapping'] = object_mapping_to_dict(replace(
        mapping, targets=tuple(targets), publication='staged',
        entries=tuple(entries),
        result_id='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest(),
    ), limits=limits)
