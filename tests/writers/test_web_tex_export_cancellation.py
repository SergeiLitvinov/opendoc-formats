"""Own finite HTML/EPUB/TeX models exercise cooperative and atomic export."""

import importlib
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from zipfile import ZipFile

import pytest
from opendoc_model import (
    DocumentModel,
    Formula,
    FormulaFormat,
    Image,
    Paragraph,
    Resource,
    ResourceKind,
    Section,
    Table,
    TableCell,
    TableRow,
    TextRun,
    document_to_json,
)

from opendoc_formats import ExportOptions, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.support.cancellation import checkpoint
from tests.writers.test_latex_lists import read_source


@pytest.fixture
def web_model():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'
    return DocumentModel(metadata={'title': 'Own', 'language': 'en'}, resources={
        'pic': Resource('pic', ResourceKind.VECTOR_IMAGE, 'image/svg+xml', data=svg),
    }, sections=[Section(blocks=[
        Paragraph([TextRun('Own start')]), Paragraph([TextRun('Own second')]),
        Table([TableRow([TableCell([Paragraph([TextRun('Own cell')])]), TableCell([Paragraph([TextRun('Other cell')])])])]),
        Paragraph([Formula('<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>', format=FormulaFormat.MATHML)]),
        Image('pic'), Image('pic'),
    ]) for _ in range(3)])


@pytest.fixture
def tex_model(tmp_path):
    return read_source(tmp_path, r'Before $x+1$.\begin{enumerate}\item First $\frac{a}{b}$.\item Last.\end{enumerate}After.')


@pytest.fixture
def bridge_model():
    return DocumentModel(sections=[Section(blocks=[Paragraph([TextRun('Before')]),
        Table([TableRow([TableCell([Paragraph([TextRun('Own bridge cell')])])])]), Paragraph([TextRun('After')])])])


def _direct(kind):
    return getattr(importlib.import_module('opendoc_formats.writers.' + kind + '_writer'), 'write_' + kind + '_model')


@pytest.mark.parametrize('kind', ['html', 'epub', 'latex'])
def test_no_signal_preserves_complete_serialization_and_input(request, tmp_path, monkeypatch, kind):
    model = request.getfixturevalue('tex_model' if kind == 'latex' else 'web_model')
    original = document_to_json(model)
    target = tmp_path / ('own.' + ('tex' if kind == 'latex' else kind))
    if kind == 'epub':
        from opendoc_formats.writers import epub_writer

        class FixedClock:
            @staticmethod
            def now(tz):
                return datetime(2020, 1, 1, tzinfo=timezone.utc)

        monkeypatch.setattr(epub_writer, 'datetime', FixedClock)

    def content():
        if kind != 'epub':
            return target.read_bytes()
        with ZipFile(target) as archive:
            return {name: archive.read(name) for name in archive.namelist()}

    assert _direct(kind)(model, target).success
    expected, polls = content(), []

    def inactive():
        polls.append(True)
        return False

    assert _direct(kind)(model, target, cancelled=inactive).success
    assert len(polls) > 20 and content() == expected
    assert document_to_json(model) == original


@pytest.mark.parametrize(('kind', 'fixture', 'module', 'owner', 'name'), [
    ('html', 'web_model', 'html_writer', '_HtmlRenderer', '_paragraph'),
    ('html', 'web_model', 'html_writer', '_HtmlRenderer', '_image'),
    ('html', 'web_model', 'html_verify', 'HtmlVerifyStage', 'execute'),
    ('epub', 'web_model', 'epub_writer', '_Xhtml', 'handle_starttag'),
    ('epub', 'web_model', 'epub_writer', '_Xhtml', '_image'),
    ('epub', 'web_model', 'epub_writer', None, '_xml'),
    ('latex', 'tex_model', 'latex_text', None, 'escape_latex'),
    ('latex', 'tex_model', 'latex_lists', None, 'paragraph_marker'),
    ('latex', 'tex_model', 'tex_math', None, 'tokenize_tex'),
    ('latex', 'bridge_model', 'docx_to_latex', None, '_para_to_latex'),
])
@pytest.mark.parametrize('public', [False, True])
def test_mid_export_stop_keeps_model_and_destination(request, monkeypatch, tmp_path, kind, fixture, module, owner, name, public):
    model = request.getfixturevalue(fixture)
    original = document_to_json(model)
    target = tmp_path / ('kept.' + ('tex' if kind == 'latex' else kind))
    target.write_bytes(b'own previous destination')
    native_owner = importlib.import_module('opendoc_formats.' + (module if module == 'tex_math' else 'writers.' + module))
    if owner:
        native_owner = getattr(native_owner, owner)
    native = getattr(native_owner, name)
    stop, completed = Event(), []

    def first(*args, **kwargs):
        assert not completed, 'Object processing continued after cancellation'
        result = native(*args, **kwargs)
        completed.append(True)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(native_owner, name, first)
        if public:
            report = write_document(model, target, options=ExportOptions(cancelled=stop.is_set))
            assert not report.success and any(issue.feature == 'export.cancelled' for issue in report.issues)
        else:
            with pytest.raises(OperationCancelledError):
                _direct(kind)(model, target, cancelled=stop.is_set)
    assert completed == [True] and target.read_bytes() == b'own previous destination'
    assert document_to_json(model) == original
    checkpoint()
    assert not list(tmp_path.glob('.*.partial'))
    assert _direct(kind)(model, target).success


@pytest.mark.parametrize('kind', ['epub', 'latex'])
@pytest.mark.parametrize('public', [False, True])
def test_cancellation_after_partial_bytes_preserves_destination(request, tmp_path, monkeypatch, kind, public):
    model = request.getfixturevalue('tex_model' if kind == 'latex' else 'web_model')
    target = tmp_path / ('kept.' + ('tex' if kind == 'latex' else kind))
    target.write_bytes(b'previous')
    stop, written = Event(), []
    write = Path.write_bytes

    def stage(path, data):
        result = write(path, data)
        if path.name.endswith('.partial'):
            written.append(path)
            stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(Path, 'write_bytes', stage)
        if public:
            report = write_document(model, target, options=ExportOptions(cancelled=stop.is_set))
            assert not report.success and any(issue.feature == 'export.cancelled' for issue in report.issues)
        else:
            with pytest.raises(OperationCancelledError):
                _direct(kind)(model, target, cancelled=stop.is_set)
    assert len(written) == 1 and not written[0].exists()
    assert target.read_bytes() == b'previous'


@pytest.mark.parametrize('kind', ['html', 'epub', 'latex'])
def test_direct_commit_has_no_false_rollback(request, tmp_path, monkeypatch, kind):
    from opendoc_formats.support import io

    model = request.getfixturevalue('tex_model' if kind == 'latex' else 'web_model')
    target = tmp_path / ('done.' + ('tex' if kind == 'latex' else kind))
    stop = Event()
    replace = io.os.replace

    def commit(source, destination):
        result = replace(source, destination)
        if Path(destination) == target:
            stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(io.os, 'replace', commit)
        report = _direct(kind)(model, target, cancelled=stop.is_set)
    assert report.success and target.is_file() and stop.is_set()
    checkpoint()
