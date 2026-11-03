"""Native EPUB table/XML guards report their own units without replacing the SDK graph budget."""

import zipfile
from threading import Event

import pytest
from opendoc_model import ArtifactLimitError, DocumentLimits

from opendoc_formats import ImportOptions, read_document
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from opendoc_formats.readers.epub_model import read_epub_model
from opendoc_formats.readers.epub_package import _xml
from tests.readers.test_epub_interactive_diagnostics import source_book


@pytest.mark.parametrize('scope', ['tables', 'chapters'])
def test_selected_cell_quota_is_shared_across_tables_and_refusal_keeps_source(tmp_path, scope):
    source = tmp_path/'cells.epub'
    table = '<table><tr><td>One</td><td>Two</td><td>Three</td></tr></table>'
    source_book(source, table+table if scope == 'tables' else table)
    if scope == 'chapters':
        with zipfile.ZipFile(source) as archive:
            values = {name: archive.read(name) for name in archive.namelist()}
        values['OPS/book.opf'] = values['OPS/book.opf'].replace(
            b'</manifest>', b'<item id="second" href="second.xhtml" media-type="application/xhtml+xml"/></manifest>').replace(
            b'</spine>', b'<itemref idref="second"/></spine>')
        values['OPS/second.xhtml'] = ('<html><body>'+table+'</body></html>').encode()
        with zipfile.ZipFile(source, 'w') as archive:
            for name, value in values.items():
                archive.writestr(name, value)
    original = source.read_bytes()
    limits = DocumentLimits(max_nodes=4)
    with pytest.raises(ArtifactLimitError) as captured:
        read_epub_model(source, limits=limits)
    assert (captured.value.quota, captured.value.maximum, captured.value.path) == (
        'table cells', 4, 'epub.table_cells[4]',
    )
    result = read_document(source, options=ImportOptions(document_limits=limits))
    assert not result.success and result.document is None
    issue, = result.issues
    assert issue.code == 'import.document-limit' and issue.measurement['quota'] == 'table cells'
    assert source.read_bytes() == original and read_document(source).success


def test_selected_depth_bounds_native_table_nesting_before_graph_construction(tmp_path):
    source = tmp_path/'depth.epub'
    original = source_book(source, '<table><tr><td>'*3+'Own'+'</td></tr></table>'*3)
    with pytest.raises(ArtifactLimitError) as captured:
        read_epub_model(source, limits=DocumentLimits(max_depth=1))
    assert captured.value.quota == 'table depth' and captured.value.maximum == 1
    assert source.read_bytes() == original and read_document(source).success


def test_per_table_profile_cap_is_distinct_from_global_selected_cell_quota(tmp_path):
    source = tmp_path/'profile.epub'
    original = source_book(source, '<table><tr>'+'<td></td>'*10_001+'</tr></table>')
    with pytest.raises(ArtifactLimitError) as captured:
        read_epub_model(source)
    assert captured.value.quota == 'cells per table' and captured.value.maximum == 10_000
    assert captured.value.path.endswith('.cells[10000]')
    assert source.read_bytes() == original


def test_xml_depth_profile_accepts_exact_maximum_and_raises_typed_limit_next():
    assert _xml(b'<r>'*128+b'</r>'*128).tag == 'r'
    with pytest.raises(ResourceLimitError, match='depth.*128') as captured:
        _xml(b'<r>'*129+b'</r>'*129)
    assert captured.value.code == 'resource-limit'


def test_xml_node_profile_accepts_exact_maximum_and_raises_typed_limit_next():
    assert len(_xml(b'<r>'+b'<e/>'*99_999+b'</r>')) == 99_999
    with pytest.raises(ResourceLimitError, match='nodes.*100000') as captured:
        _xml(b'<r>'+b'<e/>'*100_000+b'</r>')
    assert captured.value.code == 'resource-limit'


@pytest.mark.parametrize('kind,maximum', [('depth', 128), ('nodes', 100_000)])
def test_xml_refuses_before_allocating_the_element_beyond_its_profile(monkeypatch, kind, maximum):
    from opendoc_formats.readers import epub_package

    builder, element = epub_package.ET.TreeBuilder, epub_package.ET.Element
    created = 0

    def allocate(tag, attributes):
        nonlocal created
        created += 1
        assert created <= maximum, 'An over-budget XML element was allocated'
        return element(tag, attributes)

    def observed(*args, **kwargs):
        return builder(*args, element_factory=allocate, **kwargs)

    monkeypatch.setattr(epub_package.ET, 'TreeBuilder', observed)
    data = (b'<r>'*129+b'</r>'*129 if kind == 'depth'
            else b'<r>'+b'<e/>'*100_000+b'</r>')
    with pytest.raises(ResourceLimitError, match=kind):
        _xml(data)
    assert created == maximum


def test_xml_cancellation_stops_tree_construction_and_next_parse_is_independent(monkeypatch):
    from opendoc_formats.readers import epub_package

    builder, element = epub_package.ET.TreeBuilder, epub_package.ET.Element
    stop, created = Event(), []

    def allocate(tag, attributes):
        created.append(tag)
        assert len(created) <= 3, 'XML construction continued after cancellation'
        if len(created) == 3:
            stop.set()
        return element(tag, attributes)

    def observed(*args, **kwargs):
        return builder(*args, element_factory=allocate, **kwargs)

    source = b'<r>'+b'<e/>'*20+b'</r>'
    with monkeypatch.context() as context:
        context.setattr(epub_package.ET, 'TreeBuilder', observed)
        with pytest.raises(OperationCancelledError):
            _xml(source, cancelled=stop.is_set)
    assert len(created) == 3
    assert len(_xml(source)) == 20


@pytest.mark.parametrize('encoding,declaration', [('utf-8', 'UTF-8'), ('utf-16', 'UTF-16')])
def test_bounded_xml_preserves_native_namespace_mixed_content_and_external_dtd_policy(encoding, declaration):
    from xml.etree import ElementTree

    source = (f'<?xml version="1.0" encoding="{declaration}"?>'
              '<!DOCTYPE root SYSTEM "https://example.invalid/never-fetch">'
              '<root xmlns="urn:own" xmlns:x="urn:attributes" x:own="A &amp; B">'
              'α<!--source-only--><?own inert?><child>β</child>γ</root>').encode(encoding)
    expected = ElementTree.fromstring(source)
    actual = _xml(source)
    assert ElementTree.tostring(actual) == ElementTree.tostring(expected)
    assert actual.attrib == {'{urn:attributes}own': 'A & B'}
    assert list(actual.itertext()) == ['α', 'β', 'γ']
