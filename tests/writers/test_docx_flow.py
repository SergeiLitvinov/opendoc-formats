"""Own ruled PDF: explicit editable reflow, honest grid mapping and atomic refusal."""

import hashlib
from copy import deepcopy
from threading import Event
from zipfile import ZipFile

import pymupdf
import pytest
from docx import Document
from docx.oxml.ns import qn
from opendoc_model import (
    Border,
    BorderSet,
    Box,
    DocumentLimits,
    DocumentModel,
    Heading,
    Image,
    IssueSeverity,
    Paragraph,
    PreservationState,
    Table,
    TableCell,
    TableRow,
    TextRun,
    TextStyle,
    document_from_json,
    document_to_json,
    get_borders,
    set_borders,
    set_heading,
)

from opendoc_formats import DocxProfile, ExportOptions, get_object_mapping, read_document, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.writers.docx_writer import write_docx_model


@pytest.fixture
def source_model(tmp_path):
    source = tmp_path / 'own-grid.pdf'
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=600, height=500)
        page.insert_text((70, 100), 'Own outside table')
        for x in (70, 170, 270, 370):
            page.draw_line((x, 150), (x, 270), width=1)
        for y in (150, 190, 230, 270):
            page.draw_line((70, y), (370, y), width=1)
        for row in range(3):
            for column in range(3):
                page.insert_text((80+100*column, 175+40*row), f'R{row+1}C{column+1}')
        pdf.new_page(width=600, height=500).insert_text((70, 100), 'Own other page')
        pdf.save(source)
    imported = read_document(source)
    assert imported.success
    return imported.document


def _crop(model, *, box=True):
    table = next(block for block in model.sections[0].blocks if isinstance(block, Table))
    table.rows = table.rows[1:]
    for row in table.rows:
        row.cells = row.cells[:2]
    table.box = Box(70, 190, 200, 80) if box else None
    # Public semantic edits leave original resources/native hints untouched.
    outside = next(block for block in model.sections[0].blocks if isinstance(block, Paragraph)
                   and any(getattr(run, 'text', '') == 'Own outside table' for run in block.content))
    set_heading(outside, Heading(2))
    remaining = [block for block in model.sections[0].blocks if block is not table and block is not outside]
    model.sections[0].blocks = [table, outside, *remaining]


@pytest.mark.parametrize('box', [False, True])
@pytest.mark.parametrize('public', [False, True])
def test_crop_reorder_and_two_native_json_cycles(source_model, tmp_path, box, public):
    _crop(source_model, box=box)
    before = document_to_json(source_model)
    output = tmp_path / 'flow.docx'
    model = document_from_json(before)
    if public:
        report = write_document(model, output, options=ExportOptions(docx_profile=DocxProfile('flow')))
    else:
        report = write_docx_model(model, output, profile=DocxProfile('flow'))
    assert report.success, report.issues
    assert [(issue.feature, issue.severity) for issue in report.issues if issue.severity is IssueSeverity.LOSS] == [
        ('docx.flow-layout', IssueSeverity.LOSS),
    ]
    mapping = get_object_mapping(report)
    assert mapping.publication == 'published' and not mapping.assessment_complete
    assert mapping.result_id == 'sha256:'+hashlib.sha256(output.read_bytes()).hexdigest()
    assert len(mapping.sources) == 8 and len(mapping.targets) == 1
    assert len([source for entry in mapping.entries for source in entry.source_ids]) == 8
    assert len(next(entry for entry in mapping.entries if entry.state is PreservationState.LOST).source_ids) == 2
    assert mapping.targets[0].native_locator.format == 'docx'
    assert document_to_json(source_model) == before == document_to_json(model)
    with ZipFile(output) as package:
        assert not any(name.startswith('word/media/') for name in package.namelist())
    for cycle in range(3):
        native = Document(output)
        assert [[cell.text for cell in row.cells] for row in native.tables[0].rows] == [['R2C1', 'R2C2'], ['R3C1', 'R3C2']]
        assert native.paragraphs[0].text == 'Own outside table'
        assert native.paragraphs[0]._p.find(qn('w:pPr')).find(qn('w:outlineLvl')).get(qn('w:val')) == '1'
        body = list(native._element.body)
        assert body[0].tag.endswith('}tbl') and body[1].tag.endswith('}p')
        assert any(paragraph.text == 'Own other page' for paragraph in native.paragraphs)
        result = read_document(output)
        assert result.success
        table = next(block for block in result.document.sections[0].blocks if isinstance(block, Table))
        borders = get_borders(table)
        assert borders is not None and len(borders.sides) == 6
        if cycle < 2:
            output = tmp_path / f'native-{cycle}.docx'
            assert write_document(document_from_json(document_to_json(result.document)), output).success


@pytest.mark.parametrize('profile', [None, DocxProfile()])
def test_default_still_rejects_unmeasured_pdf_grid(source_model, tmp_path, profile):
    _crop(source_model, box=False)
    output = tmp_path / 'previous.docx'
    output.write_bytes(b'previous')
    report = write_docx_model(source_model, output, profile=profile)
    assert not report.success and output.read_bytes() == b'previous'


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'dash', 'unrelated', 'ambiguous', 'hole', 'edited-border'])
def test_graphics_are_not_dropped_silently(source_model, tmp_path, fault):
    section = source_model.sections[0]
    vectors = [block for block in section.blocks if isinstance(block, Paragraph)
               and len(block.content) == 1 and isinstance(block.content[0], Image)]
    table = next(block for block in section.blocks if isinstance(block, Table))
    if fault == 'missing':
        section.blocks.remove(vectors[0])
    elif fault == 'duplicate':
        section.blocks.append(deepcopy(vectors[0]))
    elif fault == 'dash':
        source_model.resources[vectors[0].content[0].resource_id].properties['dashes'] = '[2 2] 0'
    elif fault == 'unrelated':
        resource = source_model.resources[vectors[0].content[0].resource_id]
        resource.properties['items'][0][1][0] = 71
        resource.properties['items'][0][2][0] = 71
        vectors[0].content[0].box.x = 71
    elif fault == 'ambiguous':
        section.blocks.append(deepcopy(table))
    elif fault == 'edited-border':
        set_borders(table, BorderSet({'top': Border(kind='line', style='solid', width_pt=.5)}))
    else:
        table.rows[0].cells = table.rows[0].cells[:2]
    before = document_to_json(source_model)
    output = tmp_path / 'previous.docx'
    output.write_bytes(b'previous')
    report = write_document(source_model, output, options=ExportOptions(docx_profile=DocxProfile('flow')))
    assert not report.success and any(issue.feature == 'docx.flow-profile' for issue in report.issues)
    assert output.read_bytes() == b'previous' and document_to_json(source_model) == before


def test_quality_gate_and_limits_keep_previous_destination(source_model, tmp_path):
    output = tmp_path / 'previous.docx'
    output.write_bytes(b'previous')
    report = write_document(source_model, output, options=ExportOptions(
        docx_profile=DocxProfile('flow'), quality_gate=lambda report, path: report.lossless,
    ))
    assert not report.success and any(issue.feature == 'export.quality-rejected' for issue in report.issues)
    assert output.read_bytes() == b'previous'
    report = write_document(source_model, output, options=ExportOptions(
        docx_profile=DocxProfile('flow'), document_limits=DocumentLimits(max_nodes=2),
    ))
    assert not report.success and output.read_bytes() == b'previous'


@pytest.mark.parametrize('public', [False, True])
def test_cancel_during_grid_matching(source_model, tmp_path, monkeypatch, public):
    from opendoc_formats.writers import docx_flow

    output = tmp_path / 'previous.docx'
    output.write_bytes(b'previous')
    original = document_to_json(source_model)
    stop = Event()
    calls = []
    native = docx_flow._line

    def first(*args):
        assert not calls, 'Matching continued after cancellation'
        result = native(*args)
        calls.append(True)
        stop.set()
        return result

    monkeypatch.setattr(docx_flow, '_line', first)
    if public:
        report = write_document(source_model, output, options=ExportOptions(
            docx_profile=DocxProfile('flow'), cancelled=stop.is_set,
        ))
        assert not report.success and any(issue.feature == 'export.cancelled' for issue in report.issues)
    else:
        with pytest.raises(OperationCancelledError):
            write_docx_model(source_model, output, profile=DocxProfile('flow'), cancelled=stop.is_set)
    assert document_to_json(source_model) == original and output.read_bytes() == b'previous'
    assert calls == [True]


def test_invalid_profile_is_explicit(tmp_path):
    with pytest.raises(ValueError):
        DocxProfile('unknown')
    with pytest.raises(ValueError):
        ExportOptions(docx_profile='flow')
    report = write_docx_model(DocumentModel(), tmp_path / 'invalid.docx', profile=DocxProfile('flow'))
    assert not report.success


def test_profile_does_not_shift_existing_positional_options():
    gate = lambda report, path: True  # noqa: E731
    options = ExportOptions(DocumentLimits(), None, True, None, gate)
    assert options.quality_gate is gate and options.docx_profile is None


@pytest.mark.parametrize(('key', 'value'), [
    ('pdf_paint_type', 3), ('pdf_paint_opacity', .5), ('pdf_paint_unknown', True),
    ('pdf_graphics_state_unknown', True),
])
def test_unknown_or_nonopaque_text_is_refused_atomically(source_model, tmp_path, key, value):
    from opendoc_model import walk_model

    run = next(ref for ref in walk_model(source_model) if isinstance(ref.node, TextRun))
    run.node.properties[key] = value
    before = document_to_json(source_model)
    output = tmp_path / 'previous.docx'
    output.write_bytes(b'previous')
    report = write_document(source_model, output, options=ExportOptions(docx_profile=DocxProfile('flow')))
    assert not report.success
    assert any(issue.feature == 'docx.flow-profile' and issue.location == run.path for issue in report.issues)
    assert document_to_json(source_model) == before and output.read_bytes() == b'previous'


def test_border_width_outside_native_word_enum_is_refused(source_model, tmp_path):
    image = next(block.content[0] for block in source_model.sections[0].blocks if isinstance(block, Paragraph)
                 and len(block.content) == 1 and isinstance(block.content[0], Image))
    source_model.resources[image.resource_id].properties['width'] = .125
    output = tmp_path / 'previous.docx'
    output.write_bytes(b'previous')
    before = document_to_json(source_model)
    report = write_document(source_model, output, options=ExportOptions(docx_profile=DocxProfile('flow')))
    assert not report.success and any(issue.feature == 'docx.flow-profile' for issue in report.issues)
    assert document_to_json(source_model) == before and output.read_bytes() == b'previous'


def test_font_and_native_diagnostics_keep_canonical_source_locations(source_model, tmp_path):
    vectors = [block for block in source_model.sections[0].blocks if isinstance(block, Paragraph)
               and len(block.content) == 1 and isinstance(block.content[0], Image)]
    rest = [block for block in source_model.sections[0].blocks if block not in vectors]
    after = Paragraph([TextRun('After grid', TextStyle(font_family='OwnMissingMonoSource'))])
    source_model.sections[0].blocks = [*vectors, *rest, after]
    report = write_document(source_model, tmp_path / 'located.docx', options=ExportOptions(docx_profile=DocxProfile('flow')))
    assert report.success, report.issues
    assert any(issue.feature == 'font-substitution' and issue.location == 'sections[0].blocks[10].content[0]'
               for issue in report.issues)
    invalid = Table([TableRow([TableCell([Paragraph([TextRun('Bad native border')])])])])
    set_borders(invalid, BorderSet({'top': Border(kind='line', style='solid', width_pt=.3)}))
    source_model.sections[0].blocks[-1] = invalid
    output = tmp_path / 'previous.docx'
    output.write_bytes(b'previous')
    report = write_document(source_model, output, options=ExportOptions(docx_profile=DocxProfile('flow')))
    assert not report.success
    assert any(issue.severity is IssueSeverity.ERROR and issue.location == 'sections[0].blocks[10]' for issue in report.issues)
    assert output.read_bytes() == b'previous'


def test_signal_after_direct_commit_does_not_claim_rollback(source_model, tmp_path, monkeypatch):
    from pathlib import Path

    from opendoc_formats.support import io

    output = tmp_path / 'committed.docx'
    stop = Event()
    native = io.os.replace

    def commit(source, destination):
        result = native(source, destination)
        if Path(destination) == output:
            stop.set()
        return result

    monkeypatch.setattr(io.os, 'replace', commit)
    report = write_docx_model(source_model, output, profile=DocxProfile('flow'), cancelled=stop.is_set)
    assert stop.is_set() and report.success
    assert get_object_mapping(report).publication == 'published'
    assert Document(output).tables[0].cell(0, 0).text == 'R1C1'
