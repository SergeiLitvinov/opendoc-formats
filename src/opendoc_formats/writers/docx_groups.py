"""Write bound Model vector scopes as editable Word group/shape objects."""

from __future__ import annotations

from typing import Any

from opendoc_model import DocumentLimits, DocumentModel, Image, VectorScene, get_anchor, get_integration

from opendoc_formats.ooxml.group_geometry import axis_transform, paint_style, rectangle, scene_profile
from opendoc_formats.ooxml.package import points_to_emu

A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
WPG = 'http://schemas.microsoft.com/office/word/2010/wordprocessingGroup'
WPS = 'http://schemas.microsoft.com/office/word/2010/wordprocessingShape'
WPC = 'http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas'


def bound_scene(document: DocumentModel, image: Image, *, limits: DocumentLimits | None = None) -> VectorScene | None:
    anchor = get_anchor(image, limits=limits)
    integration = get_integration(document, limits=limits)
    scenes = [s for s in integration.scenes if anchor is not None and s.node_id == anchor.id] if integration else []
    if len(scenes) > 1:
        raise ValueError('Multiple scenes are bound to the same drawing')
    if not scenes and image.properties.get('docx_group_scene'):
        raise ValueError('Removed native group scene requires an explicit replacement; SVG preview is not authoritative')
    return scenes[0] if scenes else None


def write_group(paragraph: Any, image: Image, scene: VectorScene) -> None:
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls
    from lxml import etree

    from opendoc_formats.writers.docx_drawing_writer import _apply_image_placement

    boxes = scene_profile(scene)
    if (image.box is None or image.box.rotation or image.crop is not None
            or image.properties.flip_horizontal or image.properties.flip_vertical):
        raise ValueError('Group viewport rotation/crop/flip needs a verified native projection')
    if image.box.width != scene.width or image.box.height != scene.height:
        raise ValueError('Canvas resize requires an explicit scene-coordinate projection')
    width, height = points_to_emu(image.box.width), points_to_emu(image.box.height)
    identifier = paragraph.part.next_id
    run = parse_xml(f'<w:r {nsdecls("w", "wp", "a")}><w:drawing><wp:inline>'
                    f'<wp:extent cx="{width}" cy="{height}"/><wp:docPr id="{identifier}" name="Vector group"/>'
                    '<wp:cNvGraphicFramePr/><a:graphic><a:graphicData/></a:graphic>'
                    '</wp:inline></w:drawing></w:r>')
    data = run.xpath('.//a:graphicData')[0]
    data.set('uri', WPC)
    root = etree.SubElement(data, f'{{{WPC}}}wpc', nsmap={'wpc': WPC, 'wpg': WPG, 'wps': WPS})
    background = next((p for p in scene.paths if p.extra.get('docx_canvas_background')), None)
    bg = etree.SubElement(root, f'{{{WPC}}}bg')
    if background is None:
        etree.SubElement(bg, f'{{{A}}}noFill')
    else:
        color, alpha = paint_style(background)
        rgb = etree.SubElement(etree.SubElement(bg, f'{{{A}}}solidFill'), f'{{{A}}}srgbClr', val=color)
        etree.SubElement(rgb, f'{{{A}}}alpha', val=str(round(alpha*100_000)))
    whole = etree.SubElement(root, f'{{{WPC}}}whole')
    etree.SubElement(etree.SubElement(whole, f'{{{A}}}ln'), f'{{{A}}}noFill')
    paths, groups = {p.id: p for p in scene.paths}, {g.id: g for g in scene.groups}
    counter = identifier

    def transform(parent: Any, off: tuple, extent: tuple, child_off: tuple | None = None,
                  child_extent: tuple | None = None) -> None:
        node = etree.SubElement(parent, f'{{{A}}}xfrm')
        for tag, values, names in [('off', off, ('x', 'y')), ('ext', extent, ('cx', 'cy')),
                                   ('chOff', child_off, ('x', 'y')), ('chExt', child_extent, ('cx', 'cy'))]:
            if values is not None:
                etree.SubElement(node, f'{{{A}}}{tag}', **{name: str(points_to_emu(v)) for name, v in zip(names, values)})

    def emit(key: str, parent: Any) -> None:
        nonlocal counter
        counter += 1
        if key in groups:
            group = groups[key]
            target = etree.SubElement(parent, f'{{{WPG}}}wgp')
            etree.SubElement(target, f'{{{WPG}}}cNvPr', id=str(counter), name=str(group.extra.get('docx_name', group.id)))
            etree.SubElement(target, f'{{{WPG}}}cNvGrpSpPr')
            props = etree.SubElement(target, f'{{{WPG}}}grpSpPr')
            sx, sy, tx, ty = axis_transform(group.transform)
            box = boxes[key]
            transform(props, (box.x, box.y), (box.width, box.height),
                      ((box.x-tx)/sx, (box.y-ty)/sy), (box.width/sx, box.height/sy))
            for child in group.children:
                emit(child, target)
        else:
            path = paths[key]
            box = rectangle(path)
            color, alpha = paint_style(path)
            target = etree.SubElement(parent, f'{{{WPS}}}wsp')
            etree.SubElement(target, f'{{{WPS}}}cNvPr', id=str(counter), name=str(path.extra.get('docx_name', path.id)))
            etree.SubElement(target, f'{{{WPS}}}cNvSpPr')
            props = etree.SubElement(target, f'{{{WPS}}}spPr')
            transform(props, (box.x, box.y), (box.width, box.height))
            geometry = etree.SubElement(props, f'{{{A}}}prstGeom', prst='rect')
            etree.SubElement(geometry, f'{{{A}}}avLst')
            fill = etree.SubElement(props, f'{{{A}}}solidFill')
            rgb = etree.SubElement(fill, f'{{{A}}}srgbClr', val=color)
            etree.SubElement(rgb, f'{{{A}}}alpha', val=str(round(alpha*100_000)))
            etree.SubElement(etree.SubElement(props, f'{{{A}}}ln'), f'{{{A}}}noFill')
            etree.SubElement(props, f'{{{A}}}effectLst')
            etree.SubElement(target, f'{{{WPS}}}bodyPr')

    for key in scene.roots:
        if background is None or key != background.id:
            emit(key, root)
    drawing = run.xpath('.//wp:inline')[0]
    drawing.xpath('./wp:docPr')[0].set('name', 'OpenDoc scene:'+scene.id)
    drawing.xpath('./wp:docPr')[0].set('descr', image.alt_text)
    _apply_image_placement(drawing, image)
    paragraph._p.append(run)
