"""Own native sources exercise caller-selected budgets across import and JSON."""

import hashlib

import pytest
from opendoc_model import DocumentLimits, DocumentModel, Paragraph, Section, TextRun, document_to_json
from pptx import Presentation
from pptx.util import Inches

from opendoc_formats import ExportOptions, ImportOptions, read_document, write_document


@pytest.fixture(scope="module")
def large_pptx(tmp_path_factory):
    source = tmp_path_factory.mktemp("caller-limits") / "own.pptx"
    deck = Presentation()
    for slide_number in range(35):
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        for shape_number in range(6):
            frame = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1)).text_frame
            for run_number in range(32):
                frame.paragraphs[0].add_run().text = f"Own {slide_number}/{shape_number}/{run_number} "
    deck.save(source)
    return source


def test_native_pptx_selected_budget_and_two_public_json_cycles(large_pptx, tmp_path):
    before = hashlib.sha256(large_pptx.read_bytes()).digest()
    refused = read_document(large_pptx)
    assert not refused.success and refused.document is None
    issue, = refused.issues
    assert issue.code == "import.document-limit" and "#$.sections[" in issue.location
    assert issue.measurement["quota"] == "nodes" and issue.measurement["maximum"] == 100000
    limits = DocumentLimits(max_nodes=200000)
    result = read_document(large_pptx, options=ImportOptions(document_limits=limits))
    assert result.success, result.issues
    assert not result.assessment_complete and not result.lossless
    document = result.document
    texts = [run.text for section in document.sections for block in section.blocks for run in block.content]
    assert len(document.sections) == 35 and len(texts) == 6720
    snapshot = document_to_json(document, limits=limits)
    for cycle in range(2):
        path = tmp_path / f"cycle-{cycle}.json"
        report = write_document(document, path, options=ExportOptions(document_limits=limits))
        assert report.success, report.issues
        result = read_document(path, options=ImportOptions(document_limits=limits))
        assert result.success and not result.lossless and not result.assessment_complete
        document = result.document
        assert document_to_json(document, limits=limits) == snapshot
    assert hashlib.sha256(large_pptx.read_bytes()).digest() == before


@pytest.mark.parametrize("limits,quota,maximum", [
    (DocumentLimits(max_nodes=1), "nodes", 1),
    (DocumentLimits(max_depth=1), "depth", 1),
    (DocumentLimits(max_bytes=64), "bytes", 64),
    (DocumentLimits(max_embedded_bytes=0), "embedded bytes", 0),
])
def test_docx_quota_refusal_has_location_and_selected_limits(tmp_path, limits, quota, maximum):
    from docx import Document

    source = tmp_path / "own.docx"
    native = Document()
    native.add_paragraph("Own bounded source")
    native.save(source)
    before = source.read_bytes()
    result = read_document(source, options=ImportOptions(document_limits=limits))
    assert not result.success and result.document is None
    issue, = result.issues
    assert issue.code == "import.document-limit" and "#" in issue.location
    assert issue.measurement["quota"] == quota and issue.measurement["maximum"] == maximum
    assert source.read_bytes() == before


def test_cancel_and_input_limit_precede_native_read(large_pptx):
    for options, code in [
        (ImportOptions(cancelled=lambda: True), "import.cancelled"),
        (ImportOptions(max_input_bytes=1), "import.input-limit"),
    ]:
        result = read_document(large_pptx, options=options)
        assert not result.success and result.document is None and result.issues[0].code == code


@pytest.mark.parametrize("format_id", ["html", "epub", "latex", "pdf", "txt", "json"])
def test_registered_readers_return_small_budget_refusals(tmp_path, format_id):
    suffix = {"latex": "tex"}.get(format_id, format_id)
    source = tmp_path / f"own.{suffix}"
    model = DocumentModel(sections=[Section(blocks=[Paragraph(content=[TextRun("Own source")])])])
    if format_id == "html":
        source.write_text("<p>Own source</p>", encoding="utf-8")
    elif format_id == "latex":
        source.write_text("Own source", encoding="utf-8")
    elif format_id == "txt":
        source.write_text("Own source", encoding="utf-8")
    elif format_id == "json":
        source.write_text(document_to_json(model), encoding="utf-8")
    elif format_id == "pdf":
        import pymupdf

        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((72, 72), "Own source")
            pdf.save(source)
    else:
        assert write_document(model, source).success
    result = read_document(source, options=ImportOptions(document_limits=DocumentLimits(max_nodes=1)))
    assert not result.success and result.document is None
    assert result.issues[0].code == "import.document-limit"
