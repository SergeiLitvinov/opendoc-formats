"""Independent EPUB containers identify XML through all OPF renditions, without XHTML backends."""

import json
import zipfile
from dataclasses import FrozenInstanceError
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, compare_snapshots, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from tests.binary_fixtures import zip_bytes

OCF = 'urn:oasis:names:tc:opendocument:xmlns:container'
OPF = 'http://www.idpf.org/2007/opf'


def publication(*, second=False):
    rootfiles = '<rootfile full-path="Book/package" media-type="application/oebps-package+xml"/>'
    if second:
        rootfiles += '<rootfile full-path="Other/package" media-type="application/oebps-package+xml"/>'
    package = (
        f'<package xmlns="{OPF}" version="3.0" unique-identifier="uid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="uid">urn:own</dc:identifier><dc:title>Own title</dc:title>'
        '<dc:language>en</dc:language><meta property="dcterms:modified">2026-01-01T00:00:00Z</meta></metadata>'
        '<manifest><item id="chapter" href="Text/own%20chapter" media-type="application/xhtml+xml"/>'
        '<item id="binary" href="assets/own.xml" media-type="application/octet-stream"/></manifest>'
        '<spine><itemref idref="chapter"/></spine></package>'
    ).encode('utf-16')
    chapter = ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Own</title></head>'
               '<body><p>Own text</p></body></html>').encode('utf-16')
    entries = {
        'mimetype': b'application/epub+zip',
        'Book/Text/own chapter': chapter,
        'Book/assets/own.xml': b'Own binary\x00\xff',
        'META-INF/container.xml': (
            f'<container xmlns="{OCF}" version="1.0"><rootfiles>{rootfiles}</rootfiles></container>').encode(),
        'Book/package': package,
    }
    if second:
        entries['Other/package'] = package.decode('utf-16').replace(
            'href="Text/', 'href="../Book/Text/').replace('href="assets/', 'href="../Book/assets/').encode('utf-16')
    return entries


def inspect(entries, **options):
    return inspect_binary(zip_bytes(list(entries.items()), compression=zipfile.ZIP_STORED), **options)


@pytest.mark.parametrize('second', [False, True])
def test_every_rendition_contributes_types_and_shared_original_xml_is_parsed_once(second):
    entries = publication(second=second)
    snapshot = inspect(entries, capture=True)
    assert dict(snapshot.details)['epub_rootfiles'] == (('Book/package', 'Other/package') if second else ('Book/package',))
    assert snapshot.opc is None
    items = {item.locator: item for item in snapshot.items}
    chapter = items['zip:/Book/Text/own chapter']
    assert dict(chapter.details)['content_type'] == 'application/xhtml+xml'
    assert dict(chapter.details)['xml_detection'] == 'epub-media-type'
    assert chapter.xml_nodes[0].tag == '{http://www.w3.org/1999/xhtml}html'
    assert dict(items['zip:/Book/package'].details)['xml_detection'] == 'epub-package'
    assert dict(items['zip:/META-INF/container.xml'].details)['xml_detection'] == 'epub-container'
    assert not items['zip:/Book/assets/own.xml'].xml_nodes
    assert all(item.payload == entries[item.locator[5:]] for item in snapshot.items)
    nodes = sum(len(item.xml_nodes) for item in snapshot.items)
    assert inspect(entries, limits=AnatomyLimits(max_xml_nodes=nodes)).items
    with pytest.raises(ResourceLimitError, match='XML node/depth limit'):
        inspect(entries, limits=AnatomyLimits(max_xml_nodes=nodes-1))


@pytest.mark.parametrize('change', ['container-missing', 'opf-missing', 'resource-missing', 'no-rootfiles',
                                  'wrong-opf-root', 'no-manifest', 'duplicate-item', 'duplicate-root', 'conflicting-types'])
def test_incomplete_or_conflicting_manifest_bindings_are_explicit_failures(change):
    entries = publication(second=change == 'conflicting-types')
    if change == 'container-missing':
        del entries['META-INF/container.xml']
    elif change == 'opf-missing':
        del entries['Book/package']
    elif change == 'resource-missing':
        del entries['Book/Text/own chapter']
    elif change == 'no-rootfiles':
        entries['META-INF/container.xml'] = f'<container xmlns="{OCF}"><rootfiles/></container>'.encode()
    elif change == 'wrong-opf-root':
        entries['Book/package'] = b'<wrong/>'
    elif change == 'no-manifest':
        entries['Book/package'] = f'<package xmlns="{OPF}"/>'.encode()
    elif change == 'duplicate-item':
        entries['Book/package'] = entries['Book/package'].decode('utf-16').replace(
            'id="binary"', 'id="chapter"').encode('utf-16')
    elif change == 'duplicate-root':
        entries['META-INF/container.xml'] = entries['META-INF/container.xml'].replace(
            b'</rootfiles>', b'<rootfile full-path="Book/package" media-type="application/oebps-package+xml"/></rootfiles>')
    else:
        entries['Other/package'] = entries['Other/package'].decode('utf-16').replace(
            'application/xhtml+xml', 'application/octet-stream').encode('utf-16')
    with pytest.raises(InvalidDocumentError):
        inspect(entries)
    assert not any(item.xml_nodes for item in inspect(entries, parse_xml=False).items)


@pytest.mark.parametrize('href,error', [('../../outside', InvalidDocumentError), ('/absolute', InvalidDocumentError),
                                      ('../META-INF/container.xml', UnsupportedDocumentError)])
def test_manifest_addresses_never_access_remote_or_outside_resources(href, error):
    entries = publication()
    entries['Book/package'] = entries['Book/package'].decode('utf-16').replace('Text/own%20chapter', href).encode('utf-16')
    with pytest.raises(error):
        inspect(entries)


@pytest.mark.parametrize('href', ['https://example.invalid/audio.mp3?own=1#fragment',
                                'http://example.invalid/audio.mp3', '//example.invalid/audio.mp3',
                                'file:///C:/private/audio.mp3', 'data:audio/mpeg;base64,AAAA',
                                'javascript:own()', 'mailto:own@example.invalid'])
def test_external_manifest_resources_are_inert_original_observations(href, monkeypatch):
    import builtins
    import io
    import socket
    import urllib.request

    entries = publication()
    entries['Book/package'] = entries['Book/package'].decode('utf-16').replace(
        '</manifest>', f'<item id="audio" href="{href}" media-type="audio/mpeg" '
        'properties="remote-resources" own="unchanged"/></manifest>').encode('utf-16')
    source = zip_bytes(list(entries.items()), compression=zipfile.ZIP_STORED)

    def forbidden(*args, **kwargs):
        pytest.fail('Inspection must not access a manifest target through filesystem or network')

    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr(io, 'open', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    snapshot = inspect_binary(source, capture=True)
    assert snapshot.epub is not None and snapshot.opc is None
    assert len(snapshot.epub.references) == 3
    local, _, remote = snapshot.epub.references
    assert local.status == 'local' and local.resolved_target == 'Book/Text/own chapter'
    assert remote.href == href and remote.status == 'external-unassessed'
    assert remote.resolved_target is None and remote.package == 'Book/package'
    assert remote.identifier == 'audio' and remote.media_type == 'audio/mpeg'
    assert remote.location == 'zip:/Book/package#xml:0/1/2'
    assert dict(remote.attributes)['own'] == 'unchanged'
    encoded = json.loads(json.dumps(snapshot.to_dict()))['epub']
    assert not encoded['assessment_complete'] and encoded['references'][2]['href'] == href
    encoded['references'][2]['attributes']['own'] = 'edited'
    assert dict(remote.attributes)['own'] == 'unchanged'
    with pytest.raises(FrozenInstanceError):
        remote.href = 'edited'
    assert all(item.payload == entries[item.locator[5:]] for item in snapshot.items)
    assert len(snapshot.items) == len(entries)
    assert compare_snapshots(snapshot, inspect_binary(source))['binary_identical']
    assert not compare_snapshots(snapshot, inspect_binary(source))['epub_changed']
    assert inspect_binary(source, parse_xml=False).epub is None


def test_external_references_keep_each_rendition_and_detect_literal_change():
    entries = publication(second=True)
    for name in ('Book/package', 'Other/package'):
        entries[name] = entries[name].decode('utf-16').replace(
            '</manifest>', '<item id="audio" href="https://example.invalid/audio.mp3" '
            'media-type="audio/mpeg"/></manifest>').encode('utf-16')
    original = inspect(entries)
    references = [r for r in original.epub.references if r.status == 'external-unassessed']
    assert len(references) == 2 and references[0].package != references[1].package
    entries['Other/package'] = entries['Other/package'].decode('utf-16').replace(
        'audio.mp3', 'changed.mp3').encode('utf-16')
    assert compare_snapshots(original, inspect(entries))['epub_changed']
    assert not compare_snapshots(original, inspect(entries))['assessment_complete']


@pytest.mark.parametrize('change', ['missing-id', 'missing-type', 'missing-href', 'duplicate-id', 'duplicate-url', 'malformed'])
def test_invalid_external_declarations_still_fail_at_the_source(change):
    entries = publication()
    item = '<item id="audio" href="https://example.invalid/audio.mp3" media-type="audio/mpeg"/>'
    if change == 'missing-id':
        item = item.replace('id="audio" ', '')
    elif change == 'missing-type':
        item = item.replace(' media-type="audio/mpeg"', '')
    elif change == 'missing-href':
        item = item.replace('href="https://example.invalid/audio.mp3" ', '')
    elif change == 'duplicate-id':
        item += item.replace('audio.mp3', 'other.mp3')
    elif change == 'duplicate-url':
        item += item.replace('id="audio"', 'id="other"')
    else:
        item = item.replace('https://example.invalid/audio.mp3', 'https://[invalid')
    entries['Book/package'] = entries['Book/package'].decode('utf-16').replace(
        '</manifest>', item+'</manifest>').encode('utf-16')
    with pytest.raises(InvalidDocumentError, match=r'zip:/Book/package#xml:0/1/'):
        inspect(entries)


def remote_publication(count=1):
    entries = publication()
    remote = ''.join(f'<item id="audio-{index}" href="https://example.invalid/{index}.mp3" '
                     'media-type="audio/mpeg"/>' for index in range(count))
    entries['Book/package'] = entries['Book/package'].decode('utf-16').replace(
        '</manifest>', remote+'</manifest>').encode('utf-16')
    return entries


def test_remote_inventory_remains_bounded_by_the_shared_xml_budget():
    entries = remote_publication(8)
    snapshot = inspect(entries)
    node_count = sum(len(item.xml_nodes) for item in snapshot.items)
    assert len(inspect(entries, limits=AnatomyLimits(max_xml_nodes=node_count)).epub.references) == 10
    with pytest.raises(ResourceLimitError, match='XML node/depth limit'):
        inspect(entries, limits=AnatomyLimits(max_xml_nodes=node_count-1))


def test_cancel_inside_remote_reference_inventory_does_not_read_content(monkeypatch):
    import opendoc_formats.anatomy as anatomy

    stopped, references = Event(), []
    constructor = anatomy.EpubManifestReference

    def observed(*args):
        reference = constructor(*args)
        references.append(reference)
        if reference.status == 'external-unassessed':
            stopped.set()
        return reference

    source = zip_bytes(list(remote_publication(3).items()), compression=zipfile.ZIP_STORED)
    read_member = zipfile.ZipFile.open
    reads = []

    def opened(self, info, *args, **kwargs):
        reads.append(info.filename if isinstance(info, zipfile.ZipInfo) else info)
        return read_member(self, info, *args, **kwargs)

    monkeypatch.setattr(anatomy, 'EpubManifestReference', observed)
    monkeypatch.setattr(zipfile.ZipFile, 'open', opened)
    with pytest.raises(OperationCancelledError):
        inspect_binary(source, cancelled=stopped.is_set)
    assert len(references) == 3
    assert reads == ['mimetype', 'META-INF/container.xml', 'Book/package']


def test_remote_inspection_does_not_relax_the_strict_epub_reader(tmp_path):
    from opendoc_formats.readers.epub_package import read_epub_package

    source = tmp_path/'own.epub'
    original = zip_bytes(list(remote_publication().items()), compression=zipfile.ZIP_STORED)
    source.write_bytes(original)
    assert inspect_binary(source).epub.references[-1].status == 'external-unassessed'
    with pytest.raises(ValueError, match='Remote EPUB package references are not supported'):
        read_epub_package(source)
    assert source.read_bytes() == original


def test_xml_base_is_outside_the_finite_inspection_profile():
    entries = publication()
    entries['Book/package'] = entries['Book/package'].decode('utf-16').replace('<manifest>', '<manifest xml:base="elsewhere/">')
    entries['Book/package'] = entries['Book/package'].encode('utf-16')
    with pytest.raises(UnsupportedDocumentError, match='xml:base'):
        inspect(entries)


@pytest.mark.parametrize('href,target', [
    ('Text/%E2%82%AC', 'Book/Text/€'),
    ('Text/%F0%9F%A6%8A', 'Book/Text/🦊'),
    ('Text/%252F', 'Book/Text/%2F'),
    ('Text/own%20chapter#part?uninterpreted', 'Book/Text/own chapter'),
    ('Text/%2e%2e/Text/own%20chapter', 'Book/Text/own chapter'),
    ('Text/own%3Fchapter', 'Book/Text/own?chapter'),
    ('Text/own%23chapter', 'Book/Text/own#chapter'),
    ('Text/%20chapter', 'Book/Text/ chapter'),
])
def test_valid_local_percent_paths_resolve_once_and_keep_original_attributes(href, target):
    entries = publication()
    payload = entries.pop('Book/Text/own chapter')
    entries[target] = payload
    entries['Book/package'] = entries['Book/package'].decode('utf-16').replace(
        'Text/own%20chapter', href).encode('utf-16')
    snapshot = inspect(entries, capture=True)
    reference = snapshot.epub.references[0]
    assert reference.href == href and reference.resolved_target == target and reference.status == 'local'
    assert dict(reference.attributes)['href'] == href
    assert next(item for item in snapshot.items if item.locator == 'zip:/'+target).payload == payload
    assert not snapshot.epub.to_dict()['assessment_complete']


@pytest.mark.parametrize('href,error', [
    ('Text/own%chapter', InvalidDocumentError),
    ('Text/own%', InvalidDocumentError),
    ('Text/own%2', InvalidDocumentError),
    ('Text/%FF', InvalidDocumentError),
    ('Text/%C3', InvalidDocumentError),
    ('Text/%ED%A0%80', InvalidDocumentError),
    ('Text/%00', InvalidDocumentError),
    ('Text/%09', InvalidDocumentError),
    ('Text/%7F', InvalidDocumentError),
    (' Text/own%20chapter', InvalidDocumentError),
    ('Text/own%20chapter ', InvalidDocumentError),
    ('Text/own&#x9;chapter', InvalidDocumentError),
    ('Text/own&#xA;chapter', InvalidDocumentError),
    ('Text/own&#xD;chapter', InvalidDocumentError),
    ('Text%2Fown%20chapter', UnsupportedDocumentError),
    ('Text%5cown%20chapter', UnsupportedDocumentError),
    ('Text/own%20chapter?version=1', UnsupportedDocumentError),
    ('Text/own%20chapter?', UnsupportedDocumentError),
])
def test_ambiguous_local_urls_fail_at_original_manifest_node_without_reading_resource(href, error, monkeypatch):
    entries = publication()
    entries['Book/package'] = entries['Book/package'].decode('utf-16').replace(
        'Text/own%20chapter', href).encode('utf-16')
    source = zip_bytes(list(entries.items()), compression=zipfile.ZIP_STORED)
    opened = []
    original = zipfile.ZipFile.open

    def tracked(self, info, *args, **kwargs):
        opened.append(info.filename if isinstance(info, zipfile.ZipInfo) else info)
        return original(self, info, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, 'open', tracked)
    with pytest.raises(error, match=r'zip:/Book/package#xml:0/1/0:'):
        inspect_binary(source)
    assert opened == ['mimetype', 'META-INF/container.xml', 'Book/package']


@pytest.mark.parametrize('path', ['Book/package?query', 'Book/%FF', 'Book/package%', ' Book/package'])
def test_rootfile_local_url_validation_keeps_container_source_location(path):
    entries = publication()
    entries['META-INF/container.xml'] = entries['META-INF/container.xml'].replace(b'Book/package', path.encode())
    with pytest.raises((InvalidDocumentError, UnsupportedDocumentError), match=r'zip:/META-INF/container.xml#xml:0/0/0:'):
        inspect(entries)


def test_remote_rootfile_refusal_locates_the_original_container_node():
    entries = publication()
    entries['META-INF/container.xml'] = entries['META-INF/container.xml'].replace(
        b'Book/package', b'https://example.invalid/package')
    with pytest.raises(UnsupportedDocumentError, match=r'zip:/META-INF/container.xml#xml:0/0/0: remote EPUB'):
        inspect(entries)


def test_epub_inspection_does_not_guess_from_a_wrong_mimetype():
    entries = publication()
    entries['mimetype'] = b'application/epub+zip\n'
    entries['Book/assets/own.xml'] = b'<own/>'  # ordinary ZIP extension fallback remains active
    snapshot = inspect(entries)
    assert 'epub_rootfiles' not in dict(snapshot.details)
    assert not snapshot.items[1].xml_nodes


def test_control_and_resource_payloads_are_read_once(monkeypatch):
    entries = publication(second=True)
    source = zip_bytes(list(entries.items()), compression=zipfile.ZIP_STORED)
    reads = []
    open_member = zipfile.ZipFile.open

    def opened(self, name, *args, **kwargs):
        reads.append(name.filename if isinstance(name, zipfile.ZipInfo) else name)
        return open_member(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, 'open', opened)
    assert inspect_binary(source).items
    assert set(reads) == set(entries)
    assert all(reads.count(name) == 1 for name in entries)


def test_declared_extensionless_xml_keeps_dtd_policy_and_original_bytes():
    entries = publication()
    entries['Book/Text/own chapter'] = '<!DOCTYPE own [<!ENTITY own "value">]><own>&own;</own>'.encode('utf-16')
    with pytest.raises(UnsupportedDocumentError, match='DTD/entities'):
        inspect(entries)
    snapshot = inspect(entries, parse_xml=False, capture=True)
    assert snapshot.items[1].payload == entries['Book/Text/own chapter']
    assert 'epub_rootfiles' not in dict(snapshot.details)


def test_cancel_after_opf_does_not_read_resource_payloads(monkeypatch):
    import opendoc_formats.anatomy as anatomy

    stop, reads = Event(), []
    source = zip_bytes(list(publication().items()), compression=zipfile.ZIP_STORED)
    content_types = anatomy.inspection_content_types
    open_member = zipfile.ZipFile.open

    def parsed(read_xml):
        result = content_types(read_xml)
        stop.set()
        return result

    def opened(self, name, *args, **kwargs):
        member = name.filename if isinstance(name, zipfile.ZipInfo) else name
        assert member not in {'Book/Text/own chapter', 'Book/assets/own.xml'}, 'Resource was read after cancellation'
        reads.append(member)
        return open_member(self, name, *args, **kwargs)

    monkeypatch.setattr(anatomy, 'inspection_content_types', parsed)
    monkeypatch.setattr(zipfile.ZipFile, 'open', opened)
    with pytest.raises(OperationCancelledError):
        inspect_binary(source, cancelled=stop.is_set)
    assert reads == ['mimetype', 'META-INF/container.xml', 'Book/package']
