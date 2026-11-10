"""Native horizontal merges use the common span; source declarations never restore old values."""

import builtins
import shutil
import subprocess

import opendoc_model as od
import pytest

from opendoc_formats import ExportOptions, read_document, write_document
from opendoc_formats.tex_tables import KEY, MULTICOLUMN_KEY
from tests.readers.test_tex_tables import source

CASES = [
    r'\begin{tabular}{|l|c|r|}\hline\multicolumn{2}{|c|}{\textbf{Merged \& A}} & 7\%\\\hline '
    r'Left & mid & right\\\hline\end{tabular}',
    r'\begin{tabular}{lcr}A & \multicolumn{2}{r}{\(x^2\)}\\B & C & D\end{tabular}',
    r'\begin{tabular}{|l|r|}\hline\multicolumn{1}{||r|}{One} & Two\\'
    r'\multicolumn{2}{|c|}{}\\\hline\end{tabular}',
    r'\begin{tabular}{||l|c|r||}\hline\multicolumn{3}{||c||}{Заголовок}\\\hline\hline '
    r'A & H\textsubscript{2}O & \(\begin{pmatrix}1&2\\3&4\end{pmatrix}\)\\\hline\end{tabular}',
]


def table(document):
    return next(block for block in document.sections[0].blocks if isinstance(block, od.Table))


def shape(document):
    current = table(document)
    return current.properties[KEY], [[(cell.column_span, cell.properties.get(MULTICOLUMN_KEY),
        [(('math', run.value, run.display, run.fallback_text) if isinstance(run, od.Formula) else
          ('text', run.text, run.style.bold, run.style.italic, run.style.superscript, run.style.subscript))
         for run in cell.blocks[0].content]) for cell in row.cells] for row in current.rows]


@pytest.mark.parametrize('body', CASES)
def test_source_model_json_tex_preserves_merges_and_explicit_one_column_override(tmp_path, body, monkeypatch):
    native_import = builtins.__import__

    def minimal(name, *args, **kwargs):
        if name.split('.')[0] in {'docx', 'lxml', 'PIL', 'fontTools', 'pymupdf', 'fitz'}:
            raise AssertionError('Unexpected engine: '+name)
        return native_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', minimal)
    path = source(tmp_path, body)
    original = path.read_bytes()
    imported = read_document(path)
    assert imported.success, imported.issues
    document = imported.document
    expected = shape(document)
    assert any(cell.column_span > 1 for row in table(document).rows for cell in row.cells)
    for cycle in (1, 2):
        document = od.document_from_json(od.document_to_json(document))
        before = od.document_to_json(document)
        target = tmp_path/f'cycle-{cycle}.tex'
        report = write_document(document, target)
        assert report.success and report.metrics['latex_route'] == 'native-table-v1', report.issues
        assert od.document_to_json(document) == before
        document = read_document(target).document
        assert shape(document) == expected
    assert path.read_bytes() == original


def test_cell_span_and_text_edit_win_over_original_multicolumn_count(tmp_path):
    path = source(tmp_path, CASES[2])
    document = read_document(path).document
    current = table(document)
    cell = current.rows[0].cells[0]
    span = cell.properties['source_span']
    assert path.read_bytes().decode('utf-8')[span['start']:span['end']].strip() == r'\multicolumn{1}{||r|}{One}'
    cell.column_span = 2
    cell.blocks[0].content = [od.TextRun('Edited & merged')]
    current.rows[0].cells.pop()
    target = tmp_path/'edited.tex'
    result = write_document(od.document_from_json(od.document_to_json(document)), target)
    assert result.success, result.issues
    assert r'\multicolumn{2}{||r|}{Edited \& merged}' in target.read_text(encoding='utf-8')
    restored = table(read_document(target).document).rows[0].cells
    assert len(restored) == 1 and restored[0].column_span == 2 and restored[0].blocks[0].plain_text == 'Edited & merged'


@pytest.mark.parametrize('ruled', [False, True])
def test_new_common_model_merge_without_source_carrier_does_not_need_office(tmp_path, ruled):
    merged = od.TableCell([od.Paragraph([od.TextRun('Own merged cell')])], column_span=2)
    current = od.Table([od.TableRow([merged]), od.TableRow([od.TableCell(), od.TableCell()])])
    if not ruled:
        current.properties[KEY] = {'version': 1, 'columns': 'lr', 'rules': [0, 0, 0], 'trailing_break': True}
    document = od.DocumentModel(sections=[od.Section(blocks=[current])])
    target = tmp_path/'created.tex'
    result = write_document(document, target)
    assert result.success and result.metrics['latex_route'] == 'native-table-v1'
    override = '|l|' if ruled else 'l'
    assert '\\multicolumn{2}{'+override+'}{Own merged cell}' in target.read_text(encoding='utf-8')
    restored = table(read_document(target).document)
    assert restored.rows[0].cells[0].column_span == 2
    assert len(restored.rows[1].cells) == 2


def test_removing_explicit_one_column_override_does_not_restore_source_layout(tmp_path):
    document = read_document(source(tmp_path, CASES[2])).document
    first = table(document).rows[0].cells[0]
    first.properties.pop(MULTICOLUMN_KEY)
    target = tmp_path/'removed-override.tex'
    result = write_document(od.document_from_json(od.document_to_json(document)), target)
    assert result.success, result.issues
    assert r'\multicolumn{1}' not in target.read_text(encoding='utf-8')
    restored = table(read_document(target).document).rows[0].cells[0]
    assert restored.column_span == 1 and MULTICOLUMN_KEY not in restored.properties


@pytest.mark.parametrize('body', [
    r'\begin{tabular}{lr}\multicolumn{0}{c}{A}\\\end{tabular}',
    r'\begin{tabular}{lr}\multicolumn{3}{c}{A}\\\end{tabular}',
    r'\begin{tabular}{lr}\multicolumn{\count}{c}{A}\\\end{tabular}',
    r'\begin{tabular}{lr}\multicolumn{2}{cc}{A}\\\end{tabular}',
    r'\begin{tabular}{lr}\multicolumn{2}{p{\linewidth}}{A}\\\end{tabular}',
    r'\begin{tabular}{lr}\multicolumn{2}{c}{A} extra\\\end{tabular}',
    r'\begin{tabular}{lr}\multicolumn{2}{c}{A\par B}\\\end{tabular}',
])
def test_unsupported_source_merges_are_opaque_with_original_bytes(tmp_path, body):
    path = source(tmp_path, body)
    data = path.read_bytes()
    result = read_document(path)
    assert result.success, result.issues
    assert not any(isinstance(block, od.Table) for block in result.document.sections[0].blocks)
    assert result.document.resources['latex-original-source'].data == data
    records = od.get_integration(result.document).preservation
    assert any(record.issue.reason == 'unsupported-environment' and record.issue.location.startswith(str(path)+':')
               for record in records)


@pytest.mark.parametrize('value', [None, {}, {'version': True, 'columns': 'c'},
                                  {'version': 2, 'columns': 'c'}, {'version': 1, 'columns': 'cc'},
                                  {'version': 1, 'columns': r'c}\input{outside}'},
                                  {'version': 1, 'columns': 'c', 'column_span': 99}])
def test_invalid_override_never_uses_bridge_or_restores_a_span(tmp_path, monkeypatch, value):
    document = read_document(source(tmp_path, CASES[0])).document
    table(document).rows[0].cells[0].properties[MULTICOLUMN_KEY] = value
    before = od.document_to_json(document)
    target = tmp_path/'previous.tex'
    target.write_bytes(b'previous')

    def forbidden(requirements):
        raise AssertionError('Invalid explicit override attempted a DOCX bridge')

    monkeypatch.setattr('opendoc_formats.support.backends.missing_backends', forbidden)
    result = write_document(document, target)
    assert not result.success and any(issue.feature == 'latex.table-profile' for issue in result.issues)
    assert target.read_bytes() == b'previous' and od.document_to_json(document) == before


@pytest.mark.parametrize('row_index', [0, 1])
def test_logical_width_is_limited_before_constructing_a_billion_column_header(tmp_path, row_index):
    cell = od.TableCell([od.Paragraph([od.TextRun('Own')])], column_span=10**9)
    rows = ([od.TableRow([od.TableCell()])] if row_index else [])+[od.TableRow([cell])]
    document = od.DocumentModel(sections=[od.Section(blocks=[od.Table(rows)])])
    target = tmp_path/'previous.tex'
    target.write_bytes(b'previous')
    result = write_document(document, target, options=ExportOptions(document_limits=od.DocumentLimits(max_nodes=500)))
    assert not result.success and target.read_bytes() == b'previous'
    assert any('width' in issue.message for issue in result.issues)


def test_inconsistent_common_merge_does_not_fall_back_to_a_flattening_bridge(tmp_path, monkeypatch):
    merged = od.TableCell([od.Paragraph([od.TextRun('Merged')])], column_span=2)
    document = od.DocumentModel(sections=[od.Section(blocks=[od.Table([
        od.TableRow([merged]), od.TableRow([od.TableCell()])])])])
    target = tmp_path/'previous.tex'
    target.write_bytes(b'previous')

    def forbidden(requirements):
        raise AssertionError('Inconsistent merge attempted a bridge')

    monkeypatch.setattr('opendoc_formats.support.backends.missing_backends', forbidden)
    result = write_document(document, target)
    assert not result.success and any(issue.feature == 'latex.table-profile' for issue in result.issues)
    assert target.read_bytes() == b'previous'


@pytest.mark.parametrize('body', CASES)
def test_independent_multicolumn_original_and_two_complete_cycles_compile_identically(tmp_path, body):
    engine = shutil.which('pdflatex')
    if engine is None:
        pytest.skip('Independent TeX engine is optional')
    pdf = pytest.importorskip('pymupdf')
    original = source(tmp_path, body)
    original_bytes = original.read_bytes()
    document = read_document(original).document
    reference = None
    for cycle in range(3):
        target = original if cycle == 0 else tmp_path/f'cycle-{cycle}.tex'
        if cycle:
            document = od.document_from_json(od.document_to_json(document))
            result = write_document(document, target)
            assert result.success and result.metrics['latex_route'] == 'native-table-v1', result.issues
            document = read_document(target).document
        process = subprocess.run([engine, '-no-shell-escape', '-halt-on-error', '-interaction=nonstopmode',
                                  '-output-directory='+str(tmp_path), str(target)], cwd=tmp_path,
                                 capture_output=True, timeout=60)
        assert process.returncode == 0, process.stdout.decode(errors='replace')[-2000:]
        with pdf.open(target.with_suffix('.pdf')) as native:
            assert len(native) == 1 and not native[0].get_images()
            assert 'Before' in native[0].get_text() and 'After' in native[0].get_text()
            pix = native[0].get_pixmap(matrix=pdf.Matrix(1.5, 1.5), alpha=False)
            actual = pix.width, pix.height, pix.samples
        assert reference is None or actual == reference
        reference = actual
    assert original.read_bytes() == original_bytes
