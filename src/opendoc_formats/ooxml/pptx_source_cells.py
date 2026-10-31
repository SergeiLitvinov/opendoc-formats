"""Physical PPTX cell/run bindings, retaining native merge topology and caret styles."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import opendoc_model as od
from lxml import etree

from opendoc_formats.ooxml.pptx_source_xml import SourceRoots
from opendoc_formats.ooxml.pptx_table_grid import merge_origins as _origins
from opendoc_formats.ooxml.pptx_text_slots import matched_slots, paragraph_slots
from opendoc_formats.ooxml.table_grid import native_grid
from opendoc_formats.support.cancellation import cancellable_items

A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
CELL_KEY = 'opendoc_formats.pptx_cell'


@dataclass
class CellBinding:
    part: str
    location: str
    paragraph: od.Paragraph
    index: int | None
    node: Any

    def text(self) -> str:
        return self.paragraph.content[self.index if self.index is not None else 0].text




def _empty_slot(paragraph: Any, model: od.Paragraph) -> bool:
    if any(child.tag not in {A+'pPr', A+'endParaRPr'} for child in paragraph):
        return False
    end = paragraph.find(A+'endParaRPr')
    if end is not None and any(end.find(A+name) is not None for name in ('hlinkClick', 'hlinkMouseOver')):
        return False
    if not model.content:
        return True
    if len(model.content) == 1 and isinstance(model.content[0], od.TextRun):
        run = deepcopy(model.content[0])
        run.text = ''
        return run == od.TextRun('')
    return False


def cell_bindings(document: od.DocumentModel, roots: SourceRoots, *, fields: bool = False) -> list[CellBinding]:
    graph = document.package
    if graph is None or graph.format != 'pptx':
        return []
    result = []
    for si, section in enumerate(cancellable_items(document.sections)):
        part = section.provenance.package_part if section.provenance else None
        if part not in graph.parts:
            continue
        root = roots.load(graph, part)
        frames = {}
        for frame in cancellable_items(root.iter(P+'graphicFrame')):
            identity = frame.find(P+'nvGraphicFramePr/'+P+'cNvPr')
            if identity is not None:
                frames.setdefault(identity.get('id'), []).append(frame)
        for bi, model in enumerate(cancellable_items(section.blocks)):
            if not isinstance(model, od.Table):
                continue
            candidates = frames.get(model.properties.get('pptx', {}).get('object_id'), [])
            if len(candidates) != 1:
                continue
            data = candidates[0].find(A+'graphic/'+A+'graphicData')
            if data is None or data.get('uri') != 'http://schemas.openxmlformats.org/drawingml/2006/table':
                continue
            native = data.find(A+'tbl')
            if native is None:
                continue
            origins = _origins(native)
            rows = native.findall(A+'tr')
            if origins is None or len(rows) != len(model.rows):
                continue
            layout = model.properties.get('opendoc_formats.pptx_table_grid', {}).get('layout')
            if layout == 'physical-unverified':
                continue
            if layout == 'logical-origins':
                _, placements = native_grid(model, limits=roots.limits)
                if {(r, c) for r, c, _ in placements} != origins:
                    continue
                columns = {id(cell): c for _, c, cell in placements}
            else:
                if any(len(row.findall(A+'tc')) != len(model_row.cells)
                       for row, model_row in zip(rows, model.rows, strict=True)):
                    continue
                columns = {id(cell): ci for row in model.rows for ci, cell in enumerate(row.cells)}
            for ri, (row, model_row) in enumerate(cancellable_items(zip(rows, model.rows, strict=True))):
                native_cells = row.findall(A+'tc')
                for logical_ci, model_cell in enumerate(cancellable_items(model_row.cells)):
                    ci = columns[id(model_cell)]
                    if (ri, ci) not in origins or model_cell.properties.get(CELL_KEY) != {'row': ri, 'column': ci}:
                        continue
                    cell = native_cells[ci]
                    paragraphs = cell.findall(A+'txBody/'+A+'p')
                    if len(paragraphs) != len(model_cell.blocks):
                        continue
                    pairs = zip(paragraphs, model_cell.blocks, strict=True)
                    for pi, (paragraph, model_paragraph) in enumerate(cancellable_items(pairs)):
                        if not isinstance(model_paragraph, od.Paragraph):
                            continue
                        path = f'sections[{si}].blocks[{bi}].rows[{ri}].cells[{logical_ci}].blocks[{pi}]'
                        if _empty_slot(paragraph, model_paragraph):
                            result.append(CellBinding(part, path, model_paragraph, None, paragraph))
                            continue
                        native_slots = paragraph_slots(paragraph, fields=fields)
                        slots = matched_slots(native_slots, model_paragraph.content) if native_slots is not None else None
                        if slots is not None:
                            result.extend(CellBinding(part, f'{path}.content[{index}]', model_paragraph, index, node)
                                          for index, node in enumerate(slots) if node is not None)
    return result


def apply_cell_text(binding: CellBinding) -> bool:
    if binding.index is not None:
        text = binding.text()
        if text == (binding.node.text or ''):
            return False
        binding.node.text = text
        return True
    if not binding.paragraph.content or not binding.text():
        return False
    run = etree.Element(A+'r')
    end = binding.node.find(A+'endParaRPr')
    if end is not None:
        properties = deepcopy(end)
        properties.tag = A+'rPr'
        run.append(properties)
    etree.SubElement(run, A+'t').text = binding.text()
    if end is None:
        binding.node.append(run)
    else:
        binding.node.insert(binding.node.index(end), run)
    return True
