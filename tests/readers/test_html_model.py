from pathlib import Path

import pytest

pytest.importorskip("bs4")
pytest.importorskip("tinycss2")

from opendoc_formats.readers.html_text import read_html_model

CORPUS = Path(__file__).parents[1] / "corpus/scientific-html.html"






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
    assert not read_html_model(path).resources
    model = read_html_model(path, resource_root=tmp_path)
    data = next(iter(model.resources.values())).data.decode()
    assert "script" not in data and "onclick" not in data and "https://example.org/a" not in data
    assert model.metadata["html"]["warnings"]
    path.write_text('<p><img src="../outside.png"></p>')
    assert not read_html_model(path, resource_root=tmp_path).resources






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
