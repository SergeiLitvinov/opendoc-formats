"""Unsupported interactive EPUB objects have individual source witnesses, never an implicit semantic claim."""

import zipfile
from threading import Event

import pytest
from opendoc_model import document_from_json, document_to_json, get_integration

from opendoc_formats import read_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.epub import read_epub
from opendoc_formats.readers.epub_model import read_epub_model


def source_book(path, markup, *, body_attributes=''):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip')
        archive.writestr('META-INF/container.xml',
                        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                        '<rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/>'
                        '</rootfiles></container>')
        archive.writestr('OPS/book.opf',
                        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata/>'
                        '<manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
                        '</manifest><spine><itemref idref="chapter"/></spine></package>')
        attributes = ' '+body_attributes if body_attributes else ''
        archive.writestr('OPS/chapter.xhtml', '<html><body'+attributes+'><p>Editable body</p>'+markup+'</body></html>')
    return path.read_bytes()


@pytest.mark.parametrize('tag,code,reason', [
    ('iframe', 'epub.frame', 'unsupported-frame'), ('embed', 'epub.object', 'unsupported-object'),
    ('form', 'epub.form', 'unsupported-form'),
    *((tag, 'epub.control', 'unsupported-control') for tag in
      ('input', 'button', 'select', 'textarea', 'option', 'optgroup', 'output', 'datalist', 'progress', 'meter')),
])
def test_interactive_objects_have_exact_source_state_and_json_transport(tmp_path, tag, code, reason):
    source = tmp_path/'interactive.epub'
    attributes = {'name': 'own-field', 'value': 'Own & value', 'type': 'application/own',
                  'src': 'https://example.invalid/inert', 'action': 'https://example.invalid/submit'}
    # Literal bytes are authored independently of the importer and Model codec.
    original = source_book(source, f'<{tag} id="own" name="own-field" value="Own &amp; value" '
                           'type="application/own" src="https://example.invalid/inert" '
                           f'action="https://example.invalid/submit"></{tag}>')
    result = read_document(source)
    assert result.success and not result.assessment_complete and not result.lossless
    model = document_from_json(document_to_json(result.document))
    records = [record for record in get_integration(model).preservation if record.issue.code == code]
    record, = records
    assert record.state.value == 'lost' and record.issue.severity.value == 'loss'
    assert record.issue.reason == reason
    assert record.issue.location == f'{source}!/OPS/chapter.xhtml#own'
    assert record.provenance.source_path == str(source)
    assert record.provenance.package_part == '/OPS/chapter.xhtml'
    assert record.provenance.object_id == 'own'
    assert record.issue.measurement == {'element': tag, 'attributes': attributes}
    assert model.sections[0].blocks[0].plain_text == 'Editable body'
    assert source.read_bytes() == original


def test_nested_control_records_preserve_boolean_attributes_and_distinct_source_addresses(tmp_path):
    source = tmp_path/'controls.epub'
    source_book(source, '<form id="form" action="/submit"><select id="select" name="own" multiple="multiple">'
                '<option id="choice" selected="selected" value="one">One</option></select>'
                '<input name="first" checked="checked" disabled="disabled"/>'
                '<input name="second" readonly="readonly"/></form>')
    result = read_document(source)
    model = document_from_json(document_to_json(result.document))
    records = [record for record in get_integration(model).preservation if record.issue.code in {'epub.form', 'epub.control'}]
    assert len(records) == 5 and len({record.issue.location for record in records}) == 5
    choice, = [record for record in records if record.provenance.object_id == 'choice']
    assert choice.issue.measurement['attributes'] == {'selected': 'selected', 'value': 'one'}
    fields = {record.issue.measurement['attributes'].get('name'): record for record in records}
    assert fields['first'].issue.measurement['attributes']['disabled'] == 'disabled'
    assert fields['second'].issue.measurement['attributes']['readonly'] == 'readonly'
    transport = tmp_path/'transport.json'
    transport.write_text(document_to_json(model), encoding='utf-8')
    assert read_document(transport).issues == result.issues
    text = read_epub(source)
    assert [record for record in text.diagnostics.preservation if record.issue.code in {'epub.form', 'epub.control'}] == records


def test_cancel_between_interactive_objects_preserves_source_and_does_not_leak_scope(tmp_path, monkeypatch):
    from opendoc_formats.readers.epub_diagnostics import EpubDiagnostics

    source = tmp_path/'cancel.epub'
    original = source_book(source, '<input id="first"/><input id="second"/>')
    stop, calls = Event(), []
    actual = EpubDiagnostics.lost

    def lost(self, feature, *args, **kwargs):
        result = actual(self, feature, *args, **kwargs)
        if feature == 'epub.control':
            calls.append(feature)
            stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(EpubDiagnostics, 'lost', lost)
        with pytest.raises(OperationCancelledError):
            read_epub_model(source, cancelled=stop.is_set)
    assert calls == ['epub.control'] and source.read_bytes() == original
    assert read_document(source).success


def test_each_handler_has_an_attribute_address_on_body_and_nested_content(tmp_path):
    source = tmp_path/'handlers.epub'
    original = source_book(source, '<p id="target" onclick="fixture(&quot;🍀&quot;)" onfocus="other()">Visible</p>',
                           body_attributes='id="body" onload="start()"')
    result = read_document(source)
    model = document_from_json(document_to_json(result.document))
    records = [record for record in get_integration(model).preservation if record.issue.code == 'epub.event-handler']
    assert len(records) == 3
    expected = {('body', 'onload'): ('body', 'start()'),
                ('target', 'onclick'): ('p', 'fixture("🍀")'), ('target', 'onfocus'): ('p', 'other()')}
    for record in records:
        attribute = record.issue.measurement['attribute']
        element, value = expected[record.provenance.object_id, attribute]
        assert record.issue.measurement == {'element': element, 'attribute': attribute, 'value': value}
        assert record.issue.location == f'{source}!/OPS/chapter.xhtml#{record.provenance.object_id}/@{attribute}'
        assert record.provenance.package_part == '/OPS/chapter.xhtml'
        assert record.state.value == 'lost' and record.issue.reason == 'inactive-event-handler'
    assert model.sections[0].blocks[1].plain_text == 'Visible'
    assert [record for record in read_epub(source).diagnostics.preservation
            if record.issue.code == 'epub.event-handler'] == records
    assert source.read_bytes() == original


def test_no_id_handlers_have_distinct_line_column_attribute_addresses(tmp_path):
    source = tmp_path/'no-id.epub'
    source_book(source, '<p onclick="one()" onfocus="two()">One</p><p onclick="three()">Two</p>')
    result = read_document(source)
    records = [record for record in get_integration(result.document).preservation
               if record.issue.code == 'epub.event-handler']
    assert len(records) == len({record.issue.location for record in records}) == 3
    assert all(record.provenance.object_id is None and '#line=' in record.issue.location for record in records)
    assert {record.issue.measurement['value'] for record in records} == {'one()', 'two()', 'three()'}


def test_cancel_between_attributes_of_one_element_preserves_source(tmp_path, monkeypatch):
    from opendoc_formats.readers.epub_diagnostics import EpubDiagnostics

    source = tmp_path/'attribute-cancel.epub'
    original = source_book(source, '<p onclick="one()" onfocus="two()">Visible</p>')
    stop, calls = Event(), []
    actual = EpubDiagnostics.lost

    def lost(self, feature, *args, **kwargs):
        result = actual(self, feature, *args, **kwargs)
        if feature == 'epub.event-handler':
            calls.append(kwargs['attribute'])
            stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(EpubDiagnostics, 'lost', lost)
        with pytest.raises(OperationCancelledError):
            read_epub_model(source, cancelled=stop.is_set)
    assert calls == ['onclick'] and source.read_bytes() == original
    assert read_document(source).success


@pytest.mark.parametrize('href,value,scheme', [
    ('javascript:own()', 'javascript:own()', 'javascript'),
    ('JaVaScRiPt:own()', 'JaVaScRiPt:own()', 'javascript'),
    ('java&#x73;cript:own()', 'javascript:own()', 'javascript'),
    ('vbscript:own', 'vbscript:own', 'vbscript'),
])
def test_script_link_behavior_has_an_attribute_assessment_without_destroying_source_uri(tmp_path, href, value, scheme):
    source = tmp_path/'action.epub'
    source_book(source, f'<p><a id="link" href="{href}">Link text</a></p>')
    result = read_document(source)
    model = document_from_json(document_to_json(result.document))
    record, = [record for record in get_integration(model).preservation if record.issue.code == 'epub.link-action']
    assert record.state.value == 'lost' and record.issue.reason == 'unsupported-link-action'
    assert record.issue.location == f'{source}!/OPS/chapter.xhtml#link/@href'
    assert record.issue.measurement == {'element': 'a', 'attribute': 'href', 'value': value, 'scheme': scheme}
    marker, run = model.sections[0].blocks[1].content
    assert marker.text == '' and marker.link is None
    assert run.text == 'Link text' and run.link == value


@pytest.mark.parametrize('href', ['https://example.invalid/page', 'mailto:own@example.invalid'])
def test_ordinary_link_schemes_are_not_classified_as_script_actions(tmp_path, href):
    source = tmp_path/'link.epub'
    source_book(source, f'<p><a href="{href}">Link text</a></p>')
    result = read_document(source)
    assert not any(record.issue.code == 'epub.link-action' for record in get_integration(result.document).preservation)
    assert result.document.sections[0].blocks[1].content[0].link == href
