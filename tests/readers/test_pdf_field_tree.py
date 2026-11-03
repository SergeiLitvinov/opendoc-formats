"""Own canonical field graphs, independent of page widget appearances."""

from dataclasses import replace

import pytest
from opendoc_model import get_integration, set_integration

from opendoc_formats import read_document, write_document
from opendoc_formats.readers.pdf_fields import audit_field_tree

fitz = pytest.importorskip('pymupdf')
PdfReader = pytest.importorskip('pypdf').PdfReader


def _source(path, *, shared=False):
    with fitz.open() as pdf:
        for _ in range(2 if shared else 1):
            page = pdf.new_page(width=240, height=200)
            page.insert_text((20, 30), 'Own field default')
            widget = fitz.Widget()
            widget.field_name, widget.field_value = 'own-field', 'Current'
            widget.field_type, widget.rect = fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(20, 80, 150, 110)
            created = page.add_widget(widget)
            pdf.xref_set_key(created.xref, 'DV', fitz.get_pdf_str('Reset value'))
        pdf.save(path)


def _fields(path):
    return {name: {key: str(value.get(key)) for key in ('/FT', '/V', '/DV', '/Ff')}
            for name, value in (PdfReader(path).get_fields() or {}).items()}


@pytest.mark.parametrize('shared', [False, True])
def test_default_values_survive_original_and_typed_edits(tmp_path, shared):
    source = tmp_path / 'own.pdf'
    _source(source, shared=shared)
    original, current = source.read_bytes(), source
    expected = _fields(source)
    for number in range(2):
        transport = tmp_path / f'cycle{number}.json'
        assert write_document(read_document(current).document, transport).success
        current = transport.with_suffix('.pdf')
        report = write_document(read_document(transport).document, current)
        assert report.success, report.issues
        assert _fields(current) == expected
        with fitz.open(current) as pdf:
            widgets = [w.xref for page in pdf for w in page.widgets() or ()]
            assert len(widgets) == len(set(widgets)) == (2 if shared else 1)
    document = read_document(current).document
    integration = get_integration(document)
    forms = tuple(replace(form, value='Edited', extra={**form.extra, 'pdf_default_value': 'Edited default'})
                  for form in integration.forms)
    set_integration(document, replace(integration, forms=forms))
    edited = tmp_path / 'edited.pdf'
    assert write_document(document, edited).success
    assert _fields(edited)['own-field']['/DV'] == 'Edited default'
    assert _fields(edited)['own-field']['/V'] == 'Edited'
    set_integration(document, replace(get_integration(document), forms=tuple(
        replace(form, extra={**form.extra, 'pdf_default_value': None}) for form in forms)))
    removed = tmp_path / 'default-removed.pdf'
    assert write_document(document, removed).success
    assert _fields(removed)['own-field']['/DV'] == 'None'
    assert source.read_bytes() == original


def test_orphan_and_parent_fields_are_located_opaque(tmp_path):
    source = tmp_path / 'own.pdf'
    _source(source)
    custom = tmp_path / 'tree.pdf'
    with fitz.open(source) as pdf:
        page = pdf[0]
        widget = next(page.widgets())
        parent, orphan = pdf.get_new_xref(), pdf.get_new_xref()
        pdf.update_object(parent, f'<</T (group) /Kids [{widget.xref} 0 R]>>')
        pdf.xref_set_key(widget.xref, 'Parent', f'{parent} 0 R')
        pdf.update_object(orphan, '<</T (orphan) /FT /Tx /V (Own orphan)>>')
        pdf.xref_set_key(pdf.pdf_catalog(), 'AcroForm/Fields', f'[{parent} 0 R {orphan} 0 R]')
        pdf.save(custom)
    original = custom.read_bytes()
    imported = read_document(custom)
    assert imported.success
    records = [r for r in get_integration(imported.document).preservation if r.issue.code == 'pdf.field-tree']
    assert {r.issue.reason for r in records} == {'hierarchical-field', 'field-without-widget'}
    assert all(r.issue.location and r.provenance.object_id for r in records)
    output = tmp_path / 'target.pdf'
    report = write_document(imported.document, output)
    assert any(x.feature == 'pdf.field-tree' and x.location for x in report.issues)
    assert custom.read_bytes() == original


def test_conflicting_shared_default_refuses_atomically(tmp_path):
    source = tmp_path / 'own.pdf'
    _source(source, shared=True)
    document = read_document(source).document
    integration = get_integration(document)
    second = replace(integration.forms[1], extra={**integration.forms[1].extra, 'pdf_default_value': 'Conflicting'})
    set_integration(document, replace(integration, forms=(integration.forms[0], second)))
    output = tmp_path / 'previous.pdf'
    output.write_bytes(b'own previous artifact')
    report = write_document(document, output)
    assert not report.success
    assert any(x.feature == 'pdf.form-conflict' and x.location for x in report.issues)
    assert output.read_bytes() == b'own previous artifact'


def test_cyclic_canonical_tree_is_rejected(tmp_path):
    source = tmp_path / 'own.pdf'
    _source(source)
    with fitz.open(source) as pdf:
        root = pdf.get_new_xref()
        pdf.update_object(root, f'<</T (cycle) /Kids [{root} 0 R]>>')
        pdf.xref_set_key(pdf.pdf_catalog(), 'AcroForm/Fields', f'[{root} 0 R]')
        with pytest.raises(ValueError, match='cyclic'):
            audit_field_tree(pdf, set(), lambda *args: None)


def test_default_limit_refuses_with_location(tmp_path):
    source = tmp_path / 'own.pdf'
    _source(source)
    document = read_document(source).document
    integration = get_integration(document)
    form = replace(integration.forms[0], extra={**integration.forms[0].extra, 'pdf_default_value': 'X' * 65_537})
    set_integration(document, replace(integration, forms=(form,)))
    output = tmp_path / 'previous.pdf'
    output.write_bytes(b'own previous artifact')
    report = write_document(document, output)
    assert not report.success
    assert any(x.feature == 'pdf.form-default' and x.location for x in report.issues)
    assert output.read_bytes() == b'own previous artifact'
