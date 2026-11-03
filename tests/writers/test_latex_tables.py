"""Native editable tables: independent compilation, cell structure and conservative boundaries."""

import builtins
import shutil
import subprocess
from threading import Event

import opendoc_model as od
import pytest

from opendoc_formats import ExportOptions, write_document
from opendoc_formats.support.latex import PREAMBLE


def own_model():
    cells = [[od.Paragraph([od.TextRun('Own A', style=od.TextStyle(bold=True))]),
              od.Paragraph([od.TextRun('B & 7%')])],
             [od.Paragraph([od.Formula('x^2', od.FormulaFormat.LATEX)]),
              od.Paragraph([od.TextRun('H'), od.TextRun('2', style=od.TextStyle(subscript=True)), od.TextRun('O')])]]
    table = od.Table([od.TableRow([od.TableCell([paragraph]) for paragraph in row]) for row in cells])
    return od.DocumentModel(sections=[od.Section(blocks=[od.Paragraph([od.TextRun('Before')]), table,
                                                       od.Paragraph([od.TextRun('After')])])])


def test_json_cycles_export_editable_cells_math_styles_and_escaped_text_without_office(tmp_path, monkeypatch):
    native_import = builtins.__import__

    def minimal(name, *args, **kwargs):
        if name.split('.')[0] in {'docx', 'lxml', 'PIL', 'fontTools', 'fitz', 'pymupdf'}:
            raise AssertionError('Unexpected engine: '+name)
        return native_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', minimal)
    document = own_model()
    expected = None
    for cycle in (1, 2):
        document = od.document_from_json(od.document_to_json(document))
        before = od.document_to_json(document)
        target = tmp_path/f'cycle-{cycle}.tex'
        result = write_document(document, target)
        assert result.success and result.metrics['latex_route'] == 'native-table-v1', result.issues
        assert not result.lossless and result.metrics['assessment_complete'] is False
        text = target.read_text(encoding='utf-8')
        assert r'\begin{tabular}{|l|l|}' in text
        assert r'\textbf{Own A} & B \& 7\%' in text and r'\(x^2\) &' in text
        assert text.index('Before') < text.index('tabular') < text.index('After')
        assert expected is None or text == expected
        assert od.document_to_json(document) == before
        expected = text


@pytest.mark.parametrize('damage', ['merge', 'table-property', 'row-property', 'cell-property', 'paragraph-property',
                                   'multiple-paragraphs', 'nested-table', 'display-math', 'ragged'])
def test_unsupported_table_structure_is_never_silently_flattened_by_native_route(tmp_path, monkeypatch, damage):
    document = own_model()
    table = document.sections[0].blocks[1]
    cell = table.rows[0].cells[0]
    if damage == 'merge':
        cell.column_span = 2
    elif damage == 'table-property':
        table.properties['alignment'] = 'center'
    elif damage == 'row-property':
        table.rows[0].properties['height'] = 24
    elif damage == 'cell-property':
        cell.properties['vertical_alignment'] = 'center'
    elif damage == 'paragraph-property':
        cell.blocks[0].alignment = 'center'
    elif damage == 'multiple-paragraphs':
        cell.blocks.append(od.Paragraph([od.TextRun('Extra')]))
    elif damage == 'nested-table':
        cell.blocks.append(od.Table([od.TableRow([od.TableCell()])]))
    elif damage == 'display-math':
        table.rows[1].cells[0].blocks[0].content[0].display = True
    else:
        table.rows[0].cells.pop()
    monkeypatch.setattr('opendoc_formats.support.backends.missing_backends', lambda requirements: ['docx'])
    target = tmp_path/'previous.tex'
    target.write_bytes(b'previous output')
    before = od.document_to_json(document)
    result = write_document(document, target)
    assert not result.success and result.metrics.get('latex_route') != 'native-table-v1'
    assert target.read_bytes() == b'previous output' and od.document_to_json(document) == before


def test_empty_cells_keep_rectangular_shape(tmp_path):
    document = od.DocumentModel(sections=[od.Section(blocks=[od.Table([od.TableRow([od.TableCell(), od.TableCell()])])])])
    target = tmp_path/'empty.tex'
    result = write_document(document, target)
    assert result.success and result.metrics['latex_route'] == 'native-table-v1'
    assert ' &  '+r'\\' in target.read_text(encoding='utf-8')


def test_table_boundary_closes_and_resumes_numbered_list_without_losing_counter(tmp_path):
    document = own_model()
    first, _, last = document.sections[0].blocks
    od.set_anchor(first, od.Anchor('own-first'))
    od.set_anchor(last, od.Anchor('own-last'))
    od.set_list_item(first, od.ListItem('own-list', start=3))
    od.set_list_item(last, od.ListItem('own-list', start=3))
    target = tmp_path/'list-table.tex'
    result = write_document(document, target)
    assert result.success and result.metrics['latex_route'] == 'native-table-v1'
    text = target.read_text(encoding='utf-8')
    assert text.count(r'\begin{enumerate}') == text.count(r'\end{enumerate}') == 2
    assert text.index(r'\end{enumerate}') < text.index(r'\begin{tabular}')
    assert text.index(r'\end{tabular}') < text.rindex(r'\begin{enumerate}')
    assert r'\setcounter{enumi}{2}' in text and r'\setcounter{enumi}{3}' in text


def test_mid_cell_cancellation_and_node_budget_preserve_previous_output(tmp_path, monkeypatch):
    from opendoc_formats.writers import latex_tables

    document = own_model()
    before = od.document_to_json(document)
    target = tmp_path/'previous.tex'
    target.write_bytes(b'previous output')
    stop = Event()
    native = latex_tables.checkpoint
    count = 0

    def checkpoint():
        nonlocal count
        count += 1
        if count == 3:
            stop.set()
        native()

    monkeypatch.setattr(latex_tables, 'checkpoint', checkpoint)
    result = write_document(document, target, options=ExportOptions(cancelled=stop.is_set))
    assert not result.success and count == 3
    result = write_document(document, target, options=ExportOptions(document_limits=od.DocumentLimits(max_nodes=2)))
    assert not result.success
    assert target.read_bytes() == b'previous output' and od.document_to_json(document) == before


def test_independent_tabular_original_and_two_json_exports_compile_to_identical_full_pages(tmp_path):
    engine = shutil.which('pdflatex')
    if engine is None:
        pytest.skip('Independent TeX engine is optional')
    pdf = pytest.importorskip('pymupdf')
    original = tmp_path/'original.tex'
    original.write_text(PREAMBLE+r'''\begin{document}
Before

\begin{tabular}{|l|l|}
\hline
\textbf{Own A} & B \& 7\% \\
\hline
$x^2$ & H\textsubscript{2}O \\
\hline
\end{tabular}

After
\end{document}
''', encoding='utf-8')
    source_bytes = original.read_bytes()
    reference = None
    document = own_model()
    for index in range(3):
        target = original if index == 0 else tmp_path/f'cycle-{index}.tex'
        if index:
            document = od.document_from_json(od.document_to_json(document))
            result = write_document(document, target)
            assert result.success and result.metrics['latex_route'] == 'native-table-v1'
        process = subprocess.run([engine, '-no-shell-escape', '-halt-on-error', '-interaction=nonstopmode',
                                  '-output-directory='+str(tmp_path), str(target)], cwd=tmp_path,
                                 capture_output=True, timeout=60)
        assert process.returncode == 0, process.stdout.decode(errors='replace')[-2000:]
        with pdf.open(target.with_suffix('.pdf')) as native:
            assert len(native) == 1 and not native[0].get_images()
            assert 'Own A' in native[0].get_text() and 'After' in native[0].get_text()
            pix = native[0].get_pixmap(matrix=pdf.Matrix(1.5, 1.5), alpha=False)
            image = (pix.width, pix.height, pix.samples)
        assert reference is None or image == reference
        reference = image
    assert original.read_bytes() == source_bytes
