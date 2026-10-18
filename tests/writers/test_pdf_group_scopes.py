"""Independent native PDF originals for typed mixed scopes and RGB composition."""

from dataclasses import replace
from xml.etree import ElementTree as ET

import pymupdf as fitz
import pytest
from opendoc_model import (
    GroupCompositing,
    Image,
    IssueSeverity,
    TextRun,
    document_from_json,
    document_to_json,
    get_anchor,
    get_vector_scene,
    remove_vector_scene,
    set_scene_clip,
    set_scene_group,
    walk_model,
)

from opendoc_formats import read_document, write_document
from opendoc_formats.writers.pdf_docx_model import prepare_pdf_docx
from opendoc_formats.writers.pdf_to_docx import PdfModelConverter
from tests.writers.test_pdf_docx_graphics import grouped_form

MODES = ['Normal', 'Multiply', 'Screen', 'Overlay', 'Darken', 'Lighten', 'ColorDodge',
         'ColorBurn', 'HardLight', 'SoftLight', 'Difference', 'Exclusion']


def _svg_model(document):
    prepared = prepare_pdf_docx(document)
    images = [r.node for r in walk_model(prepared) if isinstance(r.node, Image)]
    assert len(images) == 1
    image = images[0]
    svg = prepared.resources[image.resource_id].data
    root = ET.fromstring(svg)
    assert not root.findall('.//{http://www.w3.org/2000/svg}image')
    assert not root.findall('.//{http://www.w3.org/2000/svg}filter')
    assert not root.findall('.//{http://www.w3.org/2000/svg}g')
    return image, svg


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('isolated', [False, True])
@pytest.mark.parametrize('background_alpha', [1, .35])
def test_group_composition_matches_independent_pdf_color_regions(tmp_path, mode, isolated, background_alpha):
    knockout = False
    source = tmp_path / 'group.pdf'
    grouped_form(source, opacity=.5, blend=mode, knockout=knockout, isolated=isolated, background_alpha=background_alpha)
    model = read_document(source).document
    original = document_to_json(model)
    scene = get_vector_scene(model, model.sections[0].properties['pdf_scene_id'])
    assert scene.scope_version == 1 and scene.occurrences
    assert any(g.compositing.knockout is knockout and g.compositing.opacity == .5 for g in scene.groups)
    model = document_from_json(document_to_json(document_from_json(original)))
    image, svg = _svg_model(model)
    with fitz.open(source) as native, fitz.open(stream=svg, filetype='svg') as vector:
        scale = image.box.width/vector[0].rect.width
        expected = native[0].get_pixmap()
        actual = vector[0].get_pixmap(matrix=fitz.Matrix(scale, scale))
        for x, y in [(30, 30), (100, 150), (150, 150), (210, 150), (300, 220)]:
            a = expected.pixel(x, y)
            b = actual.pixel(round(x-image.box.x), round(y-image.box.y))
            assert max(abs(u-v) for u, v in zip(a, b)) <= 3, (mode, isolated, knockout, (x, y), a, b)
    assert document_to_json(model) == original


@pytest.mark.parametrize('options', [{'opacity': .5}, {'blend': 'Screen'}, {'blend': 'Multiply'}])
def test_composite_vector_and_outer_editable_text_survive_two_docx_cycles(tmp_path, options):
    source, output = tmp_path / 'source.pdf', tmp_path / 'source.docx'
    grouped_form(source, **options)
    model = read_document(source).document
    result = write_document(model, output)
    assert not result.success and not output.exists()
    assert any(i.severity is IssueSeverity.LOSS and i.feature == 'pdf-docx.group-projection' for i in result.issues)
    # Exercise the private visual prototype, deliberately outside the public
    # measured PDF export profile. This does not count as lossless acceptance.
    preview = prepare_pdf_docx(model)
    preview.source_format = 'docx'
    assert write_document(preview, output).success
    previous = None
    for cycle in range(2):
        model = document_from_json(document_to_json(read_document(output).document))
        svgs = [r.data for r in model.resources.values() if r.media_type == 'image/svg+xml']
        assert len(svgs) == 1
        assert previous is None or previous == svgs[0]
        previous = svgs[0]
        assert any(isinstance(r.node, TextRun) and r.node.text == 'Outside group' for r in walk_model(model))
        output = tmp_path / f'cycle-{cycle}.docx'
        assert write_document(model, output).success


def test_strict_converter_rejects_group_structure_loss_even_with_verified_vector_appearance(tmp_path):
    source, destination = tmp_path / 'group.pdf', tmp_path / 'previous.docx'
    grouped_form(source, opacity=.5)
    destination.write_bytes(b'previous')
    result = PdfModelConverter().convert(source, destination)
    assert not result.success and destination.read_bytes() == b'previous'
    assert any(i.severity is IssueSeverity.LOSS and i.feature == 'pdf-docx.group-projection' for i in result.issues)
    assert any(i.feature == 'pdf-docx.loss-rejected' for i in result.issues)


def test_typed_group_edits_and_removal_do_not_restore_native_opacity(tmp_path):
    source = tmp_path / 'source.pdf'
    grouped_form(source, opacity=.5)
    model = read_document(source).document
    identifier = model.sections[0].properties['pdf_scene_id']
    scene = get_vector_scene(model, identifier)
    group = next(g for g in scene.groups if g.compositing.opacity == .5)
    _, before = _svg_model(model)
    set_scene_group(model, identifier, group.id, replace(group, compositing=replace(group.compositing, opacity=1)))
    prepared = prepare_pdf_docx(model)
    after = b''.join(r.data for r in prepared.resources.values() if r.media_type == 'image/svg+xml')
    assert before != after
    set_scene_group(model, identifier, group.id, replace(group, compositing=GroupCompositing()))
    destination = tmp_path / 'previous.docx'
    destination.write_bytes(b'previous')
    assert not write_document(model, destination).success
    assert destination.read_bytes() == b'previous'
    set_scene_group(model, identifier, group.id, None)
    assert write_document(model, destination).success


def test_partial_text_is_whole_in_model_and_clip_removal_is_authoritative(tmp_path):
    source = tmp_path / 'partial.pdf'
    grouped_form(source, partial_text=True)
    model = read_document(source).document
    identifier = model.sections[0].properties['pdf_scene_id']
    scene = get_vector_scene(model, identifier)
    text = next(r.node for r in walk_model(model) if isinstance(r.node, TextRun) and r.node.text == 'Partially hidden text')
    occurrence = next(o for o in scene.occurrences if o.node_id == get_anchor(text).id)
    assert occurrence
    original = document_to_json(model)
    destination = tmp_path / 'previous.docx'
    destination.write_bytes(b'previous')
    report = write_document(model, destination)
    assert not report.success and destination.read_bytes() == b'previous'
    assert any('native editable Word clipping' in issue.message for issue in report.issues)
    assert document_to_json(model) == original
    # Remove all typed clips, not just the native legacy properties.
    for clip in scene.clips:
        set_scene_clip(model, identifier, clip.id, None)
    model = document_from_json(document_to_json(model))
    assert write_document(model, destination).success
    restored = read_document(destination).document
    assert any(isinstance(r.node, TextRun) and r.node.text == text.text for r in walk_model(restored))


def test_removed_scene_does_not_restore_legacy_clip(tmp_path):
    source = tmp_path / 'partial.pdf'
    grouped_form(source, partial_text=True)
    model = read_document(source).document
    remove_vector_scene(model, model.sections[0].properties['pdf_scene_id'])
    assert write_document(model, tmp_path / 'unclipped.docx').success


@pytest.mark.parametrize('isolated', [False, True])
def test_knockout_semantics_survive_json_but_unverified_docx_is_refused(tmp_path, isolated):
    source = tmp_path / 'knockout.pdf'
    grouped_form(source, knockout=True, isolated=isolated)
    model = document_from_json(document_to_json(read_document(source).document))
    scene = get_vector_scene(model, model.sections[0].properties['pdf_scene_id'])
    assert any(g.compositing.knockout is True for g in scene.groups)
    destination = tmp_path / 'previous.docx'
    destination.write_bytes(b'previous')
    result = write_document(model, destination)
    assert not result.success and destination.read_bytes() == b'previous'
    assert any('Knockout group projection' in issue.message for issue in result.issues)


@pytest.mark.parametrize('extension', ['pdf', 'html', 'pptx'])
def test_unimplemented_target_does_not_silently_ignore_scope(tmp_path, extension):
    source = tmp_path / 'partial.pdf'
    grouped_form(source, partial_text=True)
    model = read_document(source).document
    destination = tmp_path / ('previous.' + extension)
    destination.write_bytes(b'previous')
    result = write_document(model, destination)
    assert not result.success and destination.read_bytes() == b'previous'
    assert any(issue.feature == 'export.graphics-scopes' for issue in result.issues)


@pytest.mark.parametrize('policy', ['gray', 'AIS', 'op', 'TK', 'BM'])
def test_color_and_shape_policies_refuse_instead_of_assuming_rgb_or_opacity(tmp_path, policy):
    original, source = tmp_path / 'original.pdf', tmp_path / 'policy.pdf'
    grouped_form(original, opacity=.5)
    with fitz.open(original) as native:
        form = native[0].get_xobjects()[0][0]
        if policy == 'gray':
            native.xref_set_key(form, 'Group/CS', '/DeviceGray')
        elif policy == 'BM':
            native.xref_set_key(form, 'Resources/ExtGState/ChildAlpha/BM', '/UnknownTestMode')
        else:
            native.xref_set_key(form, 'Resources/ExtGState/ChildAlpha/' + policy, 'false' if policy == 'TK' else 'true')
        native.save(source)
    imported = read_document(source)
    assert imported.success
    if policy != 'gray':
        assert any(issue.code == 'pdf.graphics-state' for issue in imported.issues)
    destination = tmp_path / 'previous.docx'
    destination.write_bytes(b'previous')
    result = PdfModelConverter().convert(source, destination)
    assert not result.success and destination.read_bytes() == b'previous'


def test_nested_group_opacity_is_applied_to_whole_intersection(tmp_path):
    original, source = tmp_path / 'original.pdf', tmp_path / 'nested.pdf'
    grouped_form(original, opacity=.5)
    with fitz.open(original) as native:
        page = native[0]
        form = page.get_xobjects()[0][0]
        outer = native.get_new_xref()
        native.update_object(outer, f'''<< /Type /XObject /Subtype /Form /BBox [0 0 160 100]
          /Group << /S /Transparency /I true /K false /CS /DeviceRGB >>
          /Resources << /XObject << /Inner {form} 0 R >>
          /ExtGState << /Layer << /ca 0.4 /CA 0.4 >> >> >> >>''')
        native.update_stream(outer, b'q /Layer gs /Inner Do Q')
        resources = int(native.xref_get_key(page.xref, 'Resources')[1].split()[0])
        native.xref_set_key(resources, 'XObject/OwnForm', f'{outer} 0 R')
        native.save(source)
    image, svg = _svg_model(read_document(source).document)
    with fitz.open(source) as native, fitz.open(stream=svg, filetype='svg') as vector:
        expected = native[0].get_pixmap()
        scale = image.box.width/vector[0].rect.width
        actual = vector[0].get_pixmap(matrix=fitz.Matrix(scale, scale))
        for x, y in [(100, 150), (150, 150), (210, 150)]:
            a, b = expected.pixel(x, y), actual.pixel(round(x-image.box.x), round(y-image.box.y))
            assert max(abs(u-v) for u, v in zip(a, b)) <= 3


def test_composition_work_budget_refuses_before_replacing_file(tmp_path):
    original, source = tmp_path / 'original.pdf', tmp_path / 'many.pdf'
    grouped_form(original, opacity=.5)
    with fitz.open(original) as native:
        form = native[0].get_xobjects()[0][0]
        commands = '\n'.join(f'q /ChildAlpha gs .2 .4 .6 rg {i*.7} {i*.6} 40 30 re f Q' for i in range(50))
        native.update_stream(form, commands.encode())
        native.save(source)
    destination = tmp_path / 'previous.docx'
    destination.write_bytes(b'previous')
    result = PdfModelConverter().convert(source, destination)
    assert not result.success and destination.read_bytes() == b'previous'
    assert any('work budget' in issue.message for issue in result.issues)


def test_typed_children_order_controls_overlap_instead_of_native_sequence(tmp_path):
    original, reference = tmp_path / 'original.pdf', tmp_path / 'reordered.pdf'
    grouped_form(original, opacity=.5)
    model = read_document(original).document
    identifier = model.sections[0].properties['pdf_scene_id']
    scene = get_vector_scene(model, identifier)
    group = next(g for g in scene.groups if g.compositing.opacity == .5)
    set_scene_group(model, identifier, group.id, replace(group, children=tuple(reversed(group.children))))
    with fitz.open(original) as native:
        form = native[0].get_xobjects()[0][0]
        native.update_stream(form, b'q /ChildAlpha gs 0 0 1 rg 50 0 110 100 re f Q\n1 0 0 rg 0 0 110 100 re f\n')
        native.save(reference)
    image, svg = _svg_model(model)
    with fitz.open(reference) as native, fitz.open(stream=svg, filetype='svg') as vector:
        scale = image.box.width/vector[0].rect.width
        a = native[0].get_pixmap().pixel(150, 150)
        b = vector[0].get_pixmap(matrix=fitz.Matrix(scale, scale)).pixel(round(150-image.box.x), round(150-image.box.y))
        assert max(abs(u-v) for u, v in zip(a, b)) <= 3
