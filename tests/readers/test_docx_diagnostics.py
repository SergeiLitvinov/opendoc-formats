"""Own DOCX source fixtures distinguish retained XML from lost objects."""

import zipfile
from threading import Event

import pytest
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from lxml import etree
from opendoc_model import DocumentModel, document_from_json, document_to_json, get_integration

from opendoc_formats import read_document, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.docx_diagnostics import attach_docx_diagnostics
from opendoc_formats.support.cancellation import cancellation_scope, checkpoint


def _text(parent, text):
    run = OxmlElement("w:r")
    node = OxmlElement("w:t")
    node.text = text
    run.append(node)
    parent.append(run)


def _verify(source, result):
    assert result.success and not result.lossless and not result.assessment_complete
    ledger = get_integration(result.document)
    assert ledger and not ledger.assessment_complete
    with zipfile.ZipFile(source) as archive:
        for record in ledger.preservation:
            assert record.provenance.source_path == str(source)
            root = etree.fromstring(archive.read(record.provenance.package_part.lstrip("/")))
            if "#xpath=" in record.issue.location:
                xpath = record.issue.location.split("#xpath=", 1)[1]
                assert root.xpath(xpath, namespaces={key: value for key, value in root.nsmap.items() if key})
    restored = document_from_json(document_to_json(result.document))
    assert get_integration(restored) == ledger
    transport = source.with_suffix(".json")
    transport.write_text(document_to_json(restored), encoding="utf-8")
    assert read_document(transport).issues == result.issues
    return restored


def test_inline_opaque_and_block_revision_loss_are_distinct(tmp_path):
    document = Document()
    paragraph = document.add_paragraph("Before ")
    inline = OxmlElement("w:ins")
    inline.set(qn("w:id"), "7")
    _text(inline, "Retained inline")
    paragraph._p.append(inline)
    block = OxmlElement("w:ins")
    block.set(qn("w:id"), "8")
    block_paragraph = OxmlElement("w:p")
    _text(block_paragraph, "Lost block")
    block.append(block_paragraph)
    document._element.body.insert(1, block)
    source = tmp_path / "revisions.docx"
    document.save(source)
    result = read_document(source)
    records = [record for record in get_integration(result.document).preservation if record.issue.code == "docx.revisions"]
    assert {(record.provenance.object_id, record.state.value) for record in records} == {("7", "opaque"), ("8", "lost")}
    assert "Retained inline" in result.document.sections[0].blocks[0].plain_text
    assert "Lost block" not in str(result.document.sections)
    _verify(source, result)


def test_comments_fields_controls_and_header_objects_have_retention_evidence(tmp_path):
    document = Document()
    paragraph = document.add_paragraph("Reviewed")
    document.add_comment(paragraph.runs[0], text="Own comment", author="Fixture")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    _text(field, "1")
    paragraph._p.append(field)
    control = OxmlElement("w:sdt")
    content = OxmlElement("w:sdtContent")
    _text(content, "Control text")
    control.append(content)
    paragraph._p.append(control)
    header = document.sections[0].header.paragraphs[0]
    insertion = OxmlElement("w:ins")
    insertion.set(qn("w:id"), "header-change")
    _text(insertion, "Header insertion")
    header._p.append(insertion)
    protection = OxmlElement("w:documentProtection")
    protection.set(qn("w:edit"), "readOnly")
    document.settings._element.append(protection)
    source = tmp_path / "features.docx"
    document.save(source)
    result = read_document(source)
    records = get_integration(result.document).preservation
    assert {record.issue.code for record in records} >= {
        "docx.comments", "docx.fields", "docx.content-controls", "docx.protection",
        "docx.relationship.comments", "docx.revisions",
    }
    assert all(record.state.value == "opaque" for record in records)
    assert any(record.provenance.package_part == "/word/header1.xml" for record in records)
    restored = _verify(source, result)
    output = tmp_path / "restored.docx"
    assert write_document(restored, output).success
    assert any(comment.text == "Own comment" for comment in Document(output).comments)


def test_office_ole_case_and_part_relationship_are_preserved_without_execution(tmp_path):
    document = Document()
    package = document.part.package
    payload = b"own inert OLE fixture"
    part = Part(PackURI("/word/embeddings/own.bin"), "application/vnd.openxmlformats-officedocument.oleObject", payload, package)
    relation_id = document.part.relate_to(part, RT.OLE_OBJECT)
    paragraph = document.add_paragraph()
    paragraph._p.append(parse_xml(f'''<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
      xmlns:o="urn:schemas-microsoft-com:office:office"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <w:object><o:OLEObject Type="Embed" r:id="{relation_id}"/></w:object></w:r>'''))
    source = tmp_path / "ole.docx"
    document.save(source)
    result = read_document(source)
    records = get_integration(result.document).preservation
    assert any(record.issue.code == "docx.embedded-ole" and record.state.value == "opaque" for record in records)
    assert any(record.issue.code == "docx.relationship.embedded_ole" and record.state.value == "opaque" for record in records)
    restored = _verify(source, result)
    assert restored.package.parts["/word/embeddings/own.bin"].data == payload
    output = tmp_path / "restored.docx"
    assert write_document(restored, output).success
    with zipfile.ZipFile(output) as archive:
        assert archive.read("word/embeddings/own.bin") == payload


def test_foreign_namespace_does_not_claim_word_revision_support(tmp_path):
    document = Document()
    paragraph = document.add_paragraph("Retained")
    paragraph._p.append(parse_xml('<other:ins xmlns:other="urn:own:foreign"/>'))
    paragraph._p.append(parse_xml('<other:documentProtection xmlns:other="urn:own:foreign"/>'))
    source = tmp_path / "foreign.docx"
    document.save(source)
    result = read_document(source)
    assert "tracked_insertions" not in result.document.metadata["docx_features"]["features"]
    assert "document_protection_xml" not in result.document.metadata["docx_features"]
    assert all(record.issue.code == 'docx.relationship.custom_xml'
               for record in get_integration(result.document).preservation)


def test_external_ole_relationship_is_not_claimed_retained(tmp_path):
    document = Document()
    relation = document.part.relate_to("https://example.invalid/inert.bin", RT.OLE_OBJECT, is_external=True)
    source = tmp_path / "external.docx"
    document.save(source)
    result = read_document(source)
    records = [record for record in get_integration(result.document).preservation
               if record.issue.code == 'docx.relationship.embedded_ole']
    assert len(records) == 1 and records[0].state.value == "lost"
    assert records[0].provenance.object_id == relation
    assert records[0].issue.measurement["external"] is True
    _verify(source, result)


@pytest.mark.parametrize("relationship_type", ["urn:own:relationship", "https://example.invalid/comments",
                                             "https://example.invalid/oleObject"])
@pytest.mark.parametrize("owner", ["document", "settings", "external", "package", "package-external"])
def test_unknown_relationships_have_located_retention_evidence(tmp_path, relationship_type, owner):
    document = Document()
    document.add_paragraph("Editable body")
    parent = document.part.part_related_by(RT.SETTINGS) if owner == "settings" else document.part
    if owner.startswith("package"):
        parent = document.part.package
    diagnostic_part = "/_rels/.rels" if owner.startswith("package") else str(parent.partname)
    external = owner in {"external", "package-external"}
    payload = b"own inert unknown relationship payload"
    target = "https://example.invalid/never-fetch.bin"
    if external:
        identifier = parent.rels.get_or_add_ext_rel(relationship_type, target)
    else:
        part = Part(PackURI("/word/own.bin"), "application/octet-stream", payload, document.part.package)
        identifier = parent.relate_to(part, relationship_type)
        target = str(part.partname)
    source = tmp_path / "unknown.docx"
    document.save(source)
    original = source.read_bytes()
    result = read_document(source)
    restored = _verify(source, result)
    records = [record for record in get_integration(restored).preservation
               if record.issue.code == "docx.relationship.unknown"]
    assert len(records) == 1
    record = records[0]
    assert record.state.value == ("opaque" if owner == "settings" else "lost")
    assert record.provenance.package_part == diagnostic_part
    assert record.provenance.object_id == identifier
    assert record.issue.location == f"{source}!{diagnostic_part}#relationship={identifier}"
    assert record.issue.measurement == {"target": target, "external": external,
                                        "relationship_type": relationship_type}
    if owner != "settings":
        features = restored.metadata["docx_features"]["features"]
        assert features["unknown"]["preservation"] == "diagnostic-only"
        assert "comments" not in features and "embedded_ole" not in features
    output = tmp_path / "restored.docx"
    assert write_document(restored, output).success
    with zipfile.ZipFile(output) as archive:
        if owner == "settings":
            assert archive.read("word/own.bin") == payload
            rels = etree.fromstring(archive.read("word/_rels/settings.xml.rels"))
            assert any(edge.get("Type") == relationship_type for edge in rels)
        else:
            assert "word/own.bin" not in archive.namelist()
    assert source.read_bytes() == original


def test_package_relationship_does_not_borrow_retention_from_another_owner(tmp_path):
    document = Document()
    document.add_paragraph("Shared payload, distinct source relationships")
    package = document.part.package
    settings = document.part.part_related_by(RT.SETTINGS)
    target = Part(PackURI("/word/shared.bin"), "application/octet-stream", b"shared inert payload", package)
    relationship_type = "urn:own:shared"
    for owner in (package, settings):
        owner.rels.add_relationship(relationship_type, target, "rId99")
    source = tmp_path / "shared.docx"
    document.save(source)
    result = read_document(source)
    restored = _verify(source, result)
    records = [record for record in get_integration(restored).preservation
               if record.issue.code == "docx.relationship.unknown"]
    assert {(record.provenance.package_part, record.state.value) for record in records} == {
        ("/_rels/.rels", "lost"), ("/word/settings.xml", "opaque"),
    }
    assert all(record.provenance.object_id == "rId99" for record in records)
    assert restored.package.parts["/word/shared.bin"].data == b"shared inert payload"
    output = tmp_path / "restored.docx"
    assert write_document(restored, output).success
    with zipfile.ZipFile(output) as archive:
        root = etree.fromstring(archive.read("_rels/.rels"))
        settings_root = etree.fromstring(archive.read("word/_rels/settings.xml.rels"))
        assert not any(edge.get("Type") == relationship_type for edge in root)
        assert any(edge.get("Type") == relationship_type for edge in settings_root)


def test_cancel_between_package_relationships_preserves_ledger_and_source(monkeypatch, tmp_path):
    from docx.opc.rel import Relationships

    document = Document()
    root_rels = document.part.package.rels
    root_rels.get_or_add_ext_rel("urn:own:first", "https://example.invalid/first")
    root_rels.get_or_add_ext_rel("urn:own:second", "https://example.invalid/second")
    source = tmp_path / "root-cancel.docx"
    document.save(source)
    original = source.read_bytes()
    model = DocumentModel()
    before = document_to_json(model)
    stop = Event()
    values = Relationships.values

    def interrupt(relationships):
        for relationship in values(relationships):
            yield relationship
            if relationships is root_rels and relationship.reltype == "urn:own:first":
                stop.set()

    with monkeypatch.context() as context:
        context.setattr(Relationships, "values", interrupt)
        with pytest.raises(OperationCancelledError):
            with cancellation_scope(stop.is_set, "DOCX root relationships"):
                attach_docx_diagnostics(document, model, source)
    assert stop.is_set()
    assert document_to_json(model) == before
    assert source.read_bytes() == original
    checkpoint()
    attach_docx_diagnostics(document, model, source)
    assert sum(record.issue.code == "docx.relationship.unknown"
               for record in get_integration(model).preservation) == 2
