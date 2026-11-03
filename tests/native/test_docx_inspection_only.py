"""Bounded read-only snapshots of orphan relationships, without package repair or object activation."""

import builtins
import io
import zipfile
from dataclasses import FrozenInstanceError, replace
from threading import Event

import pytest
from opendoc_model import ConversionIssue, IssueSeverity

from opendoc_formats.docx import DocxLimits, DocxPackage, ReplaceTextSpan
from opendoc_formats.errors import (
    InvalidDocumentError,
    OperationCancelledError,
    ResourceLimitError,
    UnsupportedDocumentError,
)
from tests.binary_fixtures import PR, zip_bytes
from tests.native.test_docx_consumer_contract import original


def orphan_source(*, target='../word/document.xml', extra=''):
    relations = (f'<Relationships xmlns="{PR}"><Relationship Id="own" Type="urn:own" '
                 f'Target="{target}"/>{extra}</Relationships>').encode()
    return original('<w:p><w:r><w:t>Own body</w:t></w:r></w:p>', [
        ('custom/_rels/ghost.xml.rels', relations),
        ('word/_rels/missing.xml.rels', relations.replace(target.encode(), b'document.xml')),
    ])


def test_two_orphan_parts_are_located_without_hiding_errors_or_changing_bytes(tmp_path, monkeypatch):
    actual_import = builtins.__import__

    def minimal(name, *args, **kwargs):
        if name.split('.')[0] in {'docx', 'pptx', 'PIL', 'fontTools', 'pymupdf', 'pypdf', 'bs4'}:
            raise AssertionError('Unexpected engine: '+name)
        return actual_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', minimal)
    source = orphan_source()
    path = tmp_path/'own.docx'
    path.write_bytes(source)
    with pytest.raises(InvalidDocumentError, match='custom/_rels/ghost.xml.rels:.*missing source part: custom/ghost.xml'):
        DocxPackage(path)
    with DocxPackage(path, inspection_only=True) as package:
        assert package.info.inspection_only
        assert [paragraph.text for paragraph in package.paragraphs if paragraph.is_body] == ['Own body']
        assert package.to_bytes() == source
        issues = package.info.issues
        assert [issue.location for issue in issues] == ['custom/_rels/ghost.xml.rels', 'word/_rels/missing.xml.rels']
        assert all(isinstance(issue, ConversionIssue) and issue.severity is IssueSeverity.ERROR
                   and issue.feature == 'docx.orphan-relationships' for issue in issues)
        assert 'custom/ghost.xml' in issues[0].message and 'word/missing.xml' in issues[1].message
        with pytest.raises(FrozenInstanceError):
            issues[0].message = 'hidden'
    assert path.read_bytes() == source


@pytest.mark.parametrize('orphans', [False, True])
def test_all_inspection_only_writes_and_patches_refuse_before_destination_changes(tmp_path, orphans):
    source = orphan_source() if orphans else original('<w:p><w:r><w:t>Own body</w:t></w:r></w:p>')
    target = tmp_path/'existing.docx'
    target.write_bytes(b'Own previous destination')
    with DocxPackage(source, inspection_only=True) as package:
        paragraph = next(item for item in package.paragraphs if item.is_body)
        patch = ReplaceTextSpan(paragraph.id, 0, 3, 'Edited')
        for action in (lambda: package.write(target), lambda: package.write(target, [patch]),
                       lambda: package.to_bytes([patch])):
            with pytest.raises(UnsupportedDocumentError, match='inspection_only'):
                action()
            assert target.read_bytes() == b'Own previous destination'
        assert package.to_bytes() == source


@pytest.mark.parametrize('target', ['../../../outside', 'https://example.invalid/never', 'absent.xml'])
def test_orphan_mode_does_not_bypass_internal_target_safety_or_presence(target):
    with pytest.raises(InvalidDocumentError):
        DocxPackage(orphan_source(target=target), inspection_only=True)


def test_duplicate_ids_and_invalid_relationship_namespace_still_refuse():
    duplicate = '<Relationship Id="own" Type="urn:other" Target="../word/document.xml"/>'
    with pytest.raises(InvalidDocumentError, match='duplicate'):
        DocxPackage(orphan_source(extra=duplicate), inspection_only=True)
    source = orphan_source()
    # Build an actual orphan XML part, rather than corrupting compressed ZIP bytes.
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        parts = [(name, archive.read(name)) for name in archive.namelist()]
    parts.append(('custom/_rels/invalid.xml.rels', b'<Relationships xmlns="urn:wrong"/>'))
    with pytest.raises(InvalidDocumentError, match='namespace'):
        DocxPackage(zip_bytes(parts), inspection_only=True)


def test_dtd_limits_and_cancellation_remain_failures(tmp_path, monkeypatch):
    from opendoc_formats.native import docx_package as native

    source = orphan_source()
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        parts = [(name, archive.read(name)) for name in archive.namelist()]
    parts.append(('custom/_rels/dtd.xml.rels', b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///never">]><x/>'))
    with pytest.raises(UnsupportedDocumentError, match='DTD'):
        DocxPackage(zip_bytes(parts), inspection_only=True)
    for limit in (replace(DocxLimits(), max_input_bytes=len(source)-1), replace(DocxLimits(), max_entries=1),
                  replace(DocxLimits(), max_text_chars=1)):
        with pytest.raises(ResourceLimitError):
            DocxPackage(source, inspection_only=True, limits=limit)
    path = tmp_path/'own.docx'
    path.write_bytes(source)
    stop = Event()
    actual_issue = native.ConversionIssue

    def located_issue(*args, **kwargs):
        result = actual_issue(*args, **kwargs)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(native, 'ConversionIssue', located_issue)
        with pytest.raises(OperationCancelledError):
            DocxPackage(path, inspection_only=True, cancelled=stop.is_set)
    assert path.read_bytes() == source
    with DocxPackage(path, inspection_only=True) as package:
        assert len(package.info.issues) == 2


@pytest.mark.parametrize('value', [None, 1, 'true'])
def test_inspection_option_requires_boolean(value):
    with pytest.raises(TypeError, match='inspection_only'):
        DocxPackage(b'Never parsed', inspection_only=value)
