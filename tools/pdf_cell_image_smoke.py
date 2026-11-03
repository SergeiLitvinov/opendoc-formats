"""Installed PDF cell-image flow without Office, Pillow, fontTools or other PDF engines."""

import hashlib
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf
from opendoc_model import (
    Box,
    DocumentModel,
    FontReference,
    Image,
    ImageCrop,
    Length,
    PageSettings,
    Paragraph,
    Resource,
    ResourceKind,
    Section,
    Table,
    TableCell,
    TableRow,
    TextRun,
    TextStyle,
    document_from_json,
    document_to_json,
    set_font_reference,
)

import opendoc_formats
from opendoc_formats import write_document


def main() -> None:
    assert 'site-packages' in Path(opendoc_formats.__file__).parts
    for name in ('fontTools', 'docx', 'lxml', 'PIL', 'numpy', 'pdfplumber', 'pypdf', 'pdf2docx'):
        assert importlib.util.find_spec(name) is None, name
    fixtures = Path(__file__).resolve().parents[1]/'tests/native/data'
    png = (fixtures/'table-image.png').read_bytes()
    assert hashlib.sha256(png).hexdigest() == '5f229f090b197209fe7703d18f3ce7a47ebb0eb2f1549e400e0748c1979372fe'
    font = (fixtures/'ligature-post3.ttf').read_bytes()
    style = TextStyle(font_family='Owned table font', font_size=Length(12))
    set_font_reference(style, FontReference('owned-font', 0))

    def text(value):
        return Paragraph([TextRun(value, style)])

    picture = Image('picture', box=Box(0, 0, 72, 72, rotation=3),
                    crop=ImageCrop(left=.1, top=.2, right=.1, bottom=.1), properties={'placement': 'inline'})
    inner = Table([TableRow([TableCell([Paragraph([picture]), text('f i')])])], properties={'grid_widths_twips': [2000]})
    outer = Table([TableRow([TableCell([inner]), TableCell([text('t i')])])],
                  properties={'grid_widths_twips': [2000, 2000]})
    model = DocumentModel(sections=[Section(blocks=[outer, text('i f')], page=PageSettings(
        width=Length(240), height=Length(300), margin_left=Length(20), margin_right=Length(20),
        margin_top=Length(20), margin_bottom=Length(20)))], resources={
            'picture': Resource('picture', ResourceKind.RASTER_IMAGE, 'image/png', png),
            'owned-font': Resource('owned-font', ResourceKind.FONT, 'font/ttf', font),
        })
    model = document_from_json(document_to_json(model))
    source = document_to_json(model)
    with TemporaryDirectory(prefix='opendoc_pdf_cell_') as directory:
        reference = None
        for cycle in range(2):
            model = document_from_json(document_to_json(model))
            target = Path(directory)/f'cell-{cycle}.pdf'
            result = write_document(model, target)
            assert result.success, result.issues
            assert document_to_json(model) == source
            with pymupdf.open(target) as pdf:
                text_value = ' '.join(''.join(page.get_text() for page in pdf).split())
                assert all(text_value.count(value) == 1 for value in ('f i', 't i', 'i f'))
                rasters = [(page, value) for page in pdf for value in page.get_image_info()]
                assert len(rasters) == 1
                page, value = rasters[0]
                matrix = pymupdf.Matrix(value['transform'])
                corners = [pymupdf.Point(x, y)*matrix for x, y in ((.1, .2), (.9, .2), (.9, .9), (.1, .9))]
                bounds = pymupdf.Rect(min(p.x for p in corners), min(p.y for p in corners),
                                     max(p.x for p in corners), max(p.y for p in corners))
                assert bounds.x0 >= 20 and bounds.x1 <= 220 and bounds.y0 >= 20 and bounds.y1 <= 280
                assert all(not (bounds & pymupdf.Rect(word[:4])).get_area() for word in page.get_text('words'))
                info = page.get_images(full=True)[0]
                pixels = pymupdf.Pixmap(pdf, info[0])
                if info[1]:
                    pixels = pymupdf.Pixmap(pixels, pymupdf.Pixmap(pdf, info[1]))
                original = pymupdf.Pixmap(png)
                assert pixels.samples == original.samples and (pixels.width, pixels.height) == (120, 180)
                rendered = [page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).samples for page in pdf]
                assert reference is None or rendered == reference
                reference = rendered
    print('Installed nested PDF cell image: crop/rotation, original RGBA pixels, text and two JSON cycles passed')


if __name__ == '__main__':
    main()
