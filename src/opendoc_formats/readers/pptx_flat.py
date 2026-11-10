"""Flat text from the physical PPTX package in presentation order."""

from pathlib import Path
from xml.etree import ElementTree as ET

from opendoc_model import DocumentLimits

from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.native.common import read_source
from opendoc_formats.readers.pptx_package import capture_pptx_package
from opendoc_formats.support.cancellation import checkpoint
from opendoc_formats.types import Block, BlockType, DocFormat, Table, Text

_P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
_A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_TABLE_URI = 'http://schemas.openxmlformats.org/drawingml/2006/table'
_PRESENTATION_TYPE = 'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml'
_SLIDE_TYPE = 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml'


def _frame_text(frame: ET.Element) -> str:
    paragraphs = []
    for paragraph in frame.iterfind(_A + 'p'):
        checkpoint()
        pieces = []
        for child in paragraph:
            checkpoint()
            if child.tag in (_A + 'r', _A + 'fld'):
                pieces.append(child.findtext(_A + 't', default=''))
            elif child.tag == _A + 'br':
                pieces.append('\v')
        paragraphs.append(''.join(pieces))
    return '\n'.join(paragraphs)


def read_pptx_flat(source: Path, *, include_tables: bool) -> Text:
    limits = DocumentLimits()
    package, _ = capture_pptx_package(read_source(source, limits.max_bytes, None), limits=limits)

    def xml(name: str, media_type: str, tag: str) -> ET.Element:
        checkpoint()
        part = package.parts.get(name)
        if part is None or part.media_type != media_type:
            raise InvalidDocumentError(f'Invalid PPTX part or content type: {name}')
        # The physical inventory already checked this declared XML, including DTD and depth policy.
        root = ET.fromstring(part.data)
        if root.tag != tag:
            raise InvalidDocumentError(f'Invalid PPTX XML root: {name}')
        return root

    presentation = xml(package.root, _PRESENTATION_TYPE, _P + 'presentation')
    edges = {edge.id: edge.target for edge in package.relationships
             if edge.source == package.root and not edge.external and edge.relationship_type == _REL + '/slide'}
    slide_ids = presentation.findall('./' + _P + 'sldIdLst/' + _P + 'sldId')
    result = Text(source_format=DocFormat.PPTX, engine='native-pptx', pages=len(slide_ids))
    plain = []
    seen: set[str] = set()
    for page, slide_id in enumerate(slide_ids, start=1):
        target = edges.get(slide_id.get('{' + _REL + '}id', ''))
        if target is None:
            raise InvalidDocumentError('PPTX slide does not have a proved internal relationship')
        if target in seen:
            raise InvalidDocumentError(f'PPTX presentation repeats a slide part: {target}')
        seen.add(target)
        slide = xml(target, _SLIDE_TYPE, _P + 'sld')
        shapes = slide.find('./' + _P + 'cSld/' + _P + 'spTree')
        if shapes is None:
            raise InvalidDocumentError(f'PPTX slide has no shape tree: {target}')
        for shape in shapes:
            checkpoint()
            frame = shape.find(_P + 'txBody') if shape.tag == _P + 'sp' else None
            if frame is not None:
                text = _frame_text(frame).strip()
                if text:
                    result.blocks.append(Block(BlockType.PARAGRAPH, text, page=page))
                    plain.append(text)
            if include_tables and shape.tag == _P + 'graphicFrame':
                graphic = shape.find('./' + _A + 'graphic/' + _A + 'graphicData')
                if graphic is not None and graphic.get('uri') == _TABLE_URI:
                    table = graphic.find(_A + 'tbl')
                    if table is None:
                        raise InvalidDocumentError(f'PPTX table frame has no table: {target}')
                    rows = []
                    for row in table.iterfind(_A + 'tr'):
                        checkpoint()
                        cells = []
                        for cell in row.iterfind(_A + 'tc'):
                            checkpoint()
                            frame = cell.find(_A + 'txBody')
                            cells.append(_frame_text(frame) if frame is not None else '')
                        rows.append(cells)
                        plain.append(' | '.join(cells))
                    result.tables.append(Table(rows=rows, page=page))
    result.plain = '\n'.join(plain)
    return result
