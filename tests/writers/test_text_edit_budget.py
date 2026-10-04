"""Word-edit budgets are exact within the threshold and bounded in resource use."""

from itertools import product

import pytest
from opendoc.diagnostics import ConversionReport
from opendoc.text_edit_budget import bounded_word_distance
from opendoc.text_quality_policy import TextPreservationPolicy


def _reference(left, right):
    matrix = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for row in range(len(left) + 1):
        matrix[row][0] = row
    for column in range(len(right) + 1):
        matrix[0][column] = column
    for row in range(1, len(left) + 1):
        for column in range(1, len(right) + 1):
            matrix[row][column] = min(matrix[row - 1][column] + 1, matrix[row][column - 1] + 1,
                                      matrix[row - 1][column - 1] + (left[row - 1] != right[column - 1]))
    return matrix[-1][-1]


def test_banded_distance_against_full_matrix_for_all_short_sequences():
    sequences = [list(sequence) for size in range(4) for sequence in product("ab", repeat=size)]
    for left, right in product(sequences, repeat=2):
        expected = _reference(left, right)
        for limit in range(4):
            distance, verified = bounded_word_distance(left, right, limit)
            assert verified
            assert distance == (expected if expected <= limit else None), (left, right, limit)


@pytest.mark.parametrize("before, after, edits", [
    ("one two", "one three", 1), ("one two", "one", 1), ("one", "one two", 1),
    ("one two", "two one", 2), ("same same", "same", 1), ("word!", "word", 1),
])
def test_budget_detects_edits_and_reports_only_proven_counts(tmp_path, before, after, edits):
    from opendoc.document_model import DocumentModel, Paragraph, Section, TextRun

    from opendoc_formats.support.inspection import compare_inspections, inspect_document_model

    def inspection(text):
        return inspect_document_model(DocumentModel(sections=[Section(blocks=[Paragraph(content=[TextRun(text)])])]))

    comparison = compare_inspections(inspection(before), inspection(after))
    for limit in [edits - 1, edits]:
        report = ConversionReport(tmp_path / "output.json")
        assert TextPreservationPolicy("flow", limit).evaluate(report, comparison) is (limit >= edits)
        gate = report.metrics["text_quality_gate"]
        assert gate["text_edits"] == (edits if limit >= edits else None)
        assert gate["text_edits_lower_bound"] == edits


def test_work_limit_returns_unknown_not_false_zero(monkeypatch):
    monkeypatch.setattr("opendoc.text_edit_budget.MAX_DISTANCE_CELLS", 1)
    assert bounded_word_distance(list("abc"), list("def"), 3) == (None, False)


@pytest.mark.parametrize("limit", [-1, True, 1.5])
def test_invalid_budgets_are_rejected(limit):
    with pytest.raises(ValueError):
        TextPreservationPolicy("flow", limit)


def test_token_inventory_is_bounded_and_equal_large_text_can_still_pass(tmp_path, monkeypatch):
    from opendoc.text_edit_budget import evaluate_text_edit_budget
    from opendoc.text_flow import TextFlowFingerprint

    monkeypatch.setattr("opendoc.text_flow.MAX_TEXT_TOKENS", 2)
    flow = TextFlowFingerprint()
    flow.add("one two three")
    snapshot = flow.to_dict()
    assert snapshot["token_count"] == 3
    assert snapshot["tokens"] is None
    report = ConversionReport(tmp_path / "output.json")
    assert evaluate_text_edit_budget(report, snapshot, snapshot, True, 1)
    changed = {**snapshot, "sha256": "different"}
    assert not evaluate_text_edit_budget(report, snapshot, changed, True, 1)
    assert report.metrics["text_quality_gate"]["verified"] is False
