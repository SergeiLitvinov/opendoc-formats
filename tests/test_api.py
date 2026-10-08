"""Independent import contracts and extensibility."""
import ast
import subprocess
import sys
from pathlib import Path

import pytest
from opendoc_model import DocumentModel, Paragraph, Section, TextRun, document_from_json, document_to_json

from opendoc_formats import AdapterRegistry, AdapterSpec, ImportOptions, default_registry, read_document


def test_txt_empty_lines_and_native_json(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("First\n\nLast", encoding="utf-8")
    result = read_document(path)
    assert result.success
    assert [block.plain_text for block in result.document.sections[0].blocks] == ["First", "", "Last"]
    assert document_from_json(document_to_json(result.document)).source_format == "txt"


def test_model_outline_survives_public_json_cycles(tmp_path):
    from opendoc_model import Outline, OutlineEntry, OutlineTarget, get_outline, set_outline

    from opendoc_formats import write_document

    document = DocumentModel(sections=[Section(blocks=[Paragraph(content=[TextRun("Own outline")])])])
    outline = Outline(entries=(
        OutlineEntry("root", "Root", 0, extra={"vendor": {"unknown": None}}),
        OutlineEntry("child", "External", 2, parent_id="root",
                     target=OutlineTarget("external", uri="https://example.invalid/inert")),
    ), extra={"unknown": [1, None]})
    set_outline(document, outline)
    before = document_to_json(document)
    for cycle in range(2):
        path = tmp_path / f"outline-{cycle}.json"
        assert write_document(document, path).success
        result = read_document(path)
        assert result.success, result.issues
        document = result.document
        assert get_outline(document) == outline
        assert document_to_json(document) == before


@pytest.mark.parametrize("value", [1, 0, "yes", None])
def test_epub_nonlinear_option_requires_boolean(value):
    with pytest.raises(ValueError, match="epub_include_nonlinear must be boolean"):
        ImportOptions(epub_include_nonlinear=value)

def test_html_actual_parser_and_diagnostics(tmp_path):
    path = tmp_path / "input.html"
    path.write_text('<h1>Title</h1><p><b>Bold</b></p><script>alert(1)</script>', encoding="utf-8")
    result = read_document(path)
    assert result.success and not result.document.validate()
    assert result.document.sections[0].blocks[0].plain_text == "Title"
    assert result.document.sections[0].blocks[1].content[0].style.bold is True
    assert any("script" in issue.message for issue in result.issues)
    assert document_from_json(document_to_json(result.document)).styles["Heading1"]


@pytest.mark.parametrize("format_id,nested", [("epub", True), ("pdf", False), ("custom", False)])
def test_reader_warnings_are_exposed_without_claiming_losslessness(tmp_path, format_id, nested):
    path = tmp_path / "input.fixture"
    path.write_text("source", encoding="utf-8")
    metadata = {"warnings": ["An object was skipped"]}
    document = DocumentModel(metadata={format_id: metadata} if nested else metadata)
    registry = AdapterRegistry()
    registry.register(AdapterSpec(format_id, (".fixture",), lambda path, options: document))
    result = registry.read(path)
    assert result.success and not result.assessment_complete and not result.lossless
    assert result.issues[0].code == f"{format_id}.warning"
    assert str(path) in result.issues[0].location
    restored = document_from_json(document_to_json(document))
    assert restored.metadata == document.metadata


@pytest.mark.parametrize("state", ["semantic", "opaque", "visual", "lost", "rejected"])
def test_json_preservation_ledger_controls_import_result(tmp_path, state):
    from opendoc_model import (
        DiagnosticIssue,
        IntegrationModel,
        IssueSeverity,
        PreservationRecord,
        PreservationState,
        set_integration,
    )

    document = DocumentModel()
    issue = DiagnosticIssue("source.object", IssueSeverity.INFO, "Object assessment", "part.xml#object-1",
                            reason="fixture-assessment")
    set_integration(document, IntegrationModel(
        assessed_features=(issue.code,), assessment_complete=True,
        preservation=(PreservationRecord(issue=issue, state=PreservationState(state)),),
    ))
    path = tmp_path / "input.json"
    path.write_text(document_to_json(document), encoding="utf-8")
    result = read_document(path)
    assert result.assessment_complete
    assert result.lossless is (state == "semantic")
    assert result.success is (state != "rejected")
    assert result.issues[0].location == issue.location
    assert result.issues[0].reason == issue.reason
    assert document_from_json(document_to_json(result.document)).metadata == document.metadata


def test_empty_import_diagnostics_do_not_prove_losslessness(tmp_path):
    path = tmp_path / "input.txt"
    path.write_text("content", encoding="utf-8")
    result = read_document(path)
    assert result.success and not result.issues
    assert not result.assessment_complete and not result.lossless

def test_registry_extension_and_duplicate_rejection(tmp_path):
    path = tmp_path / "input.custom"
    path.write_text("Value", encoding="utf-8")
    registry = default_registry()
    registry.register(AdapterSpec("custom", (".custom",), lambda path, options: DocumentModel(
        sections=[Section(blocks=[Paragraph([TextRun(path.read_text(encoding="utf-8"))])])],
    )))
    assert registry.read(path).document.sections[0].blocks[0].plain_text == "Value"
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(AdapterSpec("duplicate", (".custom",), lambda path, options: DocumentModel()))

def test_limits_cancel_and_unsupported(tmp_path):
    path = tmp_path / "input.txt"
    path.write_text("Value", encoding="utf-8")
    assert read_document(path, options=ImportOptions(max_input_bytes=1)).issues[0].code == "import.input-limit"
    assert read_document(path, options=ImportOptions(cancelled=lambda: True)).issues[0].code == "import.cancelled"
    assert read_document(path, format_id="unknown-format").issues[0].code == "import.unsupported-format"

def test_missing_backend_and_invalid_model(tmp_path, monkeypatch):
    from opendoc_formats.support import backends
    path = tmp_path / "input.html"
    path.write_text("Content", encoding="utf-8")
    monkeypatch.setattr(backends.util, "find_spec", lambda name: None)
    assert read_document(path).issues[0].code == "import.backend-unavailable"
    registry = AdapterRegistry()
    registry.register(AdapterSpec("bad", (".html",), lambda path, options: DocumentModel(
        sections=[Section(blocks=[Paragraph(style_id="missing")])],
    )))
    assert registry.read(path).issues[0].code == "import.invalid-model"

def test_cancellation_discards_completed_result(tmp_path):
    path = tmp_path / "input.custom"
    path.write_text("Content", encoding="utf-8")
    state = {"cancelled": False}
    def reader(path, options):
        state["cancelled"] = True
        return DocumentModel()
    registry = AdapterRegistry()
    registry.register(AdapterSpec("custom", (".custom",), reader))
    result = registry.read(path, options=ImportOptions(cancelled=lambda: state["cancelled"]))
    assert not result.success and result.document is None

def test_no_application_imports_and_lazy_html():
    import opendoc_formats
    for path in Path(opendoc_formats.__file__).parent.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            )
            assert not any(name == "textalchemy" or name.startswith("textalchemy.") for name in names)
    code = "import sys; import opendoc_formats; assert all(n not in sys.modules for n in ('bs4','tinycss2','textalchemy'))"
    subprocess.run([sys.executable, "-I", "-c", code], check=True)
