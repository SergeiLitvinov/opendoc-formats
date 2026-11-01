"""Source absence, declared defaults and explicit Model edits must remain distinguishable."""

from io import BytesIO
from threading import Event
from zipfile import ZipFile

import opendoc_model as od
import pytest
from lxml import etree

from opendoc_formats import ExportOptions, read_document, write_document
from opendoc_formats.ooxml.docx_defaults import KEY, SETTINGS_KEY, W
from tests.binary_fixtures import zip_bytes
from tools.docx_whitespace_acceptance import original


def source_with_settings(content):
    data = original('absent', {}, '  A  B  ')
    with ZipFile(BytesIO(data)) as archive:
        parts = [(name, archive.read(name)) for name in archive.namelist()]
    result = []
    for name, payload in parts:
        if name == '[Content_Types].xml':
            payload = payload.replace(b'</Types>', b'<Override PartName="/word/settings.xml" '
                                      b'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
                                      b'</Types>')
        result.append((name, payload))
    result.append(('word/_rels/document.xml.rels',
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="ownSettings" '
                   'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" '
                   'Target="settings.xml"/></Relationships>'))
    result.append(('word/settings.xml', f'<w:settings xmlns:w="{W[1:-1]}">{content}</w:settings>'))
    return zip_bytes(result)


@pytest.mark.parametrize('settings', [None, '', '<w:defaultTabStop w:val="840"/>'])
def test_source_settings_absence_and_declarations_survive_two_public_cycles(tmp_path, settings):
    source = tmp_path/'source.docx'
    data = original('absent', {}, '  A  B  ') if settings is None else source_with_settings(settings)
    source.write_bytes(data)
    model = read_document(source).document
    assert model.metadata[SETTINGS_KEY]['settings_present'] == (settings is not None)
    for cycle in range(2):
        before = od.document_to_json(model)
        path = tmp_path/f'cycle-{cycle}.json'
        assert write_document(model, path).success
        model = read_document(path).document
        target = tmp_path/f'cycle-{cycle}.docx'
        report = write_document(model, target)
        assert report.success, report.issues
        assert od.document_to_json(model) == before
        with ZipFile(target) as archive:
            root = etree.fromstring(archive.read('word/settings.xml'))
        assert [node.tag for node in root] == ([] if not settings else [W+'defaultTabStop'])
        if settings:
            assert root[0].get(W+'val') == '840'
        model = read_document(target).document
    assert source.read_bytes() == data


def test_explicit_even_page_settings_take_priority_over_source_absence(tmp_path):
    source = tmp_path/'source.docx'
    source.write_bytes(original('absent', {}, 'Own'))
    model = read_document(source).document
    model.sections[0].properties['odd_and_even_pages_header_footer'] = True
    before = od.document_to_json(model)
    target = tmp_path/'even.docx'
    report = write_document(model, target)
    assert report.success, report.issues
    assert od.document_to_json(model) == before
    with ZipFile(target) as archive:
        root = etree.fromstring(archive.read('word/settings.xml'))
    assert [node.tag for node in root] == [W+'evenAndOddHeaders']
    assert read_document(target).document.sections[0].properties.odd_and_even_pages_header_footer


@pytest.mark.parametrize('state', [False, {}, {'format': SETTINGS_KEY, 'version': True, 'settings_present': False},
                                  {'format': SETTINGS_KEY, 'version': 2, 'settings_present': False}])
def test_invalid_settings_profile_refuses_without_changing_destination(tmp_path, state):
    model = od.DocumentModel(metadata={SETTINGS_KEY: state})
    target = tmp_path/'written.docx'
    target.write_bytes(b'previous output')
    report = write_document(model, target)
    assert not report.success and any(issue.feature == 'docx.settings' for issue in report.issues)
    assert target.read_bytes() == b'previous output'


def test_settings_namespace_qnames_and_nested_payload_relationship_survive(tmp_path):
    xml = (f'<w:settings xmlns:w="{W[1:-1]}" xmlns:own="urn:own-settings" '
           'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" mc:Ignorable="own">'
           '<own:blob r:id="ownPayload"/></w:settings>')
    with ZipFile(BytesIO(source_with_settings(''))) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts['[Content_Types].xml'] = parts['[Content_Types].xml'].replace(
        b'</Types>', b'<Default Extension="bin" ContentType="application/octet-stream"/></Types>')
    parts['word/settings.xml'] = xml.encode()
    parts['word/own.bin'] = b'own inert payload'
    parts['word/_rels/settings.xml.rels'] = (
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="ownPayload" Type="urn:own-payload" Target="own.bin"/></Relationships>')
    source = tmp_path/'source.docx'
    data = zip_bytes(parts.items())
    source.write_bytes(data)
    model = read_document(source).document
    assert model.package.parts['/word/own.bin'].data == b'own inert payload'
    before = od.document_to_json(model)
    target = tmp_path/'retained.docx'
    report = write_document(model, target)
    assert report.success, report.issues
    assert od.document_to_json(model) == before
    with ZipFile(target) as archive:
        root = etree.fromstring(archive.read('word/settings.xml'))
        assert root.nsmap['own'] == 'urn:own-settings'
        assert root.get('{http://schemas.openxmlformats.org/markup-compatibility/2006}Ignorable') == 'own'
        assert archive.read('word/own.bin') == b'own inert payload'
    imported = read_document(target).document
    assert imported.package.parts['/word/own.bin'].data == b'own inert payload'
    assert any(edge.source == '/word/settings.xml' and edge.id == 'ownPayload' for edge in imported.package.relationships)
    assert source.read_bytes() == data


@pytest.mark.parametrize('damage', ['doctype', 'nodes', 'wrong-root'])
def test_source_settings_xml_policy_budget_and_root_are_checked_atomically(tmp_path, damage):
    from dataclasses import replace

    source = tmp_path/'source.docx'
    source.write_bytes(source_with_settings(''))
    model = read_document(source).document
    part = model.package.parts['/word/settings.xml']
    if damage == 'doctype':
        data = b'<!DOCTYPE settings [<!ENTITY own "untrusted">]>'+part.data
    elif damage == 'nodes':
        data = f'<w:settings xmlns:w="{W[1:-1]}">'.encode()+b'<w:zoom/>'*1000+b'</w:settings>'
    else:
        data = f'<w:styles xmlns:w="{W[1:-1]}"/>'.encode()
    model.package.parts[part.name] = replace(part, data=data)
    budget = od.DocumentLimits(max_nodes=500) if damage == 'nodes' else od.DocumentLimits()
    before = od.document_to_json(model)
    target = tmp_path/'refused.docx'
    target.write_bytes(b'previous output')
    report = write_document(model, target, options=ExportOptions(document_limits=budget))
    assert not report.success and any(issue.feature == 'docx.settings' for issue in report.issues)
    assert target.read_bytes() == b'previous output' and od.document_to_json(model) == before


def source_with_styles(defaults=None):
    data = original('absent', {}, '  A  B  ')
    with ZipFile(BytesIO(data)) as archive:
        parts = [(name, archive.read(name)) for name in archive.namelist()]
    relationship = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles'
    output = []
    for name, payload in parts:
        if name == '[Content_Types].xml':
            payload = payload.replace(b'</Types>', b'<Override PartName="/word/styles.xml" '
                                      b'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                                      b'</Types>')
        output.append((name, payload))
    output.append(('word/_rels/document.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   f'<Relationship Id="styles" Type="{relationship}" Target="styles.xml"/></Relationships>'))
    output.append(('word/styles.xml', '<w:styles xmlns:w="'+W[1:-1]+'">'+(defaults or '')
                   +'<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style></w:styles>'))
    return zip_bytes(output)


def defaults_xml(path):
    with ZipFile(path) as archive:
        return etree.fromstring(archive.read('word/styles.xml')).find(W+'docDefaults')


@pytest.mark.parametrize('styles_part', [False, True])
def test_absence_is_captured_before_lazy_styles_and_survives_two_public_cycles(tmp_path, styles_part):
    source = tmp_path/'source.docx'
    data = source_with_styles() if styles_part else original('absent', {}, '  A  B  ')
    source.write_bytes(data)
    imported = read_document(source)
    assert imported.success, imported.issues
    model = imported.document
    assert model.metadata[KEY] == {'format': KEY, 'version': 1, 'styles_present': styles_part,
                                   'doc_defaults_present': False}
    assert '__doc_defaults__' not in model.styles
    for cycle in range(2):
        before = od.document_to_json(model)
        model = od.document_from_json(before)
        target = tmp_path/f'cycle-{cycle}.docx'
        report = write_document(model, target)
        assert report.success, report.issues
        assert defaults_xml(target) is None
        assert od.document_to_json(model) == before
        imported = read_document(target)
        assert imported.success, imported.issues
        model = imported.document
        assert '__doc_defaults__' not in model.styles
        assert model.metadata[KEY]['doc_defaults_present'] is False
    assert source.read_bytes() == data


def test_source_declared_defaults_are_not_removed(tmp_path):
    source = tmp_path/'declared.docx'
    source.write_bytes(source_with_styles('<w:docDefaults><w:rPrDefault><w:rPr><w:sz w:val="28"/>'
                                         '<w:lang w:val="fr-FR"/></w:rPr></w:rPrDefault></w:docDefaults>'))
    imported = read_document(source)
    assert imported.success, imported.issues
    assert imported.document.metadata[KEY]['doc_defaults_present']
    assert imported.document.styles['__doc_defaults__'].font_size.pt == 14
    target = tmp_path/'written.docx'
    report = write_document(imported.document, target)
    assert report.success, report.issues
    node = defaults_xml(target)
    assert node.find('.//'+W+'sz').get(W+'val') == '28'
    assert node.find('.//'+W+'lang').get(W+'val') == 'fr-FR'


@pytest.mark.parametrize('style_id', ['__doc_defaults__', 'user-defaults'])
@pytest.mark.parametrize('styles_part', [False, True])
def test_explicit_user_default_declaration_overrides_original_absence(tmp_path, style_id, styles_part):
    source = tmp_path/'source.docx'
    source.write_bytes(source_with_styles() if styles_part else original('absent', {}, '  A  B  '))
    model = read_document(source).document
    model.styles[style_id] = od.TextStyle(font_family='Arial', font_size=od.Length(18),
                                         properties={'style_type': 'document-default', 'style_name': 'Own defaults'})
    before = od.document_to_json(model)
    target = tmp_path/'edited.docx'
    report = write_document(model, target)
    assert report.success, report.issues
    assert defaults_xml(target).find('.//'+W+'sz').get(W+'val') == '36'
    fonts = defaults_xml(target).find('.//'+W+'rFonts')
    assert fonts.get(W+'ascii') == 'Arial' and fonts.get(W+'asciiTheme') is None
    assert od.document_to_json(model) == before


@pytest.mark.parametrize('state', [None, {'format': KEY, 'version': 2},
                                  {'format': KEY, 'version': True, 'styles_present': False, 'doc_defaults_present': False},
                                  {'format': KEY, 'version': 1, 'styles_present': False, 'doc_defaults_present': True}])
def test_generic_model_without_profile_keeps_defaults_and_invalid_profiles_refuse(tmp_path, state):
    model = od.DocumentModel(sections=[od.Section(blocks=[od.Paragraph([od.TextRun('Own')])])])
    if state is not None:
        model.metadata[KEY] = state
    target = tmp_path/'written.docx'
    target.write_bytes(b'previous output')
    report = write_document(model, target)
    if state is None:
        assert report.success, report.issues
        assert defaults_xml(target) is not None
    else:
        assert not report.success and any(issue.feature == 'docx.defaults' for issue in report.issues)
        assert target.read_bytes() == b'previous output'


def test_cancel_restoring_defaults_keeps_model_and_output(tmp_path, monkeypatch):
    from opendoc_formats.ooxml import docx_defaults

    source = tmp_path/'source.docx'
    source.write_bytes(original('absent', {}, '  A  B  '))
    model = read_document(source).document
    before = od.document_to_json(model)
    target = tmp_path/'written.docx'
    target.write_bytes(b'previous output')
    stop = Event()
    real = docx_defaults.checkpoint
    def checkpoint():
        stop.set()
        real()
    monkeypatch.setattr(docx_defaults, 'checkpoint', checkpoint)
    report = write_document(model, target, options=ExportOptions(cancelled=stop.is_set))
    assert not report.success
    assert target.read_bytes() == b'previous output' and od.document_to_json(model) == before


@pytest.mark.parametrize('damage', ['doctype', 'nodes', 'source-changed'])
def test_new_defaults_source_merge_checks_xml_policy_budget_and_source_conflicts(tmp_path, damage):
    from dataclasses import replace

    source = tmp_path/'source.docx'
    source.write_bytes(source_with_styles())
    model = read_document(source).document
    model.styles['own-defaults'] = od.TextStyle(font_size=od.Length(18), properties={'style_type': 'document-default'})
    part = model.package.parts['/word/styles.xml']
    root = etree.fromstring(part.data)
    if damage == 'nodes':
        latent = etree.Element(W+'latentStyles')
        for index in range(1000):
            etree.SubElement(latent, W+'lsdException', {W+'name': f'Own{index}'})
        root.insert(0, latent)
    elif damage == 'source-changed':
        root.insert(0, etree.Element(W+'docDefaults'))
    data = etree.tostring(root)
    if damage == 'doctype':
        data = b'<!DOCTYPE w:styles [<!ENTITY own "untrusted">]>'+data
    model.package.parts[part.name] = replace(part, data=data)
    budget = od.DocumentLimits(max_nodes=500) if damage == 'nodes' else od.DocumentLimits()
    assert not model.validate(limits=budget)
    before = od.document_to_json(model)
    target = tmp_path/'written.docx'
    target.write_bytes(b'previous output')
    report = write_document(model, target, options=ExportOptions(document_limits=budget))
    assert not report.success
    assert target.read_bytes() == b'previous output' and od.document_to_json(model) == before
