"""Known relationship types need per-object evidence, not catalogue membership."""

import zipfile

import pytest
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import parse_xml
from lxml import etree
from opendoc_model import document_from_json, document_to_json, get_integration

from opendoc_formats import read_document, write_document
from opendoc_formats.readers.docx_features import _relationship_feature


@pytest.mark.parametrize('relationship_type,feature', [
    (RT.CUSTOM_XML, 'custom_xml'), (RT.A_F_CHUNK, 'altchunk'), (RT.CHART, 'chart'),
])
@pytest.mark.parametrize('owner', ['document', 'settings', 'package', 'external'])
def test_known_profiles_distinguish_retained_graphs_from_dropped_targets(tmp_path, relationship_type, feature, owner):
    document = Document()
    document.add_paragraph('Own editable body')
    parent = document.part.part_related_by(RT.SETTINGS) if owner == 'settings' else document.part
    if owner == 'package':
        parent = document.part.package
    payload = b'<own:payload xmlns:own="urn:own:inert">Own source data</own:payload>'
    target = '/customXml/own.xml'
    if owner == 'external':
        target = 'https://example.invalid/never-fetch.xml'
        identifier = parent.relate_to(target, relationship_type, is_external=True)
    else:
        part = Part(PackURI(target), 'application/xml', payload, document.part.package)
        identifier = parent.relate_to(part, relationship_type)
    source = tmp_path/'known.docx'
    document.save(source)
    original = source.read_bytes()
    result = read_document(source)
    assert result.success and not result.assessment_complete
    kept = owner == 'settings' or (owner == 'document' and feature == 'custom_xml')
    diagnostic_part = '/_rels/.rels' if owner == 'package' else str(parent.partname)
    model = result.document
    for cycle in range(2):
        model = document_from_json(document_to_json(model))
        record, = [item for item in get_integration(model).preservation
                   if item.issue.code == 'docx.relationship.'+feature
                   and item.provenance.package_part == diagnostic_part and item.provenance.object_id == identifier]
        assert record.state.value == ('opaque' if kept else 'lost')
        assert record.issue.location == f'{source}!{diagnostic_part}#relationship={identifier}'
        assert record.issue.measurement == {'target': target, 'external': owner == 'external',
                                            'relationship_type': relationship_type}
        output = tmp_path/f'known-{cycle}.docx'
        assert write_document(model, output).success
        with zipfile.ZipFile(output) as archive:
            assert ('customXml/own.xml' in archive.namelist()) == kept
            if kept:
                assert archive.read('customXml/own.xml') == payload
                rels = 'word/_rels/settings.xml.rels' if owner == 'settings' else 'word/_rels/document.xml.rels'
                edges = etree.fromstring(archive.read(rels))
                assert any(edge.get('Id') == identifier and edge.get('Type') == relationship_type for edge in edges)
    assert source.read_bytes() == original


@pytest.mark.parametrize('relationship_type,feature', [
    (RT.CUSTOM_XML_PROPS, 'custom_xml'), (RT.CHART_USER_SHAPES, 'chart'),
    ('http://schemas.microsoft.com/office/2007/relationships/diagramDrawing', 'smartart'),
    ('https://example.invalid/customXml', 'unknown'), ('https://example.invalid/chart', 'unknown'),
])
def test_known_profile_classification_uses_full_type_uri(relationship_type, feature):
    assert _relationship_feature(relationship_type) == feature


def test_custom_xml_binding_and_dependencies_survive_two_docx_cycles(tmp_path):
    document = Document()
    document.add_paragraph('Before binding')
    identifier = '{DF1BD88E-657E-4816-A0C8-A5E542812610}'
    data = b'<x:root xmlns:x="urn:own:data"><x:value>Bound source value</x:value></x:root>'
    props = ('<ds:datastoreItem xmlns:ds="http://schemas.openxmlformats.org/officeDocument/2006/customXml" '
             f'ds:itemID="{identifier}"><ds:schemaRefs/></ds:datastoreItem>').encode()
    item = Part(PackURI('/customXml/own.xml'), 'application/xml', data, document.part.package)
    properties = Part(PackURI('/customXml/ownProps.xml'),
                      'application/vnd.openxmlformats-officedocument.customXmlProperties+xml', props, document.part.package)
    item.relate_to(properties, RT.CUSTOM_XML_PROPS)
    document.part.relate_to(item, RT.CUSTOM_XML)
    control = parse_xml(
        '<w:sdt xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:sdtPr>'
        f'<w:dataBinding w:storeItemID="{identifier}" w:xpath="/x:root/x:value" '
        'w:prefixMappings="xmlns:x=\'urn:own:data\'"/></w:sdtPr>'
        '<w:sdtContent><w:p><w:r><w:t>Bound source value</w:t></w:r></w:p></w:sdtContent></w:sdt>')
    document._element.body.insert(1, control)
    source = tmp_path/'binding.docx'
    document.save(source)
    original = source.read_bytes()
    current = source
    for cycle in range(2):
        result = read_document(current)
        assert result.success and not result.assessment_complete
        model = document_from_json(document_to_json(result.document))
        assert model.package.parts['/customXml/own.xml'].data == data
        assert model.package.parts['/customXml/ownProps.xml'].data == props
        for target in ('/customXml/own.xml', '/customXml/ownProps.xml'):
            record, = [record for record in get_integration(model).preservation
                       if record.issue.code == 'docx.relationship.custom_xml'
                       and record.issue.measurement['target'] == target]
            assert record.state.value == 'opaque'
        output = tmp_path/f'binding-{cycle}.docx'
        assert write_document(model, output).success
        with zipfile.ZipFile(output) as archive:
            assert archive.read('customXml/own.xml') == data and archive.read('customXml/ownProps.xml') == props
            xml = etree.fromstring(archive.read('word/document.xml'))
            bindings = xml.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}dataBinding')
            assert len(bindings) == 1
            assert dict(bindings[0].attrib) == dict(control.find(
                './/{http://schemas.openxmlformats.org/wordprocessingml/2006/main}dataBinding').attrib)
        current = output
    assert source.read_bytes() == original
