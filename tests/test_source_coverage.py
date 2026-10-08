"""Reproducible limits of source import, linked to finite coverage tasks."""

from opendoc_model import Formula, Table

from opendoc_formats import read_document, write_document
from opendoc_formats.readers.epub_model import read_epub_model
from opendoc_formats.readers.pptx import read_pptx_model


def test_tex_source_has_no_reader(tmp_path):
    source = tmp_path / "source.tex"
    source.write_text(r"\documentclass{article}\begin{document}Hello\end{document}", encoding="utf-8")
    for identifier in (None, "latex"):
        result = read_document(source, format_id=identifier)
        assert not result.success
        assert result.issues[0].code == "import.unsupported-format"


def test_epub_table_math_are_semantic_but_nonlinear_content_is_lost(tmp_path):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("coverage-fixture")
    book.set_title("Own generated source fixture")
    book.set_language("en")
    chapter = epub.EpubHtml(title="Chapter", file_name="chapter.xhtml")
    chapter.content = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        '<p>Visible <math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math></p>'
        '<table><tr><td>TableOnly</td></tr></table></body></html>'
    )
    appendix = epub.EpubHtml(title="Appendix", file_name="appendix.xhtml")
    appendix.content = "<html><body><p>NonlinearOnly</p></body></html>"
    for item in (chapter, appendix, epub.EpubNav()):
        book.add_item(item)
    book.spine = [chapter, (appendix, "no")]
    source = tmp_path / "source.epub"
    epub.write_epub(str(source), book)
    document = read_epub_model(source)
    blocks = [block for section in document.sections for block in section.blocks]
    text = str(document)
    assert "Visible" in text and "TableOnly" in text and "NonlinearOnly" not in text
    table = next(block for block in blocks if isinstance(block, Table))
    assert table.rows[0].cells[0].blocks[0].plain_text == "TableOnly"
    assert isinstance(blocks[0].content[1], Formula)
    result = read_document(source)
    assert result.success and not result.lossless and not result.assessment_complete
    assert {issue.code for issue in result.issues} == {"epub.spine"}
    assert all(issue.severity.value == "loss" and str(source) in issue.location for issue in result.issues)
    assert any("appendix.xhtml" in issue.location and issue.reason == "nonlinear-spine" for issue in result.issues)
    from opendoc_model import document_from_json, document_to_json, get_integration

    restored = document_from_json(document_to_json(document))
    ledger = get_integration(restored)
    assert ledger == get_integration(document)
    assert all(record.provenance.source_path == str(source) for record in ledger.preservation)
    assert all(record.provenance.package_part.endswith(".xhtml") for record in ledger.preservation)
    import zipfile

    with zipfile.ZipFile(source) as archive:
        assert all(record.provenance.package_part.lstrip("/") in archive.namelist() for record in ledger.preservation)
    report = write_document(document, tmp_path / "output.epub")
    assert not report.success and report.issues[0].feature == "export.unsupported-format"


def test_pptx_import_does_not_preserve_original_package(tmp_path):
    from pptx import Presentation
    from pptx.oxml.xmlchemy import OxmlElement

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    transition = OxmlElement("p:transition")
    transition.append(OxmlElement("p:fade"))
    slide._element.append(transition)
    source = tmp_path / "transition.pptx"
    presentation.save(source)
    document = read_pptx_model(source)
    assert document.package is None
    assert "transition" not in document.sections[0].properties
    result = read_document(source)
    assert result.success and not result.lossless and not result.assessment_complete
    assert any(issue.code == "pptx.transition" and issue.reason == "unsupported-transition" for issue in result.issues)
    target = tmp_path / "output.pptx"
    assert write_document(document, target).success
    restored = Presentation(target)
    assert not restored.slides[0]._element.xpath("./p:transition")
