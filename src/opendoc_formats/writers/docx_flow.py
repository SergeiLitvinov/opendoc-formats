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
                    specs.append({'table': block, 'location': location, 'number': table_number,
                                  'segments': segments, 'matches': [], 'x': x, 'y': y})
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
                        if line is not None and _same(line, expected):
                            owners.append((spec, expected))
                if len(owners) > 1:
                    raise ValueError('Grid occurrence belongs to more than one table')
                if owners:
                    if inline_count != 1:
                        raise ValueError('Grid occurrence in a mixed paragraph cannot be consumed')
                    spec, expected = owners[0]
                    if any(item[0] == expected for item in spec['matches']):
                        raise ValueError('Duplicate grid strokes require an explicit compositing profile')
                    spec['matches'].append((expected, image, location, _style(image, result)))
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
                if len(matches) != len(spec['segments']) or len({item[3] for item in matches}) != 1:
                    raise ValueError('Table grid must be complete with a uniform native stroke')
                bounds, widths = _selected_grid(table, spec['x'], spec['y'], limits)
                width, color = matches[0][3]
                expected_borders = BorderSet({side: Border(kind='line', style='solid',
                            color=ColorValue.from_hex(color), width_pt=width)
                            for side in ('top', 'left', 'bottom', 'right', 'inside-horizontal', 'inside-vertical')})
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
                    for row in table.rows:
                        for column, cell in enumerate(row.cells):
                            checkpoint()
                            set_preferred_width(cell, WidthMeasure('absolute', widths[column], 'pt'), limits=limits)
                target_id = f'flow-table-{spec["number"]}'
                targets.append(ObjectOccurrence(target_id, extra={'body_table': spec['number'], 'width': width, 'color': color}))
                for segment, image, source_location, _ in matches:
                    checkpoint()
                    visible = (bounds[0] <= segment[0] <= bounds[2] if segment[0] == segment[2]
                               else bounds[1] <= segment[1] <= bounds[3])
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
    for _row, column, cell in placements:
        checkpoint()
        raw = cell.properties.get('pdf_cell_bbox')
        if not isinstance(raw, list) or len(raw) != 4:
            raise ValueError('Grid replacement requires source bounds for each retained cell')
        a, b, c, d = map(_number, raw)
        if a not in x or c not in x or b not in y or d not in y or a >= c or b >= d:
            raise ValueError('Retained cell is not aligned to the original PDF grid')
        if (cell.column_span != 1 or cell.row_span != 1 or x.index(c)-x.index(a) != 1 or y.index(d)-y.index(b) != 1):
            raise ValueError('Merged source grid replacement requires a separate measured profile')
        for row in range(y.index(b), y.index(d)):
            for col in range(x.index(a), x.index(c)):
                checkpoint()
                if (row, col) in occupied:
                    raise ValueError('Retained source cells overlap')
                occupied.add((row, col))
        if widths[column] not in (None, c-a):
            raise ValueError('Retained cell widths disagree within a column')
        widths[column] = c-a
        boxes.append((a, b, c, d))
    if not boxes or any(value is None for value in widths):
        raise ValueError('Selected grid is empty or incomplete')
    bounds = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    if sum((b[2]-b[0])*(b[3]-b[1]) for b in boxes) != (bounds[2]-bounds[0])*(bounds[3]-bounds[1]):
        raise ValueError('Selected cells do not form one contiguous rectangle')
    return bounds, widths


def finalize_flow_mapping(report: ConversionReport, path: Path, *, limits: DocumentLimits | None = None) -> None:
    raw = report.metrics.get('object_mapping')
    if raw is None:
        return
    mapping = object_mapping_from_dict(raw, limits=limits)
    w = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    with ZipFile(path) as package:
        root = ET.fromstring(package.read('word/document.xml'))
    tables = root.find(w+'body').findall(w+'tbl')
    targets = []
    for plan in report.metrics['docx_flow_grid_plan']:
        checkpoint()
        target = ObjectOccurrence(plan['id'], extra={key: value for key, value in plan.items() if key != 'id'})
        number = target.extra['body_table']
        borders = tables[number].find(w+'tblPr/'+w+'tblBorders')
        if borders is None or len(borders) != 6:
            raise ValueError('Native Word table border replacement was not written')
        for border in borders:
            if (border.get(w+'val') != 'single' or border.get(w+'color') != target.extra['color']
                    or int(border.get(w+'sz', '-1')) != round(target.extra['width']*8)):
                raise ValueError('Native Word table border replacement changed stroke')
        targets.append(replace(target, native_locator=NativeObjectLocator(
            'docx', f'word/document.xml#/w:document/w:body/w:tbl[{number+1}]/w:tblPr/w:tblBorders',
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
