"""Editable page-positioned Word text boxes on the native drawing layer."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

from opendoc_model import Box, IssueSeverity, Paragraph, TextRun
from opendoc_model.units import degrees_to_ooxml_angle

from opendoc_formats.ooxml.package import points_to_emu

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
WP = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
WPS = '{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}'
MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'
MARKER = 'docx_positioned_textbox'


def _native_box(source: Paragraph, *, pdf: bool) -> Box:
    box = source.box
    if box is None or min(box.width, box.height) <= 0:
        raise ValueError('Positioned text requires a positive Box')
    if not pdf or source.properties.get('pdf_text_origin') is None:
        return box
    from opendoc_formats.fonts.word_metrics import word_line_ascent

    runs = [item for item in source.content if isinstance(item, TextRun) and item.text]
    ascents = [word_line_ascent(run.style) for run in runs]
    if not ascents or any(ascent is None for ascent in ascents):
        raise ValueError('Positioned PDF text requires resolved font metrics')
    ascent = max(value + run.style.properties.get('docx_run_position_pt', 0) for run, value in zip(runs, ascents))
    origin = source.properties['pdf_text_origin']
    angle = math.radians(box.rotation)
    center_x, center_y = box.width / 2, box.height / 2
    # DrawingML rotates around the shape center; map the measured text cursor.
    dx, dy = -center_x, ascent - center_y
    x = origin[0] - center_x - (math.cos(angle) * dx - math.sin(angle) * dy)
    y = origin[1] - center_y - (math.sin(angle) * dx + math.cos(angle) * dy)
    return Box(x, y, box.width, box.height, box.rotation)


def create_positioned_text(
    container: Any, source: Paragraph, report: Any, location: str, *, pdf: bool,
) -> Any:
    from docx.oxml import OxmlElement, parse_xml
    from docx.text.paragraph import Paragraph as NativeParagraph

    wrapper = container.add_paragraph()
    try:
        box = _native_box(source, pdf=pdf)
        values = (box.x, box.y, box.width, box.height, box.rotation)
        if any(not math.isfinite(value) or abs(value) > 1_000_000 for value in values):
            raise ValueError('Positioned text exceeds native geometry limits')
        identifier = wrapper.part.next_id
        level = int(source.properties.get('docx_drawing_relative_height', 0))
        if not 0 <= level < 2**32:
            raise ValueError('Invalid native text drawing order')
        xml = f'''<w:r xmlns:w="{W[1:-1]}" xmlns:wp="{WP[1:-1]}" xmlns:a="{A[1:-1]}" xmlns:wps="{WPS[1:-1]}">
          <w:drawing><wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0"
            relativeHeight="{level}" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">
            <wp:simplePos x="0" y="0"/>
            <wp:positionH relativeFrom="page"><wp:posOffset>{points_to_emu(box.x)}</wp:posOffset></wp:positionH>
            <wp:positionV relativeFrom="page"><wp:posOffset>{points_to_emu(box.y)}</wp:posOffset></wp:positionV>
            <wp:extent cx="{points_to_emu(box.width)}" cy="{points_to_emu(box.height)}"/>
            <wp:wrapNone/><wp:docPr id="{identifier}" name="OpenDoc positioned text {identifier}"/>
            <wp:cNvGraphicFramePr/>
            <a:graphic><a:graphicData uri="{WPS[1:-1]}"><wps:wsp><wps:cNvSpPr txBox="1"/>
              <wps:spPr><a:xfrm rot="{degrees_to_ooxml_angle(box.rotation)}"><a:off x="0" y="0"/>
                <a:ext cx="{points_to_emu(box.width)}" cy="{points_to_emu(box.height)}"/></a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln>
              </wps:spPr><wps:txbx><w:txbxContent><w:p/></w:txbxContent></wps:txbx>
              <wps:bodyPr rot="0" vert="horz" wrap="none" lIns="0" rIns="0" tIns="0" bIns="0"
                anchor="t" anchorCtr="0" vertOverflow="overflow" horzOverflow="overflow"><a:noAutofit/></wps:bodyPr>
            </wps:wsp></a:graphicData></a:graphic>
          </wp:anchor></w:drawing></w:r>'''
        run = parse_xml(xml)
        wrapper._p.append(run)
        # The anchor paragraph must not consume a normal text line per object.
        spacing = OxmlElement('w:spacing')
        for key, value in [('before', '0'), ('after', '0'), ('line', '20'), ('lineRule', 'exact')]:
            spacing.set(W + key, value)
        wrapper._p.get_or_add_pPr().append(spacing)
        inner = next(run.iter(W + 'txbxContent')).find(W + 'p')
        return NativeParagraph(inner, wrapper._parent)
    except (ValueError, TypeError, OverflowError) as error:
        report.add(IssueSeverity.ERROR, 'docx.positioned-text', str(error), location)
        return wrapper


def positioned_text_source(paragraph: Any) -> tuple[Any, Box, int] | None:
    from docx.text.paragraph import Paragraph as NativeParagraph

    anchors = list(paragraph._p.iter(WP + 'anchor'))
    if len(anchors) != 1:
        return None
    anchor = anchors[0]
    name = anchor.find(WP + 'docPr')
    if name is None or not name.get('name', '').startswith('OpenDoc positioned text '):
        return None
    contents = list(anchor.iter(W + 'txbxContent'))
    if len(contents) != 1 or len(contents[0]) != 1 or contents[0][0].tag != W + 'p':
        raise ValueError('Unknown positioned text content')
    body = next(anchor.iter(WPS + 'bodyPr'), None)
    geometry = next(anchor.iter(WPS + 'spPr'), None)
    if (body is None or geometry is None or body.get('wrap') != 'none' or body.get('anchor', 't') != 't'
            or any(int(body.get(key, '0')) != 0 for key in ('lIns', 'rIns', 'tIns', 'bIns'))
            or geometry.find(A + 'noFill') is None or anchor.find(WP + 'wrapNone') is None
            or anchor.get('simplePos', '0') != '0'):
        raise ValueError('Unknown positioned text wrapping, inset or fill')
    if anchor.get('behindDoc', '0') != '0':
        raise ValueError('Unknown positioned text layer')
    # Only the finite, transparent rectangular text profile is represented.
    # Native edits outside it must not be discarded on the next export.
    allowed = {A + name for name in ('xfrm', 'prstGeom', 'noFill', 'ln')}
    outline = geometry.find(A + 'ln')
    shape = geometry.find(A + 'prstGeom')
    if (any(child.tag not in allowed for child in geometry)
            or outline is None or len(outline) != 1 or outline[0].tag != A + 'noFill'
            or shape is None or shape.get('prst') != 'rect'
            or any(len(child) for child in shape)):
        raise ValueError('Unknown positioned text shape appearance')
    fallback = _word_fallback(anchor, contents[0])
    if any(node.text for node in paragraph._p.iter(W + 't')
           if contents[0] not in node.iterancestors()
           and (fallback is None or fallback not in node.iterancestors())):
        raise ValueError('Positioned text has additional outer text')
    coordinates = []
    for axis in ('H', 'V'):
        owner = anchor.find(WP + 'position' + axis)
        if owner is None or owner.get('relativeFrom') != 'page':
            raise ValueError('Unknown positioned text coordinate space')
        coordinates.append(int(owner.findtext(WP + 'posOffset', '')) / 12700)
    extent = anchor.find(WP + 'extent')
    transforms = list(anchor.iter(A + 'xfrm'))
    if extent is None or len(transforms) != 1:
        raise ValueError('Unknown positioned text transform')
    transform = transforms[0]
    offset, size = transform.find(A + 'off'), transform.find(A + 'ext')
    if (offset is None or size is None or any(int(offset.get(key, '0')) for key in ('x', 'y'))
            or any(size.get(key) != extent.get(key) for key in ('cx', 'cy'))
            or any(transform.get(key, '0') not in {'0', 'false'} for key in ('flipH', 'flipV'))):
        raise ValueError('Unknown positioned text scale, offset or reflection')
    box = Box(*coordinates, int(extent.get('cx', '')) / 12700, int(extent.get('cy', '')) / 12700,
              int(transforms[0].get('rot', '0')) / 60000)
    return NativeParagraph(contents[0][0], paragraph._parent), box, int(anchor.get('relativeHeight', '0'))


def _word_fallback(anchor: Any, content: Any) -> Any:
    """Word adds a VML replica for pre-2010 viewers; select only proven WPS Choice."""
    choice = next((node for node in anchor.iterancestors() if node.tag == MC + 'Choice'), None)
    if choice is None:
        return None
    required = choice.get('Requires', '').split()
    owner = choice.getparent()
    if (not required or any(choice.nsmap.get(prefix) != WPS[1:-1] for prefix in required)
            or owner is None or owner.tag != MC + 'AlternateContent'
            or len(owner) != 2 or owner[0] is not choice or owner[1].tag != MC + 'Fallback'):
        raise ValueError('Unknown positioned text compatibility choice')
    fallback = owner[1]
    # Compare visible text, not XML indentation or compatibility metadata.
    native_text = ''.join(node.text or '' for node in content.iter(W + 't'))
    alternate_text = ''.join(node.text or '' for node in fallback.iter(W + 't'))
    if native_text != alternate_text:
        raise ValueError('Positioned text compatibility replica disagrees with native text')
    return fallback


def native_positioned_content_supported(node: Any) -> bool:
    paragraph = next((parent for parent in node.iterancestors() if parent.tag == W + 'p'), None)
    if paragraph is None:
        return False
    try:
        return positioned_text_source(SimpleNamespace(_p=paragraph, _parent=None)) is not None
    except (ValueError, TypeError, OverflowError):
        return False
