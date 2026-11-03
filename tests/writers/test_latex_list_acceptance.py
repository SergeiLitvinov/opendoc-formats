"""Optional independent TeX compilation, not a runtime engine dependency."""

import shutil
import subprocess

import pytest

from opendoc_formats import read_document, write_document
from opendoc_formats.support.latex import PREAMBLE


@pytest.mark.parametrize('body', [
    r'Before.\begin{enumerate}\item First.\par Continuation.\item'
    r'\begin{itemize}\item Child.\end{itemize}\par After child.\item Last.\end{enumerate}Outside.',
    r'\begin{enumerate}\setcounter{enumi}{2}\item First\par Continuation'
    r'\setcounter{enumi}{7}\item Second\item\end{enumerate}',
    r'\begin{itemize}\item First\begin{enumerate}\item Nested\begin{enumerate}\item Deep'
    r'\end{enumerate}\item Other\end{enumerate}\item Final\end{itemize}',
])
def test_independent_compilation_has_identical_pages_and_no_image_projection(tmp_path, body):
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
            result = write_document(model, source)
            assert result.success, result.issues
            model = read_document(source).document
        process = subprocess.run([engine, '-no-shell-escape', '-halt-on-error', '-interaction=nonstopmode',
                                  '-output-directory='+str(tmp_path), str(source)], cwd=tmp_path,
                                 capture_output=True, timeout=60)
        assert process.returncode == 0, process.stdout.decode(errors='replace')[-3000:]
        with pdf.open(source.with_suffix('.pdf')) as document:
            assert all(not page.get_images() for page in document)
            pixels = [page.get_pixmap(matrix=pdf.Matrix(1.5, 1.5), alpha=False).samples for page in document]
        assert reference is None or pixels == reference
        reference = pixels
