"""Legacy PDF fallback keeps valid table-only output and propagates stop conditions."""

from threading import Event
from types import SimpleNamespace

import pytest
from opendoc_model import ArtifactLimitError

from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from opendoc_formats.readers import pdf
from opendoc_formats.support.cancellation import checkpoint
from opendoc_formats.types import DocFormat, Table, Text


@pytest.mark.parametrize('error', [
    OperationCancelledError('Own stop'), ResourceLimitError('Own native limit'),
    ArtifactLimitError('Own Model limit', path='pages[0]', quota='work', maximum=1),
])
def test_stop_conditions_do_not_try_another_engine(monkeypatch, error):
    calls = []

    def stopped(path):
        calls.append(path)
        raise error

    def forbidden(path):
        pytest.fail('Another PDF engine started after a stop condition')

    monkeypatch.setattr(pdf, 'missing_backends', lambda names: [])
    monkeypatch.setattr(pdf, '_with_pdfplumber', stopped)
    monkeypatch.setattr(pdf, '_with_pypdf', forbidden)
    monkeypatch.setattr(pdf, '_with_pymupdf', forbidden)
    with pytest.raises(type(error)) as captured:
        pdf.read_pdf('own.pdf')
    assert captured.value is error and calls == ['own.pdf']
    checkpoint()


def test_table_only_result_is_not_discarded_for_another_engine(monkeypatch):
    result = Text(tables=[Table([['Own cell']], page=1)], source_format=DocFormat.PDF, engine='pdfplumber')

    def forbidden(path):
        pytest.fail('Valid table-only result was discarded')

    monkeypatch.setattr(pdf, 'missing_backends', lambda names: [])
    monkeypatch.setattr(pdf, '_with_pdfplumber', lambda path: result)
    monkeypatch.setattr(pdf, '_with_pypdf', forbidden)
    assert pdf.read_pdf('own.pdf') is result


def test_recoverable_failure_keeps_warning_and_uses_next_engine(monkeypatch):
    def failed(path):
        raise RuntimeError('Own recoverable failure')

    monkeypatch.setattr(pdf, 'missing_backends', lambda names: [])
    monkeypatch.setattr(pdf, '_with_pdfplumber', failed)
    monkeypatch.setattr(pdf, '_with_pypdf', lambda path: Text(plain='Own text', engine='pypdf'))
    result = pdf.read_pdf('own.pdf')
    assert result.plain == 'Own text' and result.engine == 'pypdf'
    assert result.warnings == ['pdfplumber: RuntimeError: Own recoverable failure']


def test_cancel_after_engine_result_precedes_next_engine_and_restores_scope(monkeypatch):
    stop = Event()

    def first(path):
        stop.set()
        return Text(plain='Own completed text')

    monkeypatch.setattr(pdf, 'missing_backends', lambda names: [])
    monkeypatch.setattr(pdf, '_with_pdfplumber', first)
    with pytest.raises(OperationCancelledError):
        pdf.read_pdf('own.pdf', cancelled=stop.is_set)
    checkpoint()
    assert pdf.read_pdf('own.pdf').plain == 'Own completed text'
    with pytest.raises(ValueError, match='callable'):
        pdf.read_pdf('own.pdf', cancelled=True)


@pytest.mark.parametrize('error', [
    OperationCancelledError('Own page stop'), ResourceLimitError('Own page native limit'),
    ArtifactLimitError('Own page Model limit', path='pages[0]', quota='work', maximum=1),
])
def test_pypdf_page_stop_condition_is_not_silently_skipped(monkeypatch, error):
    import sys

    def stopped():
        raise error

    def forbidden():
        pytest.fail('Another page started after stop')

    pages = [SimpleNamespace(extract_text=stopped), SimpleNamespace(extract_text=forbidden)]
    monkeypatch.setitem(sys.modules, 'pypdf', SimpleNamespace(PdfReader=lambda path: SimpleNamespace(pages=pages)))
    with pytest.raises(type(error)) as captured:
        pdf._with_pypdf('own.pdf')
    assert captured.value is error


def test_pypdf_recoverable_page_failure_is_reported_with_page_number(monkeypatch):
    import sys

    def failed():
        raise RuntimeError('Own page extraction failure')

    pages = [SimpleNamespace(extract_text=failed), SimpleNamespace(extract_text=lambda: 'Own second page')]
    monkeypatch.setitem(sys.modules, 'pypdf', SimpleNamespace(PdfReader=lambda path: SimpleNamespace(pages=pages)))
    result = pdf._with_pypdf('own.pdf')
    assert result.plain == 'Own second page' and result.pages == 2
    assert result.warnings == ['pypdf page 1: RuntimeError: Own page extraction failure']


def own_pdf(tmp_path):
    import pymupdf

    path = tmp_path/'own.pdf'
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 100), 'Own first paragraph')
        page.insert_text((72, 200), 'Own second paragraph')
        document.save(path)
    return path


def test_inactive_callback_keeps_complete_native_text_dict_and_source(tmp_path, monkeypatch):
    source = own_pdf(tmp_path)
    original = source.read_bytes()
    monkeypatch.setattr(pdf, 'missing_backends', lambda names: [] if names == ('pymupdf',) else list(names))
    expected = pdf.read_pdf(str(source)).to_dict()
    polls = []

    def inactive():
        polls.append(True)
        return False

    assert pdf.read_pdf(str(source), cancelled=inactive).to_dict() == expected
    assert len(polls) > 10 and source.read_bytes() == original


def test_stop_inside_semantic_analysis_precedes_next_block(tmp_path, monkeypatch):
    from opendoc_formats.readers import pdf_semantic

    source = own_pdf(tmp_path)
    original = source.read_bytes()
    stop, calls = Event(), []
    classify = pdf_semantic.classify_text_block

    def first(*args, **kwargs):
        assert not calls, 'Another semantic block was classified after cancellation'
        result = classify(*args, **kwargs)
        calls.append(True)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(pdf, 'missing_backends', lambda names: [] if names == ('pymupdf',) else list(names))
        context.setattr(pdf_semantic, 'classify_text_block', first)
        with pytest.raises(OperationCancelledError):
            pdf.read_pdf(str(source), cancelled=stop.is_set)
    assert calls == [True] and source.read_bytes() == original
    checkpoint()
    assert pdf.read_pdf(str(source)).plain
