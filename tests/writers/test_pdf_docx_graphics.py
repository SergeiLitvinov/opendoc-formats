"""Independent PDF clip scopes, Form instances and group-compositing originals."""

import base64
from io import BytesIO
from xml.etree import ElementTree as ET

import pymupdf as fitz
import pytest
from opendoc_model import Image, TextRun, document_from_json, document_to_json, walk_model
from PIL import Image as PillowImage

from opendoc_formats import read_document, write_document
from opendoc_formats.readers.pdf_graphics_state import native_paint_states
from opendoc_formats.writers.pdf_to_docx import PdfModelConverter
from tests.writers.test_pdf_docx_complex import raster_bytes


def image_form(path, rotation=0, page_rotation=0, repeated=False, reflected=False):
    with fitz.open() as child, fitz.open() as native:
        image_page = child.new_page(width=80, height=40)
        image_page.insert_image(image_page.rect, stream=raster_bytes())
        if reflected:
            stream = image_page.get_contents()[0]
            child.update_stream(stream, b'q -1 0 0 1 80 0 cm\n' + child.xref_stream(stream) + b'\nQ\n')
        page = native.new_page(width=600, height=500)
        page.draw_rect(page.rect, color=None, fill=(.9, .9, .9))
        page.show_pdf_page(fitz.Rect(60, 80, 280, 200), child, 0, clip=fitz.Rect(10, 5, 65, 35),
                           keep_proportion=False, rotate=rotation)
        if repeated:
            page.show_pdf_page(fitz.Rect(340, 240, 560, 360), child, 0, clip=fitz.Rect(5, 10, 60, 40),
                               keep_proportion=False, rotate=rotation)
        page.insert_text((60, 440), 'Outside clip scopes', fontsize=12)
        page.set_rotation(page_rotation)
        native.save(path)


def curved_clip(path, even_odd=False, vector=False):
    with fitz.open() as native:
        page = native.new_page(width=400, height=300)
        page.draw_rect(page.rect, fill=(.8, .8, .8), color=None)
        if vector:
            page.draw_rect(fitz.Rect(60, 70, 300, 190), fill=(0, .4, .8), color=None)
        else:
            page.insert_image(fitz.Rect(60, 70, 300, 190), stream=raster_bytes())
        xref = page.get_contents()[-1]
        # Independent cubic ellipse; the second subpath cuts a hole with W*.
        clip = b'80 170 m 80 210 130 230 180 230 c 230 230 280 210 280 170 c '
        clip += b'280 130 230 110 180 110 c 130 110 80 130 80 170 c h\n'
        if even_odd:
            clip += b'150 145 60 50 re\n'
        native.update_stream(xref, b'q\n' + clip + (b'W* n\n' if even_odd else b'W n\n')
                             + native.xref_stream(xref) + b'\nQ\n')
        page.insert_text((60, 260), 'Unclipped editable text', fontsize=12)
        native.save(path)


def grouped_form(path, *, opacity=1, isolated=True, knockout=False, blend='Normal', partial_text=False):
    with fitz.open() as native:
        page = native.new_page(width=400, height=300)
        page.draw_rect(page.rect, color=None, fill=(.9, .85, .6))
        page.insert_text((50, 250), 'Outside group', fontsize=12)
        form = native.get_new_xref()
        native.update_object(form, f'''<< /Type /XObject /Subtype /Form /BBox [0 0 160 100]
          /Resources << /ExtGState << /ChildAlpha << /ca 0.5 /CA 0.5 >> >> >>
          /Group << /S /Transparency /CS /DeviceRGB /I {str(isolated).lower()} /K {str(knockout).lower()} >> >>''')
        native.update_stream(form, b'1 0 0 rg 0 0 110 100 re f\nq /ChildAlpha gs 0 0 1 rg 50 0 110 100 re f Q\n')
        resources = int(native.xref_get_key(page.xref, 'Resources')[1].split()[0])
        native.xref_set_key(resources, 'XObject/OwnForm', f'{form} 0 R')
        native.xref_set_key(resources, 'ExtGState/Outer', f'<< /ca {opacity} /CA {opacity} /BM /{blend} >>')
        stream = native.get_new_xref()
        native.update_object(stream, '<< >>')
        native.update_stream(stream, b'q /Outer gs 1 0 0 1 80 100 cm /OwnForm Do Q\n')
        native.xref_set_key(page.xref, 'Contents', '[' + ' '.join(f'{ref} 0 R' for ref in page.get_contents())
                            + f' {stream} 0 R]')
        if partial_text:
            page.insert_text((80, 50), 'Partially hidden text', fontsize=12)
            text = page.get_contents()[-1]
            native.update_stream(text, b'q 80 240 25 30 re W n\n' + native.xref_stream(text) + b'\nQ\n')
        native.save(path)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('page_rotation', [0, 90])
@pytest.mark.parametrize('reflected', [False, True])
def test_form_rectangular_raster_clips_and_repeats_keep_pixels_and_scopes(tmp_path, rotation, page_rotation, reflected):
    source, output = tmp_path / 'forms.pdf', tmp_path / 'forms.docx'
    image_form(source, rotation, page_rotation, repeated=True, reflected=reflected)
    imported = read_document(source)
    assert imported.success, imported.issues
    original = document_to_json(imported.document)
    evidence = imported.document.sections[0].properties['pdf_graphics']
    image_states = [paint for paint in evidence['paints'] if paint['kind'] == 'fill-image']
    assert len(image_states) == 2 and image_states[0]['clips'] != image_states[1]['clips']
    text = next(paint for paint in evidence['paints'] if paint['kind'] == 'fill-text')
    assert text['clips'] == []  # Q restores the outer scope; no whole-page rejection.
    report = PdfModelConverter().convert(source, output)
    assert report.success, report.issues
    assert document_to_json(imported.document) == original
    expected = [image for ref in walk_model(imported.document) if isinstance(image := ref.node, Image)
                and imported.document.resources[image.resource_id].media_type.startswith('image/')]
    originals = [PillowImage.open(BytesIO(imported.document.resources[item.resource_id].data)).convert('RGBA')
                 for item in expected]
    for cycle in range(2):
        model = document_from_json(document_to_json(read_document(output).document))
        pictures = [ref.node for ref in walk_model(model) if isinstance(ref.node, Image)
                    and model.resources[ref.node.resource_id].media_type.startswith('image/')
                    and model.resources[ref.node.resource_id].media_type != 'image/svg+xml']
        assert len(pictures) == 2
        assert all(item.crop is not None for item in pictures)
        assert pictures[0].crop != pictures[1].crop
        for original_pixels, image in zip(originals, pictures, strict=True):
            restored = PillowImage.open(BytesIO(model.resources[image.resource_id].data)).convert('RGBA')
            assert restored.size == original_pixels.size and restored.tobytes() == original_pixels.tobytes()
        assert any(isinstance(ref.node, TextRun) and ref.node.text == 'Outside clip scopes' for ref in walk_model(model))
        output = tmp_path / f'cycle-{cycle}.docx'
        assert write_document(model, output).success


@pytest.mark.parametrize('even_odd', [False, True])
def test_curved_clip_svg_preserves_original_samples_and_winding_across_cycles(tmp_path, even_odd):
    source, output = tmp_path / 'curve.pdf', tmp_path / 'curve.docx'
    curved_clip(source, even_odd)
    model = read_document(source).document
    original = next(resource.data for resource in model.resources.values() if resource.media_type == 'image/png')
    report = PdfModelConverter().convert(source, output)
    assert report.success, report.issues
    previous_svg = None
    for cycle in range(2):
        model = document_from_json(document_to_json(read_document(output).document))
        svgs = [resource.data for resource in model.resources.values() if resource.media_type == 'image/svg+xml']
        clipped = [blob for blob in svgs if b'odf-native-clip' in blob]
        assert len(clipped) == 1
        root = ET.fromstring(clipped[0])
        images = root.findall('.//{http://www.w3.org/2000/svg}image')
        assert len(images) == 1
        encoded = images[0].get('{http://www.w3.org/1999/xlink}href').split(',', 1)[1]
        assert base64.b64decode(encoded) == original
        paths = root.findall('.//{http://www.w3.org/2000/svg}clipPath/{http://www.w3.org/2000/svg}path')
        assert any(path.get('clip-rule') == ('evenodd' if even_odd else 'nonzero') for path in paths)
        # A long curve at an SVG clip extremum is distorted by Office. The
        # derived SVG must retain exact cubics split into shorter pieces.
        assert any(path.get('d', '').count('C') > 4 for path in paths)
        if previous_svg is not None:
            assert clipped[0] == previous_svg
        previous_svg = clipped[0]
        output = tmp_path / f'curve-cycle-{cycle}.docx'
        assert write_document(model, output).success


def test_curved_vector_clip_is_retained_as_vector_through_two_cycles(tmp_path):
    source, output = tmp_path / 'vector.pdf', tmp_path / 'vector.docx'
    curved_clip(source, even_odd=True, vector=True)
    imported = read_document(source)
    original = document_to_json(imported.document)
    report = PdfModelConverter().convert(source, output)
    assert report.success, report.issues
    assert document_to_json(imported.document) == original
    for cycle in range(2):
        model = document_from_json(document_to_json(read_document(output).document))
        clipped = [r.data for r in model.resources.values() if r.media_type == 'image/svg+xml'
                   and b'odf-native-clip' in r.data]
        assert len(clipped) == 1
        root = ET.fromstring(clipped[0])
        assert root.findall('.//{http://www.w3.org/2000/svg}path')
        assert not root.findall('.//{http://www.w3.org/2000/svg}image')
        output = tmp_path / f'vector-{cycle}.docx'
        assert write_document(model, output).success


@pytest.mark.parametrize('isolated', [False, True])
def test_neutral_form_group_retains_child_alpha_and_editable_outer_text(tmp_path, isolated):
    source, output = tmp_path / 'group.pdf', tmp_path / 'group.docx'
    grouped_form(source, isolated=isolated)
    imported = read_document(source)
    groups = imported.document.sections[0].properties['pdf_graphics']['groups']
    assert groups and any(group['isolated'] is isolated for group in groups)
    report = PdfModelConverter().convert(source, output)
    assert report.success, report.issues
    model = read_document(output).document
    assert any(isinstance(ref.node, TextRun) and ref.node.text == 'Outside group' for ref in walk_model(model))
    assert len([r for r in model.resources.values() if r.media_type == 'image/svg+xml']) >= 3


@pytest.mark.parametrize('options', [{'opacity': .5}, {'knockout': True}, {'blend': 'Multiply'}, {'partial_text': True}])
def test_unrepresented_group_or_partial_text_clip_refuses_atomically(tmp_path, options):
    source, output = tmp_path / 'complex.pdf', tmp_path / 'previous.docx'
    grouped_form(source, **options)
    output.write_bytes(b'previous')
    report = PdfModelConverter().convert(source, output)
    assert not report.success
    assert output.read_bytes() == b'previous'


def test_native_graphics_nesting_has_selected_limits_and_borrowed_path_lifetimes(tmp_path):
    from opendoc_model import ArtifactLimitError, DocumentLimits

    source = tmp_path / 'forms.pdf'
    image_form(source)
    for index in range(12):
        with fitz.open(source) as native:
            evidence = native_paint_states(native[0])
            assert not evidence.get('unknown')
            assert evidence['clips']
            assert native[0].get_pixmap().width == 600
            with pytest.raises(ArtifactLimitError) as raised:
                native_paint_states(native[0], limits=DocumentLimits(max_depth=1))
            assert raised.value.maximum == 1 and raised.value.quota == 'depth'


def test_stencil_is_not_misidentified_as_retained_intrinsic_alpha(tmp_path):
    source, output = tmp_path / 'stencil.pdf', tmp_path / 'previous.docx'
    with fitz.open() as native:
        page = native.new_page(width=400, height=300)
        page.draw_rect(page.rect, fill=(1, 1, 1), color=None)
        image = native.get_new_xref()
        native.update_object(image, '<< /Type /XObject /Subtype /Image /Width 8 /Height 8 '
                             '/ImageMask true /BitsPerComponent 1 /Decode [0 1] >>')
        native.update_stream(image, b'\xaa\x55' * 4)
        resources = int(native.xref_get_key(page.xref, 'Resources')[1].split()[0])
        native.xref_set_key(resources, 'XObject/Stencil', f'{image} 0 R')
        stream = page.get_contents()[0]
        native.update_stream(stream, native.xref_stream(stream)
                             + b'q 1 0 0 rg 80 0 0 80 60 100 cm /Stencil Do Q\n')
        native.save(source)
    imported = read_document(source)
    assert imported.success
    assert any(issue.code == 'pdf.graphics-state' for issue in imported.issues)
    output.write_bytes(b'previous')
    assert not PdfModelConverter().convert(source, output).success
    assert output.read_bytes() == b'previous'


def test_preblended_matte_is_not_misidentified_as_straight_alpha(tmp_path):
    source, output = tmp_path / 'matte.pdf', tmp_path / 'previous.docx'
    original = tmp_path / 'original.pdf'
    image_form(original)
    with fitz.open(original) as native:
        mask = native[0].get_images(full=True)[0][1]
        assert mask > 0
        native.xref_set_key(mask, 'Matte', '[1 1 1]')
        native.save(source)
    imported = read_document(source)
    assert imported.success
    assert any(issue.code == 'pdf.graphics-state' for issue in imported.issues)
    assert imported.document.resources['pdf-original-source'].data == source.read_bytes()
    output.write_bytes(b'previous')
    assert not PdfModelConverter().convert(source, output).success
    assert output.read_bytes() == b'previous'


def test_fully_contained_form_text_keeps_editable_glyphs_and_restores_outer_scope(tmp_path):
    source, output = tmp_path / 'text-form.pdf', tmp_path / 'text-form.docx'
    with fitz.open() as child, fitz.open() as native:
        page = child.new_page(width=200, height=100)
        page.insert_text((40, 50), 'Editable Form text', fontsize=12)
        page = native.new_page(width=400, height=300)
        page.show_pdf_page(fitz.Rect(80, 100, 240, 180), child, clip=fitz.Rect(20, 10, 180, 90))
        page.insert_text((50, 250), 'Outside Form', fontsize=12, fontname='cour')
        native.save(source)
    imported = read_document(source)
    states = imported.document.sections[0].properties['pdf_graphics']['paints']
    texts = [paint for paint in states if paint['kind'] == 'fill-text']
    assert len(texts) == 2 and texts[0]['clips'] and not texts[1]['clips']
    report = PdfModelConverter().convert(source, output)
    assert report.success, report.issues
    for cycle in range(2):
        model = document_from_json(document_to_json(read_document(output).document))
        texts = [ref.node.text for ref in walk_model(model) if isinstance(ref.node, TextRun)]
        assert 'Editable Form text' in texts and 'Outside Form' in texts
        output = tmp_path / f'text-{cycle}.docx'
        assert write_document(model, output).success


@pytest.mark.parametrize('corruption', ['reference', 'bbox', 'opacity', 'command', 'unknown'])
def test_corrupt_native_evidence_refuses_atomically(tmp_path, corruption):
    source, output = tmp_path / 'curve.pdf', tmp_path / 'previous.docx'
    curved_clip(source)
    model = read_document(source).document
    state = model.sections[0].properties['pdf_graphics']
    paint = next(item for item in state['paints'] if item['kind'] == 'fill-image')
    if corruption == 'reference':
        paint['clips'] = [9999]
    elif corruption == 'bbox':
        paint['bbox'] = [10, 10, 5, 5]
    elif corruption == 'opacity':
        paint['alpha'] = 2
    elif corruption == 'command':
        state['clips'][paint['clips'][0]]['commands'][1] = ['C', 1, 2]
    else:
        paint['unknown'] = True
    output.write_bytes(b'previous')
    assert not write_document(model, output).success
    assert output.read_bytes() == b'previous'
