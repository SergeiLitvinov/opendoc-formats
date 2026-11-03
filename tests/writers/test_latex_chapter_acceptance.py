"""Independent book/report originals and an authored edit reference, two native cycles."""

import hashlib
import json
import shutil
import subprocess

import pytest
from opendoc_model import Heading, document_from_json, document_to_json, set_heading

from opendoc_formats import read_document, write_document
from opendoc_formats.support.latex import PREAMBLE

COMMANDS = ('chapter', 'section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph')


def rendered(source, root, engine, poppler):
    pdf = pytest.importorskip('pymupdf')
    compiled = root / (source.stem + '-compiled.tex')
    compiled.write_bytes(source.read_bytes().replace(b'\\begin{document}', b'\\begin{document}\\tableofcontents', 1))
    for _ in range(3):
        process = subprocess.run([engine, '-no-shell-escape', '-halt-on-error', '-interaction=nonstopmode',
                                  '-output-directory=' + str(root), str(compiled)], cwd=root,
                                 capture_output=True, timeout=60)
        assert process.returncode == 0, process.stdout.decode(errors='replace')[-2500:]
    output = compiled.with_suffix('.pdf')
    with pdf.open(output) as document:
        assert all(not page.get_images() for page in document)
        mupdf = [(page.rect.width, page.rect.height, page.get_pixmap(matrix=pdf.Matrix(1.5, 1.5), alpha=False).samples)
                 for page in document]
    prefix = root / (source.stem + '-poppler')
    process = subprocess.run([poppler, '-r', '108', '-png', str(output), str(prefix)],
                             capture_output=True, timeout=60)
    assert process.returncode == 0, process.stderr.decode(errors='replace')
    paths = sorted(root.glob(prefix.name + '-*.png'))
    assert len(paths) == len(mupdf)
    decoded = [pdf.Pixmap(str(path)) for path in paths]
    return mupdf, [(image.width, image.height, image.samples) for image in decoded]


@pytest.mark.parametrize('document_class', ['book', 'report'])
@pytest.mark.parametrize('case', ['numbered', 'starred', 'edit'])
def test_chapter_scope_matches_original_in_both_renderers(tmp_path, document_class, case):
    engine, poppler = shutil.which('pdflatex'), shutil.which('pdftoppm')
    if engine is None or poppler is None:
        pytest.skip('Independent TeX compiler and Poppler are optional')
    star = '*' if case == 'starred' else ''
    body = ''.join('\\' + command + star + '{Own H' + str(level) + r' $x^2$}Body.'
                   for level, command in enumerate(COMMANDS, 1))
    body += r'\chapter*{Own final chapter}End.'
    # Original body and the edited reference are not emitted by Formats.
    source = tmp_path / 'original.tex'
    original = (PREAMBLE.replace('{article}', '{' + document_class + '}', 1)
                + '\\begin{document}\n' + body + '\n\\end{document}\n').encode()
    source.write_bytes(original)
    model = read_document(source).document
    reference = source
    if case == 'edit':
        set_heading(model.sections[0].blocks[0], Heading(3))
        reference = tmp_path / 'authored-edit.tex'
        reference.write_bytes(original.replace(b'\\chapter{Own H1', b'\\subsection{Own H1', 1))
    expected = rendered(reference, tmp_path, engine, poppler)
    evidence = {'class': document_class, 'case': case, 'dpi': 108, 'pixel_tolerance': 0, 'masks': None,
                'source_sha256': hashlib.sha256(original).hexdigest(),
                'reference_sha256': hashlib.sha256(reference.read_bytes()).hexdigest(), 'cycles': []}
    for index in range(2):
        path = tmp_path / f'cycle-{index}.tex'
        before = document_to_json(model)
        report = write_document(document_from_json(before), path)
        assert report.success and report.metrics['latex_route'] == 'native-text-v1', report.issues
        assert document_to_json(model) == before
        observed = rendered(path, tmp_path, engine, poppler)
        assert observed == expected
        evidence['cycles'].append({'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                    'mupdf_exact_pages': len(observed[0]), 'poppler_exact_pages': len(observed[1]),
                                    'image_objects': 0})
        model = read_document(path).document
    assert source.read_bytes() == original
    evidence['source_unchanged'] = True
    (tmp_path / 'chapter-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
