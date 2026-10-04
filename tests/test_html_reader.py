"""Moved reader acceptance cases, independent of application converters."""
from pathlib import Path

import pytest
from opendoc import Formula, Table

from opendoc_formats.readers.html import read_html_model

CORPUS = Path(__file__).parent / "corpus/scientific-html.html"


def test_scientific_structure_css_and_order():
    model = read_html_model(CORPUS)
    assert not model.validate()
    assert model.metadata["html"]["warnings"] == []
    blocks = model.sections[0].blocks
    assert [block.plain_text for block in blocks[:7]] == [
        "Исследование",
        "До текста после ссылка.",
        "Важное",
        "Первый",
        "Вложенный",
        "Второй",
        "Измерения",
    ]
    assert blocks[0].style_id == "Heading1"
    assert blocks[1].content[0].style.color.to_hex() == "#778899"
    assert next(run for run in blocks[1].content if run.text == "текста").style.bold is False
    assert blocks[2].content[0].style.color.to_hex().lower() == "#aa0000"
    assert [block.properties["list_level"] for block in blocks[3:6]] == [0, 1, 0]
    assert blocks[3].properties["list_start"] == 3
    table = blocks[7]
    assert isinstance(table, Table)
    assert [p.plain_text for p in table.rows[1].cells[1].blocks] == ["12", "± 1"]
    assert table.rows[0].cells[0].blocks[0].content[0].style.bold
    assert any(isinstance(item, Formula) for item in blocks[8].content)
    assert len(model.resources) == 2
    assert 'viewBox="0 0 10 10"' in next(r.data.decode() for r in model.resources.values() if r.media_type == "image/svg+xml")
    assert blocks[-2].plain_text == " a  b\n c"

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
