"""OPC declarations identify XML independently of names and optional Office parsers."""

import zipfile
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from tests.binary_fixtures import zip_bytes

CT = 'http://schemas.openxmlformats.org/package/2006/content-types'


def package(declarations, entries, *, encoding='utf-8'):
    manifest = (f'<Types xmlns="{CT}">{declarations}</Types>').encode(encoding)
    # The manifest deliberately follows the payloads in the physical ZIP order.
    return zip_bytes([*entries, ('[Content_Types].xml', manifest)])


@pytest.mark.parametrize('media_type', ['application/xml', 'text/xml', 'application/vnd.own+xml',
                                        'Application/Own+XML; charset=utf-16'])
def test_declared_extensionless_xml_is_parsed_and_original_byte_offsets_are_retained(media_type):
    xml = '<root xmlns="urn:own"><child>Own text</child></root>'.encode('utf-16')
    source = package(f'<Override PartName="/parts/opaque" ContentType="{media_type}"/>', [('parts/opaque', xml)])
    item = inspect_binary(source, capture=True).items[0]
    assert item.locator == 'zip:/parts/opaque' and item.payload == xml
    assert dict(item.details)['content_type'] == media_type
    assert dict(item.details)['xml_detection'] == 'opc-content-type'
    child = item.xml_nodes[1]
    assert child.tag == '{urn:own}child'
    assert xml[child.start_byte:].startswith('<child>'.encode('utf-16-le'))


def test_overrides_win_over_case_insensitive_extension_defaults():
    source = package('<Default Extension="DAT" ContentType="application/octet-stream"/>'
                     '<Override PartName="/own.dat" ContentType="application/own+xml"/>',
                     [('own.dat', b'<own/>'), ('binary.DAT', b'\x00\xff')])
    xml, binary, _ = inspect_binary(source).items
    assert xml.xml_nodes[0].tag == 'own'
    assert dict(binary.details)['content_type'] == 'application/octet-stream'
    assert not binary.xml_nodes


def test_declared_binary_payload_with_an_xml_name_is_not_silently_reinterpreted():
    payload = b'Own binary\x00\xff'
    source = package('<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/opaque.xml" ContentType="application/octet-stream"/>',
                     [('opaque.xml', payload)])
    item = inspect_binary(source, capture=True).items[0]
    assert not item.xml_nodes and item.payload == payload
    assert dict(item.details)['xml_detection'] is None


def test_undeclared_members_keep_the_existing_extension_fallback():
    source = package('', [('own.svg', b'<svg/>'), ('opaque', b'Own bytes')])
    svg, opaque, manifest = inspect_binary(source).items
    assert svg.xml_nodes[0].tag == 'svg' and dict(svg.details)['xml_detection'] == 'extension'
    assert not opaque.xml_nodes and dict(opaque.details)['content_type'] is None
    assert dict(manifest.details)['xml_detection'] == 'opc-manifest'


@pytest.mark.parametrize('declarations', [
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="XML" ContentType="application/octet-stream"/>',
    '<Override PartName="/own" ContentType="application/xml"/>'
    '<Override PartName="/own" ContentType="application/octet-stream"/>',
    '<Default Extension="xml"/>',
    '<Override ContentType="application/xml"/>',
    '<Override PartName="/../escape" ContentType="application/xml"/>',
])
def test_invalid_content_type_bindings_fail_explicitly(declarations):
    with pytest.raises(InvalidDocumentError):
        inspect_binary(package(declarations, [('own', b'<own/>')]))


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16'])
def test_dtd_in_declared_extensionless_xml_is_rejected_before_expansion(encoding):
    xml = '<!DOCTYPE own [<!ENTITY value "Own">]><own>&value;</own>'.encode(encoding)
    source = package('<Override PartName="/opaque" ContentType="application/xml"/>', [('opaque', xml)])
    with pytest.raises(UnsupportedDocumentError, match='zip:/opaque: DTD/entities'):
        inspect_binary(source)
    assert inspect_binary(source, parse_xml=False, capture=True).items[0].payload == xml


def test_manifest_is_charged_once_and_declared_xml_shares_the_global_node_budget():
    source = package('<Override PartName="/opaque" ContentType="application/xml"/>', [('opaque', b'<own/>')])
    assert inspect_binary(source, limits=AnatomyLimits(max_xml_nodes=3)).items[0].xml_nodes
    with pytest.raises(ResourceLimitError, match='zip:/opaque: XML node/depth limit'):
        inspect_binary(source, limits=AnatomyLimits(max_xml_nodes=2))


def test_opaque_mode_does_not_parse_the_manifest_or_guess_its_declarations():
    source = zip_bytes([('opaque', b'<own/>'), ('[Content_Types].xml', b'Own broken manifest')])
    items = inspect_binary(source, parse_xml=False, capture=True).items
    assert not any(item.xml_nodes for item in items)
    assert all(dict(item.details)['content_type'] is None for item in items)
    assert items[1].payload == b'Own broken manifest'


def test_cancellation_after_manifest_does_not_read_any_following_payload(monkeypatch):
    import opendoc_formats.anatomy as anatomy

    stop = Event()
    original = anatomy.content_types
    open_member = zipfile.ZipFile.open
    source = package('<Override PartName="/opaque" ContentType="application/xml"/>', [('opaque', b'<own/>')])

    def parsed(nodes):
        result = original(nodes)
        stop.set()
        return result

    def checked(self, name, *args, **kwargs):
        member = name.filename if isinstance(name, zipfile.ZipInfo) else name
        assert not stop.is_set() or member == '[Content_Types].xml', 'Payload was read after cancellation'
        return open_member(self, name, *args, **kwargs)

    monkeypatch.setattr(anatomy, 'content_types', parsed)
    monkeypatch.setattr(zipfile.ZipFile, 'open', checked)
    with pytest.raises(OperationCancelledError):
        inspect_binary(source, cancelled=stop.is_set)
    monkeypatch.setattr(anatomy, 'content_types', original)
    stop.clear()
    assert inspect_binary(source).items[0].xml_nodes


def test_oversized_manifest_is_rejected_before_opening_the_member(monkeypatch):
    source = package('', [])

    def forbidden(*args, **kwargs):
        pytest.fail('Over-budget manifest payload was read')

    monkeypatch.setattr(zipfile.ZipFile, 'open', forbidden)
    with pytest.raises(ResourceLimitError, match=r'zip:/\[Content_Types\].xml: max_part_bytes'):
        inspect_binary(source, limits=AnatomyLimits(max_part_bytes=16))
