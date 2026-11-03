"""Distinct EPUB source paths/fragments retain distinct targets through JSON and HTML export."""

import posixpath
import zipfile
from html import escape
from html.parser import HTMLParser
from threading import Event
from urllib.parse import quote, unquote

import pytest
from opendoc_model import (
    ArtifactLimitError,
    DocumentLimits,
    Formula,
    Image,
    TextRun,
    document_from_json,
    document_to_json,
    get_anchor,
    iter_anchors,
)

from opendoc_formats import ImportOptions, read_document, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.epub_anchors import EpubAnchors
from opendoc_formats.readers.epub_model import read_epub_model
from tests.binary_fixtures import own_png


def source_book(path, chapters, root, assets=()):
    opf = posixpath.join(root, 'book.opf')
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip')
        archive.writestr('META-INF/container.xml',
                        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                        f'<rootfile full-path="{opf}" media-type="application/oebps-package+xml"/>'
                        '</rootfiles></container>')
        items = ''.join(f'<item id="c{index}" href="{quote(name)}" media-type="application/xhtml+xml"/>'
                        for index, (name, _) in enumerate(chapters))
        items += ''.join(f'<item id="a{index}" href="{quote(name)}" media-type="{media}"/>'
                         for index, (name, media, _) in enumerate(assets))
        spine = ''.join(f'<itemref idref="c{index}"/>' for index in range(len(chapters)))
        archive.writestr(opf, '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata/>'
                        f'<manifest>{items}</manifest><spine>{spine}</spine></package>')
        for name, markup in chapters:
            archive.writestr(posixpath.join(root, name), '<html><head><meta charset="utf-8"/></head>'
                             '<body>'+markup+'</body></html>')
        for name, _, payload in assets:
            archive.writestr(posixpath.join(root, name), payload)
    return path.read_bytes()


class HtmlTargets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links = [], []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get('id'):
            self.ids.append(values['id'])
        if values.get('href', '').startswith('#'):
            self.links.append(unquote(values['href'][1:]))


def verify_html(model, output):
    before = document_to_json(model)
    report = write_document(model, output)
    assert report.success, report.issues
    parsed = HtmlTargets()
    parsed.feed(output.read_text(encoding='utf-8'))
    assert len(parsed.ids) == len(set(parsed.ids))
    assert set(parsed.links) <= set(parsed.ids)
    assert document_to_json(model) == before


@pytest.mark.parametrize('root', ['', 'OPS'])
@pytest.mark.parametrize('in_cell', [False, True])
@pytest.mark.parametrize('target', ['<span id="café">A</span><em id="cafè">B</em>',
                                  '<a id="café"></a><span id="cafè"></span>AB',
                                  '<span id="café"><strong id="cafè">AB</strong></span>'])
def test_inline_targets_survive_json_and_html_without_duplicating_root(tmp_path, root, in_cell, target):
    source = tmp_path/'inline.epub'
    body = '<p id="owner">'+target+'</p>'
    if in_cell:
        body = '<table><tr><td>'+body+'</td></tr></table>'
    links = '<p><a href="#caf%C3%A9">Go A</a><a href="#caf%C3%A8">Go B</a></p>'
    original = source_book(source, [('chapter.xhtml', links+body)], root)
    result = read_document(source)
    assert result.success, result.issues
    model = result.document
    for cycle in range(2):
        model = document_from_json(document_to_json(model))
        blocks = model.sections[0].blocks
        paragraph = blocks[1].rows[0].cells[0].blocks[0] if in_cell else blocks[1]
        assert ''.join(item.text for item in paragraph.content) == 'AB'
        markers = [item for item in paragraph.content if get_anchor(item) is not None]
        assert len(markers) == 2
        assert all(isinstance(item, TextRun) and item.text == '' and item.link is None for item in markers)
        ids = [get_anchor(item).id for item in markers]
        assert len(set(ids)) == 2
        assert [item.link for item in blocks[0].content] == ['#'+key for key in ids]
        assert len(list(iter_anchors(model))) == 2
        assert paragraph.properties['anchor_id'] not in ids
        verify_html(model, tmp_path/f'inline-{cycle}.html')
    assert source.read_bytes() == original


@pytest.mark.parametrize('root', ['', 'OPS'])
@pytest.mark.parametrize('owner', ['inline', 'cell', 'block'])
@pytest.mark.parametrize('media', ['math', 'svg', 'img'])
def test_media_targets_keep_the_native_owner_and_payload(tmp_path, root, owner, media):
    source = tmp_path/'media.epub'
    templates = {
        'math': '<math id="{id}" xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>',
        'svg': '<svg id="{id}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2">'
               '<path d="M0 0L2 2" stroke="black"/></svg>',
        'img': '<img id="{id}" src="own.png" alt="Own image"/>',
    }
    target = ''.join(templates[media].format(id=key) for key in ('café', 'cafè'))
    if owner != 'block':
        target = '<p id="owner">'+target+'</p>'
    if owner == 'cell':
        target = '<table><tr><td>'+target+'</td></tr></table>'
    links = '<p><a href="#caf%C3%A9">Go A</a><a href="#caf%C3%A8">Go B</a></p>'
    payload = own_png()
    original = source_book(source, [('chapter.xhtml', links+target)], root,
                           [('own.png', 'image/png', payload)])
    result = read_document(source)
    assert result.success, result.issues
    model = result.document
    for cycle in range(2):
        model = document_from_json(document_to_json(model))
        blocks = model.sections[0].blocks
        if owner == 'block':
            items = [paragraph.content[0] for paragraph in blocks[1:]]
            assert all('anchor_id' not in paragraph.properties for paragraph in blocks[1:])
        else:
            paragraph = blocks[1].rows[0].cells[0].blocks[0] if owner == 'cell' else blocks[1]
            items = paragraph.content
        ids = [get_anchor(item).id for item in items]
        assert len(list(iter_anchors(model))) == 2
        assert len(items) == 2 and len(set(ids)) == 2
        assert [run.link for run in blocks[0].content] == ['#'+key for key in ids]
        assert all(isinstance(item, Formula if media == 'math' else Image) for item in items)
        for item in items:
            if media == 'math':
                assert '<' in item.value and item.fallback_text == 'x'
            else:
                resource = model.resources[item.resource_id]
                assert resource.data == payload if media == 'img' else b'<ns0:path' in resource.data
            assert item.provenance.object_id in {'café', 'cafè'}
        verify_html(model, tmp_path/f'media-{cycle}.html')
    assert source.read_bytes() == original


@pytest.mark.parametrize('root', ['', 'OPS'])
@pytest.mark.parametrize('block_level', [False, True])
def test_math_source_root_ids_from_different_chapters_do_not_alias_in_html(tmp_path, root, block_level):
    source = tmp_path/'math-chapters.epub'
    math = '<math id="shared" xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>'
    target = math if block_level else '<p>'+math+'</p>'
    original = source_book(source, [
        ('a.xhtml', '<p><a href="b.xhtml#shared">To B</a></p>'+target),
        ('b.xhtml', '<p><a href="a.xhtml#shared">To A</a></p>'+target),
    ], root)
    result = read_document(source)
    assert result.success, result.issues
    model = result.document
    for cycle in range(2):
        model = document_from_json(document_to_json(model))
        first, second = model.sections
        first_math, second_math = [section.blocks[1].content[0] for section in model.sections]
        assert get_anchor(first_math).id != get_anchor(second_math).id
        assert first.blocks[0].content[0].link == '#'+get_anchor(second_math).id
        assert second.blocks[0].content[0].link == '#'+get_anchor(first_math).id
        assert 'id="shared"' in first_math.value and 'id="shared"' in second_math.value
        verify_html(model, tmp_path/f'math-chapters-{cycle}.html')
    assert source.read_bytes() == original


@pytest.mark.parametrize('root', ['', 'OPS'])
@pytest.mark.parametrize('forward', [False, True])
@pytest.mark.parametrize('owner', ['p', 'table'])
def test_colliding_unicode_owners_and_forward_links_share_one_unique_map(tmp_path, root, forward, owner):
    source = tmp_path/'unicode.epub'
    first = '<p id="café">Target A</p>' if owner == 'p' else '<table id="café"><tr><td>Target A</td></tr></table>'
    targets = first+'<p id="cafè">Target B</p>'
    links = '<p><a href="#caf%C3%A9">Go A</a></p><p><a href="#caf%C3%A8">Go B</a></p>'
    original = source_book(source, [('chapter.xhtml', links+targets if forward else targets+links)], root)
    result = read_document(source)
    assert result.success
    model = result.document
    for cycle in range(2):
        model = document_from_json(document_to_json(model))
        blocks = model.sections[0].blocks
        target_a, target_b = blocks[-2:] if forward else blocks[:2]
        link_a, link_b = blocks[:2] if forward else blocks[-2:]
        assert target_a.properties['anchor_id'] != target_b.properties['anchor_id']
        assert link_a.content[0].link == '#'+target_a.properties['anchor_id']
        assert link_b.content[0].link == '#'+target_b.properties['anchor_id']
        verify_html(model, tmp_path/f'unicode-{cycle}.html')
    assert source.read_bytes() == original


@pytest.mark.parametrize('root', ['', 'OPS'])
@pytest.mark.parametrize('names', [('a/b.xhtml', 'a-b.xhtml'), ('a b.xhtml', 'a-b.xhtml'),
                                 ('a%2Fb.xhtml', 'a-2Fb.xhtml')])
@pytest.mark.parametrize('fragment', ['', '#own'])
def test_colliding_chapter_paths_keep_root_and_fragment_targets_distinct(tmp_path, root, names, fragment):
    source = tmp_path/'paths.epub'
    chapters = []
    for own, other in (names, names[::-1]):
        href = quote(posixpath.relpath(other, posixpath.dirname(own) or '.'))+fragment
        chapters.append((own, '<p id="own">Own target</p>'
                         f'<p><a href="{escape(href, quote=True)}">Other chapter</a></p>'))
    source_book(source, chapters, root)
    result = read_document(source)
    assert result.success
    model = document_from_json(document_to_json(result.document))
    one, two = model.sections
    assert one.properties['anchor_id'] != two.properties['anchor_id']
    assert one.blocks[0].properties['anchor_id'] != two.blocks[0].properties['anchor_id']
    for own, other in ((one, two), (two, one)):
        target = other.blocks[0].properties['anchor_id'] if fragment else other.properties['anchor_id']
        assert own.blocks[1].content[0].link == '#'+target
    verify_html(model, tmp_path/'paths.html')


@pytest.mark.parametrize('root', ['', 'OPS'])
def test_chapter_fragment_boundary_cannot_alias_another_chapter_root(tmp_path, root):
    source = tmp_path/'boundary.epub'
    source_book(source, [('chapter.xhtml', '<p id="x">Own target</p>'
                         '<p><a href="chapter.xhtml--x">Other root</a></p>'),
                         ('chapter.xhtml--x', '<p>Other chapter</p>')], root)
    result = read_document(source)
    assert result.success
    first, second = result.document.sections
    assert first.blocks[0].properties['anchor_id'] != second.properties['anchor_id']
    assert first.blocks[1].content[0].link == '#'+second.properties['anchor_id']
    verify_html(result.document, tmp_path/'boundary.html')


@pytest.mark.parametrize('root', ['', 'OPS'])
def test_archive_root_and_opf_relative_views_share_one_source_identity(tmp_path, root):
    source = tmp_path/'absolute.epub'
    href = '/'+posixpath.join(root, 'chapter.xhtml')+'#own'
    source_book(source, [('chapter.xhtml', f'<p id="own">Own target</p><p><a href="{href}">Go</a></p>')], root)
    result = read_document(source)
    assert result.success
    target, link = result.document.sections[0].blocks
    assert link.content[0].link == '#'+target.properties['anchor_id']


def test_registry_reuses_identity_and_refuses_next_distinct_identity_at_exact_limit():
    anchors = EpubAnchors(2)
    first = anchors.get('chapter.xhtml', 'first')
    assert first == 'epub-chapter.xhtml--first'
    assert anchors.get('./chapter.xhtml', 'first') == first
    anchors.get('chapter.xhtml', 'second')
    before = dict(anchors.ids), dict(anchors.owners)
    with pytest.raises(ArtifactLimitError) as captured:
        anchors.get('chapter.xhtml', 'third')
    assert (captured.value.quota, captured.value.maximum) == ('anchor identities', 2)
    assert (anchors.ids, anchors.owners) == before


def test_hash_collision_does_not_merge_distinct_owners(monkeypatch):
    from opendoc_formats.readers import epub_anchors

    class SameDigest:
        def hexdigest(self):
            return 'a'*64

    monkeypatch.setattr(epub_anchors.hashlib, 'sha256', lambda data: SameDigest())
    anchors = EpubAnchors(10)
    values = [anchors.get('chapter.xhtml', name) for name in ('café', 'cafè', 'cafê', 'cafë')]
    assert len(values) == len(set(values)) == 4
    assert anchors.get('chapter.xhtml', 'cafè') == values[1]


def test_cancelled_registry_does_not_return_even_a_cached_identity():
    stop = Event()
    anchors = EpubAnchors(1, stop.is_set)
    anchors.get('chapter.xhtml')
    stop.set()
    with pytest.raises(OperationCancelledError):
        anchors.get('chapter.xhtml')
    assert len(anchors.ids) == 1


def test_import_anchor_quota_is_not_downgraded_to_an_unresolved_uri(tmp_path):
    source = tmp_path/'quota.epub'
    body = ''.join(f'<p><a href="#{fragment}">Own reference</a></p>'
                   for fragment in ('', 'one', 'two', 'three', 'four'))
    original = source_book(source, [('chapter.xhtml', body)], 'OPS')
    limits = DocumentLimits(max_nodes=4)
    with pytest.raises(ArtifactLimitError) as captured:
        read_epub_model(source, limits=limits)
    assert (captured.value.quota, captured.value.maximum, captured.value.path) == (
        'anchor identities', 4, 'epub.anchors[4]',
    )
    result = read_document(source, options=ImportOptions(document_limits=limits))
    assert not result.success and result.document is None
    issue, = result.issues
    assert issue.code == 'import.document-limit' and issue.measurement['quota'] == 'anchor identities'
    assert issue.location == f'{source}#epub.anchors[4]'
    assert source.read_bytes() == original
