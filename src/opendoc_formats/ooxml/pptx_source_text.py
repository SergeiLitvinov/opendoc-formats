"""Formats-owned source-text bindings and freshness checks, never a Model codec."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

import opendoc_model as od

from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.ooxml.pptx_source_xml import SourceRoots
from opendoc_formats.ooxml.pptx_text_slots import TextSlot, matched_slots, paragraph_slots
from opendoc_formats.support.cancellation import cancellable_items, checkpoint

KEY = 'opendoc_formats.pptx_source_text'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'


def source_bindings(
    document: od.DocumentModel, roots: SourceRoots | None = None,
    *, structured: bool = False,
) -> list[tuple[int, int, int, str, Any]]:
    """Bind only uniquely identified text shapes with exact, simple native run topology."""
    graph = document.package
    if graph is None or graph.format != 'pptx':
        return []
    roots = SourceRoots() if roots is None else roots
    indexes: dict[str, dict[str, list[Any]]] = {}
    bindings = []
    seen = set()
    for si, section in enumerate(cancellable_items(document.sections)):
        for bi, block in enumerate(cancellable_items(section.blocks)):
            if not isinstance(block, od.Paragraph) or block.provenance is None:
                continue
            part, identity = block.provenance.package_part, block.provenance.object_id
            if part not in graph.parts or not identity:
                continue
            roots.load(graph, part)
            if part not in indexes:
                indexes[part] = {}
                for shape in cancellable_items(roots[part].iter(P+'sp')):
                    info = shape.find(P+'nvSpPr/'+P+'cNvPr')
                    if info is not None:
                        indexes[part].setdefault(info.get('id'), []).append(shape)
            shapes = indexes[part].get(identity, [])
            if len(shapes) != 1:
                continue
            paragraphs = shapes[0].findall(P+'txBody/'+A+'p')
            native_slots, supported = [], True
            for pi, paragraph in enumerate(cancellable_items(paragraphs)):
                parsed = paragraph_slots(paragraph, breaks=structured, fields=structured)
                if parsed is None:
                    supported = False
                    break
                native_slots.extend(parsed)
                if pi < len(paragraphs)-1:
                    native_slots.append(TextSlot(literal='\n' if structured else None))
            slots = matched_slots(native_slots, block.content) if supported else None
            if slots is None:
                continue
            for ri, node in enumerate(slots):
                if node is None:
                    continue
                address = (part, node.getroottree().getpath(node))
                if address in seen:
                    raise InvalidDocumentError('Ambiguous repeated PPTX source text owner')
                seen.add(address)
                bindings.append((si, bi, ri, part, node))
    return bindings


def source_digest(
    document: od.DocumentModel, *, limits: od.DocumentLimits | None = None, geometry: bool = True, tables: bool = True,
    table_geometry: bool = False,
    image_crops: bool = False,
    structured_text: bool = False,
    placeholder_geometry: bool = False,
) -> str:
    # Normalize through the official Model codec before hashing. Mask only the
    # text slots the native route can project; every other edit invalidates it.
    clone = deepcopy(document)
    clone.metadata.pop(KEY, None)
    roots = SourceRoots(limits)
    for si, bi, ri, _part, _node in source_bindings(clone, roots, structured=structured_text):
        checkpoint()
        clone.sections[si].blocks[bi].content[ri].text = ''
    if geometry:
        from opendoc_formats.ooxml.pptx_source_geometry import geometry_bindings

        for binding in geometry_bindings(clone, roots, placeholders=placeholder_geometry):
            if image_crops:
                from opendoc_formats.ooxml.pptx_crop import bind_image_crop

                crop = bind_image_crop(binding, clone.sections[binding.section].blocks[binding.block], clone)
                if crop is not None:
                    crop.mask()
            if table_geometry:
                from opendoc_formats.ooxml.pptx_source_table_grid import bind_table_grid

                grid = bind_table_grid(binding, clone.sections[binding.section].blocks[binding.block])
                if grid is not None:
                    grid.mask()
            clone.sections[binding.section].blocks[binding.block].box = binding.original
    if tables:
        from opendoc_formats.ooxml.pptx_source_cells import cell_bindings

        for cell in cell_bindings(clone, roots, fields=structured_text):
            if cell.index is None:
                cell.paragraph.content = []
            else:
                cell.paragraph.content[cell.index].text = ''
    canonical = od.document_from_json(od.document_to_json(clone, limits=limits), limits=limits)
    return hashlib.sha256(od.document_to_json(canonical, limits=limits).encode('utf-8')).hexdigest()


def remember_source_text(document: od.DocumentModel, *, limits: od.DocumentLimits | None = None) -> None:
    bindings = source_bindings(document, SourceRoots(limits), structured=True)
    if any(document.sections[si].blocks[bi].content[ri].text != (node.text or '') for si, bi, ri, _part, node in bindings):
        raise InvalidDocumentError('Imported PPTX source text does not match its native binding')
    from opendoc_formats.ooxml.pptx_source_cells import cell_bindings

    if any(cell.text() != (cell.node.text or '') for cell in cell_bindings(document, SourceRoots(limits), fields=True)
           if cell.index is not None):
        raise InvalidDocumentError('Imported PPTX cell text does not match its native binding')
    document.metadata[KEY] = {'version': 8, 'digest': source_digest(
        document, limits=limits, table_geometry=True, image_crops=True, structured_text=True, placeholder_geometry=True,
    )}
