"""Own EPUB loss fixtures, including stable source addresses and JSON transport."""

import zipfile

from opendoc_model import document_from_json, document_to_json, get_integration

from opendoc_formats import read_document


def test_epub_asset_and_xhtml_losses_survive_json(tmp_path):
    source = tmp_path / "losses.epub"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", '''<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
            <rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>''')
        archive.writestr("book.opf", '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
            <metadata/><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
            <item id="font" href="font.woff" media-type="font/woff"/>
            <item id="audio" href="audio.ogg" media-type="audio/ogg"/>
            <item id="nonxhtml" href="plain.txt" media-type="text/plain"/>
            </manifest><spine><itemref idref="chapter"/><itemref idref="nonxhtml"/></spine></package>''')
        archive.writestr("chapter.xhtml", '''<html><body>
            <p>Retained<img id="missing" src="absent.png" alt="fallback"/></p>
            <img id="standalone" src="outside.png"/>
            <svg id="drawing"><path d="M0 0 L1 1"/></svg>
            <audio id="sound" src="audio.ogg"/><video id="movie"/>
            <object id="object" data="embedded.bin"/><script id="script">window.fixture=true</script>
            </body></html>''')
        archive.writestr("font.woff", b"own inert placeholder")
        archive.writestr("audio.ogg", b"own inert placeholder")
        archive.writestr("plain.txt", "Unsupported spine member")
    result = read_document(source)
    assert result.success and not result.assessment_complete and not result.lossless
    reasons = {issue.reason for issue in result.issues}
    assert reasons == {
        "missing-image", "svg-resource", "unsupported-media",
        "unsupported-object", "inactive-script", "inert-asset", "unsupported-spine-item", "source-package-xml",
    }
    assert all(issue.severity.value == "loss" for issue in result.issues)
    assert any(issue.location.endswith("chapter.xhtml#missing") for issue in result.issues)
    assert any(issue.location.endswith("font.woff") for issue in result.issues)
    assert result.document.sections[0].blocks[0].plain_text == "Retainedfallback"
    restored = document_from_json(document_to_json(result.document))
    assert get_integration(restored) == get_integration(result.document)
    ledger = get_integration(restored)
    retained = [record for record in ledger.preservation if record.state.value == "opaque"]
    assert len(retained) == 5
    assert all(record.extra["resource_id"] in restored.resources for record in retained)
    assert restored.resources["epub-font"].data == b"own inert placeholder"
    assert restored.resources["epub-audio"].data == b"own inert placeholder"
    assert all(record.provenance.source_path == str(source) for record in ledger.preservation)
    assert any(record.provenance.object_id == "missing" for record in ledger.preservation)
    transported = tmp_path / "transport.json"
    transported.write_text(document_to_json(restored), encoding="utf-8")
    reread = read_document(transported)
    assert reread.issues == result.issues
