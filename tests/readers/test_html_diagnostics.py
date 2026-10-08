from pathlib import Path

import pytest

pytest.importorskip("bs4")
pytest.importorskip("tinycss2")

from opendoc_model.document_codec import document_from_json, document_to_json

from opendoc_formats.readers.html_text import read_html_model

CORPUS = Path(__file__).parents[1] / "corpus/html-warnings.html"


def test_repeated_inline_and_nested_warnings_point_to_separate_blocks(tmp_path):
    source = tmp_path / "nested.html"
    source.write_text(
        '<div>Начало<p>Без проблем</p><span style="position:absolute">Хвост</span></div>'
        '<table><tr><td><p id="same" style="position:absolute">Ячейка</p></td></tr></table>'
        '<p id="same"><img src="missing.png"></p><p><img src="missing.png"></p>',
        encoding="utf-8",
    )
    model = document_from_json(document_to_json(read_html_model(source)))
    diagnostics = model.metadata["html"]
    css = [w for w in diagnostics["warnings"] if w["feature"] == "html-css"]
    assert len(css) == 2
    assert {diagnostics["locations"][w["location"]]["text"] for w in css} == {"Хвост", "Ячейка"}
    resources = [w for w in diagnostics["warnings"] if w["feature"] == "html-resource"]
    assert len(resources) == 2
    assert len({w["location"] for w in resources}) == 2
    for warning, block in zip(resources, model.sections[0].blocks[-2:], strict=True):
        assert warning["location"] == block.properties["html"]["block_id"]
        assert block.plain_text == ""
        assert diagnostics["locations"][warning["location"]]["images"][0]["source"] == "missing.png"


def test_source_ledger_roundtrip_and_inert_export(tmp_path):
    from opendoc_model import PreservationState, ResourceKind, get_integration

    from opendoc_formats import read_document, write_document

    source = tmp_path / "source.html"
    source.write_bytes(
        b'\xef\xbb\xbf<html><body>\n<script id="action">throw new Error("must remain inert")</script>\n'
        b'<p id="first" style="position:absolute">Own text</p>\n'
        b'<p id="second" style="position:absolute">Other text</p>\n'
        b'<p><img src="https://example.invalid/missing.png" alt="Own alt"></p></body></html>'
    )
    result = read_document(source)
    assert result.success and not result.assessment_complete and not result.lossless
    ledger = get_integration(result.document)
    losses = [item for item in ledger.preservation if item.state is PreservationState.LOST]
    assert {item.issue.code for item in losses} >= {"html-content", "html-css", "html-resource"}
    assert all(item.provenance.source_path == str(source) for item in losses)
    css = [item for item in losses if item.issue.code == "html-css"]
    assert {item.provenance.object_id for item in css} == {"first", "second"}
    assert {item.extra["source_line"] for item in css} == {3, 4}
    assert len({item.extra["block_location"] for item in css}) == 2
    resource = result.document.resources["html-original-source"]
    assert resource.kind is ResourceKind.ATTACHMENT and resource.data == source.read_bytes()
    # Retained markup does not claim that an external image payload was obtained.
    assert all(item.kind is ResourceKind.ATTACHMENT for item in result.document.resources.values())
    restored = document_from_json(document_to_json(result.document))
    assert get_integration(restored) == ledger
    assert restored.resources[resource.id] == resource
    json_file = tmp_path / "source.json"
    assert write_document(restored, json_file).success
    imported_json = read_document(json_file)
    assert imported_json.success and any(issue.code == "html-resource" for issue in imported_json.issues)
    target = tmp_path / "export.html"
    exported_report = write_document(restored, target)
    assert exported_report.success and not exported_report.lossless
    assert any(issue.feature == "html.source" for issue in exported_report.issues)
    exported = target.read_text(encoding="utf-8")
    assert "must remain inert" not in exported and 'src="https://example.invalid' not in exported
    assert "Own text" in exported and "Own alt" in exported


def test_quiet_html_does_not_claim_complete_assessment_or_copy_source(tmp_path):
    from opendoc_model import get_integration

    from opendoc_formats import read_document

    source = tmp_path / "quiet.html"
    source.write_text("<p>Own text</p>", encoding="utf-8")
    result = read_document(source)
    assert result.success and not result.assessment_complete and not result.lossless
    assert not get_integration(result.document).preservation and not result.document.resources


def test_html_warning_limit_is_explicit():
    from opendoc_formats.readers.html_diagnostics import HtmlDiagnostics

    diagnostics = HtmlDiagnostics()
    diagnostics.pending = [("html-css", "Own warning", None)] * 10_000
    with pytest.raises(ValueError, match="diagnostic objects exceed"):
        diagnostics.warn("html-css", "Another own warning")
