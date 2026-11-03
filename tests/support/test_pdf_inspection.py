"""Native text scope and canonical fields, independent of model object inventory."""

import hashlib

import pytest
from opendoc_model.diagnostics import ConversionReport
from opendoc_model.object_quality_policy import ObjectLossPolicy
from opendoc_model.text_quality_policy import TextPreservationPolicy

from opendoc_formats.support import inspection

fitz = pytest.importorskip('pymupdf')


def _pdf(path, texts=('First page text', 'Second page text')):
    with fitz.open() as pdf:
        for text in texts:
            page = pdf.new_page(width=240, height=200)
            if text:
                page.insert_text((20, 30), text)
        pdf.save(path)
    return path


def _quality(tmp_path, source, target):
    report = ConversionReport(tmp_path / 'result.pdf')
    accepted = TextPreservationPolicy('flow', 0).evaluate(report, inspection.compare_inspections(source, target))
    return accepted, report.metrics['text_quality_gate']


def test_native_flow_preserves_order_and_empty_is_measured(tmp_path):
    source = _pdf(tmp_path / 'source.pdf')
    original = source.read_bytes()
    report = inspection.inspect_path(source)
    assert report.valid and not report.objects
    assert 'object_inventory_scope' not in report.metadata
    assert report.metadata['text_flow']['sha256'] == hashlib.sha256(b'First page text Second page text').hexdigest()
    assert report.metadata['text_flow_profile']['complete']
    object_gate = ConversionReport(tmp_path / 'objects.pdf')
    assert not ObjectLossPolicy(0).evaluate(object_gate, inspection.compare_inspections(report, report))
    accepted, metric = _quality(tmp_path, report, inspection.inspect_path(source))
    assert accepted and metric['coverage'] == 'declared-text-scope'
    changed = inspection.inspect_path(_pdf(tmp_path / 'changed.pdf', ('Second page text', 'First page text')))
    accepted, metric = _quality(tmp_path, report, changed)
    assert not accepted and metric['verified']
    empty = inspection.inspect_path(_pdf(tmp_path / 'empty.pdf', ('',)))
    assert empty.metadata['text_flow']['characters'] == 0
    assert _quality(tmp_path, empty, empty)[0]
    assert not _quality(tmp_path, report, empty)[0]
    assert source.read_bytes() == original


@pytest.mark.parametrize('limit,value,reason', [
    ('_PDF_INSPECTION_MAX_BYTES', 1, 'file-limit'),
    ('_PDF_INSPECTION_MAX_PAGES', 1, 'page-limit'),
    ('_PDF_INSPECTION_MAX_PAGE_TEXT', 1, 'text-limit'),
    ('_PDF_INSPECTION_MAX_TEXT', 20, 'text-limit'),
])
def test_limits_cannot_pass_as_empty_or_equal_text(tmp_path, monkeypatch, limit, value, reason):
    path = _pdf(tmp_path / 'source.pdf')
    baseline = inspection.inspect_path(path)
    monkeypatch.setattr(inspection, limit, value)
    partial = inspection.inspect_path(path)
    profile = partial.metadata['text_flow_profile']
    assert not profile['complete'] and profile['reason'] == reason
    accepted, metric = _quality(tmp_path, baseline, partial)
    assert not accepted and not metric['verified']
    assert any(issue.location for issue in partial.issues if issue.feature == 'pdf.inspection-limit')


def test_password_and_backend_failure_have_unknown_scope(tmp_path, monkeypatch):
    path = _pdf(tmp_path / 'source.pdf')
    baseline = inspection.inspect_path(path)
    locked = tmp_path / 'locked.pdf'
    with fitz.open(path) as pdf:
        pdf.save(locked, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='user')
    report = inspection.inspect_path(locked)
    assert not report.valid and 'text_flow' not in report.metadata
    assert report.metadata['text_flow_profile']['reason'] == 'password-required'
    assert not _quality(tmp_path, report, report)[0]
    original = fitz.Page.get_text

    def failed(page, option='text', **kwargs):
        if option == 'text':
            raise RuntimeError('Own extraction failure')
        return original(page, option, **kwargs)

    monkeypatch.setattr(fitz.Page, 'get_text', failed)
    report = inspection.inspect_path(path)
    assert report.metadata['text_flow_profile']['reason'] == 'backend-extraction-failed'
    assert not _quality(tmp_path, baseline, report)[0]


def test_canonical_names_match_independent_parser_without_counting_widgets(tmp_path):
    reader = pytest.importorskip('pypdf').PdfReader
    path = tmp_path / 'fields.pdf'
    with fitz.open() as pdf:
        widgets = []
        for _ in range(2):
            page = pdf.new_page()
            w = fitz.Widget()
            w.field_name, w.field_value = 'shared', 'Own value'
            w.field_type, w.rect = fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(20, 30, 100, 50)
            widgets.append(page.add_widget(w).xref)
        parent, child, orphan = [pdf.get_new_xref() for _ in range(3)]
        pdf.update_object(parent, f'<</T(group)/Kids[{child} 0 R]>>')
        pdf.update_object(child, f'<</T(child)/FT/Tx/Parent {parent} 0 R/V(value)>>')
        pdf.update_object(orphan, '<</T(orphan)/TM(mapped)/FT/Tx/V(value)>>')
        roots = ' '.join(f'{xref} 0 R' for xref in [*widgets, parent, orphan])
        pdf.xref_set_key(pdf.pdf_catalog(), 'AcroForm/Fields', f'[{roots}]')
        pdf.save(path)
    report = inspection.inspect_path(path)
    expected = reader(path).get_fields()
    assert set(expected) == {'shared', 'group', 'group.child', 'mapped'}
    assert report.metrics['form_fields'] == len(expected) == 4
    assert report.metrics['form_widgets'] == 2
    assert report.metadata['pdf_field_names_complete']


def test_unsupported_field_array_is_unknown_not_zero(tmp_path):
    path = _pdf(tmp_path / 'source.pdf')
    with fitz.open(path) as pdf:
        pdf.xref_set_key(pdf.pdf_catalog(), 'AcroForm', '<</Fields[<</T(Own)/FT/Tx>>]>>')
        pdf.save(tmp_path / 'direct.pdf')
    report = inspection.inspect_path(tmp_path / 'direct.pdf')
    assert 'form_fields' not in report.metrics
    assert report.metadata['pdf_field_names_complete'] is False
    assert report.metadata['text_flow_profile']['complete']
    assert any(issue.feature == 'pdf.field-inventory' and issue.location for issue in report.issues)


def test_field_cycle_is_unknown_and_empty_password_is_readable(tmp_path):
    source = _pdf(tmp_path / 'source.pdf')
    with fitz.open(source) as pdf:
        node = pdf.get_new_xref()
        pdf.update_object(node, f'<</T(cycle)/FT/Tx/Kids[{node} 0 R]>>')
        pdf.xref_set_key(pdf.pdf_catalog(), 'AcroForm', f'<</Fields[{node} 0 R]>>')
        pdf.save(tmp_path / 'cycle.pdf')
    report = inspection.inspect_path(tmp_path / 'cycle.pdf')
    assert not report.metadata['pdf_field_names_complete']
    assert 'form_fields' not in report.metrics
    with fitz.open(source) as pdf:
        pdf.save(tmp_path / 'owner.pdf', encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='owner')
    report = inspection.inspect_path(tmp_path / 'owner.pdf')
    assert report.valid and report.metadata['text_flow_profile']['complete']
    assert _quality(tmp_path, inspection.inspect_path(source), report)[0]
