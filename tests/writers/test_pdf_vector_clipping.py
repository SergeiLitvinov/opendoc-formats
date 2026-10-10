"""Own Form XObject clips retain native regions or refuse unsupported state."""

import pymupdf as fitz
import pytest
from opendoc_model import get_integration

from opendoc_formats import ExportOptions, read_document, write_document


def _source(path, rotation=0, cropped=False):
    with fitz.open() as outer, fitz.open() as inner:
        page = outer.new_page(width=240, height=240)
        page.draw_rect(fitz.Rect(20, 20, 220, 220), color=None, fill=(1, 0, 0))
        child = inner.new_page(width=240, height=240)
        child.draw_rect(child.rect, color=None, fill=(0, 0, 1))
        child.draw_rect(fitz.Rect(70, 70, 170, 170), color=None, fill=(0, 1, 0))
        page.show_pdf_page(fitz.Rect(60, 60, 180, 180), inner, 0, clip=fitz.Rect(50, 50, 190, 190))
        if cropped:
            page.set_cropbox(fitz.Rect(20, 20, 220, 220))
        page.set_rotation(rotation)
        outer.save(path)


def _pixels(path):
    with fitz.open(path) as pdf:
        raster = pdf[0].get_pixmap(alpha=False)
        return raster.width, raster.height, raster.samples


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('cropped', [False, True])
def test_form_rectangular_clips_have_exact_original_pixels_in_two_cycles(tmp_path, rotation, cropped):
    source = tmp_path / 'own.pdf'
    _source(source, rotation, cropped)
    original, pixels = source.read_bytes(), _pixels(source)
    path = source
    for cycle in range(2):
        imported = read_document(path)
        assert imported.success
        resources = [resource for resource in imported.document.resources.values()
                     if resource.media_type == 'application/pdf+vector']
        assert any(resource.properties['clip_rects'] for resource in resources)
        transport = tmp_path / f'cycle-{cycle}.json'
        assert write_document(imported.document, transport).success
        path = transport.with_suffix('.pdf')
        report = write_document(read_document(transport).document, path)
        assert report.success
        assert not report.issues
        assert _pixels(path) == pixels
    assert source.read_bytes() == original


def test_nonrectangular_clip_has_located_opaque_source_and_atomic_refusal(tmp_path):
    source = tmp_path / 'curve-clip.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page(width=240, height=240)
        page.draw_rect(page.rect, color=None, fill=(0, 0, 1))
        xref = page.get_contents()[-1]
        own_clip = b'q\n40 120 m 40 75 75 40 120 40 c 165 40 200 75 200 120 c 200 165 165 200 120 200 c '
        own_clip += b'75 200 40 165 40 120 c h W n\n'
        pdf.update_stream(xref, own_clip + pdf.xref_stream(xref) + b'\nQ\n')
        pdf.save(source)
    imported = read_document(source)
    assert imported.success
    issue = next(issue for issue in imported.issues if issue.code == 'pdf.vector-graphics-state')
    assert issue.location.startswith('resources[')
    ledger = get_integration(imported.document)
    assert any(record.issue.code == issue.code and record.state.value == 'opaque' for record in ledger.preservation)
    assert imported.document.resources['pdf-original-source'].data == source.read_bytes()
    transport = tmp_path / 'curve.json'
    assert write_document(imported.document, transport).success
    output = tmp_path / 'previous.pdf'
    output.write_bytes(b'previous artifact')
    report = write_document(read_document(transport).document, output)
    assert not report.success
    assert output.read_bytes() == b'previous artifact'


def test_clipped_vector_export_cancellation_preserves_previous_file(tmp_path):
    source = tmp_path / 'own.pdf'
    _source(source)
    output = tmp_path / 'previous.pdf'
    output.write_bytes(b'previous artifact')
    report = write_document(read_document(source).document, output, options=ExportOptions(cancelled=lambda: True))
    assert not report.success
    assert output.read_bytes() == b'previous artifact'


def test_page_content_group_is_not_hidden_by_annotation_exclusion(tmp_path):
    source = tmp_path / 'content-group.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page(width=240, height=240)
        page.draw_rect(page.rect, color=None, fill=(1, 0, 0))
        pdf.xref_set_key(page.xref, 'Group', '<< /S /Transparency /I true /K false >>')
        page.add_rect_annot(fitz.Rect(20, 20, 40, 40))
        pdf.save(source)
    original = source.read_bytes()
    imported = read_document(source)
    assert imported.success
    vectors = [resource for resource in imported.document.resources.values() if resource.media_type == 'application/pdf+vector']
    assert len(vectors) == 1 and vectors[0].properties['graphics_state_unsupported']
    assert any(issue.code == 'pdf.vector-graphics-state' and issue.location for issue in imported.issues)
    transport = tmp_path / 'group.json'
    assert write_document(imported.document, transport).success
    output = tmp_path / 'previous.pdf'
    output.write_bytes(b'previous artifact')
    assert not write_document(read_document(transport).document, output).success
    assert output.read_bytes() == b'previous artifact'
    assert source.read_bytes() == original


@pytest.mark.parametrize('invalid', ['depth', 'inverted', 'nonfinite'])
def test_invalid_clip_contract_refuses_before_replacing_file(tmp_path, invalid):
    source = tmp_path / 'own.pdf'
    _source(source)
    model = read_document(source).document
    resource = next(resource for resource in model.resources.values() if resource.properties.get('clip_rects'))
    resource.properties['clip_rects'] = {
        'depth': [[0, 0, 240, 240]] * 65,
        'inverted': [[100, 100, 50, 50]],
        'nonfinite': [[0, 0, float('nan'), 50]],
    }[invalid]
    output = tmp_path / 'previous.pdf'
    output.write_bytes(b'previous artifact')
    report = write_document(model, output)
    assert not report.success
    assert output.read_bytes() == b'previous artifact'
