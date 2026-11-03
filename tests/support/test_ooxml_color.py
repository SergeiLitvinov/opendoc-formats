"""Tests for shared DrawingML color resolution."""

import pytest
from lxml import etree
from opendoc_model import ColorValue

from opendoc_formats.ooxml.color import resolve_drawingml_color


def test_resolve_drawingml_color_uses_theme_and_ordered_modifiers():
    node = etree.fromstring(
        b'<a:solidFill xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        b'<a:schemeClr val="accent1"><a:shade val="50000"/><a:tint val="50000"/><a:alpha val="25000"/></a:schemeClr>'
        b"</a:solidFill>"
    )

    color, metadata = resolve_drawingml_color(node, {"accent1": "204060"})

    assert color is not None
    assert color.to_hex(include_alpha=True) == "#BCBEC040"
    assert metadata["color_theme"] == "accent1"


def test_unmodified_color_keeps_exact_model_components():
    node = etree.fromstring(b'<a:srgbClr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" val="204060"/>')
    color, _ = resolve_drawingml_color(node, {})
    assert color == ColorValue.from_hex('#204060')


def test_alpha_between_shades_preserves_full_precision_and_order():
    node = etree.fromstring(
        b'<a:srgbClr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" val="204060">'
        b'<a:shade val="50000"/><a:alpha val="25000"/><a:shade val="50000"/></a:srgbClr>')
    combined = etree.fromstring(
        b'<a:srgbClr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" val="204060">'
        b'<a:shade val="25000"/><a:alpha val="25000"/></a:srgbClr>')
    assert resolve_drawingml_color(node, {})[0] == resolve_drawingml_color(combined, {})[0]


@pytest.mark.parametrize('modifiers,expected', [
    ('<a:lumOff val="25000"/>', '#4080BF'),
    ('<a:lumMod val="200000"/>', '#4080C0'),
    ('<a:lumOff val="-12500"/>', '#102030'),
    ('<a:lumOff val="100000"/><a:lumMod val="50000"/>', '#7F7F7F'),
    ('<a:lumOff val="100000"/><a:lumMod val="50000"/><a:lumMod val="200000"/>', '#FFFFFF'),
])
def test_luminance_matches_native_hsl_and_final_rounding(modifiers, expected):
    node = etree.fromstring(('<a:srgbClr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                            'val="204060">'+modifiers+'</a:srgbClr>').encode())
    assert resolve_drawingml_color(node, {})[0].to_hex() == expected


@pytest.mark.parametrize('value', ['2147483648', '-2147483649', 'nan', '50%', '50000.0', '١٢٥٠٠'])
def test_luminance_integer_profile_rejects_unaccepted_lexical_values(value):
    node = etree.Element('{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr', val='204060')
    etree.SubElement(node, '{http://schemas.openxmlformats.org/drawingml/2006/main}lumMod', val=value)
    with pytest.raises(ValueError, match='DrawingML luminance'):
        resolve_drawingml_color(node, {})
