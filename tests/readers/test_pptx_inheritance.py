"""Own master/layout/slide originals, shared identities and source replay isolation."""

from dataclasses import replace
from zipfile import ZIP_DEFLATED, ZipFile

import opendoc_model as od
import pytest
from lxml import etree
from pptx import Presentation
from pptx.util import Inches

from opendoc_formats import ExportOptions, ImportOptions, PptxProfile, read_document, write_document
from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.readers.pptx import read_pptx_model
from opendoc_formats.readers.pptx_inheritance import KEY

P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'


def own_pptx(tmp_path, *, slides=2, slide_flag=None, layout_flag=None, master_text='', hidden=None, malformed=False):
    source = tmp_path/'own-inheritance.pptx'
    native = Presentation()
    for index in range(slides):
        slide = native.slides.add_slide(native.slide_layouts[6])
        shape = slide.shapes.add_textbox(Inches(3), Inches(3), Inches(4), Inches(1))
        shape.text = f'Own slide {index+1}'
        shape._element.find(P+'nvSpPr/'+P+'cNvPr').set('id', '990')
    native.save(source)
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    for name, flag in [('ppt/slides/slide1.xml', slide_flag), ('ppt/slideLayouts/slideLayout7.xml', layout_flag)]:
        if flag is not None:
            root = etree.fromstring(parts[name])
            root.set('showMasterSp', flag)
            parts[name] = etree.tostring(root)
    for name, color, text, x in [('ppt/slideMasters/slideMaster1.xml', '7A3E9D', master_text, 731520),
                                 ('ppt/slideLayouts/slideLayout7.xml', '338855', 'Own layout', 2194560)]:
        root = etree.fromstring(parts[name])
        shape = etree.fromstring(f'''<p:sp xmlns:p="{P[1:-1]}" xmlns:a="{A[1:-1]}">
          <p:nvSpPr><p:cNvPr id="990" name="Own inherited square"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
          <p:spPr><a:xfrm><a:off x="{x}" y="914400"/><a:ext cx="1097280" cy="1097280"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
          <a:ln><a:noFill/></a:ln></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>''')
        if text:
            run = etree.SubElement(shape.find(P+'txBody/'+A+'p'), A+'r')
            etree.SubElement(run, A+'t').text = text
        if hidden is not None:
            shape.find(P+'nvSpPr/'+P+'cNvPr').set('hidden', hidden)
        if malformed:
            shape.find(P+'spPr/'+A+'xfrm').remove(shape.find(P+'spPr/'+A+'xfrm/'+A+'ext'))
        root.find(P+'cSld/'+P+'spTree').append(shape)
        parts[name] = etree.tostring(root)
    with ZipFile(source, 'w', ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return source


def inherited(document, slide=0):
    return [block for block in document.sections[slide].blocks if block.properties.get(KEY)]


@pytest.mark.parametrize('slide_flag,layout_flag,scopes', [(None, None, ['master', 'layout']),
                                                         ('true', '1', ['master', 'layout']),
                                                         ('false', None, []), ('0', 'true', []),
                                                         (None, 'false', ['layout']), (None, '0', ['layout'])])
def test_visibility_layer_order_physical_provenance_and_shared_ids(tmp_path, slide_flag, layout_flag, scopes):
    source = own_pptx(tmp_path, slide_flag=slide_flag, layout_flag=layout_flag, master_text='Own master')
    before = source.read_bytes()
    model = read_pptx_model(source)
    assert [b.properties[KEY]['scope'] for b in inherited(model)] == scopes
    assert [b.properties[KEY]['scope'] for b in inherited(model, 1)] == (
        ['master', 'layout'] if layout_flag not in ('false', '0') else ['layout'])
    for block in inherited(model):
        info = block.properties[KEY]
        assert info['object_id'] == block.provenance.object_id == '990'
        assert info['owner_part'] == block.provenance.package_part
        assert info['consumer_part'] == '/ppt/slides/slide1.xml' and block.provenance.page == 1
        assert block.box.width == block.box.height == 86.4
    assert model.sections[0].blocks[-1].plain_text == 'Own slide 1'
    assert model.sections[0].provenance.package_part == '/ppt/slides/slide1.xml'
    assert source.read_bytes() == before


@pytest.mark.parametrize('mode', ['rebuild', 'source'])
def test_two_cycles_preserve_materialized_shape_and_text_relative_to_original(tmp_path, mode):
    source = own_pptx(tmp_path, slides=2, master_text='Own shared master')
    original = source.read_bytes()
    model = read_pptx_model(source)
    assert len(inherited(model)) == 2
    for cycle in range(2):
        model = od.document_from_json(od.document_to_json(model))
        before = od.document_to_json(model)
        target = tmp_path/f'{mode}-{cycle}.pptx'
        report = write_document(model, target, options=ExportOptions(pptx_profile=PptxProfile(layout=mode)))
        assert report.success, report.issues
        assert od.document_to_json(model) == before
        actual = Presentation(target)
        assert len(actual.slides) == 2
        if mode == 'source':
            with ZipFile(source) as old, ZipFile(target) as new:
                assert set(old.namelist()) == set(new.namelist())
                assert all(old.read(name) == new.read(name) for name in old.namelist())
        else:
            for slide in actual.slides:
                assert len(slide.shapes) == 3
                assert slide.shapes[0].text == 'Own shared master'
                assert slide.shapes[1].text == 'Own layout'
                assert str(slide.shapes[0].fill.fore_color.rgb) == '7A3E9D'
                assert str(slide.shapes[1].fill.fore_color.rgb) == '338855'
                assert slide.shapes[0].left == 731520 and slide.shapes[0].width == 1097280
        model = read_pptx_model(target)
    assert source.read_bytes() == original


@pytest.mark.parametrize('edit', ['text', 'box', 'marker'])
def test_source_shared_owner_edit_refuses_and_does_not_bind_colliding_local_id(tmp_path, edit):
    source = own_pptx(tmp_path, master_text='Own shared master')
    model = read_pptx_model(source)
    block = inherited(model)[0]
    if edit == 'text':
        block.content[0].text = 'Own per-slide edit'
    elif edit == 'box':
        block.box.x += 10
    else:
        del block.properties[KEY]
    target = tmp_path/'existing.pptx'
    target.write_bytes(b'previous result')
    report = write_document(model, target, options=ExportOptions(pptx_profile=PptxProfile(layout='source')))
    assert not report.success and target.read_bytes() == b'previous result'


def test_local_source_edits_remain_bound_when_ids_collide_with_master_and_layout(tmp_path):
    source = own_pptx(tmp_path, master_text='Own shared master')
    model = read_pptx_model(source)
    local = model.sections[0].blocks[-1]
    local.content[0].text = 'Own local edit'
    local.box.x += 10
    target = tmp_path/'local-edit.pptx'
    report = write_document(model, target, options=ExportOptions(pptx_profile=PptxProfile(layout='source')))
    assert report.success, report.issues
    with ZipFile(source) as old, ZipFile(target) as new:
        changed = [name for name in old.namelist() if old.read(name) != new.read(name)]
        assert changed == ['ppt/slides/slide1.xml']
    assert Presentation(target).slides[0].shapes[0].text == 'Own local edit'


@pytest.mark.parametrize('hidden', ['true', '1'])
def test_hidden_ordinary_shapes_are_not_materialized(tmp_path, hidden):
    assert not inherited(read_pptx_model(own_pptx(tmp_path, hidden=hidden)))


@pytest.mark.parametrize('field', ['slide_flag', 'layout_flag', 'hidden'])
def test_invalid_boolean_refuses_instead_of_guessing(tmp_path, field):
    with pytest.raises(InvalidDocumentError, match='invalid .*boolean'):
        read_document(own_pptx(tmp_path, **{field: 'unknown'}))


def test_unsupported_inherited_shape_has_owner_xpath_identity_and_consumer_diagnostic(tmp_path):
    model = read_pptx_model(own_pptx(tmp_path, malformed=True))
    records = [r for r in od.get_integration(model).preservation if r.issue.reason == 'incomplete-local-frame']
    assert len(records) == 4
    for record in records:
        assert record.provenance.object_id == '990'
        assert '#xpath=' in record.issue.location
        assert record.provenance.package_part in record.issue.location
        assert record.issue.measurement['consumer_part'].startswith('/ppt/slides/slide')


def test_expansion_uses_one_work_budget_across_all_consumers_before_shape_conversion(tmp_path, monkeypatch):
    from opendoc_formats.readers import pptx
    source = own_pptx(tmp_path, slides=100)
    calls = 0
    real = pptx._collect_shape_element
    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)
    monkeypatch.setattr(pptx, '_collect_shape_element', counted)
    budget = replace(od.DocumentLimits(), max_nodes=10000)
    result = read_document(source, options=ImportOptions(document_limits=budget))
    assert not result.success
    issue = next(issue for issue in result.issues if issue.reason == 'document-limit')
    assert issue.measurement['maximum'] == 10000
    assert 'inherited' in issue.message and calls > 0



def rewrite(source, change):
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    change(parts)
    with ZipFile(source, 'w', ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def test_inherited_hyperlink_uses_master_relationships_without_network_access(tmp_path):
    source = own_pptx(tmp_path, master_text='Own master link')
    def change(parts):
        name = 'ppt/slideMasters/slideMaster1.xml'
        root = etree.fromstring(parts[name])
        shape = root.find(P+'cSld/'+P+'spTree')[-1]
        run = shape.find(P+'txBody/'+A+'p/'+A+'r')
        properties = etree.Element(A+'rPr')
        etree.SubElement(properties, A+'hlinkClick', {'{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id':
                                                    'rIdOwnInheritedLink'})
        run.insert(0, properties)
        parts[name] = etree.tostring(root)
        name = 'ppt/slideMasters/_rels/slideMaster1.xml.rels'
        root = etree.fromstring(parts[name])
        etree.SubElement(root, REL+'Relationship', Id='rIdOwnInheritedLink',
                         Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink',
                         Target='https://example.invalid/own-inherited', TargetMode='External')
        parts[name] = etree.tostring(root)
    rewrite(source, change)
    model = read_pptx_model(source)
    for index in [0, 1]:
        assert inherited(model, index)[0].content[0].link == 'https://example.invalid/own-inherited'


def own_master_group(source):
    def change(parts):
        name = 'ppt/slideMasters/slideMaster1.xml'
        root = etree.fromstring(parts[name])
        tree = root.find(P+'cSld/'+P+'spTree')
        shape = tree[-1]
        group = etree.fromstring(f'''<p:grpSp xmlns:p="{P[1:-1]}" xmlns:a="{A[1:-1]}">
          <p:nvGrpSpPr><p:cNvPr id="991" name="Own inherited group"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
          <p:grpSpPr><a:xfrm><a:off x="914400" y="914400"/><a:ext cx="1828800" cy="1828800"/>
          <a:chOff x="0" y="0"/><a:chExt cx="914400" cy="914400"/></a:xfrm></p:grpSpPr></p:grpSp>''')
        group.append(shape)
        tree.append(group)
        parts[name] = etree.tostring(root)
    rewrite(source, change)


def test_inherited_group_applies_frame_before_child_and_keeps_physical_identity(tmp_path):
    source = own_pptx(tmp_path)
    own_master_group(source)
    model = read_pptx_model(source)
    master = inherited(model)[0]
    assert master.box.x == pytest.approx(187.2) and master.box.y == 216
    assert master.box.width == master.box.height == pytest.approx(172.8)
    assert master.properties['pptx']['groups'][0]['id'] == '991'
    assert master.provenance.object_id == '990'
    assert any(r.issue.reason == 'flattened-inherited-group' and r.issue.measurement['consumer_part']
               for r in od.get_integration(model).preservation)


def test_cancel_during_inherited_conversion_keeps_source_and_existing_export(tmp_path, monkeypatch):
    from opendoc_formats.readers import pptx
    source = own_pptx(tmp_path)
    before = source.read_bytes()
    stopped = False
    real = pptx._collect_shape_element
    def cancel(*args, **kwargs):
        nonlocal stopped
        result = real(*args, **kwargs)
        stopped = True
        return result
    monkeypatch.setattr(pptx, '_collect_shape_element', cancel)
    from opendoc_formats.errors import OperationCancelledError
    with pytest.raises(OperationCancelledError):
        read_pptx_model(source, cancelled=lambda: stopped)
    assert source.read_bytes() == before
    monkeypatch.setattr(pptx, '_collect_shape_element', real)
    model = read_pptx_model(source)
    destination = tmp_path/'previous.pptx'
    destination.write_bytes(b'previous result')
    options = ExportOptions(quality_gate=lambda report, staged: False)
    result = write_document(model, destination, options=options)
    assert not result.success and destination.read_bytes() == b'previous result'
    result = write_document(model, destination, options=ExportOptions(cancelled=lambda: True))
    assert not result.success and destination.read_bytes() == b'previous result'



def own_master_picture(source):
    import struct
    import zlib
    from io import BytesIO
    def chunk(tag, data):
        return struct.pack('>I', len(data))+tag+data+struct.pack('>I', zlib.crc32(tag+data))
    image = (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0))
             +chunk(b'IDAT', zlib.compress((b'\0'+b'\x12\x45\x78'*2)*2))+chunk(b'IEND', b''))
    native = Presentation(source)
    native.slides[0].shapes.add_picture(BytesIO(image), Inches(5), Inches(1), Inches(1), Inches(1))
    native.save(source)
    def change(parts):
        slide = etree.fromstring(parts['ppt/slides/slide1.xml'])
        tree = slide.find(P+'cSld/'+P+'spTree')
        picture = tree[-1]
        tree.remove(picture)
        r = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
        fill = picture.find(P+'blipFill/'+A+'blip')
        old_rid = fill.get(r+'embed')
        fill.set(r+'embed', 'rIdOwnInheritedMedia')
        rels = etree.fromstring(parts['ppt/slides/_rels/slide1.xml.rels'])
        edge = next(node for node in rels if node.get('Id') == old_rid)
        rels.remove(edge)
        edge.set('Id', 'rIdOwnInheritedMedia')
        master = etree.fromstring(parts['ppt/slideMasters/slideMaster1.xml'])
        master.find(P+'cSld/'+P+'spTree').append(picture)
        master_rels = etree.fromstring(parts['ppt/slideMasters/_rels/slideMaster1.xml.rels'])
        master_rels.append(edge)
        for name, root in [('ppt/slides/slide1.xml', slide), ('ppt/slides/_rels/slide1.xml.rels', rels),
                           ('ppt/slideMasters/slideMaster1.xml', master),
                           ('ppt/slideMasters/_rels/slideMaster1.xml.rels', master_rels)]:
            parts[name] = etree.tostring(root)
    rewrite(source, change)
    return image


def test_inherited_picture_uses_physical_owner_resource_and_rebuilds_without_substitution(tmp_path):
    source = own_pptx(tmp_path)
    image = own_master_picture(source)
    model = read_pptx_model(source)
    for cycle in range(2):
        model = od.document_from_json(od.document_to_json(model))
        for section in model.sections:
            picture = next(block for block in section.blocks if isinstance(block, od.Image))
            assert model.resources[picture.resource_id].data == image
            assert model.resources[picture.resource_id].provenance.package_part == '/ppt/media/image1.png'
        target = tmp_path/f'image-{cycle}.pptx'
        assert write_document(model, target).success
        for slide in Presentation(target).slides:
            picture = next(shape for shape in slide.shapes if shape.shape_type == 13)
            assert picture.image.blob == image
        model = read_pptx_model(target)
