"""Heading formulas survive actual moving arguments, auxiliary files and two cycles."""

import shutil
import subprocess

import pytest
from opendoc_model import document_from_json, document_to_json

from opendoc_formats import read_document, write_document
from opendoc_formats.support.latex import PREAMBLE


@pytest.mark.parametrize('body', [
    ''.join('\\'+name+r'{Own $x_i^2$ and \(\frac{\alpha}{2}\)}Body.' for name in
            ('section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph')),
    ''.join('\\'+name+r'*{Own \(\sqrt{x+1}\) and $\mathbb{R}$}Body.' for name in
            ('section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph')),
    r'\section{\(\begin{pmatrix}1&2\\3&4\end{pmatrix}\)}Body.'
    r'\subsection{Own $\left(\frac{x}{y}\right)^2$}Body.',
])
def test_heading_math_matches_original_with_toc_and_three_compiler_passes(tmp_path, body):
    engine = shutil.which('pdflatex')
    if engine is None:
        pytest.skip('Independent TeX engine is optional')
    pdf = pytest.importorskip('pymupdf')
    source = tmp_path / 'original.tex'
    source.write_bytes((PREAMBLE+'\\begin{document}\n'+body+'\n\\end{document}\n').encode())
    model = read_document(source).document
    reference = None
    for index in range(3):
        if index:
            source = tmp_path / f'cycle-{index}.tex'
            result = write_document(document_from_json(document_to_json(model)), source)
            assert result.success, result.issues
            model = read_document(source).document
        # TOC is an independent compiler harness, not a claimed source-parser feature.
        compiled = tmp_path / f'compiled-{index}.tex'
        compiled.write_bytes(source.read_bytes().replace(b'\\begin{document}',
                                                        b'\\begin{document}\\tableofcontents', 1))
        for _ in range(3):
            process = subprocess.run([engine, '-no-shell-escape', '-halt-on-error', '-interaction=nonstopmode',
                                      '-output-directory='+str(tmp_path), str(compiled)], cwd=tmp_path,
                                     capture_output=True, timeout=60)
            assert process.returncode == 0, process.stdout.decode(errors='replace')[-3000:]
        with pdf.open(compiled.with_suffix('.pdf')) as document:
            assert all(not page.get_images() for page in document)
            pixels = [(page.rect, page.get_pixmap(matrix=pdf.Matrix(1.5, 1.5), alpha=False).samples) for page in document]
        assert reference is None or pixels == reference
        reference = pixels
