"""C-GRAPHICS-02 is authoritative; native witness fields never restore it."""

from dataclasses import replace

import pytest
from opendoc_model import (
    GroupColorSpace,
    document_from_json,
    document_to_json,
    get_vector_scene,
    set_scope_color_space,
    set_vector_scene,
)

from opendoc_formats import read_document, write_document
from tests.writers.test_pdf_docx_graphics import grouped_form


@pytest.mark.parametrize('space', [None, GroupColorSpace(), GroupColorSpace('gray'), GroupColorSpace('cmyk')])
def test_color_space_edits_and_removal_never_fall_back_to_native_rgb(tmp_path, space):
    source, destination = tmp_path / 'source.pdf', tmp_path / 'previous.docx'
    grouped_form(source, opacity=.5)
    model = read_document(source).document
    scene = get_vector_scene(model, model.sections[0].properties['pdf_scene_id'])
    group = next(g for g in scene.groups if g.compositing.opacity == .5)
    assert group.compositing.color_space.space == 'rgb'
    assert group.extra['pdf_blending_colorspace'] == 'DeviceRGB'
    set_scope_color_space(model, scene.id, group.id, space)
    model = document_from_json(document_to_json(document_from_json(document_to_json(model))))
    destination.write_bytes(b'previous')
    result = write_document(model, destination)
    assert not result.success and destination.read_bytes() == b'previous'
    assert any('space' in i.message for i in result.issues)


def test_legacy_scope_without_typed_space_is_unknown_even_with_rgb_extra(tmp_path):
    source, destination = tmp_path / 'source.pdf', tmp_path / 'previous.docx'
    grouped_form(source, opacity=.5)
    model = read_document(source).document
    scene = get_vector_scene(model, model.sections[0].properties['pdf_scene_id'])
    groups = tuple(replace(g, compositing=replace(g.compositing, color_space=None)) for g in scene.groups)
    set_vector_scene(model, replace(scene, groups=groups))
    destination.write_bytes(b'previous')
    result = write_document(model, destination)
    assert not result.success and destination.read_bytes() == b'previous'
    assert any('not a fallback' in i.message for i in result.issues)
