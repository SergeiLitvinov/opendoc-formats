"""Distinct EPUB source paths/fragments retain distinct targets through JSON and HTML export."""

import posixpath
import sys
import zipfile
from html import escape
from html.parser import HTMLParser
from threading import Event
from urllib.parse import quote, unquote
from xml.etree import ElementTree as ET

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
    get_integration,
    iter_anchors,
)

from opendoc_formats import ImportOptions, read_document, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.epub_anchors import EpubAnchors
from opendoc_formats.readers.epub_model import read_epub_model
from tests.binary_fixtures import own_png


def source_book(path, chapters, root, assets=(), *, spine_order=None):
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
        order = range(len(chapters)) if spine_order is None else spine_order
        spine = ''.join(f'<itemref idref="c{index}"/>' for index in order)
        archive.writestr(opf, '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata/>'
                        f'<manifest>{items}</manifest><spine>{spine}</spine></package>')
        for name, markup in chapters:
            archive.writestr(posixpath.join(root, name), '<html><head><meta charset="utf-8"/></head>'
                             '<body>'+markup+'</body></html>')
        for name, _, payload in assets:
            archive.writestr(posixpath.join(root, name), payload)
    return path.read_bytes()


def test_missing_internal_targets_report_source_href_after_all_chapters(tmp_path):
    path = tmp_path / 'missing.epub'
    source_book(path, [
        ('one.xhtml', '<p><a id="missing" href="two.xhtml#absent">Missing</a> '
         '<a id="valid" href="two.xhtml#present">Present</a> '
         '<a id="opaque" href="two.xhtml#shape">Opaque</a></p>'),
        ('two.xhtml', '<p id="present">Target</p><p><svg xmlns="http://www.w3.org/2000/svg">'
         '<clipPath><rect id="shape" width="5" height="5"/></clipPath></svg></p>'),
    ], 'OPS')
    document = read_epub_model(path)
    issues = [record.issue for record in get_integration(document).preservation
              if record.issue.reason == 'missing-link-target']
    assert [issue.location.split('#')[-1] for issue in issues] == ['missing/@href', 'opaque/@href']
    assert all('!/OPS/one.xhtml#' in issue.location for issue in issues)
    paragraph = document.sections[0].blocks[0]
    assert [run.link for run in paragraph.content if isinstance(run, TextRun) and run.link] == [
        '#epub-two.xhtml--absent', '#epub-two.xhtml--present', '#epub-two.xhtml--shape',
    ]


def test_duplicate_source_id_is_ambiguous_even_when_one_occurrence_is_unprojected(tmp_path):
    path = tmp_path / 'ambiguous.epub'
    source_book(path, [
        ('one.xhtml', '<p><a id="jump" href="two.xhtml#dup">Jump</a></p>'),
        ('two.xhtml', '<p id="dup">Visible</p><script id="dup">ignored</script>'),
    ], 'OPS')
    document = read_epub_model(path)
    issue, = [record.issue for record in get_integration(document).preservation if record.issue.code == 'epub.hyperlink']
    assert issue.reason == 'ambiguous-link-target' and issue.location.endswith('!/OPS/one.xhtml#jump/@href')


def test_repeated_spine_chapter_has_local_self_links_and_canonical_inbound_links(tmp_path):
    source = tmp_path / 'repeat.epub'
    source_book(source, [
        ('one.xhtml', '<p id="goal">Goal</p><p><a href="#goal">Self</a></p>'),
        ('two.xhtml', '<p><a href="one.xhtml#goal">Inbound</a></p>'),
    ], 'OPS', spine_order=(0, 1, 0))
    document = read_epub_model(source)
    destination = tmp_path / 'roundtrip.epub'
    result = write_document(document_from_json(document_to_json(document)), destination)
    assert result.success, result.issues
    for imported in (document, read_epub_model(destination)):
        first, middle, repeat = imported.sections
        first_id, repeat_id = (section.blocks[0].properties['anchor_id'] for section in (first, repeat))
        assert first_id != repeat_id and first.properties['anchor_id'] != repeat.properties['anchor_id']
        assert first.blocks[1].content[0].link == middle.blocks[0].content[0].link == '#' + first_id
        assert repeat.blocks[1].content[0].link == '#' + repeat_id
        assert not [record for record in get_integration(imported).preservation if record.issue.code == 'epub.hyperlink']


def test_table_row_and_cell_targets_survive_epub_roundtrip(tmp_path):
    source = tmp_path / 'table-targets.epub'
    source_book(source, [('one.xhtml', '<p><a href="#row">Row</a> <a href="#inline">Inline</a> '
                          '<a href="#nested">Nested</a></p><table><tr id="row">'
                          '<td id="inline">Text</td><td id="nested"><p>Nested paragraph</p></td></tr></table>')], 'OPS')
    document = read_epub_model(source)
    destination = tmp_path / 'roundtrip.epub'
    result = write_document(document_from_json(document_to_json(document)), destination)
    assert result.success, result.issues
    for imported in (document, read_epub_model(destination)):
        paragraph, table = imported.sections[0].blocks
        row, = table.rows
        targets = [row.properties['anchor_id'], *(cell.properties['anchor_id'] for cell in row.cells)]
        assert [run.link for run in paragraph.content if isinstance(run, TextRun) and run.link] == [
            '#' + target for target in targets
        ]
        assert all('anchor_id' not in block.properties for cell in row.cells for block in cell.blocks)
        assert not [record for record in get_integration(imported).preservation if record.issue.code == 'epub.hyperlink']


def test_unavailable_media_keeps_link_destination_without_fallback_text(tmp_path):
    source = tmp_path / 'missing-media.epub'
    source_book(source, [('one.xhtml', '<p><a href="#image">Image</a> <a href="#broken">SVG</a> '
                          '<a href="#embed">Object</a></p><img id="image" src="absent.png"/>'
                          '<p><svg id="broken"><x:g></x:g></svg><object id="embed"></object></p>')], 'OPS')
    document = read_epub_model(source)
    destination = tmp_path / 'roundtrip.epub'
    report = write_document(document_from_json(document_to_json(document)), destination)
    assert report.success, report.issues
    for imported in (document, read_epub_model(destination)):
        markers = {get_anchor(ref.node).id for ref in iter_anchors(imported)
                   if isinstance(ref.node, TextRun) and not ref.node.text}
        links = {run.link[1:] for run in imported.sections[0].blocks[0].content if isinstance(run, TextRun) and run.link}
        assert len(links) == 3 and links <= markers
        assert not [record for record in get_integration(imported).preservation if record.issue.code == 'epub.hyperlink']
    assert {'missing-image', 'svg-profile-sanitized', 'unsupported-object'} <= {
        record.issue.reason for record in get_integration(document).preservation
    }


def test_standalone_inert_container_keeps_anchor_and_structural_fallback(tmp_path):
    source = tmp_path / 'standalone.epub'
    source_book(source, [('one.xhtml', '<p><a href="#external">Go</a></p>'
                          '<object id="external"><p>Fallback</p></object><p>After</p>')], 'OPS')
    document = read_epub_model(source)
    destination = tmp_path / 'roundtrip.epub'
    report = write_document(document_from_json(document_to_json(document)), destination)
    assert report.success, report.issues
    for imported in (document, read_epub_model(destination)):
        link, marker, fallback, after = imported.sections[0].blocks
        assert link.content[0].link == '#' + marker.properties['anchor_id']
        assert [marker.plain_text, fallback.plain_text, after.plain_text] == ['', 'Fallback', 'After']
        assert not [record for record in get_integration(imported).preservation if record.issue.code == 'epub.hyperlink']


@pytest.mark.parametrize('native', [False, True])
def test_links_to_mathml_descendants_survive_cross_chapter_roundtrip(tmp_path, monkeypatch, native):
    source = tmp_path / 'math-target.epub'
    source_book(source, [
        ('one.xhtml', '<p><a href="two.xhtml#operand">Operand</a></p>'),
        ('two.xhtml', '<p><math xmlns="http://www.w3.org/1998/Math/MathML" id="equation">'
         '<mrow><mi id="operand">x</mi><mo>+</mo><mn>1</mn></mrow></math></p>'),
    ], 'OPS')
    if native:
        monkeypatch.setitem(sys.modules, 'bs4', None)
    imported_source = read_document(source)
    assert imported_source.success, imported_source.issues
    document = imported_source.document
    if native:
        assert document.metadata['engine'] == 'native-epub-xhtml'
    destination = tmp_path / 'roundtrip.epub'
    report = write_document(document_from_json(document_to_json(document)), destination)
    assert report.success, report.issues
    for imported in (document, read_epub_model(destination)):
        link = imported.sections[0].blocks[0].content[0].link
        formula, = [item for item in imported.sections[1].blocks[0].content if isinstance(item, Formula)]
        operand = ET.fromstring(formula.value).find('.//{http://www.w3.org/1998/Math/MathML}mi')
        assert operand is not None and operand.text == 'x' and link == '#' + operand.get('id')
        assert get_anchor(formula).id != operand.get('id')
        assert not [record for record in get_integration(imported).preservation if record.issue.code == 'epub.hyperlink']


@pytest.mark.parametrize('gradient', [None, 'direct', 'inherited', 'xlink'])
def test_static_svg_shape_target_survives_cross_chapter_roundtrip(tmp_path, gradient):
    source = tmp_path / 'svg-target.epub'
    paint = 'url(#paint)' if gradient else '#123456'
    definition = ''
    if gradient:
        stops = '<stop offset="0" stop-color="#123456"/><stop offset="1" stop-color="#abcdef"/>'
        if gradient == 'direct':
            definition = f'<defs><linearGradient id="paint" spreadMethod="reflect">{stops}</linearGradient></defs>'
        else:
            href = 'href' if gradient == 'inherited' else 'xlink:href'
            definition = (f'<defs><linearGradient id="paint" {href}="#base" spreadMethod="reflect"/>'
                          f'<linearGradient id="base">{stops}</linearGradient></defs>')
    source_book(source, [
        ('one.xhtml', '<p><a href="two.xhtml#shape">Shape</a></p>'),
        ('two.xhtml', '<p><svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
         'id="drawing" width="20" height="20">'
         f'{definition}<rect id="shape" width="5" height="6" fill="{paint}"/></svg></p>'),
    ], 'OPS')
    document = read_epub_model(source)
    destination = tmp_path / 'roundtrip.epub'
    report = write_document(document_from_json(document_to_json(document)), destination)
    assert report.success, report.issues
    with zipfile.ZipFile(destination) as archive:
        chapter = ET.fromstring(archive.read('OPS/chapter-2.xhtml'))
        shape = chapter.find('.//{http://www.w3.org/2000/svg}rect')
        assert shape is not None and shape.get('height') == '6'
        if gradient:
            definition = chapter.find('.//{http://www.w3.org/2000/svg}linearGradient')
            assert definition is not None and definition.get('spreadMethod') == 'reflect'
            assert shape.get('fill') == f"url(#{definition.get('id')})"
            if gradient != 'direct':
                base = chapter.findall('.//{http://www.w3.org/2000/svg}linearGradient')[1]
                assert definition.get('href') == '#' + base.get('id')
        else:
            assert shape.get('fill') == '#123456'
    for imported in (document, read_epub_model(destination)):
        link = imported.sections[0].blocks[0].content[0].link
        image, = [item for item in imported.sections[1].blocks[0].content if isinstance(item, Image)]
        svg = ET.fromstring(imported.resources[image.resource_id].data)
        shape = svg.find('.//{http://www.w3.org/2000/svg}rect')
        assert shape is not None and link == '#' + shape.get('id')
        if gradient:
            definition = svg.find('.//{http://www.w3.org/2000/svg}linearGradient')
            assert definition is not None and shape.get('fill') == f"url(#{definition.get('id')})"
        assert not [record for record in get_integration(imported).preservation if record.issue.code == 'epub.hyperlink']


@pytest.mark.parametrize('href', ['#first', '#missing', 'https://invalid.example/paint.svg#first'])
def test_inline_svg_rejects_unproved_gradient_inheritance(href):
    from opendoc_formats.support.inline_svg import inline_svg_tree

    with pytest.raises(ValueError, match='gradient'):
        inline_svg_tree('<svg xmlns="http://www.w3.org/2000/svg">'
                        f'<defs><linearGradient id="first" href="{href}"/></defs></svg>')


@pytest.mark.parametrize('target_name', ['shape', 'group', 'symbol'])
def test_svg_use_target_and_local_shape_reference_survive_epub_roundtrip(tmp_path, target_name):
    source = tmp_path / 'svg-use.epub'
    definitions = '<rect id="shape" width="5" height="6"/>'
    if target_name == 'group':
        definitions += '<use id="copy" href="#shape"/><g id="group"><use href="#copy"/></g>'
    if target_name == 'symbol':
        definitions = ('<symbol id="symbol" viewBox="0 0 10 10" preserveAspectRatio="xMaxYMin meet">'
                       f'{definitions}</symbol>')
    source_book(source, [('one.xhtml', '<p><a href="#instance">Instance</a></p>'
                          '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">'
                          f'<defs>{definitions}</defs><use id="instance" href="#{target_name}" x="7" '
                          'width="12" height="9"/></svg>')], 'OPS')
    document = read_epub_model(source)
    destination = tmp_path / 'roundtrip.epub'
    report = write_document(document_from_json(document_to_json(document)), destination)
    assert report.success, report.issues
    for imported in (document, read_epub_model(destination)):
        first, drawing = imported.sections[0].blocks
        image, = drawing.content
        svg = ET.fromstring(imported.resources[image.resource_id].data)
        shape = svg.find('.//{http://www.w3.org/2000/svg}rect')
        instance = svg.find('{http://www.w3.org/2000/svg}use')
        assert shape is not None and instance is not None
        tag = {'shape': 'rect', 'group': 'g', 'symbol': 'symbol'}[target_name]
        target = svg.find(f'.//{{http://www.w3.org/2000/svg}}{tag}')
        assert target is not None
        assert instance.get('href') == '#' + target.get('id') and instance.get('x') == '7'
        assert first.content[0].link == '#' + instance.get('id')
        if target_name == 'group':
            indirect = target.find('{http://www.w3.org/2000/svg}use')
            copy = svg.find('./{http://www.w3.org/2000/svg}defs/{http://www.w3.org/2000/svg}use')
            assert indirect.get('href') == '#' + copy.get('id')
            assert copy.get('href') == '#' + shape.get('id')
        if target_name == 'symbol':
            assert target.get('viewBox') == '0 0 10 10' and target.get('preserveAspectRatio') == 'xMaxYMin meet'
            assert (instance.get('width'), instance.get('height')) == ('12', '9')


@pytest.mark.parametrize('href', ['#instance', '#group', 'https://invalid.example/drawing.svg#shape'])
def test_inline_svg_use_rejects_cycles_and_external_targets(href):
    from opendoc_formats.support.inline_svg import inline_svg_tree

    with pytest.raises(ValueError, match='SVG use'):
        inline_svg_tree('<svg xmlns="http://www.w3.org/2000/svg"><g id="group">'
                        f'<use id="instance" href="{href}"/></g></svg>')


def test_inline_svg_use_rejects_exponential_expansion():
    from opendoc_formats.support.inline_svg import inline_svg_tree

    groups = ''.join(f'<g id="g{i}"><use href="#g{i-1}"/><use href="#g{i-1}"/></g>' for i in range(1, 18))
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><defs><rect id="g0"/>' + groups + '</defs><use href="#g17"/></svg>'
    with pytest.raises(ValueError, match='expansion exceeds'):
        inline_svg_tree(svg)


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
