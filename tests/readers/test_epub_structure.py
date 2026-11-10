"""Own EPUB fixtures for editable XHTML tables and MathML without legacy engines."""

import hashlib
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from opendoc_model import (
    ArtifactLimitError,
    Formula,
    FormulaFormat,
    ResourceKind,
    Table,
    document_from_json,
    document_to_json,
    get_font_reference,
    get_integration,
)
from opendoc_model.color import color_to_css
from opendoc_model.spacing import get_line_spacing

from opendoc_formats import read_document, write_document


def _book(source, body, assets=(), *, obfuscated=False):
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            """<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
          <rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>""",
        )
        manifest = "".join(f'<item id="{item_id}" href="{name}" media-type="{media}"/>' for item_id, name, media, _ in assets)
        archive.writestr(
            "OPS/book.opf",
            """<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">"""
            + ('<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier>ignored</dc:identifier>'
               '<dc:identifier id="uid">urn: own\t font\n</dc:identifier></metadata>' if obfuscated else '<metadata/>')
            + '<manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
            + manifest
            + """</manifest>
          <spine><itemref idref="c"/></spine></package>""",
        )
        if obfuscated:
            archive.writestr('META-INF/encryption.xml',
                             '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
                             'xmlns:e="http://www.w3.org/2001/04/xmlenc#"><e:EncryptedData>'
                             '<e:EncryptionMethod Algorithm="http://www.idpf.org/2008/embedding"/>'
                             '<e:CipherData><e:CipherReference URI="OPS/fonts/own.ttf"/></e:CipherData>'
                             '</e:EncryptedData></encryption>')
        archive.writestr("OPS/chapter.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body>' + body + "</body></html>")
        for _, name, _, payload in assets:
            archive.writestr("OPS/" + name, payload)


def test_recovered_chapter_keeps_well_formed_svg_and_mathml(tmp_path, monkeypatch):
    source = tmp_path / "mixed.epub"
    math_line = '        <p>Before&nbsp;<br><math xmlns="http://www.w3.org/1998/Math/MathML">' \
                '<mtext>&pi; &NotEqualTilde;</mtext><mi onclick="inert()">x</mi></math> after</p>'
    _book(source, f"""
{math_line}
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10">
          <title><![CDATA[Literal &pi;]]> &pi;</title>
          <defs><linearGradient id="paint" gradientUnits="userSpaceOnUse">
            <stop offset="0" stop-color="black"/>
          </linearGradient></defs>
          <rect id="shape" width="20" height="10" fill="url(#paint)"/>
        </svg>
    """)
    monkeypatch.setitem(sys.modules, 'bs4', None)
    result = read_document(source)
    assert result.success, result.issues
    blocks = result.document.sections[0].blocks
    assert blocks[0].plain_text.startswith('Before')
    assert blocks[0].plain_text.endswith('after')
    formula, = [inline for inline in blocks[0].content if isinstance(inline, Formula)]
    math = ET.fromstring(formula.value)
    assert math.find('{*}mi').text == 'x'
    assert math.find('{*}mtext').text == 'π ≂̸'
    resource, = [value for value in result.document.resources.values() if value.kind is ResourceKind.VECTOR_IMAGE]
    svg = ET.fromstring(resource.data)
    assert svg.get('viewBox') == '0 0 20 10'
    assert svg.find('.//{*}linearGradient').get('gradientUnits') == 'userSpaceOnUse'
    assert svg.find('{*}title').text == 'Literal &pi; π'
    event, = [issue for issue in result.issues if issue.code == 'epub.event-handler']
    assert f'line=2,column={math_line.index("<mi ")}/@onclick' in event.location
    assert any(issue.reason == 'recovered-markup' for issue in result.issues)


def test_tables_math_links_mixed_cells_order_and_json(tmp_path):
    source = tmp_path / "own.epub"
    _book(
        source,
        """<p>Before <math xmlns="http://www.w3.org/1998/Math/MathML" id="inline"><mi>x</mi></math> after</p>
      <table id="data"><caption>Own caption</caption><thead><tr><th colspan="2">Header</th></tr></thead>
      <tbody><tr><td rowspan="2">Left</td><td><a href="#target">Link</a></td></tr>
      <tr><td>First<p>Middle</p>Last<table id="nested"><tr><td>Nested</td></tr></table>Tail</td></tr></tbody></table>
      <math xmlns="http://www.w3.org/1998/Math/MathML" id="display" display="block"><mfrac><mn>1</mn><mn>2</mn></mfrac></math>
      <p id="target">End</p>""",
    )
    result = read_document(source)
    assert result.success and not result.assessment_complete
    assert {issue.reason for issue in result.issues} == {"source-package-xml"}
    blocks = result.document.sections[0].blocks
    assert len(blocks) == 5 and blocks[0].plain_text == "Before x after" and blocks[1].plain_text == "Own caption"
    inline = blocks[0].content[1]
    assert isinstance(inline, Formula) and inline.format is FormulaFormat.MATHML and not inline.display
    table = blocks[2]
    assert isinstance(table, Table) and len(table.rows) == 3
    assert table.rows[0].cells[0].column_span == 2 and table.rows[0].cells[0].blocks[0].content[0].style.bold
    assert table.rows[1].cells[0].row_span == 2
    assert table.rows[1].cells[1].blocks[0].content[0].link == "#epub-chapter.xhtml--target"
    mixed = table.rows[2].cells[0].blocks
    assert [block.plain_text for block in mixed if not isinstance(block, Table)] == ["First", "Middle", "Last", "Tail"]
    assert isinstance(mixed[3], Table) and mixed[3].rows[0].cells[0].blocks[0].plain_text == "Nested"
    assert blocks[3].content[0].display and blocks[4].plain_text == "End"
    assert table.provenance.package_part == "/OPS/chapter.xhtml"
    assert inline.provenance.package_part == "/OPS/chapter.xhtml" and inline.provenance.object_id == "inline"
    restored = document_from_json(document_to_json(result.document))
    assert document_to_json(restored) == document_to_json(result.document)
    output = tmp_path / "own.html"
    report = write_document(restored, output)
    assert report.success, report.to_dict()
    exported = output.read_text(encoding="utf-8")
    assert exported.count("<table") == 2 and 'rowspan="2"' in exported and 'colspan="2"' in exported
    assert "mfrac" in exported and "Nested" in exported


@pytest.mark.parametrize("value", ["0", "-1", "999999", "bad"])
def test_invalid_cell_span_has_located_loss(tmp_path, value):
    source = tmp_path / "invalid.epub"
    _book(source, f'<table><tr><td id="cell" colspan="{value}">Own cell</td></tr></table>')
    result = read_document(source)
    assert result.success and result.document.sections[0].blocks[0].rows[0].cells[0].column_span == 1
    record = next(item for item in get_integration(result.document).preservation if item.issue.reason == "invalid-cell-span")
    assert record.issue.reason == "invalid-cell-span" and record.issue.location.endswith("OPS/chapter.xhtml#cell")
    assert record.provenance.package_part == "/OPS/chapter.xhtml"


def test_math_actions_and_script_text_are_not_executed_or_imported(tmp_path):
    source = tmp_path / "inert.epub"
    _book(
        source,
        """<p>Before<script>throw new Error("inert")</script><math xmlns="http://www.w3.org/1998/Math/MathML"
        id="math" onclick="run()"><mi>x</mi><script>run()</script></math> after</p>""",
    )
    result = read_document(source)
    assert result.success
    formula = next(item for item in result.document.sections[0].blocks[0].content if isinstance(item, Formula))
    assert "onclick" not in formula.value and "script" not in formula.value
    assert "throw new Error" not in result.document.sections[0].blocks[0].plain_text
    assert any(issue.reason == "math-profile-sanitized" for issue in result.issues)


@pytest.mark.parametrize("mode", ["tables", "containers"])
def test_table_profile_nesting_limits_reject_excessive_source(tmp_path, mode):
    source = tmp_path / "deep.epub"
    if mode == "tables":
        body = "<table><tr><td>" * 19 + "Own text" + "</td></tr></table>" * 19
    else:
        body = "<table><tr><td>" + "<div>" * 66 + "<p>Own text</p>" + "</div>" * 66 + "</td></tr></table>"
    _book(source, body)
    original = source.read_bytes()
    result = read_document(source)
    assert not result.success and result.document is None
    issue, = result.issues
    expected = ('table depth', 16) if mode == 'tables' else ('cell wrapper depth', 64)
    assert issue.code == 'import.document-limit'
    assert (issue.measurement['quota'], issue.measurement['maximum']) == expected
    from opendoc_formats.readers.epub_model import read_epub_model

    with pytest.raises(ArtifactLimitError) as captured:
        read_epub_model(source)
    assert (captured.value.quota, captured.value.maximum) == expected
    assert source.read_bytes() == original


def test_standalone_images_svg_and_inert_assets_roundtrip(tmp_path):
    import struct
    import zlib

    from opendoc_model import Image, ResourceKind

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\xff"))
        + chunk(b"IEND", b"")
    )
    source = tmp_path / "assets.epub"
    _book(
        source,
        """<p>Before</p><img id="picture" src="pic.png" alt="Own picture"/>
        <svg id="drawing" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" aria-label="Own vector">
        <rect width="10" height="10" fill="red" onclick="run()"/><script>run()</script>
        <image href="https://example.invalid/remote.png"/></svg><p>After</p>""",
        assets=(
            ("pic", "pic.png", "image/png", png),
            ("font", "font.woff", "font/woff", b"own inert font placeholder"),
            ("audio", "audio.ogg", "audio/ogg", b"own inert audio placeholder"),
        ),
    )
    result = read_document(source)
    assert result.success and not result.lossless and not result.assessment_complete
    blocks = result.document.sections[0].blocks
    assert [blocks[0].plain_text, blocks[-1].plain_text] == ["Before", "After"]
    assert len(blocks) == 4 and isinstance(blocks[1].content[0], Image) and isinstance(blocks[2].content[0], Image)
    assert result.document.resources["epub-pic"].data == png
    assert blocks[1].content[0].provenance.package_part == "/OPS/chapter.xhtml"
    vector = result.document.resources[blocks[2].content[0].resource_id]
    assert vector.kind is ResourceKind.VECTOR_IMAGE and b"viewBox" in vector.data
    assert b"onclick" not in vector.data and b"script" not in vector.data and b"https://" not in vector.data
    assert result.document.resources["epub-font"].kind is ResourceKind.ATTACHMENT
    assert result.document.resources["epub-font"].data == b"own inert font placeholder"
    assert any(issue.reason == "svg-profile-sanitized" for issue in result.issues)
    restored = document_from_json(document_to_json(result.document))
    assert restored.resources == result.document.resources and get_integration(restored) == get_integration(result.document)
    target = tmp_path / "assets.html"
    report = write_document(restored, target)
    assert report.success and not report.lossless, report.to_dict()
    assert any(issue.feature == "epub.asset" for issue in report.issues)
    exported = target.read_text(encoding="utf-8")
    assert "data:image/png;base64" in exported and "data:image/svg+xml;base64" in exported
    assert "own inert font placeholder" not in exported and "own inert audio placeholder" not in exported


def test_external_and_nonimage_references_do_not_alias_local_image(tmp_path):
    source = tmp_path / "references.epub"
    _book(
        source,
        '<img id="remote" src="https:pic.png" alt="Remote"/><img src="font.woff" alt="Not image"/>',
        assets=(
            ("pic", "pic.png", "image/png", b"own unused placeholder"),
            ("font", "font.woff", "font/woff", b"own inert font placeholder"),
        ),
    )
    result = read_document(source)
    assert result.success
    assert [block.plain_text for block in result.document.sections[0].blocks] == ["Remote", "Not image"]
    assert len([issue for issue in result.issues if issue.reason == "missing-image"]) == 2


def test_inline_svg_resource_collision_preserves_manifest_asset(tmp_path):
    import hashlib

    from opendoc_formats.readers.html_resources import clean_xml

    svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'
    digest = hashlib.sha256(clean_xml(svg, "svg", lambda *args: None).encode()).hexdigest()
    item_id = "inline-svg-" + digest
    source = tmp_path / "collision.epub"
    _book(source, svg + svg, assets=((item_id, "other.png", "image/png", b"own inert other asset"),))
    result = read_document(source)
    assert result.success
    resources = result.document.resources
    assert resources["epub-" + item_id].data == b"own inert other asset"
    images = [block.content[0] for block in result.document.sections[0].blocks]
    assert images[0].resource_id == images[1].resource_id and images[0].resource_id != "epub-" + item_id
    assert len(resources) == 4
    assert b"rect" in resources[images[0].resource_id].data


@pytest.mark.parametrize('native', [False, True])
def test_css_link_and_style_follow_chapter_order(tmp_path, monkeypatch, native):
    source = tmp_path / 'css-order.epub'
    _book(source, '<style>.before {color:#111111}</style><link rel="stylesheet" href="style.css"/>'
          '<style>.after {color:#333333}</style><p class="before">Before</p><p class="after">After</p>',
          assets=(('css', 'style.css', 'text/css', b'.before {color:#222222} .after {color:#222222}'),))
    if native:
        monkeypatch.setitem(sys.modules, 'bs4', None)
    imported = read_document(source)
    assert imported.success, imported.issues
    assert [block.content[0].style.color for block in imported.document.sections[0].blocks] == ['#222222', '#333333']


@pytest.mark.parametrize('native', [False, True])
def test_css_structural_selectors_share_native_matcher(tmp_path, monkeypatch, native):
    source = tmp_path / 'css-structure.epub'
    _book(source, '<style>div p > span.a.b:first-child {color:#123456}'
          'span.a + span[data-note="yes"] {font-style:italic}'
          'span.a ~ strong {font-weight:normal}</style>'
          '<div><p>Text <span class="a b">First</span> <span data-note="yes">Adjacent</span>'
          '<strong>Later</strong></p></div><p><span class="a b">Outside</span></p>')
    if native:
        monkeypatch.setitem(sys.modules, 'bs4', None)
    imported = read_document(source)
    assert imported.success, imported.issues
    first, outside = imported.document.sections[0].blocks
    runs = {run.text: run.style for run in first.content if run.text}
    assert runs['First'].color == '#123456'
    assert runs['Adjacent'].italic
    assert not runs['Later'].bold
    assert outside.content[0].style.color is None


def test_css_importance_precedes_specificity_and_does_not_follow_inherited_values(tmp_path):
    source = tmp_path / 'css-important.epub'
    _book(source, '<style>.keep {color:#111111 ! /* comment */ IMPORTANT; color:#222222}'
          '#first {color:#333333} strong {font-weight:normal}</style>'
          '<p id="first" class="keep" style="color:#444444">Parent'
          '<span style="color:#555555">Child</span><strong>Normal</strong></p>'
          '<p class="keep" style="color:#666666 !important; color:#777777">Inline</p>')
    imported = read_document(source)
    assert imported.success, imported.issues
    first, second = imported.document.sections[0].blocks
    runs = {run.text: run.style for run in first.content if run.text}
    assert runs['Parent'].color == '#111111'
    assert runs['Child'].color == '#555555'
    assert not runs['Normal'].bold
    assert second.content[0].style.color == '#666666'


def test_css_functional_and_named_colors_survive_epub_export(tmp_path, monkeypatch):
    source = tmp_path / 'css-color.epub'
    _book(source, '<p style="color:rgba(10,20,30,0.5);color:lab(1 2 3);'
          'background-color:hsl(120,100%,25%)">Color</p><p style="color:LightGoldenRodYellow">Named</p>')
    monkeypatch.setitem(sys.modules, 'bs4', None)
    imported = read_document(source)
    assert imported.success, imported.issues
    document = imported.document
    target = tmp_path / 'color-roundtrip.epub'
    result = write_document(document_from_json(document_to_json(document)), target)
    assert result.success, result.issues
    for model in (document, read_document(target).document):
        named = model.sections[0].blocks[1].content[0].style.color
        assert color_to_css(named).lower() == '#fafad2'
        style = model.sections[0].blocks[0].content[0].style
        assert style.color.alpha == 0.5
        assert style.color.components == pytest.approx((10/255, 20/255, 30/255))
        assert color_to_css(style.background) == '#008000'
    assert any(record.issue.reason == 'unsupported-css-value' for record in get_integration(document).preservation)


@pytest.mark.parametrize('native', [False, True])
def test_css_relative_font_sizes_follow_root_and_parent(tmp_path, monkeypatch, native):
    source = tmp_path / 'font-sizes.epub'
    _book(source, '<style>html{font-size:20px}body{font-size:120%}div{font-size:2em}'
          'p{font-size:50%}</style><div><p>Parent<span style="font-size:2em">Child</span>'
          '<span style="font-size:1.5rem">Root</span></p></div>')
    if native:
        monkeypatch.setitem(sys.modules, 'bs4', None)
    result = read_document(source)
    assert result.success, result.issues
    paragraph, = result.document.sections[0].blocks
    assert [(run.text, run.style.font_size.pt) for run in paragraph.content] == [
        ('Parent', 18), ('Child', 36), ('Root', 22.5),
    ]


@pytest.mark.parametrize('native', [False, True])
def test_css_does_not_apply_inactive_stylesheets_to_screen(tmp_path, monkeypatch, native):
    source = tmp_path / 'css-media.epub'
    _book(source, '<style media="print, SCREEN">p {color:#123456}</style>'
          '<style id="print" media="print">p {color:#ffffff !important}</style>'
          '<link id="conditional" rel="stylesheet" media="screen and (min-width: 1000px)" href="other.css"/>'
          '<link id="alternate" rel="alternate stylesheet" href="other.css"/><p>Text</p>',
          assets=(('css', 'other.css', 'text/css', b'p {color:#000000 !important}'),))
    if native:
        monkeypatch.setitem(sys.modules, 'bs4', None)
    result = read_document(source)
    assert result.success, result.issues
    assert result.document.sections[0].blocks[0].content[0].style.color == '#123456'
    records = get_integration(result.document).preservation
    assert {(record.issue.reason, record.issue.location.split('#')[-1])
            for record in records if record.issue.code == 'epub.css'} == {
        ('unsupported-stylesheet-media', 'print/@media'),
        ('unsupported-stylesheet-media', 'conditional/@media'),
        ('alternate-stylesheet', 'alternate/@rel'),
    }


def test_css_paragraph_alignment_survives_epub_roundtrip(tmp_path, monkeypatch):
    source = tmp_path / 'alignment.epub'
    _book(source, '<style>.outer{text-align:right}.outer > .local{text-align:center}'
          'td{text-align:justify}</style><div class="outer"><p>Inherited</p>'
          '<p class="local">Local</p></div><table><tr><td><p>Cell</p></td></tr></table>')
    monkeypatch.setitem(sys.modules, 'bs4', None)
    imported = read_document(source)
    assert imported.success, imported.issues
    target = tmp_path / 'alignment-roundtrip.epub'
    result = write_document(document_from_json(document_to_json(imported.document)), target)
    assert result.success, result.issues
    restored = read_document(target)
    assert restored.success, restored.issues
    for document in (imported.document, restored.document):
        inherited, local, table = document.sections[0].blocks
        assert (inherited.alignment, local.alignment, table.rows[0].cells[0].blocks[0].alignment) == (
            'right', 'center', 'justify',
        )


def test_css_white_space_keeps_whitespace_only_runs_and_wrapping_mode(tmp_path, monkeypatch):
    source = tmp_path / 'whitespace.epub'
    _book(source, '<pre>A<span>\n  \t\n</span>B</pre>'
          '<p style="white-space:pre-wrap">C<span>  </span>D</p>'
          '<p>X<span style="white-space:pre">\n  </span>Y</p>')
    monkeypatch.setitem(sys.modules, 'bs4', None)
    imported = read_document(source)
    assert imported.success, imported.issues
    target = tmp_path / 'whitespace-roundtrip.epub'
    report = write_document(document_from_json(document_to_json(imported.document)), target)
    assert report.success, report.issues
    restored = read_document(target)
    assert restored.success, restored.issues
    for model in (imported.document, restored.document):
        pre, wrap, inline = model.sections[0].blocks
        assert (pre.plain_text, wrap.plain_text, inline.plain_text) == ('A\n  \t\nB', 'C  D', 'X\n  Y')
        assert pre.properties['epub_white_space'] == 'pre'
        assert wrap.properties['epub_white_space'] == 'pre-wrap'
        assert inline.content[1].properties['epub_white_space'] == 'pre'


def test_css_paragraph_margins_and_indent_survive_epub_roundtrip(tmp_path, monkeypatch):
    source = tmp_path / 'indent.epub'
    _book(source, '<style>div{font-size:20pt;text-indent:1em;margin-left:30pt}'
          '.own{font-size:10pt;margin:0 2em 6pt 40pt;margin-left:8px;margin:9pt 10%;text-indent:-.5em}'
          '</style><div><p class="own">Own</p><p style="font-size:8pt">Inherited</p>'
          '<p style="margin:3pt 4pt!important;margin-top:50pt">Important</p></div>')
    monkeypatch.setitem(sys.modules, 'bs4', None)
    imported = read_document(source)
    assert imported.success, imported.issues
    target = tmp_path / 'indent-roundtrip.epub'
    report = write_document(document_from_json(document_to_json(imported.document)), target)
    assert report.success, report.issues
    restored = read_document(target)
    assert restored.success, restored.issues
    expected = {
        'left_indent_pt': 6, 'right_indent_pt': 20, 'space_before_pt': 0,
        'space_after_pt': 6, 'first_line_indent_pt': -5,
    }
    assert 'left_indent_pt' not in imported.document.sections[0].blocks[1].properties
    for model in (imported.document, restored.document):
        own, inherited, important = model.sections[0].blocks
        assert {name: own.properties[name] for name in expected} == expected
        assert inherited.properties['first_line_indent_pt'] == 20
        assert inherited.properties.get('left_indent_pt', 0) == 0
        assert tuple(important.properties[name] for name in ('space_before_pt', 'space_after_pt',
                                                             'left_indent_pt', 'right_indent_pt')) == (3, 3, 4, 4)


def test_css_line_height_preserves_inherited_points_and_unitless_multiplier(tmp_path, monkeypatch):
    source = tmp_path / 'line-height.epub'
    _book(source, '<style>div{font-size:20pt;line-height:150%} .relative{line-height:1.4}'
          '.reset{line-height:normal}</style><div><p style="font-size:10pt">Inherited</p>'
          '<p class="relative">Relative</p><p class="reset">Normal</p></div>')
    monkeypatch.setitem(sys.modules, 'bs4', None)
    original = read_document(source)
    assert original.success, original.issues
    target = tmp_path / 'line-height-roundtrip.epub'
    exported = write_document(document_from_json(document_to_json(original.document)), target)
    assert exported.success, exported.issues
    restored = read_document(target)
    assert restored.success, restored.issues
    for document in (original.document, restored.document):
        fixed, relative, normal = document.sections[0].blocks
        assert (get_line_spacing(fixed).rule, get_line_spacing(fixed).value) == ('minimum', 30)
        assert (get_line_spacing(relative).rule, get_line_spacing(relative).value) == ('relative', 1.4)
        assert get_line_spacing(normal) is None


@pytest.mark.parametrize('obfuscated', [False, True])
def test_epub_local_font_face_binds_original_program_without_optional_engines(tmp_path, monkeypatch, obfuscated):
    source = tmp_path / 'font.epub'
    font = (Path(__file__).resolve().parents[1] / 'native/data/ligature-post3.ttf').read_bytes()
    css = b'@font-face{font-family:"A&B + Symbols: Edition #2";src:url("../fonts/own.ttf")}' \
          b'p{font-family:"A&B + Symbols: Edition #2"}'
    key = hashlib.sha1(b'urn:ownfont', usedforsecurity=False).digest()
    payload = bytes(value ^ key[index % 20] for index, value in enumerate(font[:1040])) + font[1040:] if obfuscated else font
    _book(source, '<link rel="stylesheet" href="styles/main.css"/><p>fit</p>', obfuscated=obfuscated,
          assets=(('css', 'styles/main.css', 'text/css', css), ('font', 'fonts/own.ttf', 'font/ttf', payload)))
    for name in ('bs4', 'tinycss2', 'fontTools'):
        monkeypatch.setitem(sys.modules, name, None)
    imported = read_document(source)
    assert imported.success, imported.issues
    document = document_from_json(document_to_json(imported.document))
    run = document.sections[0].blocks[0].content[0]
    assert run.style.font_family == 'A&B + Symbols: Edition #2'
    reference = get_font_reference(run.style)
    assert reference is not None and reference.resource_id == ('epub-decoded-font-font' if obfuscated else 'epub-font')
    assert document.resources[reference.resource_id].kind is ResourceKind.FONT
    assert document.resources[reference.resource_id].data == font
    if obfuscated:
        assert document.resources['epub-font'].data == payload
        assert document.resources['epub-font'].kind is ResourceKind.ATTACHMENT
        document.metadata['identifier'] = 'urn: new\t identifier'
    target = tmp_path / 'font-roundtrip.epub'
    exported = write_document(document, target)
    assert exported.success, exported.issues
    with zipfile.ZipFile(target) as archive:
        if obfuscated:
            encryption = ET.fromstring(archive.read('META-INF/encryption.xml'))
            entry, = encryption.findall('{*}EncryptedData')
            assert entry.find('{*}EncryptionMethod').get('Algorithm') == 'http://www.idpf.org/2008/embedding'
            member = entry.find('{*}CipherData/{*}CipherReference').attrib['URI']
            assert member.startswith('OPS/fonts/')
            new_key = hashlib.sha1(b'urn:newidentifier', usedforsecurity=False).digest()
            assert archive.read(member) == (
                bytes(value ^ new_key[index % 20] for index, value in enumerate(font[:1040])) + font[1040:]
            )
            package = ET.fromstring(archive.read('OPS/book.opf'))
            assert any(item.get('href') == member.removeprefix('OPS/') and item.get('media-type') == 'font/ttf'
                       for item in package.findall('{*}manifest/{*}item'))
            assert all(b'data:font/' not in archive.read(name) for name in archive.namelist() if name.endswith('.xhtml'))
        else:
            assert 'META-INF/encryption.xml' not in archive.namelist()
    restored = read_document(target)
    assert restored.success, restored.issues
    run = restored.document.sections[0].blocks[0].content[0]
    reference = get_font_reference(run.style)
    assert reference is not None and restored.document.resources[reference.resource_id].data == font


def test_css_profile_preserves_supported_rules_and_locates_unsupported_source(tmp_path):
    source = tmp_path / "css.epub"
    css = (
        b".keep {color:#123456} @media print {p {color:red}} "
        b".keep {position:absolute; font-size:1.2.3pt} p:hover > span {font-weight:bold}"
    )
    _book(
        source,
        """<link rel="stylesheet" href="style.css"/><p id="first" class="keep">Own text</p>
      <p id="inline" style="display:grid; font-size:calc(12pt)">Other</p>""",
        assets=(("css", "style.css", "text/css", css),),
    )
    result = read_document(source)
    assert result.success
    text = result.document.sections[0].blocks[0].content[0]
    assert text.style.color == "#123456" and text.style.font_size is None
    records = [record for record in get_integration(result.document).preservation if record.issue.code == "epub.css"]
    assert {record.issue.reason for record in records} == {
        "complex-stylesheet",
        "unsupported-declaration",
        "invalid-font-size",
        "unsupported-selector",
        "unsupported-css-value",
    }
    source_css = [record for record in records if record.state.value == "opaque"]
    assert len(source_css) == 4 and all(record.provenance.package_part == "/OPS/style.css" for record in source_css)
    assert all(record.extra["resource_id"] == "epub-css" for record in source_css)
    assert result.document.resources["epub-css"].data == css
    inline = [record for record in records if record.state.value == "lost"]
    assert len(inline) == 2 and all(record.issue.location.endswith("chapter.xhtml#inline") for record in inline)
    restored = document_from_json(document_to_json(result.document))
    assert get_integration(restored) == get_integration(result.document)


def test_external_stylesheet_does_not_alias_local_css(tmp_path):
    source = tmp_path / "external-css.epub"
    _book(
        source,
        '<link rel="stylesheet" href="https:style.css"/><p>Own text</p>',
        assets=(("css", "style.css", "text/css", b"p {color:red}"),),
    )
    result = read_document(source)
    assert result.success and result.document.sections[0].blocks[0].content[0].style.color is None
    assert any(issue.reason == "external-stylesheet" for issue in result.issues)
