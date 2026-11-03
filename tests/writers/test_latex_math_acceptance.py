"""Independent compilation of own formula originals and two JSON/TeX cycles."""

import shutil
import subprocess

import pytest
from opendoc_model import document_from_json, document_to_json

from opendoc_formats import read_document, write_document
from opendoc_formats.support.latex import PREAMBLE


@pytest.mark.parametrize('body', [
    r'Before $x^2$ and \(\frac{a}{b}\).\[\sqrt[3]{x}+\sum_{i=1}^{n}i\]After.',
    r'\[\begin{pmatrix}1&2\\3&4\end{pmatrix}\quad'
    r'\begin{cases}x^2&x>0\\-x&x\leq0\end{cases}\]'
    r'\[\begin{aligned}a&=b+c\\d&=\frac{1}{2}\end{aligned}\]',
    r'\begin{enumerate}\item Inline $\alpha+\beta$.\par'
    r'\[\int_{0}^{1}x^2\,dx=\frac{1}{3}\]\item'
    r'\begin{itemize}\item $$\left(\frac{x}{y}\right)^2$$\end{itemize}\end{enumerate}',
    r'\[\frac{a}{b}\]',
])
def test_native_formula_compilation_preserves_pages_without_images(tmp_path, body):
    engine = shutil.which('pdflatex')
    if engine is None:
        pytest.skip('Independent TeX engine is optional')
    pdf = pytest.importorskip('pymupdf')
    source = tmp_path / 'original.tex'
    source.write_bytes((PREAMBLE+'\\begin{document}\n'+body+'\n\\end{document}\n').encode())
    model = read_document(source).document
    if body == r'\[\frac{a}{b}\]':
        model.sections[0].blocks = [model.sections[0].blocks[0].content[0]]
    reference = None
    for index in range(3):
        if index:
            source = tmp_path / f'cycle-{index}.tex'
            model = document_from_json(document_to_json(model))
            result = write_document(model, source)
            assert result.success, result.issues
            model = read_document(source).document
        process = subprocess.run([engine, '-no-shell-escape', '-halt-on-error', '-interaction=nonstopmode',
                                  '-output-directory='+str(tmp_path), str(source)], cwd=tmp_path,
                                 capture_output=True, timeout=60)
        assert process.returncode == 0, process.stdout.decode(errors='replace')[-3000:]
        with pdf.open(source.with_suffix('.pdf')) as document:
            assert all(not page.get_images() for page in document)
            pixels = [(page.rect, page.get_pixmap(matrix=pdf.Matrix(1.5, 1.5), alpha=False).samples) for page in document]
        assert reference is None or pixels == reference
        reference = pixels
