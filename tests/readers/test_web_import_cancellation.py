"""HTML/EPUB cooperative cancellation preserves sources and never returns a partial model."""

import zipfile
from pathlib import Path
from threading import Event

import pytest
from opendoc_model import document_to_json

from opendoc_formats import ImportOptions, read_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.epub import read_epub, read_epub_model
from opendoc_formats.readers.epub_package import read_epub_package
from opendoc_formats.readers.html import read_html_model

pytest.importorskip('bs4')

BODY = ('<p id="first">First <b>bold</b> <math><mi>x</mi></math></p><p id="second">Second</p>'
        '<table><caption>Own caption</caption><tr><th scope="col">Name</th></tr><tr><td>Own cell</td></tr></table>')


@pytest.fixture
def html_source(tmp_path):
    path = tmp_path / 'own.html'
    path.write_text('<html lang="en"><head><style>p {color:red}</style></head><body>'+BODY+'</body></html>', encoding='utf-8')
    return path


@pytest.fixture
def epub_source(tmp_path):
    path = tmp_path / 'own.epub'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip')
        archive.writestr('META-INF/container.xml',
                         '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                         '<rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/>'
                         '</rootfiles></container>')
        archive.writestr('OPS/book.opf', '<package xmlns="http://www.idpf.org/2007/opf"><metadata/>'
                         '<manifest>'+''.join(f'<item id="c{i}" href="{i}.xhtml" media-type="application/xhtml+xml"/>'
                                             for i in range(3))+'<item id="css" href="style.css" media-type="text/css"/>'
                         '</manifest><spine>'+''.join(f'<itemref idref="c{i}"/>' for i in range(3))+'</spine></package>')
        for index in range(3):
            archive.writestr(f'OPS/{index}.xhtml', '<html><head><link rel="stylesheet" href="style.css"/></head>'
                             '<body>'+BODY+'</body></html>')
        archive.writestr('OPS/style.css', 'p {color:red}')
    return path


@pytest.mark.parametrize('fixture', ['html_source', 'epub_source'])
def test_stop_after_native_soup_parse_does_not_build_or_parse_next_chapter(request, fixture, monkeypatch):
    from bs4 import BeautifulSoup

    path = request.getfixturevalue(fixture)
    original = path.read_bytes()
    stop, parsed = Event(), []
    initialize = BeautifulSoup.__init__

    def parse(soup, *args, **kwargs):
        initialize(soup, *args, **kwargs)
        parsed.append(True)
        stop.set()

    with monkeypatch.context() as context:
        context.setattr(BeautifulSoup, '__init__', parse)
        result = read_document(path, options=ImportOptions(cancelled=stop.is_set))
    assert not result.success and result.document is None and result.issues[0].code == 'import.cancelled'
    assert parsed == [True] and path.read_bytes() == original
    assert read_document(path).success


def test_epub_zip_stops_after_one_chapter_member_and_releases_archive(epub_source, monkeypatch):
    stop, visited = Event(), []
    original = epub_source.read_bytes()
    read = zipfile.ZipFile.read

    def member(archive, name, *args, **kwargs):
        visited.append(name)
        payload = read(archive, name, *args, **kwargs)
        if name == 'OPS/0.xhtml':
            stop.set()
        return payload

    monkeypatch.setattr(zipfile.ZipFile, 'read', member)
    result = read_document(epub_source, options=ImportOptions(cancelled=stop.is_set))
    assert not result.success and result.document is None and result.issues[0].code == 'import.cancelled'
    assert 'OPS/1.xhtml' not in visited and epub_source.read_bytes() == original
    with zipfile.ZipFile(epub_source) as archive:
        assert 'OPS/2.xhtml' in archive.namelist()


@pytest.mark.parametrize('fixture', ['html_source', 'epub_source'])
def test_block_cancellation_does_not_visit_second_paragraph(request, fixture, monkeypatch):
    path, stop, visited = request.getfixturevalue(fixture), Event(), []
    if fixture == 'html_source':
        from opendoc_formats.readers.html_diagnostics import HtmlDiagnostics

        original = HtmlDiagnostics.bind

        def bind(diagnostics, block, root, nodes=()):
            original(diagnostics, block, root, nodes)
            if root.get('id'):
                visited.append(root['id'])
                stop.set()

        monkeypatch.setattr(HtmlDiagnostics, 'bind', bind)
    else:
        import opendoc_formats.readers.epub_model as epub

        original = epub._paragraph

        def paragraph(tag, *args, **kwargs):
            result = original(tag, *args, **kwargs)
            visited.append(tag.get('id'))
            stop.set()
            return result

        monkeypatch.setattr(epub, '_paragraph', paragraph)
    result = read_document(path, options=ImportOptions(cancelled=stop.is_set))
    assert not result.success and result.document is None and result.issues[0].code == 'import.cancelled'
    assert visited == ['first']


def test_html_local_resource_cancel_does_not_read_next_asset(html_source, tmp_path, monkeypatch):
    for name in ('one.svg', 'two.svg'):
        (tmp_path / name).write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>')
    html_source.write_text('<p><img src="one.svg"/><img src="two.svg"/></p>', encoding='utf-8')
    original, stop, reads = html_source.read_bytes(), Event(), []
    read = Path.read_bytes

    def resource(path):
        payload = read(path)
        if path.suffix == '.svg':
            reads.append(path.name)
            stop.set()
        return payload

    monkeypatch.setattr(Path, 'read_bytes', resource)
    result = read_document(html_source, options=ImportOptions(resource_root=tmp_path, cancelled=stop.is_set))
    assert not result.success and result.document is None and result.issues[0].code == 'import.cancelled'
    assert reads == ['one.svg'] and html_source.read_bytes() == original


@pytest.mark.parametrize('fixture', ['html_source', 'epub_source'])
def test_inactive_callback_preserves_the_complete_model(request, fixture):
    path, calls = request.getfixturevalue(fixture), []

    def keep_running():
        calls.append(True)
        return False

    expected, observed = read_document(path), read_document(path, options=ImportOptions(cancelled=keep_running))
    assert expected.success and observed.success and len(calls) > 20
    assert document_to_json(expected.document) == document_to_json(observed.document)


@pytest.mark.parametrize('reader,fixture', [(read_html_model, 'html_source'), (read_epub_model, 'epub_source'),
                                         (read_epub, 'epub_source'), (read_epub_package, 'epub_source')])
def test_direct_readers_expose_cancel_and_reject_non_callable(request, reader, fixture):
    path = request.getfixturevalue(fixture)
    with pytest.raises(OperationCancelledError):
        reader(path, cancelled=lambda: True)
    with pytest.raises(ValueError, match='callable'):
        reader(path, cancelled=True)


def test_epub_css_scanner_cancels_long_input_without_rules():
    from opendoc_formats.readers.epub_model import _css_rules

    calls = []

    def cancel():
        calls.append(True)
        return len(calls) > 1

    with pytest.raises(OperationCancelledError):
        list(_css_rules(' '*10_000, lambda *args: None, cancelled=cancel))


def test_html_css_parser_cancel_stops_before_processing_declarations(html_source, monkeypatch):
    import tinycss2

    stop, parsed = Event(), []
    parser = tinycss2.parse_stylesheet

    def stylesheet(*args, **kwargs):
        result = parser(*args, **kwargs)
        parsed.append(True)
        stop.set()
        return result

    def forbidden(*args, **kwargs):
        raise AssertionError('Cancelled CSS proceeded to declarations')

    monkeypatch.setattr(tinycss2, 'parse_stylesheet', stylesheet)
    monkeypatch.setattr('opendoc_formats.readers.html_css.Cascade.declarations', forbidden)
    result = read_document(html_source, options=ImportOptions(cancelled=stop.is_set))
    assert parsed == [True] and not result.success and result.document is None
    assert result.issues[0].code == 'import.cancelled'


@pytest.mark.parametrize('fixture', ['html_source', 'epub_source'])
def test_direct_reader_late_cancellation_during_preservation_does_not_return_model(request, fixture, monkeypatch):
    path, stop = request.getfixturevalue(fixture), Event()
    if fixture == 'html_source':
        from opendoc_formats.readers.html_diagnostics import HtmlDiagnostics as Diagnostics
        reader = read_html_model
    else:
        from opendoc_formats.readers.epub_diagnostics import EpubDiagnostics as Diagnostics
        reader = read_epub_model
    attach = Diagnostics.attach

    def finish(*args, **kwargs):
        attach(*args, **kwargs)
        stop.set()

    monkeypatch.setattr(Diagnostics, 'attach', finish)
    with pytest.raises(OperationCancelledError):
        reader(path, cancelled=stop.is_set)
