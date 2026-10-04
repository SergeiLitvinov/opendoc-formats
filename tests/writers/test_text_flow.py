"""Text flow allows paragraph resegmentation, not changes to words or order."""

import pytest
from opendoc.diagnostics import ConversionReport
from opendoc.document_model import DocumentModel, Paragraph, Section, Table, TableCell, TableRow, TextRun
from opendoc.text_quality_policy import TextPreservationPolicy, resolve_text_policy

from opendoc_formats.support.inspection import compare_inspections, inspect_document_model


def _inspect(texts, nested):
    blocks = [Paragraph(content=[TextRun(text)]) for text in texts]
    if nested:
        blocks = [Table(rows=[TableRow(cells=[TableCell(blocks=blocks)])])]
    return inspect_document_model(DocumentModel(sections=[Section(blocks=blocks)]))


@pytest.mark.parametrize("before, after, accepted", [
    (["First Second"], ["First", "Second"], True),
    (["First", "Second"], ["First Second"], True),
    ([" First\tSecond\nThird "], ["First Second Third"], True),
    (["First\u00a0Second"], ["First Second"], True),
    (["First", "Second"], ["Second", "First"], False),
    (["Same", "Same"], ["Same"], False),
    (["Original"], ["Replaced"], False),
    (["First"], ["first"], False),
    (["First!"], ["First"], False),
    (["First"], ["First Added"], False),
    (["word"], ["wo", "rd"], False),
    (["long-", "word"], ["longword"], False),
    (["", "  "], [], True),
])
@pytest.mark.parametrize("nested", [False, True])
def test_flow_normalizes_only_whitespace_and_paragraph_boundaries(tmp_path, before, after, accepted, nested):
    comparison = compare_inspections(_inspect(before, nested), _inspect(after, nested))
    report = ConversionReport(tmp_path / "output.json")
    assert TextPreservationPolicy("flow").evaluate(report, comparison) is accepted
    assert report.metrics["text_quality_gate"]["verified"] is True




def test_flow_without_measurement_is_unavailable(tmp_path):
    source, target = _inspect(["Text"], False), _inspect(["Text"], False)
    target.metadata.pop("text_flow")
    report = ConversionReport(tmp_path / "output.json")
    assert not TextPreservationPolicy("flow").evaluate(report, compare_inspections(source, target))
    assert report.metrics["text_quality_gate"]["source_characters"] is None


def test_conflicting_modes_are_rejected():
    with pytest.raises(ValueError):
        resolve_text_policy(True, "flow")
    with pytest.raises(ValueError):
        resolve_text_policy(False, "invalid")
