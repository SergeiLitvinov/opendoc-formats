"""Exact text preservation detects changes hidden by object/length counts."""

import pytest
from opendoc_model.diagnostics import ConversionReport
from opendoc_model.document_model import DocumentModel, Paragraph, Section, Table, TableCell, TableRow, TextRun
from opendoc_model.text_quality_policy import TextPreservationPolicy

from opendoc_formats.support.inspection import DocumentInspection, compare_inspections, inspect_document_model


def _inspect(texts, nested=False):
    blocks = [Paragraph(content=[TextRun(text)]) for text in texts]
    if nested:
        blocks = [Table(rows=[TableRow(cells=[TableCell(blocks=blocks)])])]
    return inspect_document_model(DocumentModel(sections=[Section(blocks=blocks)]))


@pytest.mark.parametrize("before, after, accepted, unmatched", [
    (["First", "Second"], ["Second", "First", "Added"], True, 0),
    (["Same", "Same"], ["Same", "Same"], True, 0),
    (["Same", "Same"], ["Same"], False, 1),
    (["abcdef"], ["abc"], False, 1),
    (["abcdef"], ["ghijkl"], False, 1),
    (["First Second"], ["First", "Second"], False, 1),
    (["First", "Second"], ["FirstSecond"], False, 2),
    (["First "], ["First"], False, 1),
    ([""], [], True, 0),
])
@pytest.mark.parametrize("nested", [False, True])
def test_text_policy_is_exact_and_multiplicity_aware(tmp_path, before, after, accepted, unmatched, nested):
    report = ConversionReport(tmp_path / "result.json")
    comparison = compare_inspections(_inspect(before, nested), _inspect(after, nested))
    assert TextPreservationPolicy().evaluate(report, comparison) is accepted
    assert report.metrics["text_quality_gate"]["unmatched_source_paragraphs"] == unmatched


def test_unavailable_inventory_does_not_pass_as_empty_text(tmp_path):
    report = ConversionReport(tmp_path / "result.html")
    comparison = compare_inspections(_inspect(["Text"]), DocumentInspection(None, "html"))
    assert TextPreservationPolicy().evaluate(report, comparison) is False
    assert report.metrics["text_quality_gate"]["unmatched_source_paragraphs"] is None
