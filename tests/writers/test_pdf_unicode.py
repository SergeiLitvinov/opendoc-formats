"""Own synthetic OpenType ligatures: text repair must preserve painted pixels."""

from types import SimpleNamespace

import pytest
from opendoc_model import ConversionReport

from opendoc_formats.writers.pdf_unicode import _ligature_map, restore_ligature_unicode


def _font(path):
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    builder = FontBuilder(1000, isTTF=True)
    names = ['.notdef', 'space', 'f', 'i', 't', 'fi', 'ti']
    builder.setupGlyphOrder(names)
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        if name != 'space':
            pen.moveTo((40, 0))
            pen.lineTo((400, 0))
            pen.lineTo((400, 650))
            pen.lineTo((40, 650))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (500, 0) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupCharacterMap({32: 'space', 102: 'f', 105: 'i', 116: 't'})
    builder.setupNameTable({'familyName': 'OwnLigature', 'styleName': 'Regular', 'psName': 'OwnLigature-Regular'})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    addOpenTypeFeaturesFromString(builder.font, 'feature liga { sub f i by fi; sub t i by ti; } liga;')
    builder.save(path)


def test_native_ligatures_preserve_text_and_pixels(tmp_path):
    fitz = pytest.importorskip('pymupdf')
    pytest.importorskip('fontTools')
    _font(tmp_path / 'own.ttf')
    story = fitz.Story(html='<p>fi ti fi</p>', user_css=(
        '@font-face {font-family:Own;src:url(own.ttf);} p {font-family:Own;font-size:20pt;}'
    ), archive=fitz.Archive(str(tmp_path)))
    pdf = story.write_with_links(lambda *_: (fitz.Rect(0, 0, 240, 200), fitz.Rect(20, 20, 220, 180), fitz.Identity))
    try:
        before = pdf[0].get_pixmap().samples
        assert ''.join(pdf[0].get_text().split()) != 'fitifi'
        report = ConversionReport(None)
        restore_ligature_unicode(pdf, report, 'sections[0]')
        # Reload ensures the native font cache does not conceal the amended stream.
        with fitz.open(stream=pdf.tobytes(), filetype='pdf') as result:
            assert ''.join(result[0].get_text().split()) == 'fitifi'
            assert result[0].get_pixmap().samples == before
        assert report.metrics['pdf_ligature_unicode_mappings'] == 2
        assert report.success
    finally:
        pdf.close()


def test_ambiguous_or_unknown_components_are_not_invented():
    class Font(dict):
        def getBestCmap(self):  # noqa: N802 - fontTools protocol
            return {102: 'f', 105: 'i', 116: 't'}

        def getGlyphID(self, glyph):  # noqa: N802 - fontTools protocol
            return 42

    ligatures = {'f': [SimpleNamespace(Component=['i'], LigGlyph='lig')],
                 't': [SimpleNamespace(Component=['i'], LigGlyph='lig')]}
    font = Font(GSUB=SimpleNamespace(table=SimpleNamespace(LookupList=SimpleNamespace(Lookup=[
        SimpleNamespace(LookupType=4, SubTable=[SimpleNamespace(ligatures=ligatures)])
    ]))))
    assert _ligature_map(font) == {}
    ligatures['t'][0].Component = ['unknown']
    assert _ligature_map(font) == {}
