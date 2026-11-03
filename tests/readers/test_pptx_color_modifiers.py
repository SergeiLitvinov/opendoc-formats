"""Native DrawingML source colors must be materialized before exporting literal RGB."""

import pytest
from opendoc_model import ColorValue, document_from_json, document_to_json
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.util import Pt

from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document

A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
CASES = [('shade', [('shade', 25000)]), ('tint', [('tint', 25000)]),
         ('shade-tint', [('shade', 50000), ('tint', 50000)]),
         ('tint-shade', [('tint', 50000), ('shade', 50000)])]


def own_colors(folder, modifiers, *, chart=False):
    from lxml import etree

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])

    def color(target):
        target.rgb = RGBColor.from_string('204060')
        for name, value in modifiers:
            etree.SubElement(target._xFill.find(A+'srgbClr'), A+name, val=str(value))

    textbox = slide.shapes.add_textbox(Pt(40), Pt(30), Pt(550), Pt(60))
    run = textbox.text_frame.paragraphs[0].add_run()
    run.text = 'Own background control'
    run.font.name, run.font.size = 'Arial', Pt(28)
    color(run.font.color)
    if chart:
        data = CategoryChartData()
        data.categories = ['Own A', 'Own B']
        data.add_series('Own series', [1, 2])
        plot = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Pt(60), Pt(120), Pt(500), Pt(300), data).chart
        plot.series[0].format.fill.solid()
        color(plot.series[0].format.fill.fore_color)
    else:
        shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, Pt(60), Pt(140), Pt(400), Pt(150))
        shape.fill.solid()
        color(shape.fill.fore_color)
        shape.line.fill.background()
    source = folder / 'original.pptx'
    presentation.save(source)
    return source


@pytest.mark.parametrize('name,modifiers', CASES)
@pytest.mark.parametrize('chart', [False, True])
def test_text_and_object_color_are_stable_through_two_json_rebuild_cycles(tmp_path, name, modifiers, chart):
    source = own_colors(tmp_path, modifiers, chart=chart)
    original = source.read_bytes()
    model = read_document(source).document
    color = model.sections[0].blocks[0].content[0].style.color
    assert color is not None

    def object_color(document):
        meta = document.sections[0].blocks[1].properties['pptx']
        return meta['chart']['series'][0]['color'] if chart else meta['shape']['fill']

    assert object_color(model) == color.to_hex()
    for index in range(2):
        target = tmp_path / f'cycle-{index}.pptx'
        model = document_from_json(document_to_json(model))
        report = write_document(model, target, options=ExportOptions(pptx_profile=PptxProfile(layout='rebuild')))
        assert report.success, report.issues
        model = read_document(target).document
        assert model.sections[0].blocks[0].content[0].style.color.to_hex() == color.to_hex()
        assert object_color(model) == color.to_hex()
    assert source.read_bytes() == original


@pytest.mark.parametrize('chart', [False, True])
def test_explicit_color_edit_overrides_old_source_modifiers(tmp_path, chart):
    source = own_colors(tmp_path, [('shade', 25000)], chart=chart)
    original = source.read_bytes()
    model = read_document(source).document
    replacement = ColorValue.from_hex('#885522')
    model.sections[0].blocks[0].content[0].style.color = replacement
    meta = model.sections[0].blocks[1].properties['pptx']
    if chart:
        series = meta['chart']['series'][0]
        series['color'], series['color_value'] = replacement.to_hex(), replacement.to_dict()
    else:
        meta['shape']['fill'], meta['shape']['fill_color'] = replacement.to_hex(), replacement.to_dict()
    for index in range(2):
        target = tmp_path / f'edit-{index}.pptx'
        report = write_document(document_from_json(document_to_json(model)), target,
                                options=ExportOptions(pptx_profile=PptxProfile(layout='rebuild')))
        assert report.success, report.issues
        model = read_document(target).document
        assert model.sections[0].blocks[0].content[0].style.color.to_hex() == '#885522'
        meta = model.sections[0].blocks[1].properties['pptx']
        assert (meta['chart']['series'][0]['color'] if chart else meta['shape']['fill']) == '#885522'
    assert source.read_bytes() == original
