"""Actual master parts, theme overrides and consumer color maps drive every object color."""

from copy import deepcopy

import pytest
from lxml import etree
from opendoc_model import document_from_json, document_to_json, get_integration
from pptx import Presentation
from pptx.enum.dml import MSO_THEME_COLOR_INDEX
from pptx.opc.constants import CONTENT_TYPE as CT
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI
from pptx.parts.slide import SlideLayoutPart, SlideMasterPart

from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document
from opendoc_formats.readers.pptx_theme_colors import A, P
from tests.readers.test_pptx_color_modifiers import own_colors

CASES = [('master', '#A06020'), ('second-master', '#A06020'), ('layout-map', '#4060A0'),
         ('slide-map', '#4060A0'), ('slide-inherit', '#4060A0'),
         ('layout-theme', '#228866'), ('slide-theme', '#8844AA'), ('inherited-master', '#4060A0')]


def own_theme(folder, case, *, chart=False):
    source = own_colors(folder, [], chart=chart)
    presentation = Presentation(source)
    slide = presentation.slides[0]
    master = slide.slide_layout.slide_master
    if case == 'second-master':
        package = presentation.part.package
        new_master = SlideMasterPart.load(PackURI('/ppt/slideMasters/ownMaster.xml'), CT.PML_SLIDE_MASTER,
                                          package, master.part.blob)
        new_layout = SlideLayoutPart.load(PackURI('/ppt/slideLayouts/ownLayout.xml'), CT.PML_SLIDE_LAYOUT,
                                          package, slide.slide_layout.part.blob)
        original_theme = master.part.part_related_by(RT.THEME)
        theme = Part(PackURI('/ppt/theme/ownTheme.xml'), original_theme.content_type, package, original_theme.blob)
        new_master.relate_to(theme, RT.THEME)
        layout_id = new_master.relate_to(new_layout, RT.SLIDE_LAYOUT)
        entries = new_master._element.find(P+'sldLayoutIdLst')
        entries.clear()
        etree.SubElement(entries, P+'sldLayoutId', id='2147484001',
                         attrib={'{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id': layout_id})
        new_layout.relate_to(new_master, RT.SLIDE_MASTER)
        master_id = presentation.part.relate_to(new_master, RT.SLIDE_MASTER)
        etree.SubElement(presentation._element.find(P+'sldMasterIdLst'), P+'sldMasterId', id='2147484000',
                         attrib={'{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id': master_id})
        old = next(rel for rel in slide.part.rels.values() if rel.reltype == RT.SLIDE_LAYOUT)
        slide.part.drop_rel(old.rId)
        slide.part.relate_to(new_layout, RT.SLIDE_LAYOUT)
        # Reopen to avoid python-pptx's cached layout object from the authored source.
        presentation.save(source)
        presentation = Presentation(source)
        slide = presentation.slides[0]
        master = slide.slide_layout.slide_master
    theme = master.part.part_related_by(RT.THEME)
    root = etree.fromstring(theme.blob)
    scheme = root.find(A+'themeElements/'+A+'clrScheme')
    for key, value in [('accent2', 'A06020'), ('accent3', '4060A0')]:
        node = scheme.find(A+key)
        node.clear()
        etree.SubElement(node, A+'srgbClr', val=value)
    theme._blob = etree.tostring(root)
    for shape in slide.shapes:
        if shape.has_text_frame and shape.text:
            shape.text_frame.paragraphs[0].runs[0].font.color.theme_color = MSO_THEME_COLOR_INDEX.ACCENT_2
        elif shape.has_chart:
            shape.chart.series[0].format.fill.fore_color.theme_color = MSO_THEME_COLOR_INDEX.ACCENT_2
        else:
            shape.fill.fore_color.theme_color = MSO_THEME_COLOR_INDEX.ACCENT_2
    if case in ('layout-map', 'slide-map', 'slide-inherit', 'inherited-master'):
        for existing in slide._element.findall(P+'clrMapOvr'):
            slide._element.remove(existing)
        parent = slide if case == 'slide-map' else slide.slide_layout
        for existing in parent._element.findall(P+'clrMapOvr'):
            parent._element.remove(existing)
        override = etree.SubElement(parent._element, P+'clrMapOvr')
        mapping = etree.SubElement(override, A+'overrideClrMapping', **dict(master._element.find(P+'clrMap').attrib))
        mapping.set('accent2', 'accent3')
        if case == 'slide-inherit':
            etree.SubElement(etree.SubElement(slide._element, P+'clrMapOvr'), A+'masterClrMapping')
    if case in ('layout-theme', 'slide-theme'):
        override = etree.Element(A+'themeOverride', nsmap={'a': A[1:-1]})
        colors = deepcopy(scheme)
        color = colors.find(A+'accent2')
        color.clear()
        etree.SubElement(color, A+'srgbClr', val='228866' if case == 'layout-theme' else '8844AA')
        override.append(colors)
        part = Part(PackURI('/ppt/theme/ownOverride.xml'),
                    'application/vnd.openxmlformats-officedocument.themeOverride+xml',
                    presentation.part.package, etree.tostring(override))
        (slide if case == 'slide-theme' else slide.slide_layout).part.relate_to(part, RT.THEME_OVERRIDE)
    if case == 'inherited-master' and not chart:
        shape = slide.shapes[-1]._element
        inherited = deepcopy(shape)
        identity = inherited.find('.//'+P+'cNvPr')
        identity.set('id', '1001')
        identity.set('name', 'Own inherited theme square')
        master._element.find(P+'cSld/'+P+'spTree').append(inherited)
        shape.getparent().remove(shape)
    presentation.save(source)
    return source


def colors(model):
    values = []
    for block in model.sections[0].blocks:
        meta = block.properties.get('pptx', {})
        chart = meta.get('chart')
        if chart:
            values.append(chart['series'][0]['color'])
        else:
            if meta.get('shape', {}).get('fill_color'):
                values.append(meta['shape']['fill'])
            values.extend(run.style.color.to_hex() for run in block.content if getattr(run, 'style', None) and run.style.color)
    return values


@pytest.mark.parametrize('case,expected', CASES)
@pytest.mark.parametrize('chart', [False, True])
def test_actual_theme_and_color_map_survive_two_cycles(tmp_path, case, expected, chart):
    source = own_theme(tmp_path, case, chart=chart)
    original = source.read_bytes()
    model = read_document(source).document
    for cycle in range(2):
        assert colors(model) == [expected, expected]
        target = tmp_path / f'cycle-{cycle}.pptx'
        report = write_document(document_from_json(document_to_json(model)), target,
                                options=ExportOptions(pptx_profile=PptxProfile(layout='rebuild')))
        assert report.success, report.issues
        model = read_document(target).document
    assert colors(model) == [expected, expected] and source.read_bytes() == original


def test_missing_effective_theme_is_diagnosed_instead_of_guessing_colors(tmp_path):
    source = own_theme(tmp_path, 'master')
    presentation = Presentation(source)
    for part in (presentation.slide_master.part, presentation.part):
        for rel in list(part.rels.values()):
            if rel.reltype == RT.THEME:
                part.drop_rel(rel.rId)
    presentation.save(source)
    model = read_document(source).document
    assert any(record.issue.reason == 'missing-effective-color-scheme' for record in get_integration(model).preservation)


def test_two_masters_in_one_import_never_share_palette_values(tmp_path):
    from pptx.util import Pt

    source = own_theme(tmp_path, 'second-master')
    presentation = Presentation(source)
    first_master = presentation.slide_masters[0]
    root = etree.fromstring(first_master.part.part_related_by(RT.THEME).blob)
    expected = '#'+root.find(A+'themeElements/'+A+'clrScheme/'+A+'accent2/'+A+'srgbClr').get('val')
    slide = presentation.slides.add_slide(first_master.slide_layouts[6])
    run = slide.shapes.add_textbox(Pt(40), Pt(30), Pt(400), Pt(60)).text_frame.paragraphs[0].add_run()
    run.text = 'Own second palette'
    run.font.color.theme_color = MSO_THEME_COLOR_INDEX.ACCENT_2
    presentation.save(source)
    model = read_document(source).document
    assert len(model.sections) == 2
    assert model.sections[0].blocks[0].content[0].style.color.to_hex() == '#A06020'
    assert model.sections[1].blocks[0].content[0].style.color.to_hex() == expected
    assert expected != '#A06020'
