"""Editable native background gradients: geometry, source precision and authoritative stop edits."""

from copy import deepcopy

import pytest
from lxml import etree
from opendoc_model import ColorValue, document_from_json, document_to_json
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.util import Pt

from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document
from opendoc_formats.ooxml.pptx_gradient import KEY, A

P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
CASES = ['linear', 'diagonal', 'layout-linear', 'circle', 'rect', 'shape', 'tile-flip', 'theme', 'alpha']


def own_gradient(folder, case):
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    run = slide.shapes.add_textbox(Pt(40), Pt(30), Pt(550), Pt(60)).text_frame.paragraphs[0].add_run()
    run.text, run.font.name, run.font.size = 'Own background control', 'Arial', Pt(28)
    owner = slide.slide_layout if case == 'layout-linear' else presentation.slide_master if case == 'circle' else slide
    fill = etree.Element(A+'gradFill', nsmap={'a': A[1:-1]})
    stops = etree.SubElement(fill, A+'gsLst')
    values = [(0, '226688'), (45000, '44AA66'), (100000, '8844AA')]
    if case == 'rect':
        values.insert(2, (45000, 'CC8844'))
    for index, (position, value) in enumerate(values):
        color = etree.SubElement(etree.SubElement(stops, A+'gs', pos=str(position)), A+'srgbClr', val=value)
        if case == 'alpha':
            etree.SubElement(color, A+'alpha', val=str(25000+25000*index))
    if case in ('circle', 'rect', 'shape'):
        path = etree.SubElement(fill, A+'path', path=case)
        offsets = 50000 if case == 'circle' else 25000
        etree.SubElement(path, A+'fillToRect', **{key: str(offsets) for key in ('l', 't', 'r', 'b')})
    else:
        etree.SubElement(fill, A+'lin', ang='2700000' if case == 'diagonal' else '5400000' if case == 'layout-linear' else '0',
                         scaled='0' if case == 'diagonal' else '1')
    if case == 'tile-flip':
        fill.set('flip', 'xy')
        fill.set('rotWithShape', '0')
        etree.SubElement(fill, A+'tileRect', l='10000', t='5000', r='-10000', b='-5000')
    background = etree.Element(P+'bg')
    if case == 'theme':
        theme = presentation.slide_master.part.part_related_by(RT.THEME)
        root = etree.fromstring(theme.blob)
        styles = root.find(A+'themeElements/'+A+'fmtScheme/'+A+'bgFillStyleLst')
        first = fill.find(A+'gsLst/'+A+'gs/'+A+'srgbClr')
        first.tag = A+'schemeClr'
        first.set('val', 'phClr')
        etree.SubElement(first, A+'lumMod', val='80000')
        etree.SubElement(first, A+'lumOff', val='20000')
        styles.replace(styles[1], fill)
        theme._blob = etree.tostring(root)
        reference = etree.SubElement(background, P+'bgRef', idx='1002')
        etree.SubElement(reference, A+'srgbClr', val='204060')
    else:
        props = etree.SubElement(background, P+'bgPr')
        props.append(fill)
        etree.SubElement(props, A+'effectLst')
    common = owner._element.find(P+'cSld')
    for old in common.findall(P+'bg'):
        common.remove(old)
    common.insert(0, background)
    source = folder/'original.pptx'
    presentation.save(source)
    return source


def export(model, path):
    return write_document(model, path, options=ExportOptions(pptx_profile=PptxProfile(layout='rebuild')))


@pytest.mark.parametrize('case', CASES)
def test_geometry_and_editable_stops_survive_two_json_cycles(tmp_path, case):
    source = own_gradient(tmp_path, case)
    original = source.read_bytes()
    model = read_document(source).document
    before_stops = deepcopy(model.sections[0].properties['background_gradient_colors'])
    assert KEY in model.sections[0].properties
    for index in range(2):
        model = document_from_json(document_to_json(model))
        before = document_to_json(model)
        target = tmp_path/f'cycle-{index}.pptx'
        report = export(model, target)
        assert report.success and not any('Градиент фона' in issue.message for issue in report.issues), report.issues
        assert document_to_json(model) == before
        native = Presentation(target).slides[0]._element.find(P+'cSld/'+P+'bg/'+P+'bgPr/'+A+'gradFill')
        assert native is not None and len(native.find(A+'gsLst')) == len(before_stops)
        model = read_document(target).document
        assert model.sections[0].properties['background_gradient_colors'] == before_stops
    assert source.read_bytes() == original


def test_current_color_position_and_removal_never_restore_old_stops(tmp_path):
    model = read_document(own_gradient(tmp_path, 'linear')).document
    properties = model.sections[0].properties
    stops = properties['background_gradient_colors']
    stops.pop(1)
    stops[0]['color'] = ColorValue.from_hex('#22AA66').to_dict()
    stops[1]['position'] = .6
    target = tmp_path/'edited.pptx'
    report = export(document_from_json(document_to_json(model)), target)
    assert report.success, report.issues
    current = read_document(target).document.sections[0].properties['background_gradient_colors']
    assert len(current) == 2 and current[0]['color'] == stops[0]['color'] and current[1]['position'] == .6


@pytest.mark.parametrize('none', [False, True])
def test_gradient_role_removal_ignores_unused_future_hint(tmp_path, none):
    model = read_document(own_gradient(tmp_path, 'linear')).document
    properties = model.sections[0].properties
    properties[KEY]['version'] = 999
    if none:
        properties['background_fill'] = 'none'
    else:
        del properties['background_gradient_colors']
    target = tmp_path/'removed.pptx'
    assert export(model, target).success
    assert not Presentation(target).slides[0]._element.findall('.//'+A+'gradFill')


def test_explicit_no_background_does_not_restore_old_color_in_html(tmp_path):
    from html.parser import HTMLParser

    model = read_document(own_gradient(tmp_path, 'linear')).document
    model.sections[0].properties['background_fill'] = 'none'
    target = tmp_path/'cleared.html'
    report = write_document(model, target)
    assert report.success, report.issues

    class Sections(HTMLParser):
        style = ''

        def handle_starttag(self, tag, attrs):
            if tag == 'section':
                self.style = dict(attrs).get('style', '')

    parser = Sections()
    parser.feed(target.read_text(encoding='utf-8'))
    assert 'background-color' not in parser.style


@pytest.mark.parametrize('damage', [
    'version', 'xml', 'witness', 'order', 'color', 'position', 'xml-order', 'external', 'oversize',
])
def test_invalid_active_gradient_refuses_without_replacing_target(tmp_path, damage):
    source = own_gradient(tmp_path, 'linear')
    original = source.read_bytes()
    model = read_document(source).document
    properties = model.sections[0].properties
    hint = properties[KEY]
    if damage == 'version':
        hint['version'] = 2
    elif damage == 'xml':
        hint['xml'] = '<!DOCTYPE x [<!ENTITY e SYSTEM "file:///never-read">]><x/>'
    elif damage == 'oversize':
        hint['xml'] = ' '*262145
    elif damage == 'witness':
        hint['colors'][0] = ColorValue.from_hex('#FF0000').to_dict()
    elif damage == 'order':
        properties['background_gradient_colors'].reverse()
    elif damage == 'color':
        properties['background_gradient_colors'][0]['color']['components'][0] = .123456
    elif damage == 'position':
        properties['background_gradient_colors'][0]['position'] = .000001
    else:
        node = etree.fromstring(hint['xml'].encode())
        if damage == 'xml-order':
            node.insert(0, node[-1])
        else:
            node.set('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed', 'outside')
        hint['xml'] = etree.tostring(node, encoding='unicode')
    target = tmp_path/'existing.pptx'
    target.write_bytes(b'Own previous destination')
    report = export(model, target)
    assert not report.success and any(issue.feature == 'pptx.gradient-profile' for issue in report.issues)
    assert target.read_bytes() == b'Own previous destination' and source.read_bytes() == original


@pytest.mark.parametrize('target', ['html', 'docx', 'pdf'])
def test_other_targets_report_gradient_loss_explicitly(tmp_path, target):
    from opendoc_model import ConversionReport, IssueSeverity

    from opendoc_formats.writers.color_preflight import preflight_colors

    model = read_document(own_gradient(tmp_path, 'linear')).document
    report = ConversionReport(tmp_path/('output.'+target))
    preflight_colors(model, report, target=target)
    assert any(issue.feature == 'background-gradient' and issue.severity is IssueSeverity.LOSS
               and issue.location == 'sections[0]' for issue in report.issues)


def test_cancel_inside_gradient_validation_keeps_previous_destination(tmp_path, monkeypatch):
    from threading import Event

    from opendoc_formats.ooxml import pptx_gradient

    source = own_gradient(tmp_path, 'linear')
    original = source.read_bytes()
    model = read_document(source).document
    target = tmp_path/'existing.pptx'
    target.write_bytes(b'Own previous destination')
    stop, calls = Event(), 0
    actual = pptx_gradient.checkpoint

    def checkpoint():
        nonlocal calls
        calls += 1
        if calls == 20:
            stop.set()
        actual()

    monkeypatch.setattr(pptx_gradient, 'checkpoint', checkpoint)
    report = write_document(model, target, options=ExportOptions(
        pptx_profile=PptxProfile(layout='rebuild'), cancelled=stop.is_set))
    assert not report.success and any(issue.feature == 'export.cancelled' for issue in report.issues)
    assert calls == 20 and source.read_bytes() == original and target.read_bytes() == b'Own previous destination'
