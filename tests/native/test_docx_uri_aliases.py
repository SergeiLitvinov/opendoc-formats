"""Independently authored encoded main-part bindings and native transactions, without a DOCX writer."""

import io
import zipfile
from threading import Event

import pytest

from opendoc_formats.docx import DocxPackage, ReplaceTextSpan
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, UnsupportedDocumentError
from tests.binary_fixtures import PR, zip_bytes
from tools.docx_native_smoke import source_package

TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'


def package(physical, target, override, *, extra=(), duplicate=None):
    with zipfile.ZipFile(io.BytesIO(source_package())) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    body = parts.pop('word/document.xml')
    parts[physical] = body
    parts['_rels/.rels'] = parts['_rels/.rels'].replace(b'word/document.xml', target.encode())
    parts['[Content_Types].xml'] = parts['[Content_Types].xml'].replace(b'/word/document.xml', override.encode())
    if duplicate is not None:
        parts['[Content_Types].xml'] = parts['[Content_Types].xml'].replace(
            b'</Types>', f'<Override PartName="{duplicate}" ContentType="{TYPE}"/></Types>'.encode())
    parts.update(extra)
    return zip_bytes(list(parts.items()))


CASES = [
    ('word/own doc.xml', 'word/own%20doc.xml', '/word/own%20doc.xml'),
    ('word/own%20doc.xml', 'word/own%20doc.xml', '/word/own%20doc.xml'),
    ('word/текст.xml', 'word/%D1%82%D0%B5%D0%BA%D1%81%D1%82.xml', '/word/текст.xml'),
    ('word/🦊.xml', './word/%F0%9F%A6%8A.xml', '/word/%f0%9f%a6%8a.xml'),
    ('word/own%2F.xml', 'word/own%252F.xml', '/word/own%252F.xml'),
    ('document.xml', './word/../document.xml', '/document.xml'),
]


@pytest.mark.parametrize('physical,target,override', CASES)
def test_encoded_main_and_content_type_aliases_support_exact_noop_and_native_edits(tmp_path, physical, target, override):
    source = package(physical, target, override)
    path = tmp_path/'own.docx'
    path.write_bytes(source)
    with DocxPackage(path) as document:
        assert document.to_bytes() == source
        paragraph, = document.paragraphs
        assert paragraph.part == physical and paragraph.is_body and paragraph.text == 'Own текст\ttail'
        result = document.to_bytes([ReplaceTextSpan(paragraph.id, 0, 3, 'Edited')])
    with DocxPackage(result) as edited:
        assert edited.paragraphs[0].text == 'Edited текст\ttail' and edited.paragraphs[0].part == physical
    with zipfile.ZipFile(io.BytesIO(source)) as before, zipfile.ZipFile(io.BytesIO(result)) as after:
        assert before.namelist() == after.namelist()
        for name in before.namelist():
            if name != physical:
                assert before.read(name) == after.read(name)
    assert path.read_bytes() == source


@pytest.mark.parametrize('inspection_only', [False, True])
def test_two_physical_main_aliases_are_never_resolved_by_preference(inspection_only):
    source = package('word/é.xml', 'word/%C3%A9.xml', '/word/%C3%A9.xml',
                     extra=[('word/%C3%A9.xml', b'<other/>')])
    with pytest.raises(UnsupportedDocumentError, match=r'_rels/.rels.*ambiguous'):
        DocxPackage(source, inspection_only=inspection_only)


def test_content_type_alias_cannot_select_between_two_physical_names():
    source = package('word/é.xml', 'word/é.xml', '/word/%C3%A9.xml',
                     extra=[('word/%C3%A9.xml', b'<other/>')])
    with pytest.raises(UnsupportedDocumentError, match=r'Content_Types.*ambiguous'):
        DocxPackage(source)


@pytest.mark.parametrize('duplicate', ['/word/é.xml', '/word/%c3%a9.xml'])
def test_duplicate_main_content_type_aliases_do_not_silently_overwrite_each_other(duplicate):
    source = package('word/é.xml', 'word/%C3%A9.xml', '/word/%C3%A9.xml', duplicate=duplicate)
    with pytest.raises(InvalidDocumentError, match=r'Content_Types.*exactly one'):
        DocxPackage(source)


@pytest.mark.parametrize('stored', ['custom/own part.xml', 'custom/own%20part.xml'])
def test_attached_relationship_resolves_relative_escaped_and_decoded_zip_names(stored):
    rels = (f'<Relationships xmlns="{PR}"><Relationship Id="own" Type="urn:own" '
            'Target="../custom/own%20part.xml"/></Relationships>').encode()
    source = package('word/é.xml', 'word/%C3%A9.xml', '/word/é.xml',
                     extra=[('word/_rels/é.xml.rels', rels), (stored, b'<own/>')])
    with DocxPackage(source) as document:
        assert document.to_bytes() == source and not document.info.issues


@pytest.mark.parametrize('inspection_only', [False, True])
def test_attached_relationship_with_two_physical_aliases_refuses(inspection_only):
    rels = (f'<Relationships xmlns="{PR}"><Relationship Id="own" Type="urn:own" '
            'Target="../custom/own%20part.xml"/></Relationships>').encode()
    source = package('word/é.xml', 'word/%C3%A9.xml', '/word/é.xml', extra=[
        ('word/_rels/é.xml.rels', rels), ('custom/own part.xml', b'<decoded/>'),
        ('custom/own%20part.xml', b'<escaped/>')])
    with pytest.raises(UnsupportedDocumentError, match=r'word/_rels/é.xml.rels.*own.*ambiguous'):
        DocxPackage(source, inspection_only=inspection_only)


@pytest.mark.parametrize('target', ['word%2Fdocument.xml', 'word%5Cdocument.xml', '../../../document.xml'])
def test_unsupported_encoded_separators_and_root_escape_never_bind(target):
    source = package('word/document.xml', target, '/word/document.xml')
    with pytest.raises((UnsupportedDocumentError, InvalidDocumentError)):
        DocxPackage(source)


def test_alias_resolution_cancellation_keeps_original_and_scope(tmp_path, monkeypatch):
    from opendoc_formats.native import docx_uri

    source = package(*CASES[0])
    path = tmp_path/'own.docx'
    path.write_bytes(source)
    stop, calls = Event(), 0
    actual = docx_uri.check_cancel

    def cancel(callback):
        nonlocal calls
        calls += 1
        if calls == 4:
            stop.set()
        actual(callback)

    with monkeypatch.context() as context:
        context.setattr(docx_uri, 'check_cancel', cancel)
        with pytest.raises(OperationCancelledError):
            DocxPackage(path, cancelled=stop.is_set)
    assert path.read_bytes() == source and calls == 4
    with DocxPackage(path) as document:
        assert document.to_bytes() == source
