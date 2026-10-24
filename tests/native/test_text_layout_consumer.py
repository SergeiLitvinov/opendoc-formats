"""Unpublished Model layout gate: real Formats placements, no format parser in Model."""

import hashlib
import json
from dataclasses import replace

import opendoc_model as od
import pytest

from opendoc_formats.pdf import PdfDocument
from tests.binary_fixtures import own_pdf, own_placement_font

pytest.importorskip('opendoc_model.text_layout', reason='C-TEXT-LAYOUT-01 requires the separate local Model dev artifact')


def native_document(tmp_path):
    font = own_placement_font()
    source, _ = own_pdf(font_program=font, commands=b'BT /F1 12 Tf 2 Tr 1 .25 .5 1 60 300 Tm (ABC) Tj ET\n')
    path = tmp_path/'own.pdf'
    path.write_bytes(source)
    with PdfDocument(path) as pdf:
        placements = pdf.page_text_placements(0)
    assert [p.operation for p in placements] == ['fill', 'stroke']
    run = od.TextRun('ABfi', od.TextStyle(font_family='OwnPlacement-Regular', font_size=od.Length(12)))
    od.set_font_reference(run.style, od.FontReference('own-font', 0))
    od.set_anchor(run, od.Anchor('own-text'))
    document = od.DocumentModel(
        source_format='pdf', sections=[od.Section(blocks=[od.Paragraph([run])])],
        resources={'own-font': od.Resource('own-font', od.ResourceKind.FONT, 'font/ttf', font)},
    )
    od.set_integration(document, od.IntegrationModel(
        pages=(od.DocumentPage('own-page', 300, 400),),
        ranges=tuple(od.TextRange(name, od.TextPosition('own-text', start), od.TextPosition('own-text', end))
                     for name, start, end in [('A', 0, 1), ('B', 1, 2), ('fi', 2, 4)]),
    ))
    for occurrence in placements:
        assert occurrence.font_program_sha256 == hashlib.sha256(font).hexdigest()
        assert [(g.unicode, g.glyph_id) for g in occurrence.glyphs] == [(65, 1), (66, 2), (102, 3), (105, -1)]
        # The original's ToUnicode explicitly maps code C to "fi"; -1 is a continuation, not another placed glyph.
        # The fixture's program is a single-face TTF, known independently of its family name.
        glyphs = tuple((0, glyph.glyph_id, *glyph.transform) for glyph in occurrence.glyphs if glyph.glyph_id >= 0)
        layout = od.TextLayout(
            occurrence.operation, glyphs=glyphs, fonts=(od.FontReference('own-font', 0),), page_id='own-page',
            clusters=tuple(od.TextCluster((index,), (name,)) for index, name in enumerate(('A', 'B', 'fi'))),
            provenance=od.Provenance('pdf', str(path), page=0, object_id=f'text-placement:{occurrence.occurrence_index}'),
            extra={'opendoc_formats.pdf_text_operation': occurrence.operation,
                   'opendoc_formats.glyph_space': 'font-at-1pt', 'own': {'values': [1]}},
        )
        od.set_text_layout(document, layout, verify=True)
    return document, placements, path, source


def test_actual_pdf_matrices_font_and_ligature_clusters_survive_two_json_cycles(tmp_path):
    document, placements, path, source = native_document(tmp_path)
    expected = json.loads(od.document_to_json(document))
    for _ in range(2):
        document = od.document_from_json(od.document_to_json(document))
        assert json.loads(od.document_to_json(document)) == expected
        for native in placements:
            layout = od.get_text_layout(document, native.operation)
            assert layout.state == 'verified' and len(layout.glyphs) == 3
            assert [row[2:] for row in layout.glyphs] == [glyph.transform for glyph in native.glyphs if glyph.glyph_id >= 0]
            assert layout.clusters[-1].glyph_indices == (2,) and layout.clusters[-1].range_ids == ('fi',)
            assert layout.fonts[0].face_index == 0
            assert layout.extra['opendoc_formats.pdf_text_operation'] == native.operation
        assert not od.get_integration(document).assessment_complete
    detached = od.get_text_layout(document, 'fill')
    detached.extra['own']['values'].append(2)
    assert json.loads(od.document_to_json(document)) == expected
    assert path.read_bytes() == source


def test_text_edit_invalidates_all_actual_paint_occurrences_without_guessing_new_positions(tmp_path):
    document, placements, path, source = native_document(tmp_path)
    changed = od.edit_anchored_text(document, 'own-text', 2, 4, 'ffi')
    for occurrence in placements:
        assert od.get_text_layout(changed, occurrence.operation).state == 'stale'
        assert od.get_text_layout(document, occurrence.operation).state == 'verified'
        assert (od.get_text_layout(changed, occurrence.operation).glyphs
                == od.get_text_layout(document, occurrence.operation).glyphs)
    assert od.document_from_json(od.document_to_json(changed))
    assert path.read_bytes() == source


def test_direct_text_edit_allows_atomic_invalidation_of_both_fill_and_stroke(tmp_path):
    document, _, _, _ = native_document(tmp_path)
    document.sections[0].blocks[0].content[0].text = 'ABfI'
    assert od.get_text_layout(document, 'fill').state == od.get_text_layout(document, 'stroke').state == 'stale'
    with pytest.raises(ValueError, match='stale'):
        od.document_to_json(document)
    before = od.integration_to_dict(od.get_integration(document))
    with pytest.raises(ValueError, match='stale'):
        od.invalidate_text_layouts(document, ('fill',))
    assert od.integration_to_dict(od.get_integration(document)) == before
    od.invalidate_text_layouts(document, ('fill', 'stroke'))
    restored = od.document_from_json(od.document_to_json(document))
    assert od.get_text_layout(restored, 'fill').state == od.get_text_layout(restored, 'stroke').state == 'stale'


def test_missing_font_reference_is_rejected_atomically_in_the_consumer(tmp_path):
    document, _, _, _ = native_document(tmp_path)
    before = od.document_to_json(document)
    value = replace(od.get_text_layout(document, 'fill'), fonts=(od.FontReference('missing', 0),))
    with pytest.raises(ValueError):
        od.set_text_layout(document, value, verify=True)
    assert od.document_to_json(document) == before


def test_actualtext_one_codepoint_to_two_real_glyphs_keeps_both_native_placements(tmp_path):
    font = own_placement_font()
    source, _ = own_pdf(font_program=font, commands=(
        b'/Span << /ActualText <FEFF0041> >> BDC BT /F1 12 Tf 60 300 Td (AB) Tj ET EMC\n'))
    with PdfDocument(source) as pdf:
        assert pdf.page_info(0).text.strip() == 'A'
        occurrence, = pdf.page_text_placements(0)
    assert [(g.unicode, g.glyph_id) for g in occurrence.glyphs] == [(65, 1), (66, 2)]
    assert occurrence.font_program_sha256 == hashlib.sha256(font).hexdigest()
    run = od.TextRun('A')
    od.set_anchor(run, od.Anchor('actualtext'))
    document = od.DocumentModel(sections=[od.Section(blocks=[od.Paragraph([run])])], resources={
        'own-font': od.Resource('own-font', od.ResourceKind.FONT, 'font/ttf', font),
    })
    od.set_integration(document, od.IntegrationModel(ranges=(
        od.TextRange('logical', od.TextPosition('actualtext', 0), od.TextPosition('actualtext', 1)),
    )))
    od.set_text_layout(document, od.TextLayout(
        'actualtext', fonts=(od.FontReference('own-font', 0),),
        glyphs=tuple((0, glyph.glyph_id, *glyph.transform) for glyph in occurrence.glyphs),
        clusters=(od.TextCluster((0, 1), ('logical',)),),
    ), verify=True)
    for _ in range(2):
        document = od.document_from_json(od.document_to_json(document))
        layout = od.get_text_layout(document, 'actualtext')
        assert layout.state == 'verified' and len(layout.glyphs) == 2
        assert layout.clusters[0].range_ids == ('logical',) and layout.clusters[0].glyph_indices == (0, 1)
        assert document.sections[0].blocks[0].content[0].text == 'A'


def test_unbound_program_and_unknown_mapping_never_invent_a_font_or_glyph_id(tmp_path):
    document, native, _, _ = native_document(tmp_path)
    raw = native[0].glyphs[0]
    value = od.TextLayout('unbound', glyphs=((None, None, *raw.transform),), clusters=(od.TextCluster((0,)),),
                          extra={'opendoc_formats.native_glyph_id': raw.glyph_id})
    od.set_text_layout(document, value)
    restored = od.document_from_json(od.document_to_json(document))
    result = od.get_text_layout(restored, 'unbound')
    assert result.state == 'unknown' and result.fonts == () and result.clusters[0].range_ids == ()
    assert result.glyphs[0][:2] == (None, None)
    assert result.extra['opendoc_formats.native_glyph_id'] == raw.glyph_id


def test_large_actual_native_observation_uses_the_selected_model_budget():
    font = own_placement_font()
    source, _ = own_pdf(font_program=font, commands=b'BT /F1 12 Tf 60 300 Td ('+b'ABC'*4000+b') Tj ET\n')
    with PdfDocument(source) as pdf:
        occurrence, = pdf.page_text_placements(0)
    rows = tuple((0, glyph.glyph_id, *glyph.transform) for glyph in occurrence.glyphs if glyph.glyph_id >= 0)
    assert len(rows) == 12000
    document = od.DocumentModel(resources={'font': od.Resource('font', od.ResourceKind.FONT, 'font/ttf', font)})
    layout = od.TextLayout('large-observation', glyphs=rows, fonts=(od.FontReference('font', 0),),
                           clusters=(od.TextCluster(tuple(range(len(rows)))),))
    before = od.document_to_json(document)
    with pytest.raises(od.ArtifactLimitError) as failure:
        od.set_text_layout(document, layout)
    assert failure.value.quota == 'nodes' and failure.value.maximum == od.DocumentLimits().max_nodes
    assert od.document_to_json(document) == before
    budget = od.DocumentLimits(max_nodes=500000)
    od.set_text_layout(document, layout, limits=budget)
    for _ in range(2):
        document = od.document_from_json(od.document_to_json(document, limits=budget), limits=budget)
        restored = od.get_text_layout(document, layout.id, limits=budget)
        assert restored.glyphs == rows and restored.state == 'unknown'


def test_batch_of_native_occurrences_does_not_promote_unmapped_observation(tmp_path):
    document, native, _, _ = native_document(tmp_path)
    unknown = od.TextLayout('unmapped', glyphs=((None, None, *native[0].glyphs[0].transform),),
                            clusters=(od.TextCluster((0,)),), extra={'own': {'source': [1]}})
    od.set_text_layout(document, unknown)
    document.sections[0].blocks[0].content[0].text = 'ABfI'
    before = od.integration_to_dict(od.get_integration(document))
    with pytest.raises(ValueError):
        od.invalidate_text_layouts(document, ('fill', 'missing'))
    assert od.integration_to_dict(od.get_integration(document)) == before
    od.invalidate_text_layouts(document)
    restored = od.document_from_json(od.document_to_json(document))
    assert od.get_text_layout(restored, 'fill').state == od.get_text_layout(restored, 'stroke').state == 'stale'
    value = od.get_text_layout(restored, 'unmapped')
    assert value.state == 'unknown' and value.glyphs == unknown.glyphs and value.extra == unknown.extra
