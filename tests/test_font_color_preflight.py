"""Color preflight must keep the document that owns inherited FONT references."""

from pathlib import Path

import opendoc_model as od
import pytest

from opendoc_formats import write_document


@pytest.mark.parametrize('inherited', [False, True])
def test_plain_export_preserves_valid_style_font_context_and_reports_color_loss(tmp_path, inherited):
    style = od.TextStyle(font_family='Own document font', color='auto')
    od.set_font_reference(style, od.FontReference('owned-font', 0))
    paragraph = od.Paragraph([od.TextRun('Visible text', od.TextStyle() if inherited else style)],
                             style_id='own' if inherited else None)
    font = (Path(__file__).parent/'native/data/ligature-post3.ttf').read_bytes()
    model = od.DocumentModel(sections=[od.Section(blocks=[paragraph])], styles={'own': style}, resources={
        'owned-font': od.Resource('owned-font', od.ResourceKind.FONT, 'font/ttf', data=font),
    })
    assert not model.validate()
    before = od.document_to_json(model)
    target = tmp_path/'visible.txt'
    report = write_document(model, target)
    assert report.success, report.issues
    assert target.read_text(encoding='utf-8').strip() == 'Visible text'
    assert any(issue.feature == 'color-auto' for issue in report.issues)
    assert od.document_to_json(model) == before
    assert od.get_font_reference(model.styles['own']).resource_id == 'owned-font'
    assert model.resources['owned-font'].data == font


def test_genuinely_missing_font_resource_still_refuses_before_replacing_output(tmp_path):
    style = od.TextStyle(font_family='Own document font')
    od.set_font_reference(style, od.FontReference('missing-font'))
    model = od.DocumentModel(sections=[od.Section(blocks=[od.Paragraph([od.TextRun('Visible')], style_id='own')])],
                             styles={'own': style})
    target = tmp_path/'kept.txt'
    target.write_bytes(b'previous output')
    report = write_document(model, target)
    assert not report.success
    assert any(issue.feature == 'export.invalid-model' and 'unknown font resource' in issue.message for issue in report.issues)
    assert target.read_bytes() == b'previous output'
