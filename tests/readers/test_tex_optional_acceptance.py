"""An independent TeX engine accepts the optional-argument cases retained as opaque."""

import shutil
import subprocess

import pytest
from opendoc_model import get_integration

from opendoc_formats.readers.tex_model import read_tex_model
from opendoc_formats.support.latex import PREAMBLE


def test_valid_rich_short_titles_compile_and_keep_visible_heading_body(tmp_path):
    engine = shutil.which('pdflatex')
    if engine is None:
        pytest.skip('Independent TeX compiler is optional')
    pdf = pytest.importorskip('pymupdf')
    arguments = [r'[Short {]} and \textbf{bold} $x^2$]', r'[[Literal]', r'[]',
                 r'[{\textbf{label [and]}}]', '[Short % comment with ]\n title]']
    source = tmp_path / 'own.tex'
    original = (PREAMBLE + '\\begin{document}\n\\tableofcontents\n' + ''.join(
        '\\section' + argument + '{Visible ' + letter + '}Body ' + letter + '.\n'
        for argument, letter in zip(arguments, 'ABCDE', strict=True)) + '\\end{document}\n').encode()
    source.write_bytes(original)
    document = read_tex_model(source)
    assert [block.plain_text for block in document.sections[0].blocks] == [
        text for letter in 'ABCDE' for text in ('Visible ' + letter, 'Body ' + letter + '.')]
    records = [record for record in get_integration(document).preservation if record.issue.reason == 'heading-short-title']
    assert [original.decode()[record.extra['source_span']['start']:record.extra['source_span']['end']]
            for record in records] == arguments
    for _ in range(3):
        process = subprocess.run([engine, '-no-shell-escape', '-halt-on-error', '-interaction=nonstopmode',
                                  '-output-directory=' + str(tmp_path), str(source)], cwd=tmp_path,
                                 capture_output=True, timeout=60)
        assert process.returncode == 0, process.stdout.decode(errors='replace')[-2500:]
    with pdf.open(source.with_suffix('.pdf')) as native:
        text = ''.join(page.get_text() for page in native)
        assert '[Literal' in text and all('Visible ' + letter in text for letter in 'ABCDE')
    assert source.read_bytes() == original and document.resources['latex-original-source'].data == original
