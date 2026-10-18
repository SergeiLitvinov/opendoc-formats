"""Parse native Word groups into editable official vector paths and groups."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any

from opendoc_model import (
    AffineTransform,
    Anchor,
    ArtifactLimitError,
    Box,
    ColorValue,
    DocumentLimits,
    DocumentModel,
    GroupColorSpace,
    GroupCompositing,
    Image,
    Paint,
    PathCommand,
    Resource,
    ResourceKind,
    VectorGroup,
    VectorPath,
    VectorScene,
    get_anchor,
    set_anchor,
    set_vector_scene,
    walk_model,
)

from opendoc_formats.ooxml.group_geometry import preview_svg

A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
WPG = '{http://schemas.microsoft.com/office/word/2010/wordprocessingGroup}'
WPS = '{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}'
WP = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
WPC = '{http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas}'
NEUTRAL = GroupCompositing(1, False, False, 'normal', color_space=GroupColorSpace('rgb'))


def stage_groups(run: Any, model: DocumentModel) -> list[Image]:
    from lxml import etree

    from opendoc_formats.readers.docx_drawing import _drawing_position, _drawing_properties

    result = []
    for drawing in run._r.xpath('.//wp:anchor | .//wp:inline'):
        data = drawing.find(A+'graphic/'+A+'graphicData')
        roots = [child for child in data if child.tag in {WPG+'wgp', WPC+'wpc'}] if data is not None else []
        if not roots:
            continue
        if len(roots) != 1:
            raise ValueError('Ambiguous native group viewport')
        extent, properties = drawing.find(WP+'extent'), drawing.find(WP+'docPr')
        if extent is None or properties is None:
            raise ValueError('Native group has no extent or drawing identity')
        width, height = int(extent.get('cx', '0'))/12700, int(extent.get('cy', '0'))/12700
        if width <= 0 or height <= 0:
            raise ValueError('Invalid native group extent')
        token = properties.get('name', '')
        scene_id = token.removeprefix('OpenDoc scene:') if token.startswith('OpenDoc scene:') else 'docx-group-'+hashlib.sha256(
            (str(run.part.partname)+'#'+properties.get('id', '')).encode()).hexdigest()[:16]
        resource_id = scene_id+'-preview'
        if resource_id in model.resources:
            raise ValueError('Duplicate native group identity')
        x, y = _drawing_position(drawing)
        image = Image(resource_id, alt_text=properties.get('descr', ''), box=Box(x, y, width, height),
                      properties={**_drawing_properties(drawing), 'docx_group_scene': scene_id,
                                  'docx_group_pending': etree.tostring(drawing, encoding='unicode')})
        set_anchor(image, Anchor(scene_id+'-node'))
        model.add_resource(Resource(resource_id, ResourceKind.VECTOR_IMAGE, 'image/svg+xml', data=b'<svg/>'))
        result.append(image)
    return result


def attach_groups(model: DocumentModel, *, limits: DocumentLimits | None) -> None:
    from lxml import etree

    for ref in walk_model(model, limits=limits):
        image = ref.node
        if not isinstance(image, Image) or 'docx_group_pending' not in image.properties:
            continue
        source = image.properties.pop('docx_group_pending')
        root = etree.fromstring(source.encode(), etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True))
        scene = parse_group(root, image.properties['docx_group_scene'], get_anchor(image).id, limits=limits)
        model.resources[image.resource_id] = replace(model.resources[image.resource_id], data=preview_svg(scene))
        set_vector_scene(model, scene, limits=limits)


def parse_group(drawing: Any, identifier: str, node_id: str, *, limits: DocumentLimits | None) -> VectorScene:
    budget = limits or DocumentLimits()
    paths, groups = [], []
    used = 0

    def guard(depth: int) -> None:
        nonlocal used
        used += 1
        if used > budget.max_nodes or depth > budget.max_depth:
            raise ArtifactLimitError('Native group exceeds selected budget', path='$.docx.groups',
                                     quota='nodes' if used > budget.max_nodes else 'depth',
                                     maximum=budget.max_nodes if used > budget.max_nodes else budget.max_depth)

    def number(node: Any, name: str) -> float:
        if node is None or node.get(name) is None:
            raise ValueError('Incomplete native group transform')
        return int(node.get(name))/12700

    def transform(props: Any, *, group: bool) -> tuple:
        if props is None:
            raise ValueError('Missing native group properties')
        for effect in (props.find(A+'effectLst'), props.find(A+'effectDag')):
            if effect is not None and (len(effect) or effect.tag == A+'effectDag'):
                raise ValueError('Native group effect needs a verified non-raster projection')
        if any(child.tag not in {A+n for n in ('xfrm', 'prstGeom', 'solidFill', 'ln', 'effectLst', 'effectDag', 'extLst')}
               for child in props):
            raise ValueError('Unsupported native group/shape paint property')
        extensions = props.find(A+'extLst')
        if extensions is not None:
            # Word stores its inactive theme outline here after an explicit noFill.
            hidden_line = '{http://schemas.microsoft.com/office/drawing/2010/main}hiddenLine'
            if any(ext.tag != A+'ext' or ext.get('uri') != '{91240B29-F687-4F45-9708-019B960494DF}'
                   or len(ext) != 1 or ext[0].tag != hidden_line for ext in extensions):
                raise ValueError('Unverified native drawing extension')
        tr = props.find(A+'xfrm')
        if tr is None or any(tr.get(name, '0') not in ('0', 'false') for name in ('rot', 'flipH', 'flipV')):
            raise ValueError('Native group rotation/flip requires a verified projection')
        off, ext = tr.find(A+'off'), tr.find(A+'ext')
        x, y = number(off, 'x'), number(off, 'y')
        width, height = number(ext, 'cx'), number(ext, 'cy')
        if width <= 0 or height <= 0:
            raise ValueError('Degenerate native shape/group')
        if not group:
            return Box(x, y, width, height), None
        child_off, child_ext = tr.find(A+'chOff'), tr.find(A+'chExt')
        cx, cy = number(child_off, 'x'), number(child_off, 'y')
        cw, ch = number(child_ext, 'cx'), number(child_ext, 'cy')
        if cw <= 0 or ch <= 0:
            raise ValueError('Degenerate native child coordinate frame')
        return Box(x, y, width, height), AffineTransform(a=width/cw, d=height/ch, e=x-cx*width/cw, f=y-cy*height/ch)

    def compose(parent: AffineTransform, child: AffineTransform) -> AffineTransform:
        return AffineTransform(a=parent.a*child.a, d=parent.d*child.d,
                               e=parent.e+parent.a*child.e, f=parent.f+parent.d*child.f)

    def paint(fill: Any) -> Paint:
        if fill is None or len(fill) != 1:
            raise ValueError('Native group requires an explicit solid RGB paint')
        node = fill[0]
        if node.tag == A+'srgbClr':
            color = ColorValue.from_hex(node.get('val'))
        elif node.tag == A+'prstClr' and node.get('val') in {'white', 'black'}:
            color = ColorValue.from_hex('FFFFFF' if node.get('val') == 'white' else '000000')
        else:
            raise ValueError('Native group color needs a separately verified color resolver')
        if any(child.tag != A+'alpha' for child in node) or len(node) > 1:
            raise ValueError('Unsupported native group color transform')
        alpha = node.find(A+'alpha')
        return Paint(color, int(alpha.get('val'))/100_000 if alpha is not None else 1.)

    def visit(node: Any, depth: int, outer: AffineTransform = AffineTransform()) -> str:
        guard(depth)
        if node.tag in {WPG+'grpSp', WPG+'wgp'}:
            key = 'group-'+str(len(groups))
            _, matrix = transform(node.find(WPG+'grpSpPr'), group=True)
            label = node.find(WPG+'cNvPr')
            index = len(groups)
            groups.append(None)
            children = [visit(c, depth+1) for c in node if c.tag in {WPG+'grpSp', WPS+'wsp'}]
            if any(c.tag not in {WPG+n for n in ('cNvPr', 'cNvGrpSpPr', 'grpSpPr', 'grpSp')} | {WPS+'wsp'} for c in node):
                raise ValueError('Unsupported native group child')
            groups[index] = VectorGroup(key, tuple(children), transform=compose(outer, matrix), compositing=NEUTRAL,
                                        extra={'docx_name': label.get('name', key) if label is not None else key})
            return key
        if node.tag != WPS+'wsp':
            raise ValueError('Native group contains unsupported text, raster or custom geometry')
        props = node.find(WPS+'spPr')
        box, _ = transform(props, group=False)
        geometry, line, fill = props.find(A+'prstGeom'), props.find(A+'ln'), props.find(A+'solidFill')
        if (geometry is None or geometry.get('prst') != 'rect' or line is None or line.find(A+'noFill') is None
                or fill is None):
            raise ValueError('Native group requires explicit RGB rectangles without strokes')
        if any(child.tag != A+'avLst' or len(child) for child in geometry):
            raise ValueError('Adjusted native geometry is outside the verified rectangle profile')
        if any(child.tag not in {WPS+n for n in ('cNvPr', 'cNvSpPr', 'spPr', 'style', 'bodyPr')} for child in node):
            raise ValueError('Unsupported native shape member')
        if any(len(child) for child in node if child.tag == WPS+'cNvPr'):
            raise ValueError('Native shape links/extensions need an explicit projection')
        if node.find('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}txbxContent') is not None:
            raise ValueError('Mixed native text group is outside the verified profile')
        style = node.find(WPS+'style')
        effect_ref = style.find(A+'effectRef') if style is not None else None
        if effect_ref is not None and effect_ref.get('idx') != '0':
            raise ValueError('Referenced native shape effect is outside the verified profile')
        fill_paint = paint(fill)
        x, y = outer.e+outer.a*box.x, outer.f+outer.d*box.y
        w, h = outer.a*box.width, outer.d*box.height
        key = 'path-'+str(len(paths))
        label = node.find(WPS+'cNvPr')
        commands = tuple(PathCommand(op, values) for op, values in [('move', (x, y)), ('line', (x+w, y)),
                         ('line', (x+w, y+h)), ('line', (x, y+h)), ('close', ())])
        paths.append(VectorPath(key, commands, fill=fill_paint,
                                extra={'docx_name': label.get('name', key) if label is not None else key}))
        return key

    viewport = drawing.find(WP+'extent')
    width, height = number(viewport, 'cx'), number(viewport, 'cy')
    data = drawing.find(A+'graphic/'+A+'graphicData')
    root = data[0] if data is not None and len(data) == 1 else None
    if root is None:
        raise ValueError('Missing native group root')
    if drawing.tag == WP+'anchor':
        if (drawing.find(WP+'wrapNone') is None or any(
                drawing.find(WP+'position'+axis) is None
                or drawing.find(WP+'position'+axis).get('relativeFrom') != 'page'
                or drawing.find(WP+'position'+axis+'/'+WP+'posOffset') is None for axis in ('H', 'V'))):
            raise ValueError('Native group requires measured page-relative anchor coordinates')
    if root.tag == WPC+'wpc':
        background, whole = root.find(WPC+'bg'), root.find(WPC+'whole')
        if background is None or len(background) != 1 or whole is None:
            raise ValueError('Canvas background/outline is outside the verified profile')
        if any(child.tag != A+'ln' or child.find(A+'noFill') is None for child in whole):
            raise ValueError('Canvas stroke/effect needs a verified native projection')
        canvas_background = None
        if background[0].tag == A+'solidFill':
            commands = tuple(PathCommand(op, values) for op, values in [('move', (0., 0.)), ('line', (width, 0.)),
                             ('line', (width, height)), ('line', (0., height)), ('close', ())])
            canvas_background = 'canvas-background'
            paths.append(VectorPath(canvas_background, commands, fill=paint(background[0]),
                                    extra={'docx_canvas_background': True}))
        elif background[0].tag != A+'noFill':
            raise ValueError('Canvas background requires an explicit supported fill')
        matrix = AffineTransform()
        allowed = {WPC+'bg', WPC+'whole', WPS+'wsp', WPG+'wgp'}
        paint_tags = {WPS+'wsp', WPG+'wgp'}
    else:
        canvas_background = None
        frame, matrix = transform(root.find(WPG+'grpSpPr'), group=True)
        if frame.x or frame.y or abs(frame.width-width) > .0001 or abs(frame.height-height) > .0001:
            raise ValueError('Native group viewport differs from its drawing frame')
        allowed = {WPG+n for n in ('cNvPr', 'cNvGrpSpPr', 'grpSpPr', 'grpSp')} | {WPS+'wsp'}
        paint_tags = {WPG+'grpSp', WPS+'wsp'}
    if any(c.tag not in allowed for c in root):
        raise ValueError('Unsupported native group viewport member')
    roots = tuple(visit(child, 1, matrix) for child in root if child.tag in paint_tags)
    if canvas_background is not None:
        roots = (canvas_background, *roots)
    return VectorScene(identifier, width, height, paths=tuple(paths), groups=tuple(groups), roots=roots,
                       node_id=node_id, scope_version=1)
