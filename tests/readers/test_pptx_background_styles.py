"""Independently authored DrawingML style matrices, inherited backgrounds and color maps."""

from threading import Event
from types import SimpleNamespace

import pytest
from lxml import etree
from opendoc_model import ArtifactLimitError, DocumentLimits, document_from_json, document_to_json, get_integration
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.util import Pt

from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.pptx_background import A, P, background_style


def own_background(folder, *, owner='master', index=1001, mapped=False, shade=False, style='solidFill'):
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_textbox(Pt(40), Pt(40), Pt(350), Pt(50)).text = 'Own background control'
    master = slide.slide_layout.slide_master
    theme = master.part.part_related_by(RT.THEME)
    root = etree.fromstring(theme.blob)
    scheme = root.find(A+'themeElements/'+A+'clrScheme')
    for name, color in [('accent2', 'A06020'), ('accent3', '4060A0')]:
        entry = scheme.find(A+name)
        entry.clear()
        etree.SubElement(entry, A+'srgbClr', val=color)
    matrix = root.find(A+'themeElements/'+A+'fmtScheme')
    for name in ('fillStyleLst', 'bgFillStyleLst'):
        entries = matrix.find(A+name)
        entries.clear()
        first = etree.SubElement(entries, A+'solidFill')
        etree.SubElement(first, A+'srgbClr', val='226688')
        second = etree.SubElement(entries, A+style)
        color = etree.SubElement(second, A+'schemeClr', val='phClr')
        if shade:
            etree.SubElement(color, A+'shade', val='50000')
        third = etree.SubElement(entries, A+'solidFill')
        etree.SubElement(third, A+'srgbClr', val='663399')
    theme._blob = etree.tostring(root)
    parent = {'master': master, 'layout': slide.slide_layout, 'slide': slide}[owner]
    common = parent._element.find(P+'cSld')
    for existing in common.findall(P+'bg'):
        common.remove(existing)
    background = etree.Element(P+'bg')
    reference = etree.SubElement(background, P+'bgRef', idx=str(index))
    color = etree.SubElement(reference, A+'schemeClr', val='accent2')
    if shade:
        etree.SubElement(color, A+'shade', val='50000')
    common.insert(0, background)
    if mapped:
        for existing in slide._element.findall(P+'clrMapOvr'):
            slide._element.remove(existing)
        parent = slide.slide_layout._element
        for existing in parent.findall(P+'clrMapOvr'):
            parent.remove(existing)
        override = etree.SubElement(parent, P+'clrMapOvr')
        mapping = etree.SubElement(override, A+'overrideClrMapping', **dict(master._element.find(P+'clrMap').attrib))
        mapping.set('accent2', 'accent3')
    path = folder / 'original.pptx'
    presentation.save(path)
    return path


@pytest.mark.parametrize('owner', ['master', 'layout', 'slide'])
@pytest.mark.parametrize('index,expected', [(1001, '#226688'), (1002, '#A06020'), (1, '#226688'), (2, '#A06020')])
def test_style_matrix_is_not_a_color_index_and_survives_two_cycles(tmp_path, owner, index, expected):
    source = own_background(tmp_path, owner=owner, index=index)
    original = source.read_bytes()
    model = read_document(source).document
    for cycle in range(2):
        model = document_from_json(document_to_json(model))
        assert model.sections[0].properties['background_fill'] == expected
        before = document_to_json(model)
        target = tmp_path / f'rebuild-{cycle}.pptx'
        report = write_document(model, target, options=ExportOptions(pptx_profile=PptxProfile(layout='rebuild')))
        assert report.success and document_to_json(model) == before, report.issues
        model = read_document(target).document
    assert source.read_bytes() == original


@pytest.mark.parametrize('reset,expected', [(False, '#4060A0'), (True, '#4060A0')])
def test_layout_color_map_and_slide_master_mapping_inherit_parent(tmp_path, reset, expected):
    source = own_background(tmp_path, index=1002, mapped=True)
    if reset:
        presentation = Presentation(source)
        override = presentation.slides[0]._element.find(P+'clrMapOvr')
        if override is not None:
            presentation.slides[0]._element.remove(override)
        override = etree.SubElement(presentation.slides[0]._element, P+'clrMapOvr')
        etree.SubElement(override, A+'masterClrMapping')
        presentation.save(source)
    assert read_document(source).document.sections[0].properties['background_fill'] == expected


def test_reference_then_style_color_transforms_are_composed_without_mutating_theme(tmp_path):
    source = own_background(tmp_path, index=1002, shade=True)
    before = source.read_bytes()
    assert read_document(source).document.sections[0].properties['background_fill'] == '#54300C'
    assert source.read_bytes() == before


@pytest.mark.parametrize('index', [0, 1000])
def test_explicit_no_background_blocks_master_inheritance(tmp_path, index):
    source = own_background(tmp_path, owner='slide', index=index)
    presentation = Presentation(source)
    master = presentation.slide_master
    master.background.fill.solid()
    from pptx.dml.color import RGBColor

    master.background.fill.fore_color.rgb = RGBColor(255, 0, 0)
    presentation.save(source)
    assert read_document(source).document.sections[0].properties['background_fill'] == 'none'


@pytest.mark.parametrize('index,style', [(1009, 'solidFill'), ('invalid', 'solidFill'), (1002, 'pattFill')])
def test_unprojected_background_has_physical_owner_xpath_and_consumer(tmp_path, index, style):
    source = own_background(tmp_path, index=index, style=style)
    model = read_document(source).document
    records = [record for record in get_integration(model).preservation if record.issue.code == 'pptx.background']
    assert len(records) == 1
    record = records[0]
    assert record.issue.reason == 'unsupported-background-style'
    assert record.provenance.package_part == '/ppt/slideMasters/slideMaster1.xml'
    assert '#xpath=' in record.issue.location
    assert record.issue.measurement['consumer_part'] == '/ppt/slides/slide1.xml'


def test_theme_work_and_style_copy_share_expansion_budget(tmp_path):
    source = own_background(tmp_path)
    slide = Presentation(source).slides[0]
    state = SimpleNamespace(inheritance_work=0, limits=DocumentLimits(max_nodes=1))
    with pytest.raises(ArtifactLimitError, match='background expansion'):
        background_style(slide, work_state=state)


def test_theme_is_parsed_and_charged_once_per_import_context(tmp_path):
    source = own_background(tmp_path)
    slide = Presentation(source).slides[0]
    state = SimpleNamespace(inheritance_work=0, limits=DocumentLimits(), background_theme_roots={})
    first = background_style(slide, work_state=state)
    before = state.inheritance_work
    assert len(state.background_theme_roots) == 1
    assert background_style(slide, work_state=state) == first
    assert state.inheritance_work-before == 2  # Only the selected solidFill/srgbClr copy, not the entire theme.


@pytest.mark.parametrize('name,value,expected', [
    ('tint', '0', '#FFFFFF'), ('tint', '100000', '#A06020'),
    ('shade', '0', '#000000'), ('shade', '100000', '#A06020'),
])
def test_native_color_modifier_endpoints(name, value, expected):
    from opendoc_formats.readers.pptx_background import _native_color

    node = etree.Element(A+'srgbClr', val='A06020')
    etree.SubElement(node, A+name, val=value)
    assert _native_color(node, {}).to_hex() == expected


def test_cancellation_inside_theme_work_keeps_source(tmp_path, monkeypatch):
    from opendoc_formats.readers import pptx_theme_colors
    from opendoc_formats.support.cancellation import cancellation_scope

    source = own_background(tmp_path)
    before = source.read_bytes()
    slide = Presentation(source).slides[0]
    stop = Event()
    original = pptx_theme_colors.checkpoint
    calls = 0

    def checkpoint():
        nonlocal calls
        calls += 1
        if calls == 20:
            stop.set()
        original()

    monkeypatch.setattr(pptx_theme_colors, 'checkpoint', checkpoint)
    with pytest.raises(OperationCancelledError), cancellation_scope(stop.is_set, 'own background'):
        background_style(slide)
    assert calls == 20 and source.read_bytes() == before
