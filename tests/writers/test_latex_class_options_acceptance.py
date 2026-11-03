"""Independently authored class headers: exact full-page QA through two JSON/TeX cycles."""

import hashlib
import json
import shutil

import pytest
from opendoc_model import document_from_json, document_to_json

from opendoc_formats import read_document, write_document
from opendoc_formats.support.latex import PREAMBLE
from opendoc_formats.tex_headings import CLASS_OPTIONS_KEY
from tests.writers.test_latex_chapter_acceptance import rendered


@pytest.mark.parametrize('case,cls,argument', [
    ('columns', 'article', '[10pt,letterpaper,twocolumn]'),
    ('book', 'book', '[11pt,a5paper,oneside,openany]'),
    ('empty', 'report', '[]'),
    ('bom-crlf', 'article', '[ 11pt , a4paper , landscape ]'),
    ('edit', 'article', '[10pt,letterpaper]'),
])
def test_literal_class_options_match_independent_reference(tmp_path, case, cls, argument):
    engine, poppler = shutil.which('pdflatex'), shutil.which('pdftoppm')
    if engine is None or poppler is None:
        pytest.skip('Independent TeX compiler and Poppler are optional')
    header = '\\documentclass' + argument + '{' + cls + '}\n'
    body = (r'\section{Own heading $x^2$}Own plain text with \textbf{bold} and \textit{italic}.'
            '\n\n' + 'Own paragraph for source typography and paper dimensions. ' * 16)
    if cls == 'book':
        body = r'\chapter{Own chapter}' + body + r'\chapter{Own second chapter}Final text.'
    text = header + PREAMBLE.split('\n', 1)[1] + '\\begin{document}\n' + body + '\n\\end{document}\n'
    original = text.encode()
    if case == 'bom-crlf':
        original = b'\xef\xbb\xbf' + text.replace('\n', '\r\n').encode()
    source = tmp_path / 'original.tex'
    source.write_bytes(original)
    model = read_document(source).document
    reference = source
    if case == 'edit':
        model.metadata[CLASS_OPTIONS_KEY] = {'version': 1, 'source': '11pt,a4paper'}
        reference = tmp_path / 'authored-edit.tex'
        reference.write_bytes(original.replace(b'[10pt,letterpaper]', b'[11pt,a4paper]', 1))
    expected = rendered(reference, tmp_path, engine, poppler)
    evidence = {'case': case, 'class': cls, 'dpi': 108, 'pixel_tolerance': 0, 'masks': None,
                'source_sha256': hashlib.sha256(original).hexdigest(),
                'reference_sha256': hashlib.sha256(reference.read_bytes()).hexdigest(), 'cycles': []}
    for index in range(2):
        target = tmp_path / f'cycle-{index}.tex'
        before = document_to_json(model)
        report = write_document(document_from_json(before), target)
        assert report.success and report.metrics['latex_route'] == 'native-text-v1', report.issues
        assert document_to_json(model) == before
        observed = rendered(target, tmp_path, engine, poppler)
        assert observed == expected
        evidence['cycles'].append({'source_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                                   'mupdf_exact_pages': len(observed[0]), 'poppler_exact_pages': len(observed[1]),
                                   'image_objects': 0})
        model = read_document(target).document
    assert source.read_bytes() == original
    evidence['source_unchanged'] = True
    (tmp_path / 'class-options-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
