"""Visible text from independent DOCX originals, accepted against native Word."""

import hashlib
from threading import Event

import opendoc_model as od
import pytest

from opendoc_formats import read_document, write_document
from opendoc_formats.docx import DocxPackage
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.docx import read_docx, read_docx_model
from tools.docx_whitespace_acceptance import cases, original

EXPECTED = {
    'absent': 'L[A  B]R', 'explicit-default': 'L[A  B]R', 'explicit-preserve': 'L[  A  B  ]R',
    'run-preserve': 'L[A  B]R', 'paragraph-preserve': 'L[A  B]R', 'body-preserve': 'L[A  B]R',
    'document-preserve': 'L[  A  B  ]R', 'paragraph-preserve-text-default': 'L[A  B]R',
    'document-preserve-paragraph-default': 'L[  A  B  ]R', 'document-default-text-preserve': 'L[  A  B  ]R',
    'document-preserve-text-default': 'L[A  B]R', 'only-spaces': 'L[]R', 'only-spaces-preserve': 'L[   ]R',
    'unicode-spaces': 'L[\u00a0A\u2003]R', 'literal-controls': 'L[A  B]R',
    'literal-controls-preserve': 'L[  A\t B ]R', 'character-references': 'L[A  B]R',
    'character-references-preserve': 'L[  A\t B ]R', 'hyperlink-boundary': 'L[AfterLink]R',
}


@pytest.mark.parametrize('text,mode', [('\u00a0A\u2003', None), (' A\t B ', 'preserve')])
def test_source_text_profile_preserves_single_text_node_and_honors_edits(text, mode):
    from docx import Document
    from docx.oxml import OxmlElement
    from opendoc_model.diagnostics import ConversionReport

    from opendoc_formats.ooxml.docx_whitespace import SPACE, TEXT_KEY, source_text_profile, write_text_profile

    paragraph = Document().add_paragraph()
    source = paragraph.add_run()
    node = OxmlElement('w:t')
    node.text = text
    if mode is not None:
        node.set(SPACE, mode)
    source._r.append(node)
    profile = source_text_profile(source._r, text)
    assert profile is not None
    target = paragraph.add_run()
    report = ConversionReport(output_path=None)
    assert write_text_profile(target, text, {TEXT_KEY: profile}, report, 'run')
    assert target._r.find(node.tag).text == text
    assert target._r.find(node.tag).get(SPACE) == mode
    assert len(target._r) == 1
    assert not write_text_profile(paragraph.add_run(), 'edited', {TEXT_KEY: profile}, report, 'run')
    invalid = dict(profile, version=2)
    assert write_text_profile(paragraph.add_run(), text, {TEXT_KEY: invalid}, report, 'run')
    assert any(issue.feature == 'docx.text-profile' for issue in report.issues)


def model_text(model):
    return '\n'.join(''.join(run.text for run in block.content if isinstance(run, od.TextRun))
                     for section in model.sections for block in section.blocks if isinstance(block, od.Paragraph))


@pytest.mark.parametrize('name,attributes,text', cases(), ids=[item[0] for item in cases()])
def test_native_word_text_flat_projection_two_json_docx_cycles_and_plain_export(tmp_path, name, attributes, text):
    source = tmp_path/'source.docx'
    data = original(name, attributes, text)
    source.write_bytes(data)
    expected = EXPECTED[name]
    assert read_docx(source).plain == expected
    model = read_docx_model(source)
    assert model_text(model) == expected
    for cycle in range(2):
        before = od.document_to_json(model)
        json_path = tmp_path/f'cycle-{cycle}.json'
        assert write_document(model, json_path).success
        imported = read_document(json_path)
        assert imported.success, imported.issues
        assert model_text(imported.document) == expected
        path = tmp_path/f'cycle-{cycle}.docx'
        report = write_document(imported.document, path)
        assert report.success, report.issues
        model = read_docx_model(path)
        assert model_text(model) == expected and read_docx(path).plain == expected
        assert od.document_to_json(imported.document) == before
    plain = tmp_path/'visible.txt'
    report = write_document(model, plain)
    assert report.success, report.issues
    assert plain.read_text(encoding='utf-8').rstrip('\n') == expected
    assert hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(data).digest()


def test_raw_native_snapshot_preserves_source_offsets_and_untrimmed_w_t(tmp_path):
    data = original('absent', {}, '  A  B  ')
    source = tmp_path/'raw.docx'
    source.write_bytes(data)
    with DocxPackage(source) as package:
        paragraph = package.paragraphs[0]
        assert paragraph.text == 'L[  A  B  ]R'
    assert model_text(read_docx_model(source)) == 'L[A  B]R'
    assert source.read_bytes() == data


def test_unknown_space_mode_retains_original_projection_and_has_source_diagnostic(tmp_path):
    path = tmp_path/'unknown.docx'
    path.write_bytes(original('unknown', {'t': 'unaccepted'}, '  A  B  '))
    result = read_document(path)
    assert model_text(result.document) == 'L[  A  B  ]R'
    issues = [issue for issue in result.issues if issue.code == 'docx.text-whitespace']
    assert issues and all('word/document.xml' in issue.location for issue in issues)


@pytest.mark.parametrize('reader', [read_docx, read_docx_model])
def test_cancel_inside_visible_run_projection(tmp_path, monkeypatch, reader):
    from opendoc_formats.ooxml import docx_whitespace

    path = tmp_path/'cancel.docx'
    path.write_bytes(original('absent', {}, '  A  B  '))
    stop = Event()
    real = docx_whitespace.checkpoint
    def checkpoint():
        stop.set()
        real()
    monkeypatch.setattr(docx_whitespace, 'checkpoint', checkpoint)
    with pytest.raises(OperationCancelledError):
        reader(path, cancelled=stop.is_set)


def test_explicit_run_controls_keep_the_native_mapping(tmp_path):
    path = tmp_path/'controls.docx'
    text = 'A</w:t><w:tab/><w:t>B</w:t><w:br/><w:t>C</w:t><w:noBreakHyphen/><w:t>D'
    path.write_bytes(original('controls', {}, text))
    # This retains the existing native API mapping of explicit control elements.
    assert read_docx(path).plain == 'L[A\tB\nC-D]R'
    assert model_text(read_docx_model(path)) == 'L[A\tB\nC-D]R'


def test_table_only_flat_reader_and_rich_cell_use_the_same_projection(tmp_path):
    from io import BytesIO
    from zipfile import ZipFile

    from tests.binary_fixtures import zip_bytes

    data = original('cell', {}, '  A  B  ')
    with ZipFile(BytesIO(data)) as archive:
        parts = [(name, archive.read(name)) for name in archive.namelist()]
    opening = (b'<w:body><w:tbl><w:tblPr/><w:tblGrid><w:gridCol w:w="8640"/></w:tblGrid>'
               b'<w:tr><w:tc><w:tcPr/>')
    parts = [(name, payload.replace(b'<w:body>', opening).replace(b'<w:sectPr>', b'</w:tc></w:tr></w:tbl><w:sectPr>')
              if name == 'word/document.xml' else payload) for name, payload in parts]
    path = tmp_path/'table.docx'
    path.write_bytes(zip_bytes(parts))
    assert read_docx(path).plain == 'L[A  B]R'
    table = read_docx_model(path).sections[0].blocks[0]
    assert isinstance(table, od.Table)
    paragraph = table.rows[0].cells[0].blocks[0]
    assert ''.join(run.text for run in paragraph.content) == 'L[A  B]R'
