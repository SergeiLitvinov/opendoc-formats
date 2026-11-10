"""Independent EPUB source order, text structure and located projection losses."""

import builtins
import sys
from threading import Event
from zipfile import ZipFile

import opendoc_model as od
import pytest

from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.epub import read_epub
from opendoc_formats.support.document_adapters import text_to_document
from opendoc_formats.types import BlockType
from tests.binary_fixtures import own_png


def own_epub(path):
    parts = {
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/>'
        '</rootfiles></container>',
        'OPS/book.opf': '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:language>ru</dc:language></metadata>'
        '<manifest><item id="first" href="first.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="second" href="second.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="note" href="note.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="orphan" href="orphan.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        '<item id="picture" href="picture.png" media-type="image/png"/>'
        '<item id="sound" href="sound.ogg" media-type="audio/ogg"/></manifest>'
        '<spine><itemref idref="nav"/><itemref idref="second"/><itemref idref="first"/>'
        '<itemref idref="note" linear="no"/></spine></package>',
        'OPS/nav.xhtml': '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Navigation only</p></body></html>',
        'OPS/first.xhtml': '<html><body><h2>First heading</h2><p>Before <b>bold</b> after</p>'
        '<ul><li>Own item<ul><li>Child item</li></ul></li></ul>'
        '<table><tr><td>Cell A</td><td>Cell B</td></tr></table>'
        '<p><img id="own-image" src="picture.png" alt="Own image"/></p>'
        '<script id="own-script">never_execute()</script>'
        '<audio id="own-audio" src="sound.ogg"/></body></html>',
        'OPS/second.xhtml': '<html><body><p>Second chapter</p></body></html>',
        'OPS/note.xhtml': '<html><body><p>Nonlinear note</p></body></html>',
        'OPS/orphan.xhtml': '<html><body><p>Not in spine</p></body></html>',
        'OPS/picture.png': own_png(),
        'OPS/sound.ogg': b'own inert audio fixture',
    }
    with ZipFile(path, 'w') as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return path.read_bytes()


def test_spine_order_table_alt_text_inline_spaces_and_semantic_block_types(tmp_path):
    source = tmp_path/'own.epub'
    original = own_epub(source)
    result = read_epub(source)
    assert [block.text for block in result.blocks] == [
        'Second chapter', 'First heading', 'Before bold after', 'Own item', 'Child item', 'Cell A | Cell B', 'Own image']
    assert result.blocks[1].type is BlockType.HEADING and result.blocks[1].level == 2
    assert result.blocks[3].type is BlockType.LIST_ITEM
    assert result.blocks[4].type is BlockType.LIST_ITEM and result.blocks[4].level == 1
    assert result.blocks[5].type is BlockType.TABLE
    assert result.tables[0].rows == [['Cell A', 'Cell B']]
    assert result.language == 'ru' and result.pages == 0
    assert 'Navigation only' not in result.plain and 'Not in spine' not in result.plain
    assert 'Nonlinear note' not in result.plain and 'never_execute' not in result.plain
    assert source.read_bytes() == original


def test_nonlinear_opt_in_has_same_order_without_navigation_or_manifest_only_chapter(tmp_path):
    source = tmp_path/'own.epub'
    own_epub(source)
    result = read_epub(source, include_nonlinear=True)
    assert result.blocks[-1].text == 'Nonlinear note'
    assert result.blocks[0].text == 'Second chapter'
    assert 'Navigation only' not in result.plain and 'Not in spine' not in result.plain


def test_source_and_projection_losses_keep_locations_through_two_model_json_cycles(tmp_path):
    source = tmp_path/'own.epub'
    original = own_epub(source)
    text = read_epub(source)
    integration = text.diagnostics
    assert not integration.assessment_complete
    records = integration.preservation
    for feature, object_id in [('epub.script', 'own-script'), ('epub.media', 'own-audio'), ('legacy.image', 'own-image')]:
        matches = [record for record in records if record.issue.code == feature and record.provenance.object_id == object_id]
        assert len(matches) == 1
        assert matches[0].state is od.PreservationState.LOST
        assert matches[0].provenance.package_part == '/OPS/first.xhtml'
        assert matches[0].issue.location
    model = text_to_document(text)
    for _ in range(2):
        model = od.document_from_json(od.document_to_json(model))
        restored = od.get_integration(model)
        assert not restored.assessment_complete
        assert [record.issue for record in restored.preservation] == [record.issue for record in records]
    assert source.read_bytes() == original


def test_text_profile_does_not_import_other_format_or_font_engines(tmp_path, monkeypatch):
    source = tmp_path/'own.epub'
    own_epub(source)
    native_import = builtins.__import__

    def minimal(name, *args, **kwargs):
        if name.split('.')[0] in {'bs4', 'ebooklib', 'lxml', 'PIL', 'fontTools', 'fitz', 'pymupdf', 'docx', 'tinycss2'}:
            raise AssertionError('Unexpected optional engine: '+name)
        return native_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', minimal)
    assert read_epub(source).tables[0].rows == [['Cell A', 'Cell B']]


def test_well_formed_epub_text_without_beautifulsoup(tmp_path, monkeypatch):
    source = tmp_path / 'own.epub'
    original = own_epub(source)
    expected = read_epub(source)
    monkeypatch.setitem(sys.modules, 'bs4', None)
    native = read_epub(source)
    assert native.engine == 'native-epub-xhtml'
    assert (native.plain, native.blocks, native.tables, native.language) == (
        expected.plain, expected.blocks, expected.tables, expected.language,
    )
    assert source.read_bytes() == original


@pytest.mark.parametrize('encoding, label', [
    ('utf-8', 'UTF-8'), ('utf-8-sig', 'UTF-8'), ('utf-16', 'UTF-16'),
    ('utf-32', 'UTF-32'), ('cp1251', 'windows-1251'), ('iso8859-5', 'ISO-8859-5'),
])
def test_native_epub_recovers_entities_void_elements_and_unclosed_inline_markup(tmp_path, monkeypatch, encoding, label):
    source = tmp_path / 'own.epub'
    own_epub(source)
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts['OPS/second.xhtml'] = (
        f'<?xml version="1.0" encoding="{label}"?><html><body>\r\n'
        '<p onclick="one()">Свой&nbsp;<br><b>текст</p></body></html>'
    ).encode(encoding)
    with ZipFile(source, 'w') as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    monkeypatch.setitem(sys.modules, 'bs4', None)
    result = read_epub(source)
    assert result.engine == 'native-epub-xhtml'
    assert result.blocks[0].text.split() == ['Свой', 'текст']
    handler, = [record for record in result.diagnostics.preservation if record.issue.code == 'epub.event-handler']
    assert '#line=2,column=0/@onclick' in handler.issue.location
    recovery, = [record for record in result.diagnostics.preservation if record.issue.code == 'epub.xhtml']
    assert recovery.issue.reason == 'recovered-markup'
    assert recovery.provenance.package_part == '/OPS/second.xhtml'


def test_malformed_foreign_epub_markup_retains_optional_recovery(monkeypatch):
    from opendoc_formats.errors import InvalidDocumentError
    from opendoc_formats.readers.epub_xhtml import parse_chapter

    pytest.importorskip('bs4')
    payload = b'<html><body><svg><text>Own&nbsp;text</svg></body></html>'
    assert parse_chapter(payload).get_text() == 'Own\xa0text'
    monkeypatch.setitem(sys.modules, 'bs4', None)
    with pytest.raises(InvalidDocumentError, match='well-formed XHTML'):
        parse_chapter(payload)


def test_native_xhtml_cancels_between_parser_feeds_inside_large_comment(monkeypatch):
    from opendoc_formats.readers import epub_package
    from opendoc_formats.readers.epub_xhtml import parse_xhtml

    check = epub_package.check_cancelled
    feeds = []

    def observe(cancelled, operation):
        if operation == 'EPUB XML feed':
            feeds.append(operation)
        check(cancelled, operation)

    monkeypatch.setattr(epub_package, 'check_cancelled', observe)
    payload = b'<html><body><!--' + b'a' * 200_000 + b'--><p>Text</p></body></html>'
    with pytest.raises(OperationCancelledError, match='XML feed'):
        parse_xhtml(payload, cancelled=lambda: len(feeds) == 2)
    assert len(feeds) == 2


def test_selected_model_budget_refuses_without_modifying_source(tmp_path):
    source = tmp_path/'own.epub'
    original = own_epub(source)
    with pytest.raises(od.ArtifactLimitError):
        read_epub(source, limits=od.DocumentLimits(max_nodes=1))
    assert source.read_bytes() == original


def test_cancellation_after_import_reaches_text_projection(tmp_path, monkeypatch):
    from opendoc_formats.readers import epub

    source = tmp_path/'own.epub'
    original = own_epub(source)
    stop = Event()
    native_read = epub.read_epub_model

    def imported(*args, **kwargs):
        model = native_read(*args, **kwargs)
        stop.set()
        return model

    monkeypatch.setattr(epub, 'read_epub_model', imported)
    with pytest.raises(OperationCancelledError):
        read_epub(source, cancelled=stop.is_set)
    assert source.read_bytes() == original
