"""Byte-level text profiles, strict decoding and atomic export acceptance."""

import codecs
import json

import pytest
from opendoc_model import DocumentModel, Paragraph, Section, TextRun, document_from_json, document_to_json

from opendoc_formats import ExportOptions, ImportOptions, TextProfile, read_document, write_document
from opendoc_formats.readers.txt import read_txt


@pytest.mark.parametrize("encoding,bom", [
    ("utf-8", False), ("utf-8", True), ("utf-16-le", True), ("utf-16-be", True),
    ("utf-16-le", False), ("utf-16-be", False), ("cp1251", False),
])
@pytest.mark.parametrize("text", ["", "Первая\n\nПоследняя\n", "Первая\r\nВторая\rТретья\n", "Одна строка"])
def test_original_profile_roundtrips_through_json(tmp_path, encoding, bom, text):
    prefixes = {"utf-8": codecs.BOM_UTF8, "utf-16-le": codecs.BOM_UTF16_LE, "utf-16-be": codecs.BOM_UTF16_BE}
    data = (prefixes[encoding] if bom else b"") + text.encode(encoding)
    source = tmp_path / "source.txt"
    source.write_bytes(data)
    profile = TextProfile(encoding=encoding)
    result = read_document(source, options=ImportOptions(txt_profile=profile))
    assert result.success, result.issues
    assert result.document.metadata["txt"]["encoding"] == encoding
    assert result.document.metadata["txt"]["bom"] is bom
    assert read_txt(source, profile=profile).plain == text
    document = document_from_json(document_to_json(result.document))
    event = document.sections[0].provenance.events[0]
    assert event.operation == "import.txt.profile"
    assert json.loads(event.detail)["source_bytes"] == len(data)
    output = tmp_path / "output.txt"
    report = write_document(document, output, options=ExportOptions(txt_profile=TextProfile()))
    assert report.success and report.lossless and report.metrics["output_verified"], report.to_dict()
    assert output.read_bytes() == data


@pytest.mark.parametrize("data,profile,reason", [
    (b"\xff", TextProfile(), "ambiguous-encoding"),
    (b"a\x00b\x00", TextProfile(), "binary-or-ambiguous"),
    (codecs.BOM_UTF8 + b"\xff", TextProfile(), "invalid-encoding"),
    (codecs.BOM_UTF16_LE + b"x", TextProfile(), "invalid-encoding"),
    (codecs.BOM_UTF16_BE + b"\xd8\x00", TextProfile(), "invalid-encoding"),
    (b"\x98", TextProfile("cp1251"), "invalid-encoding"),
    (codecs.BOM_UTF8 + b"text", TextProfile("utf-16-le"), "conflicting-bom"),
    (b"text", TextProfile(bom="require"), "missing-bom"),
    (codecs.BOM_UTF8 + b"text", TextProfile(bom="forbid"), "forbidden-bom"),
    (codecs.BOM_UTF32_LE + b"x\0\0\0", TextProfile(), "unsupported-encoding"),
])
def test_malformed_or_ambiguous_input_is_rejected(tmp_path, data, profile, reason):
    source = tmp_path / "bad.txt"
    source.write_bytes(data)
    result = read_document(source, options=ImportOptions(txt_profile=profile))
    assert result.document is None and not result.success
    assert result.issues[0].code == "import.txt-encoding" and result.issues[0].reason == reason
    assert result.issues[0].location == str(source)


@pytest.mark.parametrize("encoding,prefix", [
    ("utf-8", codecs.BOM_UTF8), ("utf-16-le", codecs.BOM_UTF16_LE), ("utf-16-be", codecs.BOM_UTF16_BE),
])
def test_auto_recognizes_bom_without_retaining_it_as_text(tmp_path, encoding, prefix):
    source = tmp_path / "bom.txt"
    source.write_bytes(prefix + "Привет".encode(encoding))
    result = read_document(source)
    assert result.success and result.document.sections[0].blocks[0].plain_text == "Привет"


def test_cp1251_requires_explicit_profile_and_defaults_export_utf8(tmp_path):
    source = tmp_path / "legacy.txt"
    source.write_bytes("Привет\r\n".encode("cp1251"))
    assert not read_document(source).success
    document = read_document(source, options=ImportOptions(txt_profile=TextProfile("cp1251"))).document
    target = tmp_path / "normalized.txt"
    report = write_document(document, target)
    assert report.success and target.read_bytes() == "Привет\n".encode("utf-8")


def test_explicit_export_and_unencodable_text_preserve_previous_output(tmp_path):
    document = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun("a\nb")])])])
    target = tmp_path / "explicit.txt"
    report = write_document(document, target, options=ExportOptions(txt_profile=TextProfile("utf-16-be", "require", "crlf")))
    assert report.success and target.read_bytes() == codecs.BOM_UTF16_BE + "a\r\nb".encode("utf-16-be")
    previous = target.read_bytes()
    document.sections[0].blocks[0].content[0].text = "emoji 😀"
    report = write_document(document, target, options=ExportOptions(txt_profile=TextProfile("cp1251")))
    assert not report.success and target.read_bytes() == previous


def test_changed_line_count_reports_loss_of_original_separator_sequence(tmp_path):
    source = tmp_path / "original.txt"
    source.write_bytes(b"a\r\nb\rc")
    document = read_document(source).document
    document.sections[0].blocks.append(Paragraph([TextRun("new")]))
    target = tmp_path / "edited.txt"
    report = write_document(document, target, options=ExportOptions(txt_profile=TextProfile()))
    assert report.success and not report.lossless
    assert any(issue.feature == "txt-newlines" for issue in report.issues)
    assert target.read_bytes() == b"a\nb\nc\nnew"


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16-le", "utf-16-be"])
def test_non_bmp_unicode_and_combining_characters(tmp_path, encoding):
    source = tmp_path / "unicode.txt"
    data = "😀 e\u0301\r\n水".encode(encoding)
    source.write_bytes(data)
    document = read_document(source, options=ImportOptions(txt_profile=TextProfile(encoding))).document
    target = tmp_path / "copy.txt"
    assert write_document(document, target, options=ExportOptions(txt_profile=TextProfile())).success
    assert target.read_bytes() == data


def test_invalid_source_profile_never_replaces_existing_file(tmp_path):
    document = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun("content")])])],
                             metadata={"txt": {"encoding": "utf-8", "line_separators": ["invalid"]}})
    target = tmp_path / "existing.txt"
    target.write_bytes(b"previous")
    report = write_document(document, target, options=ExportOptions(txt_profile=TextProfile()))
    assert not report.success and target.read_bytes() == b"previous"


@pytest.mark.parametrize("kwargs", [
    {"encoding": "latin1"}, {"bom": True}, {"newline": "native"}, {"encoding": "cp1251", "bom": "require"},
])
def test_invalid_profiles(kwargs):
    with pytest.raises(ValueError):
        TextProfile(**kwargs)
