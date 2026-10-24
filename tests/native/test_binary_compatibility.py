"""Compatibility baselines come from actual wire structures, not a converter's own output."""

import hashlib

import pytest
from opendoc_model import Table, document_from_json, document_to_json

from opendoc_formats.anatomy import compare_snapshots, inspect_binary
from opendoc_formats.support.document_adapters import document_to_text, text_to_document
from tests.binary_fixtures import RGB, W, own_docx, own_pdf


def test_docx_native_edit_preserves_unknown_binary_parts_relationships_and_table_order(tmp_path):
    pytest.importorskip('docx')
    from opendoc_formats.docx import DocxPackage, ReplaceTextSpan

    source = own_docx()
    before = inspect_binary(source, capture=True)
    with DocxPackage(source) as document:
        paragraph = next(item for item in document.paragraphs if item.is_body and item.text == 'Before')
        edited = document.to_bytes([ReplaceTextSpan(paragraph.id, 0, len('Before'), 'Edited')])
    (tmp_path/'source.docx').write_bytes(source)
    (tmp_path/'edited.docx').write_bytes(edited)
    after = inspect_binary(edited, capture=True)
    difference = compare_snapshots(before, after)
    assert difference['added'] == difference['removed'] == []
    assert difference['content_changed'] == ['zip:/word/document.xml']
    originals = {item.locator: item for item in before.items}
    modified = {item.locator: item for item in after.items}
    for name in ('word/media/own.png', 'word/embeddings/unknown.bin', 'word/_rels/document.xml.rels'):
        assert modified['zip:/'+name].payload == originals['zip:/'+name].payload
    for snapshot in (before, after):
        body = next(item for item in snapshot.items if item.locator == 'zip:/word/document.xml')
        assert [node.tag for node in body.xml_nodes if node.path in ('0/0/0', '0/0/1', '0/0/2')] == [
            '{'+W+'}p', '{'+W+'}tbl', '{'+W+'}p',
        ]
    assert before.source_sha256 == hashlib.sha256(source).hexdigest()


def test_docx_binary_original_exposes_nested_content_and_projected_losses(tmp_path):
    pytest.importorskip('docx')
    from opendoc_formats.readers.docx import read_docx_model

    source = tmp_path/'own.docx'
    original = own_docx()
    source.write_bytes(original)
    model = read_docx_model(source)
    view = document_to_text(model)
    cell = view.tables[0].rows[0][0]
    assert 'Cell' in cell and 'Nested' in cell and 'Own alt' in cell
    assert view.plain.index('Before') < view.plain.index('Cell') < view.plain.index('After')
    codes = {record.issue.code for record in view.diagnostics.preservation}
    assert {'legacy.image', 'legacy.link', 'legacy.nested-table', 'legacy.text-style'} <= codes
    for _ in range(2):
        restored = document_from_json(document_to_json(text_to_document(view)))
        assert isinstance(restored.sections[0].blocks[1], Table)
        view = document_to_text(restored)
        assert view.tables[0].rows[0][0] == cell
    assert source.read_bytes() == original


@pytest.mark.parametrize('route', ['geometry', 'ocr'])
def test_pdf_binary_original_table_occurrences_are_positioned_without_duplicate_tables(tmp_path, route):
    pytest.importorskip('pymupdf')
    from opendoc_formats.readers.pdf_geometry import extract_pdf_geometry
    from opendoc_formats.readers.pdf_ocr_merge import merge_pdf_with_ocr
    from opendoc_formats.readers.pdf_semantic import analyze_pdf_geometry

    source = tmp_path/'own.pdf'
    original, _ = own_pdf()
    source.write_bytes(original)
    geometry = extract_pdf_geometry(source)
    view = analyze_pdf_geometry(geometry) if route == 'geometry' else merge_pdf_with_ocr(geometry)
    assert len(view.tables) == 1 and view.tables[0].rows == [['R1C1', 'R1C2'], ['R2C1', 'R2C2']]
    restored = text_to_document(view)
    assert sum(isinstance(block, Table) for section in restored.sections for block in section.blocks) == 1
    assert restored.sections[0].blocks[0].plain_text == 'Before'
    assert isinstance(restored.sections[0].blocks[1], Table)
    assert restored.sections[0].blocks[-1].plain_text == 'After'
    assert source.read_bytes() == original


def test_pdf_binary_image_baseline_is_compared_to_actual_decoded_pixels_and_located_losses(tmp_path):
    engine = pytest.importorskip('pymupdf')
    from opendoc_formats import read_document

    source = tmp_path/'own.pdf'
    original, _ = own_pdf()
    source.write_bytes(original)
    manifest = inspect_binary(source, capture=True)
    assert next(item for item in manifest.items if item.locator == 'pdf:xref=6').payload is not None
    imported = read_document(source)
    assert imported.success
    images = [resource for resource in imported.document.resources.values() if resource.media_type == 'image/png']
    assert images and any(engine.Pixmap(resource.data).samples == RGB for resource in images)
    view = document_to_text(imported.document)
    losses = [record for record in view.diagnostics.preservation if record.issue.code == 'legacy.image']
    assert losses and all(record.provenance.source_path == str(source) and record.provenance.page == 1 for record in losses)
    assert source.read_bytes() == original
