"""Independent tabular sources: semantic cells, inert unsupported syntax and native cycles."""

import builtins
import shutil
import subprocess
from threading import Event

import opendoc_model as od
import pytest

from opendoc_formats import ImportOptions, read_document, write_document
from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError
from opendoc_formats.support.latex import PREAMBLE
from opendoc_formats.tex_tables import KEY

CASES = [
    r'\begin{tabular}{|l|r|}\hline A \& B & \textbf{7\%}\\\hline'
    r'\(x^2\) & H\textsubscript{2}O\\\hline\end{tabular}',
    r'\begin{tabular}{lc}A & B\\C & D\end{tabular}',
    r'\begin{tabular}{|| c | r ||}\hline\hline A & B\\ C & D\\\hline\end{tabular}',
    r'\begin{tabular}{|l|l|}\hline & \\\hline \textit{Кириллица} & '
    r'\(\begin{pmatrix}1&2\\3&4\end{pmatrix}\)\\\hline\end{tabular}',
]


def source(tmp_path, body, name='original.tex'):
    path = tmp_path/name
    path.write_text(PREAMBLE+'\\begin{document}\nBefore\n\n'+body+'\n\nAfter\n\\end{document}\n', encoding='utf-8')
    return path


def shape(document):
    def cell(block):
        return [(('math', run.value, run.display, run.fallback_text) if isinstance(run, od.Formula) else
                 ('text', run.text, run.style.bold, run.style.italic, run.style.superscript, run.style.subscript))
                for run in block.content]

    table = next(block for block in document.sections[0].blocks if isinstance(block, od.Table))
    return table.properties[KEY], [[cell(part.blocks[0]) for part in row.cells] for row in table.rows]


@pytest.mark.parametrize('body', CASES)
def test_independent_tabular_structure_source_spans_and_two_native_tex_cycles(tmp_path, body, monkeypatch):
    native_import = builtins.__import__

    def minimal(name, *args, **kwargs):
        if name.split('.')[0] in {'docx', 'lxml', 'PIL', 'fontTools', 'pymupdf', 'fitz'}:
            raise AssertionError('Unexpected engine: '+name)
        return native_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', minimal)
    path = source(tmp_path, body)
    original = path.read_bytes()
    result = read_document(path)
    assert result.success, result.issues
    document = result.document
    assert [type(block) for block in document.sections[0].blocks] == [od.Paragraph, od.Table, od.Paragraph]
    table = document.sections[0].blocks[1]
    span = table.properties['source_span']
    assert path.read_bytes().decode('utf-8')[span['start']:span['end']] == body
    assert table.provenance.source_path == str(path)
    expected = shape(document)
    for cycle in (1, 2):
        document = od.document_from_json(od.document_to_json(document))
        before = od.document_to_json(document)
        target = tmp_path/f'cycle-{cycle}.tex'
        report = write_document(document, target)
        assert report.success and report.metrics['latex_route'] == 'native-table-v1', report.issues
        assert od.document_to_json(document) == before
        imported = read_document(target)
        assert imported.success, imported.issues
        document = imported.document
        assert shape(document) == expected
        assert [block.plain_text for block in document.sections[0].blocks
                if isinstance(block, od.Paragraph)] == ['Before', 'After']
    assert path.read_bytes() == original


@pytest.mark.parametrize('body', [
    r'\begin{tabular}{p{\linewidth}r}A&B\\\end{tabular}',
    r'\begin{tabular}{lr}\multicolumn{2}{p{0pt}}{A}\\\end{tabular}',
    r'\begin{tabular}{l}A\\[2pt]B\\\end{tabular}',
    r'\begin{tabular}{l}\begin{tabular}{l}A\\\end{tabular}\\\end{tabular}',
    r'\begin{tabular}{l}A\par B\\\end{tabular}',
    r'\begin{tabular}{lr}A\\\end{tabular}',
    r'\begin{tabular}{l}\ref{unknown}\\\end{tabular}',
])
def test_unsupported_sources_retain_original_and_located_opaque_diagnostics(tmp_path, body):
    path = source(tmp_path, body)
    data = path.read_bytes()
    result = read_document(path)
    assert result.success, result.issues
    assert not any(isinstance(block, od.Table) for block in result.document.sections[0].blocks)
    assert result.document.resources['latex-original-source'].data == data
    records = od.get_integration(result.document).preservation
    assert any(record.issue.reason == 'unsupported-environment' and record.issue.location.startswith(str(path)+':')
               for record in records)
    assert not result.assessment_complete and path.read_bytes() == data


@pytest.mark.parametrize('body', [r'\begin{tabular}{l}A', r'\begin{tabular}{l}{A\\\end{tabular}',
                                  r'\begin{tabular}{l}$x\\\end{tabular}'])
def test_unclosed_table_groups_and_math_are_explicit_failures(tmp_path, body):
    path = source(tmp_path, body)
    with pytest.raises(InvalidDocumentError):
        read_document(path)


def test_cell_edit_is_authoritative_and_layout_changes_require_consistent_profile(tmp_path):
    path = source(tmp_path, CASES[0])
    document = read_document(path).document
    table = document.sections[0].blocks[1]
    table.rows[0].cells[0].blocks[0].content = [od.TextRun('Edited & cell')]
    target = tmp_path/'edit.tex'
    assert write_document(document, target).success
    assert read_document(target).document.sections[0].blocks[1].rows[0].cells[0].blocks[0].plain_text == 'Edited & cell'
    table.rows.pop()
    target.write_bytes(b'previous')
    result = write_document(document, target)
    assert not result.success and any(issue.feature == 'latex.table-profile' for issue in result.issues)
    assert target.read_bytes() == b'previous'


def test_explicit_invalid_layout_is_not_replaced_with_default_or_office_bridge(tmp_path):
    document = read_document(source(tmp_path, CASES[0])).document
    target = tmp_path/'previous.tex'
    target.write_bytes(b'previous')
    document.sections[0].blocks[1].properties[KEY] = None
    result = write_document(document, target)
    assert not result.success and any(issue.feature == 'latex.table-profile' for issue in result.issues)
    assert target.read_bytes() == b'previous'


def test_table_cell_work_limit_and_late_cancel_do_not_change_source(tmp_path, monkeypatch):
    from opendoc_formats import tex_tables

    path = source(tmp_path, CASES[0])
    data = path.read_bytes()
    with pytest.raises((od.ArtifactLimitError, ResourceLimitError)):
        read_document(path, options=ImportOptions(document_limits=od.DocumentLimits(max_nodes=2)))
    stop = Event()
    native = tex_tables.checkpoint
    calls = 0

    def checkpoint():
        nonlocal calls
        calls += 1
        if calls == 12:
            stop.set()
        native()

    monkeypatch.setattr(tex_tables, 'checkpoint', checkpoint)
    result = read_document(path, options=ImportOptions(cancelled=stop.is_set))
    assert not result.success and path.read_bytes() == data and calls == 12


@pytest.mark.parametrize('value', [False, {}, {'version': True}, {'version': 2}])
def test_unknown_table_carrier_refuses_atomically(tmp_path, value):
    document = read_document(source(tmp_path, CASES[0])).document
    document.sections[0].blocks[1].properties[KEY] = value
    before = od.document_to_json(document)
    target = tmp_path/'previous.tex'
    target.write_bytes(b'previous')
    result = write_document(document, target)
    assert not result.success and target.read_bytes() == b'previous'
    assert od.document_to_json(document) == before


@pytest.mark.parametrize('change', [
    {'columns': r'l}\input{outside}'}, {'rules': [-1, 1, 1]}, {'rules': [1, 10**9, 1]},
    {'rules': [True, 1, 1]}, {'trailing_break': False}, {'unknown': 'future layout'},
])
def test_forged_layout_does_not_emit_commands_allocate_rules_or_use_bridge(tmp_path, monkeypatch, change):
    document = read_document(source(tmp_path, CASES[0])).document
    document.sections[0].blocks[1].properties[KEY].update(change)
    before = od.document_to_json(document)
    target = tmp_path/'previous.tex'
    target.write_bytes(b'previous')

    def forbidden(requirements):
        raise AssertionError('Invalid native layout attempted a bridge')

    monkeypatch.setattr('opendoc_formats.support.backends.missing_backends', forbidden)
    result = write_document(document, target)
    assert not result.success and any(issue.feature == 'latex.table-profile' for issue in result.issues)
    assert target.read_bytes() == b'previous' and od.document_to_json(document) == before


def test_source_table_brace_depth_is_a_resource_limit(tmp_path):
    path = source(tmp_path, r'\begin{tabular}{l}'+'{'*65+'A'+'}'*65+r'\\\end{tabular}')
    with pytest.raises(ResourceLimitError, match='depth'):
        read_document(path)


@pytest.mark.parametrize('body', CASES)
def test_independent_tabular_and_two_source_model_json_tex_cycles_compile_identically(tmp_path, body):
    engine = shutil.which('pdflatex')
    if engine is None:
        pytest.skip('Independent TeX engine is optional')
    pdf = pytest.importorskip('pymupdf')
    original = source(tmp_path, body)
    source_bytes = original.read_bytes()
    document = read_document(original).document
    reference = None
    for cycle in range(3):
        target = original if cycle == 0 else tmp_path/f'cycle-{cycle}.tex'
        if cycle:
            document = od.document_from_json(od.document_to_json(document))
            report = write_document(document, target)
            assert report.success and report.metrics['latex_route'] == 'native-table-v1', report.issues
            imported = read_document(target)
            assert imported.success, imported.issues
            document = imported.document
        process = subprocess.run([engine, '-no-shell-escape', '-halt-on-error', '-interaction=nonstopmode',
                                  '-output-directory='+str(tmp_path), str(target)], cwd=tmp_path,
                                 capture_output=True, timeout=60)
        assert process.returncode == 0, process.stdout.decode(errors='replace')[-2000:]
        with pdf.open(target.with_suffix('.pdf')) as native:
            assert len(native) == 1 and not native[0].get_images()
            assert 'Before' in native[0].get_text() and 'After' in native[0].get_text()
            pix = native[0].get_pixmap(matrix=pdf.Matrix(1.5, 1.5), alpha=False)
            actual = (pix.width, pix.height, pix.samples)
        assert reference is None or actual == reference
        reference = actual
    assert original.read_bytes() == source_bytes
