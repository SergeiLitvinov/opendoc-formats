"""Chart-local themes/color maps override the consumer context without changing nearby objects."""

from copy import deepcopy
from threading import Event
from types import SimpleNamespace

import pytest
from lxml import etree
from opendoc_model import ArtifactLimitError, DocumentLimits, document_from_json, document_to_json
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.dml import MSO_THEME_COLOR_INDEX
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI
from pptx.util import Pt

from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.pptx_theme_colors import A, C, P, theme_context
from tests.readers.test_pptx_theme_colors import own_theme

CASES = [('chart-theme', '#A06020', ['#228866']), ('chart-map', '#A06020', ['#4060A0']),
         ('combined', '#A06020', ['#8844AA']), ('consumer-map', '#4060A0', ['#8844AA']),
         ('chart-map-priority', '#4060A0', ['#228866']),
         ('two-charts', '#A06020', ['#228866', '#8844AA']),
         ('inherited-chart', '#4060A0', ['#228866']),
         ('layout-chart', '#4060A0', ['#228866']),
         ('layout-owner-map', '#A06020', ['#8844AA'])]


def own_chart_theme(folder, case):
    parent = ('layout-map' if case == 'layout-owner-map' else
              'slide-map' if case in ('consumer-map', 'chart-map-priority', 'inherited-chart', 'layout-chart') else 'master')
    source = own_theme(folder, parent, chart=True)
    presentation = Presentation(source)
    slide = presentation.slides[0]
    master = slide.slide_layout.slide_master
    if case == 'layout-owner-map':
        for previous in slide._element.findall(P+'clrMapOvr'):
            slide._element.remove(previous)
        override = etree.SubElement(slide._element, P+'clrMapOvr')
        etree.SubElement(override, A+'overrideClrMapping', **dict(master._element.find(P+'clrMap').attrib))
    scheme = etree.fromstring(master.part.part_related_by(RT.THEME).blob).find(A+'themeElements/'+A+'clrScheme')
    charts = [shape for shape in slide.shapes if shape.has_chart]
    if case == 'two-charts':
        charts[0].left, charts[0].width = Pt(30), Pt(300)
        data = CategoryChartData()
        data.categories = ['Own A', 'Own B']
        data.add_series('Own second series', [1, 2])
        second = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Pt(350), Pt(120), Pt(300), Pt(300), data)
        second.chart.series[0].format.fill.solid()
        second.chart.series[0].format.fill.fore_color.theme_color = MSO_THEME_COLOR_INDEX.ACCENT_2
        charts.append(second)
    for index, shape in enumerate(charts):
        if case != 'chart-map':
            override = etree.Element(A+'themeOverride', nsmap={'a': A[1:-1]})
            colors = deepcopy(scheme)
            for key, value in [('accent2', '8844AA' if index == 1 else '228866'), ('accent3', '8844AA')]:
                node = colors.find(A+key)
                node.clear()
                etree.SubElement(node, A+'srgbClr', val=value)
            override.append(colors)
            part = Part(PackURI(f'/ppt/theme/ownChartOverride{index+1}.xml'),
                        'application/vnd.openxmlformats-officedocument.themeOverride+xml',
                        presentation.part.package, etree.tostring(override))
            shape.chart.part.relate_to(part, RT.THEME_OVERRIDE)
        if case in ('chart-map', 'combined', 'chart-map-priority'):
            root = shape.chart.part._element
            mapping = etree.Element(C+'clrMapOvr', **dict(master._element.find(P+'clrMap').attrib))
            mapping.set('accent2', 'accent2' if case == 'chart-map-priority' else 'accent3')
            root.insert(root.index(root.find(C+'chart')), mapping)
    if case in ('inherited-chart', 'layout-chart', 'layout-owner-map'):
        shape = charts[0]
        owner = master if case == 'inherited-chart' else slide.slide_layout
        inherited = deepcopy(shape._element)
        inherited.find('.//'+P+'cNvPr').set('id', '1002')
        related = owner.part.relate_to(shape.chart.part, RT.CHART)
        inherited.find('.//'+C+'chart').set('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id', related)
        owner._element.find(P+'cSld/'+P+'spTree').append(inherited)
        old = next(rel for rel in slide.part.rels.values() if rel.reltype == RT.CHART)
        slide.part.drop_rel(old.rId)
        shape._element.getparent().remove(shape._element)
    presentation.save(source)
    return source


def chart_colors(model):
    return [series['color'] for block in model.sections[0].blocks
            for series in block.properties.get('pptx', {}).get('chart', {}).get('series', [])]


@pytest.mark.parametrize('case,text,expected', CASES)
def test_local_chart_context_and_neighbour_text_survive_two_cycles(tmp_path, case, text, expected):
    source = own_chart_theme(tmp_path, case)
    original = source.read_bytes()
    model = read_document(source).document
    for index in range(2):
        assert chart_colors(model) == expected
        runs = [run for block in model.sections[0].blocks if not block.properties.get('pptx', {}).get('chart')
                for run in block.content if getattr(run, 'style', None) and run.style.color]
        assert [run.style.color.to_hex() for run in runs] == [text]
        target = tmp_path / f'cycle-{index}.pptx'
        report = write_document(document_from_json(document_to_json(model)), target,
                                options=ExportOptions(pptx_profile=PptxProfile(layout='rebuild')))
        assert report.success, report.issues
        model = read_document(target).document
    assert chart_colors(model) == expected and source.read_bytes() == original


def test_chart_override_charges_shared_theme_budget_before_projection(tmp_path):
    source = own_chart_theme(tmp_path, 'chart-theme')
    before = source.read_bytes()
    slide = Presentation(source).slides[0]
    chart = next(shape.chart for shape in slide.shapes if shape.has_chart)
    state = SimpleNamespace(inheritance_work=0, limits=DocumentLimits(), background_theme_roots={})
    theme_context(slide, state)
    state.limits = DocumentLimits(max_nodes=state.inheritance_work)
    with pytest.raises(ArtifactLimitError, match='theme/background expansion'):
        theme_context(slide, state, chart_part=chart.part, chart_root=chart.part._element, chart_owner=slide.part)
    assert source.read_bytes() == before


def test_cancel_while_parsing_chart_local_override_keeps_source(tmp_path, monkeypatch):
    from opendoc_formats.readers import pptx_theme_colors
    from opendoc_formats.support.cancellation import cancellation_scope

    source = own_chart_theme(tmp_path, 'chart-theme')
    before = source.read_bytes()
    slide = Presentation(source).slides[0]
    chart = next(shape.chart for shape in slide.shapes if shape.has_chart)
    stop = Event()
    state = SimpleNamespace(inheritance_work=0, limits=DocumentLimits(), background_theme_roots={})
    theme_context(slide, state)
    actual = pptx_theme_colors.charge_theme

    def charge(node, state, part):
        if part.endswith('ownChartOverride1.xml'):
            stop.set()
        return actual(node, state, part)

    monkeypatch.setattr(pptx_theme_colors, 'charge_theme', charge)
    with pytest.raises(OperationCancelledError), cancellation_scope(stop.is_set, 'own chart theme'):
        theme_context(slide, state, chart_part=chart.part, chart_root=chart.part._element, chart_owner=slide.part)
    assert source.read_bytes() == before
