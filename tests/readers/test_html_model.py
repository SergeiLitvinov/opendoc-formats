from pathlib import Path

import pytest

pytest.importorskip("bs4")
pytest.importorskip("tinycss2")

from opendoc_formats.readers.html_text import read_html_model

CORPUS = Path(__file__).parents[1] / "corpus/scientific-html.html"


@pytest.mark.parametrize('color', [
    '#123456', '#abc', 'RED', 'LightGoldenRodYellow', 'darkslategrey', 'transparent',
    'rgb(1, 2, 3)', 'rgba(1, 2, 3, 0.5)',
    'hsl(-240, 100%, 50%)', 'HSLA(+4.2e2,75%,40%,.5)', 'hsla(90, 25.5%, 40%, 2)',
    '#aBc7', '#12345678', 'rgb(10.5%, 20%, 100%)', 'RGBA(+1, 02, -0, 2.5e-1)',
])
def test_simple_stylesheet_and_inline_cascade_match_tinycss2(tmp_path, monkeypatch, color):
    from opendoc_model import document_to_json

    from opendoc_formats.readers.html_css import Cascade

    source = tmp_path/'inline.html'
    source.write_text('<style>/* top } ; */ p, span { /* declaration }; */ color:/* before }; */#010101 } '
                      '.own { color:'+color+' ! important } '
                      '#target { color:#aBcDeF; font-size:inherit } '
                      '.own { color:#654321; font-style:italic; display:flex; margin:16pt auto }'
                      '@media print { .own { color:blue } .own:last-child { break-after:auto } }'
                      '@page ta-page-1 { size: 612pt 792pt; }</style>'
                      '<p style="font-size:16px; text-align:RIGHT; font-family: \'Шрифт 文\', Alternate Sans, serif">'
                      '<span id="target" class="own" style="/* inline ; */font-weight:normal !IMPORTANT;'
                      'font-weight:/* before ; */BOLD; text-align:initial; white-space:unset; mix-blend-mode:multiply">Own</span>'
                      '<span style="display:none">Hidden</span></p>', encoding='utf-8')
    native = read_html_model(source)
    assert native.metadata.pop('engine') == 'bs4'
    monkeypatch.setattr(Cascade, '_simple_inline', lambda self, raw: None)
    monkeypatch.setattr(Cascade, '_simple_stylesheet', lambda self, raw: None)
    monkeypatch.setattr('opendoc_formats.readers.html_css.parse_static_css_color', lambda token: None)
    full = read_html_model(source)
    assert full.metadata.pop('engine') == 'bs4+tinycss2'
    assert document_to_json(native) == document_to_json(full)





@pytest.mark.parametrize(
    "css,expected",
    [
        ("p {color:red} .x {color:blue}", "#0000FF"),
        ("#a {color:red} .x {color:blue}", "#FF0000"),
        (".x {color:red} .x {color:blue}", "#0000FF"),
        (".x {color:red!important}", "#FF0000"),
    ],
)
def test_cascade_precedence(tmp_path, css, expected):
    path = tmp_path / "style.html"
    path.write_text(f'<style>{css}</style><p id="a" class="x">Text</p>', encoding="utf-8")
    assert read_html_model(path).sections[0].blocks[0].content[0].style.color.to_hex().upper() == expected


@pytest.mark.parametrize('rule', [
    '@import "https://example.invalid/a;b}.css";',
    "@IMPORT url('other.css') screen;",
    '@import url(./other.css);',
])
def test_native_cascade_ignores_import_and_preserves_following_rules(tmp_path, monkeypatch, rule):
    from opendoc_model import document_to_json

    from opendoc_formats.readers.html_css import Cascade

    source = tmp_path / 'imports.html'
    source.write_text(f'<style>{rule} p {{color:navy}}</style><p>Text</p>', encoding='utf-8')
    native = read_html_model(source)
    assert native.metadata.pop('engine') == 'bs4'
    assert native.sections[0].blocks[0].content[0].style.color.to_hex().lower() == '#000080'
    monkeypatch.setattr(Cascade, '_simple_stylesheet', lambda self, raw: None)
    reference = read_html_model(source)
    assert reference.metadata.pop('engine') == 'bs4+tinycss2'
    assert document_to_json(native) == document_to_json(reference)


def test_native_cascade_matches_unicode_and_hyphenated_identifiers(tmp_path, monkeypatch):
    from opendoc_model import document_to_json

    from opendoc_formats.readers.html_css import Cascade

    source = tmp_path / 'unicode.html'
    source.write_text(
        '<style>.отчёт > #-итог:first-child {color:navy} .--важно {font-weight:bold}</style>'
        '<div class="отчёт"><p id="-итог" class="--важно">Текст</p></div>', encoding='utf-8',
    )
    native = read_html_model(source)
    assert native.metadata.pop('engine') == 'bs4'
    style = native.sections[0].blocks[0].content[0].style
    assert style.color.to_hex().lower() == '#000080'
    assert style.bold
    monkeypatch.setattr(Cascade, '_simple_stylesheet', lambda self, raw: None)
    reference = read_html_model(source)
    assert reference.metadata.pop('engine') == 'bs4+tinycss2'
    assert document_to_json(native) == document_to_json(reference)


@pytest.mark.parametrize("value,engine", [
    ("CURRENTcolor", "bs4"),
    (r"current\43 olor", "bs4+tinycss2"),
])
def test_current_color_on_color_uses_parent_after_cascade(tmp_path, value, engine):
    path = tmp_path / "current-color.html"
    path.write_text(
        f'<style>span {{color:{value} !important}}</style><p style="color:#123456">'
        '<span style="color:red">Own</span></p>', encoding="utf-8",
    )
    document = read_html_model(path)
    assert document.metadata["engine"] == engine
    assert document.sections[0].blocks[0].content[0].style.color.to_hex() == "#123456"


def test_descendant_and_child_selectors_keep_all_matching_ancestor_paths(tmp_path, monkeypatch):
    from opendoc_model import document_to_json

    from opendoc_formats.readers.html_css import Cascade

    path = tmp_path / "nested.html"
    path.write_text(
        '<style>article > div span {color:blue} article > span {color:red}'
        'article span {color:green}</style>'
        '<article><div><div><p><span>Nested</span></p></div></div></article>',
        encoding="utf-8",
    )
    native = read_html_model(path)
    assert native.metadata.pop("engine") == "bs4"
    assert native.sections[0].blocks[0].content[0].style.color.to_hex().upper() == "#0000FF"
    monkeypatch.setattr(Cascade, "_simple_stylesheet", lambda self, raw: None)
    full = read_html_model(path)
    assert full.metadata.pop("engine") == "bs4+tinycss2"
    assert document_to_json(native) == document_to_json(full)


def test_sibling_selectors_match_elements_and_stay_under_one_parent(tmp_path):
    path = tmp_path / "siblings.html"
    path.write_text(
        '<style>h2 + p {color:blue} h2 ~ p {font-weight:bold}</style>'
        '<section><h2>Heading</h2><!-- skip --> <p>Near</p><div></div><p>Far</p></section>'
        '<section><p>Other parent</p></section>', encoding="utf-8",
    )
    document = read_html_model(path)
    assert document.metadata["engine"] == "bs4"
    styles = {block.plain_text: block.content[0].style for block in document.sections[0].blocks if block.plain_text}
    assert styles["Near"].color.to_hex().upper() == "#0000FF"
    assert styles["Near"].bold and styles["Far"].bold
    assert styles["Far"].color.to_hex() == "#000000"
    assert not styles["Other parent"].bold


def test_attribute_selectors_apply_specificity_and_case_sensitive_data_values(tmp_path):
    path = tmp_path / "attributes.css.html"
    path.write_text(
        '<style>p[lang] {color:green} p[DATA-tone="Accent"] {color:blue}'
        'p[data-empty=""] {font-style:italic} p {color:red}</style>'
        '<p lang="ru" data-tone="Accent" data-empty="">Exact</p>'
        '<p lang="ru" data-tone="accent">Different</p><p>Absent</p>', encoding="utf-8",
    )
    document = read_html_model(path)
    assert document.metadata["engine"] == "bs4"
    styles = [block.content[0].style for block in document.sections[0].blocks]
    assert [style.color.to_hex().upper() for style in styles] == ["#0000FF", "#008000", "#FF0000"]
    assert [style.italic for style in styles] == [True, False, False]


def test_structural_pseudo_classes_ignore_non_element_siblings(tmp_path):
    path = tmp_path / "structural.html"
    path.write_text(
        '<style>section > p:FIRST-child {color:blue} p:last-child {font-weight:bold}'
        'p:only-child {font-style:italic} p {color:red}</style>'
        '<section><!-- before --><p>First</p> <p>Last</p><!-- after --></section>'
        '<section> <p>Only</p> </section>', encoding="utf-8",
    )
    document = read_html_model(path)
    assert document.metadata["engine"] == "bs4"
    styles = [block.content[0].style for block in document.sections[0].blocks]
    assert [(style.color.to_hex().upper(), style.bold, style.italic) for style in styles] == [
        ("#0000FF", False, False), ("#FF0000", True, False), ("#0000FF", True, True),
    ]


def test_nested_relative_sizes_and_whitespace(tmp_path):
    path = tmp_path / "size.html"
    path.write_text(
        '<html style="font-size:10pt"><body><div style="font-size:2em"><p style="font-size:50%">A\n <b>B</b> C</p>'
        '<p style="font-size:2rem">D</p></div></body></html>'
    )
    a, b = read_html_model(path).sections[0].blocks
    assert a.plain_text == "A B C" and a.content[0].style.font_size.pt == 10
    assert b.content[0].style.font_size.pt == 20




def test_external_assets_opt_in_and_svg_sanitizing(tmp_path):
    path = tmp_path / "input.html"
    (tmp_path / "asset.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script>'
        '<rect width="3" height="3" onclick="run()"/><image href="https://example.org/a"/></svg>'
    )
    path.write_text('<p><img src="asset.svg"></p>')
    restricted = read_html_model(path)
    assert set(restricted.resources) == {"html-original-source"}
    assert restricted.resources["html-original-source"].data == path.read_bytes()
    model = read_html_model(path, resource_root=tmp_path)
    data = next(iter(model.resources.values())).data.decode()
    assert "script" not in data and "onclick" not in data and "https://example.org/a" not in data
    assert model.metadata["html"]["warnings"]
    path.write_text('<p><img src="../outside.png"></p>')
    restricted = read_html_model(path, resource_root=tmp_path)
    assert set(restricted.resources) == {"html-original-source"}
    assert restricted.resources["html-original-source"].data == path.read_bytes()






def test_nested_underline_and_inline_preserved_spaces(tmp_path):
    path = tmp_path / "inline.html"
    path.write_text('<p><u><b>Decorated</b></u></p><p><span style="white-space:pre">  x  </span></p>')
    first, second = read_html_model(path).sections[0].blocks
    assert first.content[0].style.underline and first.content[0].style.bold
    assert second.plain_text == "  x  "


def test_unsupported_active_attributes_and_background_are_reported(tmp_path):
    path = tmp_path / "attributes.html"
    path.write_text('<p onclick="run()" style="background-color:red;font-weight:BOLD">Visible</p>')
    model = read_html_model(path)
    assert model.sections[0].blocks[0].content[0].style.bold
    assert {item["feature"] for item in model.metadata["html"]["warnings"]} == {"html-css", "html-content"}


def test_inline_span_background_roundtrips_without_css_backend(tmp_path):
    from opendoc_formats import read_document, write_document

    path = tmp_path / "highlight.html"
    path.write_text(
        '<p style="color:#123456">Plain <span style="background-color:currentColor">Solid</span> '
        '<span style="background-color:rgba(90,110,120,.5)">Tint</span></p>', encoding="utf-8",
    )
    imported = read_document(path)
    assert imported.success, imported.issues
    assert imported.document.metadata["engine"] == "bs4"
    target = tmp_path / "roundtrip.html"
    report = write_document(imported.document, target)
    assert report.success, report.issues
    reopened = read_document(target)
    assert reopened.success, reopened.issues
    assert reopened.document.metadata["engine"] == "bs4"
    for document in (imported.document, reopened.document):
        runs = {run.text.strip(): run.style.background for run in document.sections[0].blocks[0].content}
        assert runs["Plain"] is None
        assert runs["Solid"].to_hex() == "#123456"
        assert runs["Tint"].to_hex().upper() == "#5A6E78"
        assert runs["Tint"].alpha == 0.5
