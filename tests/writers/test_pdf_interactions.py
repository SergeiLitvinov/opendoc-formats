"""Independent native interaction inventories, including canonical AcroForm values."""

from dataclasses import replace

import pytest
from opendoc_model import get_integration, set_integration

from opendoc_formats import ExportOptions, read_document, write_document

fitz = pytest.importorskip('pymupdf')
PdfReader = pytest.importorskip('pypdf').PdfReader


def _source(path, small, rotation):
    with fitz.open() as pdf:
        page = pdf.new_page(width=240 if small else 595, height=200 if small else 842)
        page.insert_text((20, 30), 'Own body', fontsize=10)
        page.add_text_annot((20, 45), 'Own note').update()
        page.add_highlight_annot(page.search_for('Own')).update()
        page.insert_link({'kind': fitz.LINK_URI, 'from': fitz.Rect(20, 80, 100, 100), 'uri': 'https://example.invalid/'})
        widget = fitz.Widget()
        widget.field_name, widget.field_value = 'own-field', 'Initial'
        widget.field_type, widget.rect = fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(20, 110, 150, 135)
        widget.script = '/* Own inert marker */'
        page.add_widget(widget)
        page.set_rotation(rotation)
        pdf.save(path)


def _snapshot(path):
    with fitz.open(path) as pdf:
        page = pdf[0]
        return {
            'text': ' '.join(page.get_text().split()), 'rotation': page.rotation,
            'notes': [(a.type[1], a.info['content'], tuple(a.rect), a.vertices) for a in page.annots() or ()],
            'links': [(a.get('uri'), tuple(a['from'])) for a in page.get_links()],
            'widgets': [(w.field_name, w.field_value, w.script, tuple(w.rect)) for w in page.widgets() or ()],
            'fields': {k: (str(v.get('/FT')), str(v.get('/V'))) for k, v in (PdfReader(path).get_fields() or {}).items()},
        }


def _equal(actual, expected):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            _equal(actual[key], expected[key])
    elif isinstance(expected, (list, tuple)):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected, strict=True):
            _equal(a, b)
    elif type(expected) in (int, float):
        assert actual == pytest.approx(expected, abs=.01)
    else:
        assert actual == expected


def _cycle(source, output):
    imported = read_document(source)
    assert imported.success
    transport = output.with_suffix('.json')
    assert write_document(imported.document, transport).success
    report = write_document(read_document(transport).document, output)
    assert report.success, report.issues
    assert not [x for x in report.issues if x.feature.startswith(('pdf.form', 'pdf.annotation', 'pdf.link', 'pdf.highlight'))]


@pytest.mark.parametrize('small', [False, True])
@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_two_cycles_and_native_edit_against_original(tmp_path, small, rotation):
    source = tmp_path / 'own.pdf'
    _source(source, small, rotation)
    original_bytes, expected = source.read_bytes(), _snapshot(source)
    current = source
    for number in range(2):
        output = tmp_path / f'cycle{number}.pdf'
        _cycle(current, output)
        _equal(_snapshot(output), expected)
        current = output
    edited = tmp_path / 'native-edited.pdf'
    with fitz.open(current) as pdf:
        page = pdf[0]
        widget = next(page.widgets())
        widget.field_value = 'Native edit'
        widget.update()
        pdf.save(edited)
    _cycle(edited, tmp_path / 'edited-cycle.pdf')
    _equal(_snapshot(tmp_path / 'edited-cycle.pdf'), _snapshot(edited))
    assert source.read_bytes() == original_bytes


def test_common_edits_and_deletion_never_resurrect_source(tmp_path):
    source = tmp_path / 'own.pdf'
    _source(source, True, 90)
    document = read_document(source).document
    integration = get_integration(document)
    set_integration(document, replace(integration, forms=(replace(integration.forms[0], value='Typed edit', action={}),),
                                      annotations=tuple(replace(a, text='Typed note') if a.kind == 'note' else a
                                                        for a in integration.annotations)))
    output = tmp_path / 'typed.pdf'
    assert write_document(document, output).success
    measured = _snapshot(output)
    assert measured['widgets'][0][1:3] == ('Typed edit', None)
    assert measured['notes'][0][1] == 'Typed note'
    edited = read_document(output).document
    set_integration(edited, replace(get_integration(edited), forms=(), annotations=()))
    assert write_document(edited, tmp_path / 'deleted.pdf').success
    _cycle(tmp_path / 'deleted.pdf', tmp_path / 'deleted-cycle.pdf')
    measured = _snapshot(tmp_path / 'deleted-cycle.pdf')
    assert measured['widgets'] == measured['notes'] == measured['links'] == []
    assert measured['fields'] == {}
    sentinel = tmp_path / 'previous.pdf'
    sentinel.write_bytes(b'own previous artifact')
    report = write_document(document, sentinel, options=ExportOptions(cancelled=lambda: True))
    assert not report.success and sentinel.read_bytes() == b'own previous artifact'
