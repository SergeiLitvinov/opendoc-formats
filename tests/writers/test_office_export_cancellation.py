"""Native export cancellation preserves source models and existing destinations."""

import importlib
from pathlib import Path
from threading import Event

import pytest
from opendoc_model import document_to_json

from opendoc_formats import ExportOptions, read_document, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.support.cancellation import checkpoint
from tests.readers.test_office_import_cancellation import docx_source as docx_source
from tests.readers.test_office_import_cancellation import pptx_source as pptx_source


def _writer(kind):
    return getattr(importlib.import_module('opendoc_formats.writers.' + kind + '_writer'), 'write_' + kind + '_model')


@pytest.mark.parametrize('kind', ['docx', 'pptx'])
def test_no_signal_preserves_complete_native_model(request, monkeypatch, tmp_path, kind):
    source = request.getfixturevalue(kind + '_source')
    model = read_document(source).document
    original = document_to_json(model)
    if kind == 'pptx':
        from datetime import datetime, timezone
        from zipfile import ZipInfo

        from pptx.chart import xlsx
        from pptx.opc.serialized import _ZipPkgWriter

        workbook_type = xlsx.Workbook

        def stable_workbook(*args, **kwargs):
            workbook = workbook_type(*args, **kwargs)
            # Capture now includes complete XLSX bytes. Hold producer timestamps
            # fixed to compare the cancellation callback, without ignoring parts.
            workbook.set_properties({'created': datetime(2000, 1, 1, tzinfo=timezone.utc)})
            return workbook

        monkeypatch.setattr(xlsx, 'Workbook', stable_workbook)

        def stable_package_write(writer, pack_uri, blob):
            info = ZipInfo(pack_uri.membername, date_time=(2000, 1, 1, 0, 0, 0))
            info.compress_type = writer._zipf.compression
            writer._zipf.writestr(info, blob)

        # Source SHA now includes archive headers too; keep only producer time
        # deterministic and still compare the complete captured model/package.
        monkeypatch.setattr(_ZipPkgWriter, 'write', stable_package_write)
    target = tmp_path / ('complete.' + kind)
    assert _writer(kind)(model, target).success
    expected = document_to_json(read_document(target).document)
    polls = []

    def inactive():
        polls.append(True)
        return False

    assert _writer(kind)(model, target, cancelled=inactive).success
    assert len(polls) > 30
    assert document_to_json(read_document(target).document) == expected
    assert document_to_json(model) == original


@pytest.mark.parametrize(('kind', 'module', 'name'), [
    ('docx', 'docx_text_writer', 'apply_text_style'),
    ('docx', 'docx_table_writer', '_apply_cell_properties'),
    ('docx', 'docx_drawing_writer', '_apply_image_transform'),
    ('docx', 'docx_writer', 'embed_docx_fonts'),
    ('docx', 'docx_writer', '_restore_package_graph'),
    ('pptx', 'pptx_text_writer', 'configure_paragraph'),
    ('pptx', 'pptx_objects_writer', 'configure_cell'),
    ('pptx', 'pptx_chart_writer', '_number'),
    ('pptx', 'pptx_writer', 'write_image'),
    ('pptx', 'pptx_writer', 'restore_groups'),
])
@pytest.mark.parametrize('public', [False, True])
def test_cancel_during_object_work_keeps_input_and_destination(request, monkeypatch, tmp_path, kind, module, name, public):
    source = request.getfixturevalue(kind + '_source')
    model = read_document(source).document
    original = document_to_json(model)
    target = tmp_path / ('kept.' + kind)
    target.write_bytes(b'own previous destination')
    owner = importlib.import_module('opendoc_formats.writers.' + module)
    native = getattr(owner, name)
    stop, completed = Event(), []

    def first(*args, **kwargs):
        assert not completed, 'Native work continued after cancellation'
        result = native(*args, **kwargs)
        completed.append(True)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(owner, name, first)
        if public:
            report = write_document(model, target, options=ExportOptions(cancelled=stop.is_set))
            assert not report.success and any(issue.feature == 'export.cancelled' for issue in report.issues)
        else:
            with pytest.raises(OperationCancelledError):
                _writer(kind)(model, target, cancelled=stop.is_set)
    assert completed == [True]
    checkpoint()
    assert target.read_bytes() == b'own previous destination'
    assert document_to_json(model) == original
    assert not list(tmp_path.glob('.*.partial'))
    assert _writer(kind)(model, target).success
    assert read_document(target).document is not None


@pytest.mark.parametrize('kind', ['docx', 'pptx'])
@pytest.mark.parametrize('boundary', ['save', 'copy'])
@pytest.mark.parametrize('public', [False, True])
def test_cancel_after_native_save_or_partial_copy_discards_output(request, monkeypatch, tmp_path, kind, boundary, public):
    source = request.getfixturevalue(kind + '_source')
    model = read_document(source).document
    target = tmp_path / ('kept.' + kind)
    target.write_bytes(b'previous')
    stop, completed = Event(), []
    if boundary == 'save':
        owner = getattr(importlib.import_module(kind + ('.document' if kind == 'docx' else '.presentation')),
                        'Document' if kind == 'docx' else 'Presentation')
        name = 'save'
    else:
        import shutil

        owner, name = shutil, 'copy2'
    native = getattr(owner, name)

    def finish(*args, **kwargs):
        result = native(*args, **kwargs)
        completed.append(True)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(owner, name, finish)
        if public:
            report = write_document(model, target, options=ExportOptions(cancelled=stop.is_set))
            assert not report.success and any(issue.feature == 'export.cancelled' for issue in report.issues)
        else:
            with pytest.raises(OperationCancelledError):
                _writer(kind)(model, target, cancelled=stop.is_set)
    assert completed == [True]
    assert target.read_bytes() == b'previous'
    assert not list(tmp_path.glob('.*.partial'))
    assert _writer(kind)(model, target).success


@pytest.mark.parametrize('kind', ['docx', 'pptx'])
def test_signal_after_direct_commit_does_not_claim_rollback(request, monkeypatch, tmp_path, kind):
    from opendoc_formats.support import io

    model = read_document(request.getfixturevalue(kind + '_source')).document
    target = tmp_path / ('committed.' + kind)
    stop = Event()
    replace = io.os.replace

    def commit(source, destination):
        result = replace(source, destination)
        if Path(destination) == target:
            stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(io.os, 'replace', commit)
        report = _writer(kind)(model, target, cancelled=stop.is_set)
    assert report.success and stop.is_set()
    assert read_document(target).document is not None
    checkpoint()
