"""Independent EPUB containers identify XML through all OPF renditions, without XHTML backends."""

import zipfile
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
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


@pytest.mark.parametrize('href,error', [('https://example.invalid/own', UnsupportedDocumentError),
                                      ('../../outside', InvalidDocumentError), ('/absolute', InvalidDocumentError),
                                      ('../META-INF/container.xml', UnsupportedDocumentError)])
def test_manifest_addresses_never_access_remote_or_outside_resources(href, error):
    entries = publication()
    entries['Book/package'] = entries['Book/package'].decode('utf-16').replace('Text/own%20chapter', href).encode('utf-16')
    with pytest.raises(error):
        inspect(entries)


def test_xml_base_is_outside_the_finite_inspection_profile():
    entries = publication()
    entries['Book/package'] = entries['Book/package'].decode('utf-16').replace('<manifest>', '<manifest xml:base="elsewhere/">')
    entries['Book/package'] = entries['Book/package'].encode('utf-16')
    with pytest.raises(UnsupportedDocumentError, match='xml:base'):
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
