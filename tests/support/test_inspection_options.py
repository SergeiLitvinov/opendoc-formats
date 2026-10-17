"""Caller budgets and cancellation preserve independent inspection scopes."""

import hashlib

import pytest
from opendoc_model import DocumentLimits, DocumentModel, Paragraph, Resource, ResourceKind, Section, TextRun, document_to_json

from opendoc_formats import ImportOptions
from opendoc_formats.support import inspection


@pytest.mark.parametrize('limits,quota,maximum', [
    (DocumentLimits(max_nodes=10), 'nodes', 10), (DocumentLimits(max_depth=1), 'depth', 1),
    (DocumentLimits(max_bytes=10), 'bytes', 10), (DocumentLimits(max_embedded_bytes=0), 'embedded bytes', 0),
])
def test_limits_are_structured_and_do_not_validate_an_empty_comparison(tmp_path, limits, quota, maximum):
    source = tmp_path / 'own.json'
    model = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun('Own')])])],
                          resources={'own': Resource('own', ResourceKind.ATTACHMENT, 'application/octet-stream', data=b'Own')})
    source.write_text(document_to_json(model),
                      encoding='utf-8')
    before = source.read_bytes()
    report = inspection.inspect_path(source, options=ImportOptions(document_limits=limits))
    assert not report.valid and report.metadata['inspection_status'] == 'refused'
    assert report.metadata['inspection_source_sha256'] == hashlib.sha256(before).hexdigest()
    limit = report.metadata['document_limit']
    assert limit['quota'] == quota and limit['maximum'] == maximum and limit['limits']['max_nodes'] == limits.max_nodes
    assert report.issues[0].feature == 'inspection.document-limit'
    assert report.issues[0].location.startswith(str(source) + '#$')
    assert 'object_inventory_scope' not in report.metadata and not report.objects
    assert not inspection.compare_inspections(report, report).valid
    assert source.read_bytes() == before


@pytest.mark.parametrize('suffix', ['.txt', '.json', '.docx', '.pptx', '.html', '.tex', '.pdf'])
@pytest.mark.parametrize('cancelled', [False, True])
def test_input_guard_precedes_backend_or_parser(tmp_path, monkeypatch, suffix, cancelled):
    source = tmp_path / ('own' + suffix)
    source.write_bytes(b'Own source, not a parsed fixture')

    def forbidden(*args, **kwargs):
        pytest.fail('Refused input must not reach a parser')

    monkeypatch.setattr(inspection, '_inspect_path', forbidden)
    report = inspection.inspect_path(source, options=ImportOptions(max_input_bytes=1, cancelled=lambda: cancelled))
    assert not report.valid and not report.metrics and not report.objects
    assert report.issues[0].feature == ('inspection.cancelled' if cancelled else 'inspection.input-limit')
    assert 'inspection_source_sha256' not in report.metadata


@pytest.mark.parametrize('action,feature', [('cancel', 'inspection.cancelled'), ('change', 'inspection.source-changed')])
def test_late_cancel_and_source_change_discard_measurements(tmp_path, monkeypatch, action, feature):
    source = tmp_path / 'own.txt'
    source.write_text('Own content', encoding='utf-8')
    state = {'cancelled': False}
    original = inspection._inspect_path

    def modified(path, options):
        report = original(path, options)
        if action == 'cancel':
            state['cancelled'] = True
        else:
            path.write_text('Changed own content', encoding='utf-8')
        return report

    monkeypatch.setattr(inspection, '_inspect_path', modified)
    report = inspection.inspect_path(source, options=ImportOptions(cancelled=lambda: state['cancelled']))
    assert not report.valid and report.issues[0].feature == feature
    assert not report.objects and not report.metrics and 'text_flow' not in report.metadata


@pytest.mark.parametrize('suffix', ['.html', '.tex'])
def test_native_scope_is_retained_with_options(tmp_path, suffix):
    source = tmp_path / ('own' + suffix)
    source.write_text('<p>Own text</p><math>x</math>' if suffix == '.html'
                      else r'\documentclass[a4paper]{article}\begin{document}Own $x$\end{document}', encoding='utf-8')
    before = source.read_bytes()
    old = inspection.inspect_path(source)
    report = inspection.inspect_path(source, options=ImportOptions(document_limits=DocumentLimits(max_nodes=200000)))
    assert report.valid and report.metadata['inspection_status'] == 'completed'
    assert report.metrics == old.metrics and report.pages == old.pages
    assert report.formula_formats == old.formula_formats and not report.objects
    assert 'object_inventory_scope' not in report.metadata
    assert report.metadata['inspection_source_sha256'] == hashlib.sha256(before).hexdigest()
    assert source.read_bytes() == before


@pytest.mark.parametrize('suffix', ['.docx', '.txt'])
def test_model_readers_use_selected_budget_and_keep_scope(tmp_path, suffix):
    source = tmp_path / ('own' + suffix)
    if suffix == '.docx':
        from docx import Document
        native = Document()
        native.add_paragraph('Own source')
        native.save(source)
    else:
        source.write_text('Own source', encoding='utf-8')
    before = source.read_bytes()
    report = inspection.inspect_path(source, options=ImportOptions(document_limits=DocumentLimits(max_nodes=200000)))
    assert report.valid and report.metrics['text_runs'] == 1
    refused = inspection.inspect_path(source, options=ImportOptions(document_limits=DocumentLimits(max_nodes=10)))
    assert not refused.valid and refused.metadata['document_limit']['maximum'] == 10
    if suffix == '.txt':
        assert not report.pages and 'pages' not in report.metrics
    assert source.read_bytes() == before


def test_pdf_partial_scope_and_page_cancellation(tmp_path, monkeypatch):
    fitz = pytest.importorskip('pymupdf')
    source = tmp_path / 'own.pdf'
    with fitz.open() as pdf:
        for _ in range(2):
            page = pdf.new_page()
            page.insert_text((20, 30), 'Own text')
        pdf.save(source)
    before = source.read_bytes()
    options = ImportOptions()
    full = inspection.inspect_path(source, options=options)
    monkeypatch.setattr(inspection, '_PDF_INSPECTION_MAX_PAGES', 1)
    partial = inspection.inspect_path(source, options=options)
    assert partial.metadata['inspection_status'] == 'partial'
    assert not partial.metadata['text_flow_profile']['complete'] and not partial.objects
    from opendoc_model import ConversionReport, TextPreservationPolicy
    gate = ConversionReport(tmp_path / 'unused.pdf')
    assert not TextPreservationPolicy('flow', 0).evaluate(gate, inspection.compare_inspections(full, partial))
    monkeypatch.setattr(inspection, '_PDF_INSPECTION_MAX_PAGES', 10000)
    state = {'cancelled': False, 'pages': 0}
    original = fitz.Page.get_text

    def text(page, option='text', **kwargs):
        state['pages'] += option == 'text'
        state['cancelled'] = True
        return original(page, option, **kwargs)

    monkeypatch.setattr(fitz.Page, 'get_text', text)
    report = inspection.inspect_path(source, options=ImportOptions(cancelled=lambda: state['cancelled']))
    assert not report.valid and report.metadata['inspection_status'] == 'cancelled'
    assert not report.pages and 'text_flow' not in report.metadata and state['pages'] == 1
    assert source.read_bytes() == before
