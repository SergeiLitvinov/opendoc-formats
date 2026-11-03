"""TXT cancellation preserves bytes, source metadata and publication boundaries."""

import codecs
from pathlib import Path
from threading import Event

import pytest
from opendoc_model import DocumentModel, Paragraph, Section, Table, TableCell, TableRow, TextRun, document_to_json

from opendoc_formats import ExportOptions, ImportOptions, TextProfile, read_document, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.txt import read_txt, read_txt_model
from opendoc_formats.support.cancellation import checkpoint
from opendoc_formats.writers.txt_writer import write_txt_model


@pytest.mark.parametrize('encoding,bom', [('utf-8', b''), ('utf-16-le', codecs.BOM_UTF16_LE),
                                         ('utf-16-be', codecs.BOM_UTF16_BE), ('cp1251', b'')])
def test_inactive_signal_keeps_full_json_and_original_bytes(tmp_path, encoding, bom):
    source = tmp_path / 'own.txt'
    data = bom + 'Первая\r\n\rВторая\nПоследняя\r\n'.encode(encoding)
    source.write_bytes(data)
    profile = TextProfile(encoding)
    expected = read_txt_model(source, profile=profile)
    polls = []

    def inactive():
        polls.append(True)
        return False

    actual = read_document(source, options=ImportOptions(txt_profile=profile, cancelled=inactive))
    assert actual.success and document_to_json(actual.document) == document_to_json(expected)
    target = tmp_path / 'output.txt'
    report = write_document(actual.document, target, options=ExportOptions(txt_profile=TextProfile(), cancelled=inactive))
    assert report.success and target.read_bytes() == data == source.read_bytes()
    assert len(polls) > 20


@pytest.mark.parametrize('public', [False, True])
def test_cancel_between_paragraphs_discards_partial_model(tmp_path, monkeypatch, public):
    from opendoc_formats.readers import _txt_model

    source = tmp_path / 'own.txt'
    source.write_bytes(b'First\r\nSecond\nThird\r')
    native = _txt_model.Paragraph
    stop, completed = Event(), []

    def first(*args, **kwargs):
        assert not completed
        result = native(*args, **kwargs)
        completed.append(result)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(_txt_model, 'Paragraph', first)
        if public:
            result = read_document(source, options=ImportOptions(cancelled=stop.is_set))
            assert result.document is None and any(issue.code == 'import.cancelled' for issue in result.issues)
        else:
            with pytest.raises(OperationCancelledError):
                read_txt_model(source, cancelled=stop.is_set)
    assert len(completed) == 1 and source.read_bytes() == b'First\r\nSecond\nThird\r'
    checkpoint()
    assert len(read_txt_model(source).sections[0].blocks) == 4


@pytest.mark.parametrize('reader', [read_txt, read_txt_model])
def test_cancel_after_decode_keeps_source_and_restores_context(tmp_path, monkeypatch, reader):
    from opendoc_formats import text_profile

    source = tmp_path / 'own.txt'
    source.write_bytes(b'First\nSecond')
    native = text_profile.normalize_newlines
    stop = Event()

    def normalize(text):
        result = native(text)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(text_profile, 'normalize_newlines', normalize)
        # Readers bind normalize_newlines on import; inject the same boundary there.
        owner = __import__(reader.__module__, fromlist=['normalize_newlines'])
        context.setattr(owner, 'normalize_newlines', normalize)
        with pytest.raises(OperationCancelledError):
            reader(source, profile=TextProfile(newline='lf'), cancelled=stop.is_set)
    checkpoint()
    assert reader(source) is not None


@pytest.mark.parametrize('public', [False, True])
@pytest.mark.parametrize('boundary', ['table', 'encode', 'partial'])
def test_cancel_inside_export_keeps_model_and_previous_destination(tmp_path, monkeypatch, public, boundary):
    from opendoc_formats import text_profile
    from opendoc_formats.writers import txt_writer

    model = DocumentModel(sections=[Section(blocks=[Table(rows=[TableRow(cells=[
        TableCell(blocks=[Paragraph([TextRun('Own cell')])]), TableCell(blocks=[Paragraph([TextRun('Other cell')])]),
    ])]), Paragraph([TextRun('After table')])])])
    original = document_to_json(model)
    target = tmp_path / 'previous.txt'
    target.write_bytes(b'previous artifact')
    stop, finished = Event(), []
    owner, name = ((txt_writer, 'TextStyle') if boundary == 'table' else
                   (text_profile, 'decode_text') if boundary == 'encode' else (Path, 'write_bytes'))
    native = getattr(owner, name)

    def finish(*args, **kwargs):
        result = native(*args, **kwargs)
        if boundary != 'partial' or args[0].suffix == '.partial':
            finished.append(True)
            stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(owner, name, finish)
        if public:
            report = write_document(model, target, options=ExportOptions(cancelled=stop.is_set))
            assert not report.success and any(issue.feature == 'export.cancelled' for issue in report.issues)
        else:
            with pytest.raises(OperationCancelledError):
                write_txt_model(model, target, cancelled=stop.is_set)
    assert finished
    assert target.read_bytes() == b'previous artifact' and document_to_json(model) == original
    assert not list(tmp_path.glob('.*.partial'))
    checkpoint()
    assert write_txt_model(model, target).success
