"""Two full native format cycles preserve declarations and remeasure live targets."""

import json

import pymupdf
import pytest
from opendoc_model import (
    PreservationState,
    document_from_json,
    document_to_json,
    validate_object_mapping,
)

from opendoc_formats import get_object_mapping, read_document, read_pdf_origin_mapping, write_document
from opendoc_formats.support.pdf_mapping_history import CATALOG_KEY, HISTORY_KEY, load_history
from opendoc_formats.writers.html_resources import document_images
from tests.writers.test_pdf_mapping import _document


def _sources(mapping):
    return {item.id: item.provenance for item in mapping.sources}


def test_two_full_pdf_json_cycles_preserve_origins_and_edit_delete(tmp_path):
    current = tmp_path / 'initial.pdf'
    original = _document()
    assert write_document(original, current).success
    history = read_pdf_origin_mapping(current)
    expected = _sources(history)
    assert len(expected) == 2
    initial_bytes = current.read_bytes()
    for cycle in range(2):
        imported = read_document(current)
        assert imported.success, imported.issues
        document = document_from_json(document_to_json(imported.document))
        previous = document_to_json(document)
        history = read_pdf_origin_mapping(current)
        assert history.assessment_complete and _sources(history) == expected
        validate_object_mapping(history, target=document)
        images = list(document_images(document))
        assert len(images) == 2 and all(HISTORY_KEY in image.properties for image, _ in images)
        assert all(item.resource_id is None and item.node_id is None for item in history.sources)
        document.sections[0].blocks.reverse()
        output = tmp_path / f'cycle{cycle}.pdf'
        report = write_document(document, output)
        assert report.success, report.to_dict()
        measured = get_object_mapping(report)
        assert measured.assessment_complete and measured.publication == 'published'
        assert all(entry.state is PreservationState.VISUAL for entry in measured.entries)
        assert _sources(read_pdf_origin_mapping(output)) == expected
        assert document_to_json(imported.document) == previous
        current = output
    assert (tmp_path / 'initial.pdf').read_bytes() == initial_bytes
    document = read_document(current).document
    document.sections[0].blocks.pop()
    # Remove unused raster resources too: carried origin declarations have no dangling handles.
    live = {image.resource_id for image, _ in document_images(document)}
    document.resources = {key: value for key, value in document.resources.items()
                          if key in live or value.media_type == 'application/pdf'}
    assert not document.validate()
    final = tmp_path / 'deleted.pdf'
    report = write_document(document, final)
    assert report.success, report.to_dict()
    history = read_pdf_origin_mapping(final)
    assert len(history.sources) == len(history.targets) == 1
    validate_object_mapping(history, target=read_document(final).document)
    assert set(_sources(history)) < set(expected)


def test_stale_native_geometry_does_not_bind_or_resurrect_history(tmp_path):
    source = tmp_path / 'initial.pdf'
    assert write_document(_document(), source).success
    changed = tmp_path / 'changed.pdf'
    with pymupdf.open(source) as pdf:
        box = pdf[0].mediabox
        pdf[0].set_cropbox(pymupdf.Rect(10, 10, box.width, box.height))
        pdf.save(changed, garbage=4)
    routes, issues = load_history(changed)
    assert not routes and all(item.code == 'pdf.mapping-history-stale' and item.location for item in issues)
    imported = read_document(changed)
    assert imported.success and any(item.code == 'pdf.mapping-history-stale' for item in imported.issues)
    assert all(HISTORY_KEY not in image.properties for image, _ in document_images(imported.document))
    assert read_pdf_origin_mapping(changed) is None


@pytest.mark.parametrize('case', ['json', 'version', 'compressed-limit', 'decoded-limit', 'route-owner'])
def test_invalid_history_is_located_and_pixels_still_import(tmp_path, monkeypatch, case):
    from opendoc_formats.support import pdf_mapping_history as module

    source = tmp_path / 'initial.pdf'
    assert write_document(_document(), source).success
    changed = tmp_path / 'invalid.pdf'
    with pymupdf.open(source) as pdf:
        xref = int(pdf.xref_get_key(pdf.pdf_catalog(), CATALOG_KEY)[1].split()[0])
        raw = pdf.xref_stream(xref)
        if case == 'json':
            raw = b'{invalid'
        elif case == 'version':
            data = json.loads(raw)
            data['version'] = 99
            raw = json.dumps(data).encode()
        elif case == 'route-owner':
            data = json.loads(raw)
            data['routes'].append(data['routes'][0])
            raw = json.dumps(data).encode()
        elif case == 'decoded-limit':
            raw += b' ' * 200_000
        pdf.update_stream(xref, raw, compress=True)
        pdf.save(changed)
    if case == 'compressed-limit':
        monkeypatch.setattr(module, 'MAX_HISTORY_BYTES', 1)
    elif case == 'decoded-limit':
        monkeypatch.setattr(module, 'MAX_HISTORY_BYTES', 20_000)
    imported = read_document(changed)
    assert imported.success, imported.issues
    assert any(item.code == 'pdf.mapping-history-invalid' and item.location for item in imported.issues)
    assert len(list(document_images(imported.document))) == 2
    assert all(HISTORY_KEY not in image.properties for image, _ in document_images(imported.document))


def test_editable_json_declaration_cannot_claim_current_handles(tmp_path):
    source = tmp_path / 'initial.pdf'
    assert write_document(_document(), source).success
    document = document_from_json(document_to_json(read_document(source).document))
    image = next(document_images(document))[0]
    history = image.properties[HISTORY_KEY]
    history['sources'][0]['resource_id'] = image.resource_id
    output = tmp_path / 'output.pdf'
    output.write_bytes(b'previous')
    report = write_document(document, output)
    assert not report.success and output.read_bytes() == b'previous'
