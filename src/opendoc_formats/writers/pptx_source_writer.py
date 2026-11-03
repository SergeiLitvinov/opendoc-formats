"""Bound text edits in original PPTX parts; untouched payloads remain exact."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import opendoc_model as od
from lxml import etree

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.opc import part_name
from opendoc_formats.ooxml.pptx_crop import bind_image_crop, project_image_crop
from opendoc_formats.ooxml.pptx_source_cells import apply_cell_text, cell_bindings
from opendoc_formats.ooxml.pptx_source_chart_frame import chart_frame
from opendoc_formats.ooxml.pptx_source_geometry import geometry_bindings, project_geometry
from opendoc_formats.ooxml.pptx_source_table_grid import bind_table_grid, project_table_grid
from opendoc_formats.ooxml.pptx_source_text import KEY, source_bindings, source_digest
from opendoc_formats.ooxml.pptx_source_xml import SourceRoots
from opendoc_formats.support.cancellation import cancellable_items, checkpoint
from opendoc_formats.support.io import atomic_copy


def write_source_text(
    document: od.DocumentModel, output: Path, *, limits: od.DocumentLimits | None = None,
) -> od.ConversionReport:
    report = od.ConversionReport(output)
    binding = document.metadata.get(KEY)
    graph = document.package
    if (graph is None or graph.format != 'pptx' or not isinstance(binding, dict)
            or type(binding.get('version')) is not int or binding['version'] not in {1, 2, 3, 4, 5, 6, 7, 8}):
        report.add(od.IssueSeverity.ERROR, 'pptx.source-binding', 'Source PPTX with current text bindings required', 'package')
        return report
    try:
        fresh = source_digest(document, limits=limits, geometry=binding['version'] >= 2,
                              tables=binding['version'] >= 3, table_geometry=binding['version'] >= 4,
                              image_crops=binding['version'] >= 6,
                              structured_text=binding['version'] >= 7,
                              placeholder_geometry=binding['version'] >= 8) == binding.get('digest')
    except od.ArtifactLimitError:
        raise
    except ResourceLimitError as error:
        report.add(od.IssueSeverity.ERROR, 'pptx.source-xml-limit', str(error), 'package')
        return report
    except (InvalidDocumentError, UnsupportedDocumentError, ValueError) as error:
        report.add(od.IssueSeverity.ERROR, 'pptx.source-binding', str(error), 'package')
        return report
    if not fresh:
        report.add(od.IssueSeverity.ERROR, 'pptx.source-binding',
                   'Edits outside bound text slots require another native projection; source export refused', 'package')
        return report
    inventory = document.metadata.get('opendoc_formats.pptx_source_package', {})
    if not isinstance(inventory, dict) or inventory.get('relationship_assessment_complete') is not True:
        report.add(od.IssueSeverity.ERROR, 'pptx.source-package', 'Unproved source relationship profile', 'package')
        return report
    changed: dict[str, bytes] = {}
    roots = {}
    source_roots = SourceRoots(limits)
    geometry_edits = 0
    cell_text_edits = 0
    table_grid_edits = 0
    chart_frame_edits = 0
    image_crop_edits = 0
    for si, bi, ri, part, node in source_bindings(document, source_roots, structured=binding['version'] >= 7):
        checkpoint()
        text = document.sections[si].blocks[bi].content[ri].text
        if text == (node.text or ''):
            continue
        if any(char in text for char in '\r\n\t\v'):
            report.add(od.IssueSeverity.ERROR, 'pptx.source-text', 'Native run edits cannot change break topology', part)
            return report
        try:
            node.text = text
        except ValueError:
            report.add(od.IssueSeverity.ERROR, 'pptx.source-text', 'Text is outside the native XML character profile', part)
            return report
        roots[part] = node.getroottree()
    if binding['version'] >= 3:
        for cell in cell_bindings(document, source_roots, fields=binding['version'] >= 7):
            checkpoint()
            if not cell.paragraph.content:
                continue
            if cell.index is not None and cell.text() == (cell.node.text or ''):
                continue
            if any(char in cell.text() for char in '\r\n\t\v'):
                report.add(od.IssueSeverity.ERROR, 'pptx.source-cell-text',
                           'Cell edits cannot change break topology', cell.location)
                return report
            try:
                edited = apply_cell_text(cell)
            except ValueError:
                report.add(od.IssueSeverity.ERROR, 'pptx.source-cell-text',
                           'Cell text is outside the native XML profile', cell.location)
                return report
            if edited:
                roots[cell.part] = cell.node.getroottree()
                cell_text_edits += 1
    if binding['version'] >= 2:
        for native in geometry_bindings(document, source_roots, placeholders=binding['version'] >= 8):
            try:
                block = document.sections[native.section].blocks[native.block]
                crop = bind_image_crop(native, block, document) if binding['version'] >= 6 else None
                grid = bind_table_grid(native, block) if binding['version'] >= 4 else None
                resize = (block.box.width, block.box.height) != (native.original.width, native.original.height)
                chart = binding['version'] >= 5 and resize and chart_frame(native, document, source_roots)
                checkpoint()
                moved = project_geometry(native, block.box, frame_resize=grid is not None or chart)
                resized = project_table_grid(grid) if grid is not None else False
                cropped = project_image_crop(crop) if crop is not None else False
            except ResourceLimitError as error:
                report.add(od.IssueSeverity.ERROR, 'pptx.source-xml-limit', str(error), native.part)
                return report
            except (InvalidDocumentError, UnsupportedDocumentError) as error:
                report.add(od.IssueSeverity.ERROR, 'pptx.source-geometry', str(error), native.part)
                return report
            except ValueError as error:
                report.add(od.IssueSeverity.ERROR, 'pptx.source-geometry', str(error),
                           f'sections[{native.section}].blocks[{native.block}].box')
                return report
            if moved or resized or cropped:
                roots[native.part] = native.shape.getroottree()
                geometry_edits += int(moved)
                table_grid_edits += int(resized)
                chart_frame_edits += int(chart and moved)
                image_crop_edits += int(cropped)
    signed = (any(name.lower().startswith('/_xmlsignatures/')
                  or part.media_type.lower().startswith('application/vnd.openxmlformats-package.digital-signature')
                  for name, part in graph.parts.items())
              or any(edge.relationship_type.startswith(
                  'http://schemas.openxmlformats.org/package/2006/relationships/digital-signature/'
              ) for edge in graph.relationships))
    if roots and signed:
        report.add(od.IssueSeverity.ERROR, 'pptx.source-signature', 'Cannot edit a signed source package', 'package')
        return report
    for part, root in cancellable_items(roots.items()):
        changed[part] = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
    with TemporaryDirectory(prefix='opendoc_pptx_source_') as directory:
        staged = Path(directory)/'source.pptx'
        with ZipFile(staged, 'w', ZIP_DEFLATED) as archive:
            for name, part in cancellable_items(graph.parts.items()):
                safe = part_name(name)
                with archive.open(safe[1:], 'w') as member:
                    data = changed.get(name, part.data)
                    for offset in range(0, len(data), 65536):
                        checkpoint()
                        member.write(data[offset:offset+65536])
        checkpoint()
        if staged.stat().st_size > (limits or od.DocumentLimits()).max_bytes:
            raise od.ArtifactLimitError('PPTX output exceeds byte budget', path='output', quota='bytes',
                                        maximum=(limits or od.DocumentLimits()).max_bytes)
        atomic_copy(staged, output, max_bytes=None, before_replace=checkpoint)
    report.add(od.IssueSeverity.LOSS, 'pptx.source-container',
               'Original file payloads retained; ZIP storage metadata and archive-byte identity are not preserved', 'package')
    report.metrics['source_parts'] = len(graph.parts)
    report.metrics['changed_parts'] = sorted(changed)
    report.metrics['geometry_edits'] = geometry_edits
    report.metrics['cell_text_edits'] = cell_text_edits
    report.metrics['table_grid_edits'] = table_grid_edits
    report.metrics['chart_frame_edits'] = chart_frame_edits
    report.metrics['image_crop_edits'] = image_crop_edits
    if geometry_edits:
        report.metrics['geometry_precision'] = {'max_slide_error_emu': 1, 'max_angle_error_degrees': 1/120000}
    return report
