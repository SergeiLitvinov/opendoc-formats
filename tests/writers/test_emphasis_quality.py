"""Inspect serialized emphasis, including partial losses and strict publication."""

import pytest
from opendoc.document_model import DocumentModel, Paragraph, Section, TextRun, TextStyle
from opendoc.emphasis_quality import EmphasisInventory, EmphasisLossPolicy

from opendoc_formats.support.inspection import compare_inspections, inspect_document_model


def emphasis_document():
    return DocumentModel(sections=[Section(blocks=[Paragraph(content=[
        TextRun('Test', TextStyle(bold=True, italic=True)), TextRun(' plain'),
    ])])])


@pytest.mark.parametrize('limit', [-1, True, 0.1, '0'])
def test_invalid_emphasis_limit(limit):
    with pytest.raises(ValueError):
        EmphasisLossPolicy(limit)






def test_run_splitting_whitespace_and_paragraph_boundaries_do_not_change_emphasis(tmp_path):
    from opendoc.diagnostics import ConversionReport

    source = emphasis_document()
    target = DocumentModel(sections=[Section(blocks=[
        Paragraph(content=[TextRun('Te ', TextStyle(bold=True, italic=True))]),
        Paragraph(content=[TextRun('st', TextStyle(bold=True, italic=True)), TextRun('plain')]),
    ])])
    comparison = compare_inspections(inspect_document_model(source), inspect_document_model(target))
    report = ConversionReport(tmp_path / 'out.json')
    assert EmphasisLossPolicy(0).evaluate(report, comparison)




def test_emphasis_inventory_is_bounded(monkeypatch):
    monkeypatch.setattr('opendoc.emphasis_quality.MAX_EMPHASIS_RUNS', 2)
    inventory = EmphasisInventory()
    for bold in (True, False, True):
        inventory.add(TextRun('x', TextStyle(bold=bold)))
    assert inventory.to_dict()['runs'] is None
    assert inventory.to_dict()['characters'] == 3
