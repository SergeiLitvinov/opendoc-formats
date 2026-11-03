"""DrawingML luminance changes HSL lightness, including signed and >100% source percentages."""

import pytest
from opendoc_model import document_from_json, document_to_json

from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document
from tests.readers.test_pptx_color_modifiers import own_colors

CASES = [('lum-mod', [('lumMod', 50000)]), ('lum-off', [('lumOff', 25000)]),
         ('mod-off', [('lumMod', 80000), ('lumOff', 20000)]),
         ('off-mod', [('lumOff', 20000), ('lumMod', 80000)]),
         ('mod-double', [('lumMod', 200000)]), ('off-negative', [('lumOff', -12500)]),
         ('shade-lum', [('shade', 50000), ('lumOff', 25000)]),
         ('lum-shade', [('lumOff', 25000), ('shade', 50000)]),
         ('clip-return', [('lumOff', 100000), ('lumMod', 50000)]),
         ('negative-return', [('lumMod', -100000), ('lumOff', 50000)]),
         ('grey-double', [('lumOff', 100000), ('lumMod', 50000), ('lumMod', 200000)]),
         ('grey-shade', [('lumOff', 100000), ('lumMod', 50000), ('shade', 50000)])]


@pytest.mark.parametrize('name,modifiers', CASES)
@pytest.mark.parametrize('chart', [False, True])
def test_luminance_text_and_fill_survive_two_json_cycles(tmp_path, name, modifiers, chart):
    source = own_colors(tmp_path, modifiers, chart=chart)
    original = source.read_bytes()
    model = read_document(source).document
    color = model.sections[0].blocks[0].content[0].style.color.to_hex()
    for index in range(2):
        meta = model.sections[0].blocks[1].properties['pptx']
        assert (meta['chart']['series'][0]['color'] if chart else meta['shape']['fill']) == color
        target = tmp_path / f'cycle-{index}.pptx'
        report = write_document(document_from_json(document_to_json(model)), target,
                                options=ExportOptions(pptx_profile=PptxProfile(layout='rebuild')))
        assert report.success, report.issues
        model = read_document(target).document
        assert model.sections[0].blocks[0].content[0].style.color.to_hex() == color
    assert source.read_bytes() == original
