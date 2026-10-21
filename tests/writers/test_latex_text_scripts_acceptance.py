"""Independent TeX rendering accepts script roles, lists and moving arguments."""

import shutil
import subprocess

import pytest
from opendoc_model import document_from_json, document_to_json

from opendoc_formats import read_document, write_document
from opendoc_formats.support.latex import PREAMBLE


@pytest.mark.parametrize('body', [
    r'Own H\textsubscript{2}O and 1\textsuperscript{st}. '
    r'\textbf{Bold\textsuperscript{B}} \textsubscript{\textit{i}}.',
    r'\section{Own\textsuperscript{2}}Before.\begin{enumerate}\item H\textsubscript{2}O'
    r'\par After\textsuperscript{1}.\item Last.\end{enumerate}Outside.',
    r'\textsuperscript{\bfseries B\normalfont N} and \textsubscript{\itshape i\normalfont n}.',
    r'A\textsuperscript{B}\textsuperscript{C}D \textsubscript{i}\textsubscript{j}.',
    r'\textsuperscript{\textit{f}n} and \textsuperscript{\itshape f\normalfont n}.',
])
def test_scripts_match_original_pixels_after_two_cycles_with_toc(tmp_path, body):
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
            report = write_document(document_from_json(document_to_json(model)), source)
            assert report.success, report.issues
            model = read_document(source).document
        compiled = tmp_path / f'compiled-{index}.tex'
        compiled.write_bytes(source.read_bytes().replace(b'\\begin{document}', b'\\begin{document}\\tableofcontents', 1))
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
