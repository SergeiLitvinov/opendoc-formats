"""XHTML references do not borrow U+FFFD resources or turn remote authority into local anchors."""

import zipfile
from html import escape
from threading import Event

import pytest
from opendoc_model import Image, document_from_json, document_to_json, get_integration

from opendoc_formats import read_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.epub import read_epub
from opendoc_formats.readers.epub_model import read_epub_model
from tests.binary_fixtures import own_png


def source_book(path, markup):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip')
        archive.writestr('META-INF/container.xml',
                        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                        '<rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/>'
                        '</rootfiles></container>')
        archive.writestr('OPS/book.opf',
                        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata/>'
                        '<manifest><item id="main" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
                        '<item id="extra" href="%EF%BF%BD.xhtml" media-type="application/xhtml+xml"/>'
                        '<item id="picture" href="%EF%BF%BD.png" media-type="image/png"/>'
                        '<item id="css" href="%EF%BF%BD.css" media-type="text/css"/></manifest>'
                        '<spine><itemref idref="main"/><itemref idref="extra"/></spine></package>')
        archive.writestr('OPS/chapter.xhtml', '<html><head><meta charset="utf-8"/></head><body>'+markup+'</body></html>')
        archive.writestr('OPS/�.xhtml', '<html><body><p id="own">Own asset chapter</p></body></html>')
        archive.writestr('OPS/�.png', own_png())
        archive.writestr('OPS/�.css', 'p { color: #123456; }')
    return path.read_bytes()


def restored(source):
    result = read_document(source)
    assert result.success and not result.assessment_complete
    return document_from_json(document_to_json(result.document))


@pytest.mark.parametrize('href', ['//example.invalid/target.xhtml#part', '//example.invalid:8443/path?own=1#part'])
def test_protocol_relative_external_links_keep_authority_and_original_uri(tmp_path, href):
    source = tmp_path/'external.epub'
    original = source_book(source, f'<p><a href="{escape(href, quote=True)}">Own text</a></p>')
    model = restored(source)
    run, = model.sections[0].blocks[0].content
    assert run.link == href and run.text == 'Own text'
    assert source.read_bytes() == original


@pytest.mark.parametrize('identifier,fragment', [('café', 'caf%C3%A9'), ('literal%FF', 'literal%25FF'),
                                              ('literal%20', 'literal%2520')])
def test_utf8_and_literal_percent_fragments_bind_the_actual_anchor_once(tmp_path, identifier, fragment):
    source = tmp_path/'fragment.epub'
    source_book(source, f'<p id="{identifier}">Own target</p><p><a href="#{fragment}">Go</a></p>')
    model = restored(source)
    target, link = model.sections[0].blocks
    assert link.content[0].link == '#'+target.properties['anchor_id']
    assert not any(record.issue.reason == 'unresolved-reference-uri' for record in get_integration(model).preservation)


@pytest.mark.parametrize('href', ['%FF.xhtml#own', '#%FF', '#%C0%AF', 'https://[invalid'])
def test_invalid_local_utf8_or_uri_syntax_does_not_fabricate_a_bound_link(tmp_path, href):
    source = tmp_path/'bad-link.epub'
    original = source_book(source, f'<p><a id="link" href="{escape(href, quote=True)}">Own text</a></p>')
    model = restored(source)
    marker, run = model.sections[0].blocks[0].content
    assert marker.text == '' and marker.link is None
    assert run.text == 'Own text' and run.link is None
    record, = [record for record in get_integration(model).preservation if record.issue.reason == 'unresolved-reference-uri']
    assert record.issue.code == 'epub.hyperlink' and record.state.value == 'lost'
    assert record.issue.location == f'{source}!/OPS/chapter.xhtml#link/@href'
    assert record.issue.measurement['value'] == href and record.issue.measurement['error']
    source_record, = [item for item in read_epub(source).diagnostics.preservation
                     if item.issue.reason == 'unresolved-reference-uri']
    assert source_record == record
    assert source.read_bytes() == original


@pytest.mark.parametrize('src,valid', [('%FF.png', False), ('%C0%AF.png', False), ('%EF%BF%BD.png', True)])
def test_image_does_not_borrow_a_genuine_replacement_character_filename(tmp_path, src, valid):
    source = tmp_path/'image.epub'
    source_book(source, f'<p><img id="picture" src="{src}" alt="Own alt"/></p>')
    model = restored(source)
    content = model.sections[0].blocks[0].content
    records = [record for record in get_integration(model).preservation if record.issue.reason == 'unresolved-reference-uri']
    if valid:
        image, = content
        assert isinstance(image, Image) and image.resource_id == 'epub-picture' and not records
    else:
        assert model.sections[0].blocks[0].plain_text == 'Own alt'
        assert not any(isinstance(item, Image) for item in content)
        record, = records
        assert record.issue.code == 'epub.image' and record.issue.location.endswith('#picture/@src')
        assert record.issue.measurement['value'] == src
    assert model.resources['epub-picture'].data == own_png()


@pytest.mark.parametrize('href,valid', [('%FF.css', False), ('%EF%BF%BD.css', True)])
def test_stylesheet_does_not_apply_a_replacement_character_alias(tmp_path, href, valid):
    source = tmp_path/'style.epub'
    source_book(source, f'<link id="sheet" rel="stylesheet" href="{href}"/><p>Own body</p>')
    model = restored(source)
    run, = model.sections[0].blocks[0].content
    assert run.style.color == ('#123456' if valid else None)
    records = [record for record in get_integration(model).preservation if record.issue.reason == 'unresolved-reference-uri']
    if valid:
        assert not records
    else:
        record, = records
        assert record.issue.code == 'epub.css' and record.issue.location.endswith('#sheet/@href')
        assert record.issue.measurement['value'] == href
    assert model.resources['epub-css'].data == b'p { color: #123456; }'


def test_cancel_after_uri_refusal_keeps_source_and_next_import_independent(tmp_path, monkeypatch):
    from opendoc_formats.readers.epub_diagnostics import EpubDiagnostics

    source = tmp_path/'cancel.epub'
    original = source_book(source, '<p><a id="link" href="%FF.xhtml">Own text</a></p>')
    stop = Event()
    actual = EpubDiagnostics.lost

    def lost(self, feature, reason, *args, **kwargs):
        result = actual(self, feature, reason, *args, **kwargs)
        if reason == 'unresolved-reference-uri':
            stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(EpubDiagnostics, 'lost', lost)
        with pytest.raises(OperationCancelledError):
            read_epub_model(source, cancelled=stop.is_set)
    assert stop.is_set() and source.read_bytes() == original
    assert read_document(source).success
