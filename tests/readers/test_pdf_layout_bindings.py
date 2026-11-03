"""Verified mappings require exact source text, font program and origin, not a layout guess."""

from copy import deepcopy
from dataclasses import replace
from threading import Event

import pytest
from opendoc_model import (
    FontReference,
    TextRun,
    document_from_json,
    document_to_json,
    get_anchor,
    get_font_reference,
    get_integration,
    get_text_layout,
    set_font_reference,
    set_text_layout,
    walk_model,
)

from opendoc_formats import ImportOptions, read_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.pdf_layout_bindings import _unicode_groups
from opendoc_formats.readers.pdf_text_layout import capture_pdf_text_layouts
from tests.binary_fixtures import own_pdf, own_placement_font


def source_document(tmp_path, mode=0):
    path = tmp_path/'logical.pdf'
    path.write_bytes(own_pdf(font_program=own_placement_font(),
                            commands=f'BT /F1 12 Tf {mode} Tr 60 300 Td (ABC) Tj ET\n'.encode())[0])
    return path, read_document(path).document


def runs(document):
    return [reference.node for reference in walk_model(document) if isinstance(reference.node, TextRun)]


def test_production_ligature_mapping_and_public_snapshot_survive_two_json_cycles(tmp_path):
    path, _ = source_document(tmp_path)
    result = read_document(path, options=ImportOptions(pdf_text_layouts=True))
    assert result.success, result.issues
    document = result.document
    for _ in range(2):
        document = document_from_json(document_to_json(document))
        integration = get_integration(document)
        layout = integration.text_layouts[0]
        assert layout.state == 'verified' and layout.binding_version == 2 and layout.binding_sha256
        assert [cluster.glyph_indices for cluster in layout.clusters] == [(0,), (1,), (2,)]
        ranges = {value.id: value for value in integration.ranges}
        intervals = [ranges[cluster.range_ids[0]] for cluster in layout.clusters]
        assert [(value.start.offset, value.end.offset) for value in intervals] == [(0, 1), (1, 2), (2, 4)]
        owner = next(run for run in runs(document) if get_anchor(run).id == intervals[0].start.node_id)
        assert [owner.text[value.start.offset:value.end.offset] for value in intervals] == ['A', 'B', 'fi']
        assert len(layout.glyphs) == 3 and layout.extra['opendoc_formats.pdf_native_records'] == 4
        assert layout.extra['opendoc_formats.paint_state'] == 'unassessed'


@pytest.mark.parametrize('edit', ['text', 'style'])
def test_logical_text_or_style_edits_make_the_public_snapshot_stale(tmp_path, edit):
    path, _ = source_document(tmp_path)
    document = read_document(path, options=ImportOptions(pdf_text_layouts=True)).document
    layout = get_integration(document).text_layouts[0]
    assert get_text_layout(document, layout.id).state == 'verified'
    changed = deepcopy(document)
    run = runs(changed)[0]
    if edit == 'text':
        run.text = 'CDxx'
    else:
        run.style.bold = not run.style.bold
    stale = get_text_layout(changed, layout.id)
    assert stale.state == 'stale' and stale.glyphs == layout.glyphs
    assert get_text_layout(document, layout.id).state == 'verified'


@pytest.mark.parametrize('problem', ['text', 'nearby-origin', 'font-reference', 'duplicate-owner', 'style'])
def test_nearly_matching_or_ambiguous_semantics_are_not_verified(tmp_path, problem):
    path, document = source_document(tmp_path)
    run = runs(document)[0]
    assert get_font_reference(run.style) is not None
    if problem == 'text':
        run.text = 'ABxx'
    elif problem == 'nearby-origin':
        run.properties['pdf_origin'][0] += 0.0001
    elif problem == 'font-reference':
        set_font_reference(run.style, None)
    elif problem == 'style':
        run.style.bold = not run.style.bold
    else:
        document.sections[0].blocks[0].content.append(deepcopy(run))
    before = document_to_json(document)
    result = capture_pdf_text_layouts(document, path)
    assert all(value.state == 'unknown' and not value.clusters for value in get_integration(result).text_layouts)
    assert document_to_json(document) == before


def test_fill_stroke_bindings_stay_separate_and_share_proven_ranges(tmp_path):
    path, document = source_document(tmp_path, mode=2)
    # The caller explicitly supplies the font identity; paint ambiguity is still retained.
    font = next(resource.id for resource in document.resources.values() if resource.media_type == 'font/ttf')
    set_font_reference(runs(document)[0].style, FontReference(font, 0))
    result = capture_pdf_text_layouts(document, path)
    integration = get_integration(result)
    assert [value.extra['opendoc_formats.pdf_text_operation'] for value in integration.text_layouts] == ['fill', 'stroke']
    assert all(value.state == 'verified' for value in integration.text_layouts)
    assert integration.text_layouts[0].clusters == integration.text_layouts[1].clusters
    assert len(integration.ranges) == 3


def test_verified_recapture_is_idempotent_and_retains_unknown_extra(tmp_path):
    path, _ = source_document(tmp_path)
    document = read_document(path, options=ImportOptions(pdf_text_layouts=True)).document
    layout = get_integration(document).text_layouts[0]
    set_text_layout(document, replace(layout, extra={**layout.extra, 'own': {'values': [1]}}), verify=True)
    before = document_to_json(document)
    recaptured = capture_pdf_text_layouts(document, path)
    assert document_to_json(recaptured) == before


@pytest.mark.parametrize('verified', [False, True])
def test_recapture_preserves_other_producers_layouts(tmp_path, verified):
    path, _ = source_document(tmp_path)
    document = read_document(path, options=ImportOptions(pdf_text_layouts=True)).document
    layout = get_integration(document).text_layouts[0]
    other = replace(layout, id='other-producer', state='unknown', binding_sha256=None, extra={'owner': 'other'})
    set_text_layout(document, other, verify=verified)
    before = document_to_json(document)
    recaptured = capture_pdf_text_layouts(document, path)
    assert document_to_json(recaptured) == before


@pytest.mark.parametrize('edit', ['style', 'text'])
def test_recapture_does_not_bless_stale_source_geometry_after_semantic_edits(tmp_path, edit):
    path, _ = source_document(tmp_path)
    document = read_document(path, options=ImportOptions(pdf_text_layouts=True)).document
    layout = get_integration(document).text_layouts[0]
    if edit == 'style':
        runs(document)[0].style.bold = not runs(document)[0].style.bold
    else:
        runs(document)[0].text = 'CDxx'
    assert get_text_layout(document, layout.id).state == 'stale'
    result = capture_pdf_text_layouts(document, path)
    assert get_text_layout(result, layout.id).state == 'unknown'
    assert get_text_layout(document, layout.id).state == 'stale'


def test_cancellation_after_verification_does_not_publish_anchors_ranges_or_snapshots(tmp_path, monkeypatch):
    import opendoc_formats.readers.pdf_text_layout as capture

    path, document = source_document(tmp_path)
    before, stop = document_to_json(document), Event()
    original = capture.set_text_layouts
    calls = []

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        calls.append(kwargs.get('verify', False))
        if kwargs.get('verify'):
            stop.set()

    monkeypatch.setattr(capture, 'set_text_layouts', interrupted)
    with pytest.raises(OperationCancelledError):
        capture_pdf_text_layouts(document, path, cancelled=stop.is_set)
    assert calls == [False, True] and stop.is_set()
    assert document_to_json(document) == before


@pytest.mark.parametrize('problem', ['replacement', 'invalid-scalar', 'wrong-position', 'leading-continuation', 'unknown-gid'])
def test_unproven_native_unicode_never_becomes_a_logical_group(tmp_path, problem):
    from opendoc_formats.pdf import PdfDocument

    path, _ = source_document(tmp_path)
    with PdfDocument(path) as native:
        observation = native.page_text_placements(0)[0]
    glyphs = list(observation.glyphs)
    if problem == 'replacement':
        glyphs[0] = replace(glyphs[0], unicode=0xfffd)
    elif problem == 'invalid-scalar':
        glyphs[0] = replace(glyphs[0], unicode=0xd800)
    elif problem == 'wrong-position':
        glyphs[-1] = replace(glyphs[-1], transform=(1, 0, 0, 1, 0, 0))
    elif problem == 'leading-continuation':
        glyphs[0] = replace(glyphs[0], glyph_id=-1)
    else:
        glyphs[-1] = replace(glyphs[-1], glyph_id=-2)
    assert _unicode_groups(replace(observation, glyphs=tuple(glyphs)), None) is None
