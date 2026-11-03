"""Compound source bytes are real opaque evidence, not a claimed semantic flow group."""

import builtins
import codecs
import hashlib
from threading import Event
from zipfile import ZipFile

import opendoc_model as od

from opendoc_formats import ImportOptions, read_document
from opendoc_formats.readers.epub_diagnostics import EpubDiagnostics


def chapter():
    return codecs.BOM_UTF8+b'''<html xmlns="http://www.w3.org/1999/xhtml"><body>\r
  <!-- Own byte control: CR/LF, BOM, entities and single quotes -->\r
  <blockquote id='quote'><p>Before &amp; after</p>\r
    <table id='first'><tr><td>Cell A</td></tr></table>\r
    <p>Between</p><table id='second'><tr><td>Cell B</td></tr></table>\r
    <p>After</p></blockquote></body></html>'''


def own_epub(path, *, chapters=None, assets=()):
    chapters = chapters or [('chapter.xhtml', chapter())]
    manifest = ''.join(f'<item id="c{index}" href="{name}" media-type="application/xhtml+xml"/>'
                       for index, (name, _) in enumerate(chapters))
    manifest += ''.join(f'<item id="{identifier}" href="{name}" media-type="{media}"/>'
                        for identifier, name, media, _ in assets)
    spine = ''.join(f'<itemref idref="c{index}"/>' for index in range(len(chapters)))
    with ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip')
        archive.writestr('META-INF/container.xml',
                        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                        '<rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/>'
                        '</rootfiles></container>')
        archive.writestr('OPS/book.opf', '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
                        '<metadata/><manifest>'+manifest+'</manifest><spine>'+spine+'</spine></package>')
        for name, data in chapters:
            archive.writestr('OPS/'+name, data)
        for _, name, _, data in assets:
            archive.writestr('OPS/'+name, data)
    return path.read_bytes()


def nested_records(document):
    return [record for record in od.get_integration(document).preservation if record.issue.reason == 'nested-table-block']


def test_exact_chapter_bytes_one_resource_multiple_located_objects_and_two_json_cycles(tmp_path):
    path = tmp_path/'own.epub'
    original = own_epub(path)
    imported = read_document(path)
    assert imported.success and not imported.lossless and not imported.assessment_complete
    document = imported.document
    for _ in range(3):
        records = nested_records(document)
        assert len(records) == 2 and {record.provenance.object_id for record in records} == {'first', 'second'}
        resources = {record.extra['resource_id'] for record in records}
        assert len(resources) == 1
        resource = document.resources[resources.pop()]
        assert resource.kind is od.ResourceKind.ATTACHMENT and resource.media_type == 'application/xhtml+xml'
        assert resource.data == chapter() and resource.filename == 'chapter.xhtml'
        assert resource.provenance.package_part == '/OPS/chapter.xhtml'
        for record in records:
            assert record.state is od.PreservationState.OPAQUE
            assert record.issue.location.endswith('OPS/chapter.xhtml#'+record.provenance.object_id)
            assert record.provenance.package_part == '/OPS/chapter.xhtml'
        document = od.document_from_json(od.document_to_json(document))
    assert path.read_bytes() == original


def test_identical_chapters_have_distinct_physical_source_bindings(tmp_path):
    path = tmp_path/'two.epub'
    original = own_epub(path, chapters=[('one.xhtml', chapter()), ('two.xhtml', chapter())])
    document = read_document(path).document
    records = nested_records(document)
    assert len(records) == 4
    assert {record.provenance.package_part for record in records} == {'/OPS/one.xhtml', '/OPS/two.xhtml'}
    identifiers = {record.extra['resource_id'] for record in records}
    assert len(identifiers) == 2
    assert all(document.resources[identifier].data == chapter() for identifier in identifiers)
    assert path.read_bytes() == original


def test_manifest_resource_collision_preserves_both_payloads(tmp_path):
    path = tmp_path/'collision.epub'
    digest = hashlib.sha256(b'chapter.xhtml')
    digest.update(chapter())
    identifier = 'compound-source-'+digest.hexdigest()
    own_epub(path, assets=[(identifier, 'own.woff', 'font/woff', b'Own inert font payload')])
    document = read_document(path).document
    assert document.resources['epub-'+identifier].data == b'Own inert font payload'
    retained = {record.extra['resource_id'] for record in nested_records(document)}
    assert len(retained) == 1 and 'epub-'+identifier not in retained
    assert document.resources[retained.pop()].data == chapter()


def test_diagnostics_without_source_bytes_cannot_fabricate_opaque_preservation(tmp_path):
    from bs4 import BeautifulSoup

    diagnostics = EpubDiagnostics(tmp_path/'unavailable.epub')
    body = BeautifulSoup('<p><table id="own"><tr><td>Own</td></tr></table></p>', 'html.parser')
    diagnostics.chapter(body, 'chapter.xhtml', {'p'})
    assert diagnostics.records[0].state is od.PreservationState.LOST
    assert not diagnostics.resources and 'resource_id' not in diagnostics.records[0].extra


def test_source_only_capture_needs_no_other_format_or_font_engine(tmp_path, monkeypatch):
    path = tmp_path/'minimal.epub'
    own_epub(path)
    native_import = builtins.__import__

    def minimal(name, *args, **kwargs):
        if name.split('.')[0] in {'lxml', 'docx', 'PIL', 'fontTools', 'fitz', 'pymupdf', 'tinycss2', 'ebooklib'}:
            raise AssertionError('Unexpected engine: '+name)
        return native_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', minimal)
    assert len(nested_records(read_document(path).document)) == 2


def test_late_cancellation_during_source_capture_preserves_input_and_next_import(tmp_path, monkeypatch):
    path = tmp_path/'cancel.epub'
    original = own_epub(path)
    stop = Event()
    native = EpubDiagnostics.retain_chapter

    def capture(self, part):
        result = native(self, part)
        stop.set()
        return result

    monkeypatch.setattr(EpubDiagnostics, 'retain_chapter', capture)
    result = read_document(path, options=ImportOptions(cancelled=stop.is_set))
    assert not result.success and path.read_bytes() == original
    stop.clear()
    assert read_document(path).success


def test_selected_embedded_budget_counts_the_retained_original(tmp_path):
    path = tmp_path/'budget.epub'
    original = own_epub(path)
    document = read_document(path).document
    maximum = sum(len(resource.data or b'') for resource in document.resources.values())
    assert read_document(path, options=ImportOptions(document_limits=od.DocumentLimits(max_embedded_bytes=maximum))).success
    refused = read_document(path, options=ImportOptions(document_limits=od.DocumentLimits(max_embedded_bytes=maximum-1)))
    assert not refused.success and refused.document is None
    assert any(issue.code == 'import.document-limit' and 'embedded bytes' in issue.message for issue in refused.issues)
    assert path.read_bytes() == original
