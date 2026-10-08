"""Native EPUB container and hostile-input acceptance without an EPUB engine."""

import builtins
import zipfile

import pytest

from opendoc_formats import read_document
from opendoc_formats.readers.epub_package import read_epub_package


def _package(path, *, href="text/chapter%20one.xhtml", extra_manifest="", container=None, nav=True, metadata_extra=""):
    manifest = f'<item id="chapter" href="{href}" media-type="application/xhtml+xml"/>' + extra_manifest
    navigation = ('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>' if nav
                  else '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    opf = f'''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Native book</dc:title>
      <dc:language>ru</dc:language><dc:identifier>id-42</dc:identifier>{metadata_extra}</metadata>
      <manifest>{manifest}{navigation}</manifest><spine toc="ncx"><itemref idref="chapter"/></spine></package>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container or '''
          <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
          <rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>''')
        archive.writestr("OPS/book.opf", opf)
        archive.writestr("OPS/text/chapter one.xhtml", '<html><body><h1>Глава</h1><p>Текст</p></body></html>')
        archive.writestr("OPS/nav.xhtml", '''<html xmlns="http://www.w3.org/1999/xhtml"
          xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol><li>
          <a href="text/chapter%20one.xhtml#start">Название</a></li></ol></nav></body></html>''')
        archive.writestr("OPS/toc.ncx", '''<!DOCTYPE ncx SYSTEM "https://invalid.example/never-fetch">
          <ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap><navPoint id="p">
          <navLabel><text>Название</text></navLabel><content src="text/chapter%20one.xhtml#start"/>
          </navPoint></navMap></ncx>''')


@pytest.mark.parametrize("nav", [True, False])
def test_native_spine_nav_ncx_and_metadata_without_ebooklib_or_lxml(tmp_path, monkeypatch, nav):
    source = tmp_path / "native.epub"
    _package(source, nav=nav)
    original = builtins.__import__

    def no_engines(name, *args, **kwargs):
        if name.split(".")[0] in {"ebooklib", "lxml"}:
            raise ImportError("Optional engine unavailable")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_engines)
    package = read_epub_package(source)
    assert package.metadata == {"title": "Native book", "language": "ru", "identifier": "id-42"}
    assert package.titles["text/chapter one.xhtml"] == "Название"
    result = read_document(source)
    assert result.success, result.issues
    assert result.document.metadata["engine"] == "native-epub+bs4"
    assert result.document.sections[0].properties["epub"]["title"] == "Название"
    assert result.document.sections[0].blocks[1].plain_text == "Текст"


@pytest.mark.parametrize("nav", [True, False])
def test_original_package_metadata_and_navigation_survive_json(tmp_path, nav):
    from opendoc_model import document_from_json, document_to_json, get_integration

    source = tmp_path / "metadata.epub"
    _package(source, nav=nav, metadata_extra='''<dc:creator id="author">Own author</dc:creator>
      <dc:creator>Second own author</dc:creator><meta property="rendition:layout">pre-paginated</meta>
      <meta refines="#author" property="role">aut</meta>''')
    imported = read_document(source)
    assert imported.success and not imported.assessment_complete
    restored = document_from_json(document_to_json(imported.document))
    profile = restored.metadata["epub"]
    assert profile["package_properties"] == {"version": "3.0"}
    entries = profile["metadata_entries"]
    assert len(entries) == 7 and sum("creator" in entry for entry in entries) == 2
    assert any('refines="#author"' in entry for entry in entries)
    assert any("pre-paginated" in entry for entry in entries)
    expected = {"META-INF/container.xml", "OPS/book.opf", "OPS/nav.xhtml" if nav else "OPS/toc.ncx"}
    assert set(profile["source_xml_resources"]) == expected
    with zipfile.ZipFile(source) as archive:
        for part, resource_id in profile["source_xml_resources"].items():
            resource = restored.resources[resource_id]
            assert resource.data == archive.read(part) and resource.provenance.package_part == "/" + part
    records = [record for record in get_integration(restored).preservation if record.issue.code == "epub.package"]
    assert len(records) == 3 and all(record.state.value == "opaque" for record in records)
    assert {record.extra["resource_id"] for record in records} == set(profile["source_xml_resources"].values())


@pytest.mark.parametrize("href", ["../../outside.xhtml", "%2e%2e/%2e%2e/outside.xhtml",
                                  "https://example.com/chapter.xhtml", "//example.com/chapter.xhtml",
                                  "/absolute.xhtml", "missing.xhtml"])
def test_native_rejects_external_escaping_or_missing_manifest_members(tmp_path, href):
    source = tmp_path / "unsafe.epub"
    _package(source, href=href)
    with pytest.raises(ValueError):
        read_epub_package(source)


def test_native_rejects_duplicate_manifest_id(tmp_path):
    source = tmp_path / "duplicate.epub"
    _package(source, extra_manifest='<item id="chapter" href="nav.xhtml" media-type="application/xhtml+xml"/>')
    with pytest.raises(ValueError, match="duplicate"):
        read_epub_package(source)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-32"])
def test_native_rejects_entity_declarations_in_all_xml_encodings(tmp_path, encoding):
    source = tmp_path / "entity.epub"
    xml = '<?xml version="1.0"?><!DOCTYPE container [<!ENTITY x "expanded">]><container>&x;</container>'
    _package(source, container=xml.encode(encoding))
    with pytest.raises(ValueError, match="entity declarations"):
        read_epub_package(source)
