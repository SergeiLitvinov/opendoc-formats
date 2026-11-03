"""Literal class options survive JSON; edits are authoritative and unsafe carriers fail atomically."""

import pytest
from opendoc_model import DocumentModel, Paragraph, Section, TextRun, document_from_json, document_to_json, get_integration

from opendoc_formats import read_document, write_document
from opendoc_formats.support.latex import PREAMBLE
from opendoc_formats.tex_headings import CLASS_OPTIONS_KEY, known_preamble_length


@pytest.mark.parametrize('cls', ['article', 'book', 'report'])
@pytest.mark.parametrize('options', [None, '', '10pt,letterpaper,twocolumn', ' 11pt , a4paper , landscape '])
def test_literal_options_and_absence_survive_two_cycles(tmp_path, cls, options):
    argument = '' if options is None else '[' + options + ']'
    header = '\\documentclass' + argument + '{' + cls + '}\n'
    original = (header + PREAMBLE.split('\n', 1)[1] + '\\begin{document}\nOwn text.\n\\end{document}\n').encode()
    path = tmp_path / 'original.tex'
    path.write_bytes(original)
    model = read_document(path).document
    for index in range(2):
        model = document_from_json(document_to_json(model))
        assert model.metadata[CLASS_OPTIONS_KEY] == {'version': 1, 'source': options}
        before = document_to_json(model)
        target = tmp_path / f'cycle-{index}.tex'
        report = write_document(model, target)
        assert report.success and report.metrics['latex_route'] == 'native-text-v1', report.issues
        assert target.read_text(encoding='utf-8').startswith(header)
        assert document_to_json(model) == before
        model = read_document(target).document
    assert path.read_bytes() == original


@pytest.mark.parametrize('replacement', ['11pt,a4paper,onecolumn', None, 'remove'])
@pytest.mark.parametrize('crlf', [False, True])
def test_current_metadata_overrides_original_even_with_bom_crlf(tmp_path, replacement, crlf):
    source = PREAMBLE.replace('12pt,a4paper', '10pt,letterpaper,twocolumn', 1)
    source += '\\begin{document}\nOwn text.\n\\end{document}\n'
    if crlf:
        source = source.replace('\n', '\r\n')
    raw = b'\xef\xbb\xbf' + source.encode()
    path = tmp_path / 'source.tex'
    path.write_bytes(raw)
    model = read_document(path).document
    if replacement == 'remove':
        del model.metadata[CLASS_OPTIONS_KEY]
        expected = '[12pt,a4paper]'
    else:
        model.metadata[CLASS_OPTIONS_KEY] = {'version': 1, 'source': replacement}
        expected = '' if replacement is None else '[' + replacement + ']'
    target = tmp_path / 'edited.tex'
    report = write_document(document_from_json(document_to_json(model)), target)
    assert report.success, report.issues
    assert target.read_text(encoding='utf-8').startswith('\\documentclass' + expected + '{article}')
    assert path.read_bytes() == raw
    assert known_preamble_length(raw) == len(source.split('\\begin{document}', 1)[0])


@pytest.mark.parametrize('carrier', [
    {'version': 2, 'source': '10pt'}, {'version': True, 'source': '10pt'},
    {'version': 1, 'source': '10pt', 'extra': True}, {'version': 1, 'source': ['10pt']},
    {'version': 1, 'source': 'custom'}, {'version': 1, 'source': r'10pt]\input{evil}'},
    {'version': 1, 'source': '10pt%comment'}, {'version': 1, 'source': '10pt,'},
    {'version': 1, 'source': ' ' * 2049}, None,
])
def test_invalid_or_future_carrier_refuses_before_replacing_output(tmp_path, carrier):
    model = DocumentModel([Section([Paragraph([TextRun('Own text.')])])], metadata={CLASS_OPTIONS_KEY: carrier})
    target = tmp_path / 'existing.tex'
    target.write_bytes(b'existing')
    report = write_document(model, target)
    assert not report.success
    assert any(issue.feature == 'latex.preamble-profile' for issue in report.issues)
    assert target.read_bytes() == b'existing'


def test_legacy_model_retains_generated_default(tmp_path):
    model = DocumentModel([Section([Paragraph([TextRun('Own text.')])])])
    target = tmp_path / 'legacy.tex'
    assert write_document(model, target).success
    assert target.read_text(encoding='utf-8').startswith(PREAMBLE)


def test_source_unsupported_options_stay_inert_and_refuse_export(tmp_path):
    path = tmp_path / 'original.tex'
    original = b'\\documentclass[10pt,custom]{article}\\begin{document}Own text.\\end{document}'
    path.write_bytes(original)
    result = read_document(path)
    assert result.document.metadata[CLASS_OPTIONS_KEY] == {'version': 1, 'source': '10pt,custom'}
    records = [record for record in get_integration(result.document).preservation
               if record.issue.reason == 'documentclass-options']
    assert len(records) == 1
    span = records[0].extra['source_span']
    assert original.decode()[span['start']:span['end']] == '[10pt,custom]'
    assert records[0].extra['resource_id'] == 'latex-original-source'
    target = tmp_path / 'out.tex'
    report = write_document(result.document, target)
    assert not report.success and any(issue.feature == 'latex.preamble-profile' for issue in report.issues)
    assert not target.exists() and path.read_bytes() == original


def test_custom_options_cannot_silently_enter_docx_bridge(tmp_path):
    run = TextRun('Own text.')
    run.style.font_family = 'Unsupported native font'
    model = DocumentModel([Section([Paragraph([run])])],
                          metadata={CLASS_OPTIONS_KEY: {'version': 1, 'source': '11pt,letterpaper'}})
    target = tmp_path / 'existing.tex'
    target.write_bytes(b'existing')
    report = write_document(model, target)
    assert not report.success and any(issue.feature == 'latex.preamble-profile' for issue in report.issues)
    assert target.read_bytes() == b'existing'


def test_generated_prefix_recognition_never_ignores_custom_packages():
    assert known_preamble_length(PREAMBLE.encode()) == len(PREAMBLE)
    assert known_preamble_length(PREAMBLE.replace('amsmath', 'ownpackage').encode()) == 0
    assert known_preamble_length(PREAMBLE.replace('12pt,a4paper', '12pt,unknown').encode()) == 0
    assert known_preamble_length(PREAMBLE[:-1].encode()) == 0
