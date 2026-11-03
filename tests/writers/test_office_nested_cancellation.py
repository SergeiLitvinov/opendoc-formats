"""Cancellation inside one table, vector scene or contiguous slide group."""

from copy import deepcopy
from threading import Event

import pytest
from opendoc_model import (
    Border,
    BorderSet,
    ColorValue,
    DocumentModel,
    Paragraph,
    Section,
    Table,
    TableCell,
    TableRow,
    TextRun,
    document_to_json,
    set_borders,
)

from opendoc_formats import ExportOptions, read_document, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.support.cancellation import checkpoint
from tests.readers.test_office_import_cancellation import pptx_source as pptx_source


def _scene_document():
    from opendoc_model import (
        Anchor,
        Box,
        GroupColorSpace,
        GroupCompositing,
        Image,
        Paint,
        PathCommand,
        Resource,
        ResourceKind,
        VectorGroup,
        VectorPath,
        VectorScene,
        set_anchor,
        set_vector_scene,
    )

    image = Image('preview', box=Box(0, 0, 200, 100))
    set_anchor(image, Anchor('own-scene-node'))
    model = DocumentModel(source_format='docx', sections=[Section(blocks=[Paragraph([image])])], resources={
        'preview': Resource('preview', ResourceKind.VECTOR_IMAGE, 'image/svg+xml',
                            data=b'<svg xmlns="http://www.w3.org/2000/svg"/>'),
    })
    paths = tuple(VectorPath(str(x), tuple(PathCommand(op, values) for op, values in (
        ('move', (x, 10)), ('line', (x+50, 10)), ('line', (x+50, 60)), ('line', (x, 60)), ('close', ()),
    )), fill=Paint(ColorValue.from_hex('112233'))) for x in (10, 80))
    group = VectorGroup('own-pair', tuple(path.id for path in paths),
                        compositing=GroupCompositing(1, False, False, 'normal', color_space=GroupColorSpace('rgb')))
    set_vector_scene(model, VectorScene('own-scene', 200, 100, paths=paths, groups=(group,),
                                       roots=(group.id,), node_id='own-scene-node'))
    return model


def _export(model, path, kind, public, stop):
    if public:
        report = write_document(model, path, options=ExportOptions(cancelled=stop.is_set))
        assert not report.success
        assert any(issue.feature == 'export.cancelled' for issue in report.issues)
    else:
        from importlib import import_module

        writer = getattr(import_module('opendoc_formats.writers.' + kind + '_writer'), 'write_' + kind + '_model')
        with pytest.raises(OperationCancelledError):
            writer(model, path, cancelled=stop.is_set)


@pytest.mark.parametrize('public', [False, True])
@pytest.mark.parametrize('stage', ['grid', 'merge', 'scene'])
def test_docx_stops_inside_one_native_object(monkeypatch, tmp_path, public, stage):
    from opendoc_formats.ooxml import group_geometry, merged_cell_borders, table_grid

    table = Table([
        TableRow([TableCell([Paragraph([TextRun('Merged')])], row_span=2),
                  TableCell([Paragraph([TextRun('Right top')])])]),
        TableRow([TableCell([Paragraph([TextRun('Right bottom')])])]),
    ])
    set_borders(table.rows[0].cells[0], BorderSet({
        'bottom': Border(style='solid', width_pt=1, color=ColorValue.from_hex('112233')),
    }))
    model = _scene_document() if stage == 'scene' else DocumentModel(sections=[Section(blocks=[table])])
    owner, name = {'grid': (table_grid, 'bisect_left'), 'merge': (merged_cell_borders, 'export_width'),
                   'scene': (group_geometry, 'paint_style')}[stage]
    native = getattr(owner, name)
    stop, calls = Event(), []
    original = document_to_json(model)
    target = tmp_path / 'kept.docx'
    target.write_bytes(b'previous complete output')

    def first(*args, **kwargs):
        assert not calls, 'A second part of the same object ran after cancellation'
        result = native(*args, **kwargs)
        calls.append(True)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(owner, name, first)
        _export(model, target, 'docx', public, stop)
    assert calls == [True]
    assert document_to_json(model) == original
    assert target.read_bytes() == b'previous complete output'
    assert not list(tmp_path.glob('.*.partial'))
    checkpoint()
    assert write_document(model, target).success
    assert read_document(target).document is not None


@pytest.mark.parametrize('public', [False, True])
@pytest.mark.parametrize('stage', ['groups', 'combo'])
def test_pptx_stops_while_collecting_one_contiguous_group(monkeypatch, tmp_path, pptx_source, public, stage):
    from opendoc_formats.writers import pptx_combo_writer, pptx_scene_writer
    from tests.writers.test_pptx_combo_roundtrip import source_combo

    if stage == 'combo':
        source = tmp_path / 'combo.pptx'
        source_combo(source, secondary=True)
        model = read_document(source).document
        chart = model.sections[0].blocks[0].properties['pptx']['chart']
        extra = deepcopy(chart['series'][0])
        extra['name'] = 'Own second bar series'
        chart['series'].insert(1, extra)
        owner = pptx_combo_writer
    else:
        model = read_document(pptx_source).document
        owner = pptx_scene_writer
    original = document_to_json(model)
    target = tmp_path / 'kept.pptx'
    target.write_bytes(b'previous complete output')
    stop, consumed = Event(), []
    native = owner.groupby

    def interrupted_rows(rows):
        for row in rows:
            consumed.append(True)
            stop.set()
            yield row

    def interrupt_group(*args, **kwargs):
        for identity, rows in native(*args, **kwargs):
            yield identity, interrupted_rows(rows)

    with monkeypatch.context() as context:
        context.setattr(owner, 'groupby', interrupt_group)
        _export(model, target, 'pptx', public, stop)
    assert consumed == [True], 'Whole group was consumed despite cancellation'
    assert document_to_json(model) == original
    assert target.read_bytes() == b'previous complete output'
    assert not list(tmp_path.glob('.*.partial'))
    checkpoint()
    assert write_document(model, target).success
    restored = read_document(target).document
    assert restored is not None
    if stage == 'combo':
        series = restored.sections[0].blocks[0].properties['pptx']['chart']['series']
        assert [item['name'] for item in series] == [item['name'] for item in chart['series']]
