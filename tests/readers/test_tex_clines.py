"""Partial native table rules: ordered declarations, authoritative edits and independent TeX QA."""

import builtins
import hashlib
import json
import shutil
import subprocess

import opendoc_model as od
import pytest

from opendoc_formats import read_document, write_document
from opendoc_formats.errors import ResourceLimitError
from opendoc_formats.tex_tables import KEY
from tests.readers.test_tex_tables import source

CASES = [
    r'\begin{tabular}{|l|c|r|}\hline A&B&C\\\cline{1-2}D&E&F\\\cline{2-3}\hline\end{tabular}',
    r'\begin{tabular}{lcr}\cline{1-1}\cline{2-3}A&B&C\\\cline{1-2}\cline{2-3}D&E&F\end{tabular}',
    r'\begin{tabular}{|l|c|r|}\hline\multicolumn{2}{|c|}{Merged}&C\\\cline{1-2}D&E&F\\\hline\end{tabular}',
    r'\begin{tabular}{lr}\hline\cline{1-1}\hline A&B\\\cline{2-2}\hline\cline{1-1}C&D\\\hline\end{tabular}',
]


@pytest.mark.parametrize('body', CASES)
def test_partial_rules_keep_order_and_logical_ranges_through_two_native_cycles(tmp_path, body, monkeypatch):
    real_import = builtins.__import__

    def minimal(name, *args, **kwargs):
        if name.split('.')[0] in {'docx', 'lxml', 'PIL', 'fontTools', 'pymupdf', 'fitz'}:
            raise AssertionError('Unexpected document engine: '+name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', minimal)
    path = source(tmp_path, body)
    original = path.read_bytes()
    document = read_document(path).document
    table = document.sections[0].blocks[1]
    assert isinstance(table, od.Table)
    layout = table.properties[KEY]
    assert layout['version'] == 2 and any(rule is not None for boundary in layout['rules'] for rule in boundary)
    for cycle in range(2):
        document = od.document_from_json(od.document_to_json(document))
        before = od.document_to_json(document)
        target = tmp_path/f'cycle-{cycle}.tex'
        report = write_document(document, target)
        assert report.success and report.metrics['latex_route'] == 'native-table-v1', report.issues
        assert od.document_to_json(document) == before
        document = read_document(target).document
        assert document.sections[0].blocks[1].properties[KEY] == layout
    assert path.read_bytes() == original


@pytest.mark.parametrize('body', [
    r'\begin{tabular}{lr}\cline{0-1}A&B\\\end{tabular}',
    r'\begin{tabular}{lr}\cline{2-1}A&B\\\end{tabular}',
    r'\begin{tabular}{lr}\cline{1-3}A&B\\\end{tabular}',
    r'\begin{tabular}{lr}\cline{\first-2}A&B\\\end{tabular}',
    r'\begin{tabular}{lr}A\cline{1-2}&B\\\end{tabular}',
])
def test_unsupported_source_rules_keep_original_and_opaque_diagnostics(tmp_path, body):
    path = source(tmp_path, body)
    original = path.read_bytes()
    result = read_document(path)
    assert not any(isinstance(block, od.Table) for block in result.document.sections[0].blocks)
    assert result.document.resources['latex-original-source'].data == original and path.read_bytes() == original
    assert any(record.issue.reason == 'unsupported-environment'
               for record in od.get_integration(result.document).preservation)


@pytest.mark.parametrize('damage', ['version', 'bool-version', 'zero', 'reverse', 'outside', 'bool-index', 'text', 'quota'])
def test_invalid_active_rules_refuse_without_bridge_or_target_replacement(tmp_path, damage, monkeypatch):
    document = read_document(source(tmp_path, CASES[0])).document
    layout = document.sections[0].blocks[1].properties[KEY]
    if damage in ('version', 'bool-version'):
        layout['version'] = 3 if damage == 'version' else True
    elif damage == 'quota':
        layout['rules'][0] = [[1, 1]]*10001
    else:
        layout['rules'][1] = [{'zero': [0, 1], 'reverse': [2, 1], 'outside': [1, 4],
                               'bool-index': [True, 2], 'text': '\\input{never}'}[damage]]
    before = od.document_to_json(document)
    target = tmp_path/'previous.tex'
    target.write_bytes(b'Own previous file')

    def forbidden(requirements):
        raise AssertionError('Invalid native profile attempted a bridge')

    monkeypatch.setattr('opendoc_formats.support.backends.missing_backends', forbidden)
    report = write_document(document, target)
    assert not report.success and any(issue.feature == 'latex.table-profile' for issue in report.issues)
    assert target.read_bytes() == b'Own previous file' and od.document_to_json(document) == before


def test_import_rule_work_budget_is_shared_by_hline_and_cline(tmp_path):
    body = r'\begin{tabular}{l}'+r'\cline{1-1}'*10001+r'A\\\end{tabular}'
    with pytest.raises(ResourceLimitError, match='horizontal rule work limit'):
        read_document(source(tmp_path, body))


def test_explicit_rule_removal_never_restores_old_source(tmp_path):
    document = read_document(source(tmp_path, CASES[0])).document
    layout = document.sections[0].blocks[1].properties[KEY]
    layout['rules'][1].clear()
    layout['rules'][2] = [None]
    target = tmp_path/'removed.tex'
    report = write_document(document, target)
    assert report.success and r'\cline' not in target.read_text(encoding='utf-8')
    current = read_document(target).document.sections[0].blocks[1].properties[KEY]
    assert current['version'] == 1 and current['rules'] == [1, 0, 1]


def test_source_table_outside_native_cell_profile_never_uses_a_flattening_bridge(tmp_path, monkeypatch):
    document = read_document(source(tmp_path, CASES[0])).document
    document.sections[0].blocks[1].rows[0].cells[0].blocks.append(od.Paragraph([od.TextRun('Extra paragraph')]))
    target = tmp_path/'previous.tex'
    target.write_bytes(b'Own previous file')

    def forbidden(requirements):
        raise AssertionError('Unsupported native table attempted a bridge')

    monkeypatch.setattr('opendoc_formats.support.backends.missing_backends', forbidden)
    report = write_document(document, target)
    assert not report.success and any(issue.feature == 'latex.table-profile' for issue in report.issues)
    assert target.read_bytes() == b'Own previous file'


def rendered(path, root):
    pdf = pytest.importorskip('pymupdf')
    process = subprocess.run([shutil.which('pdflatex'), '-no-shell-escape', '-halt-on-error', '-interaction=nonstopmode',
                              '-output-directory='+str(root), str(path)], cwd=root, capture_output=True, timeout=60)
    assert process.returncode == 0, process.stdout.decode(errors='replace')[-2000:]
    with pdf.open(path.with_suffix('.pdf')) as document:
        assert len(document) == 1 and not document[0].get_images()
        image = document[0].get_pixmap(matrix=pdf.Matrix(1.5, 1.5), alpha=False)
        mupdf = image.width, image.height, image.samples
    prefix = root/(path.stem+'-poppler')
    subprocess.run([shutil.which('pdftoppm'), '-singlefile', '-r', '108', '-png', str(path.with_suffix('.pdf')), str(prefix)],
                   check=True, capture_output=True, timeout=60)
    image = pdf.Pixmap(str(prefix.with_suffix('.png')))
    return mupdf, (image.width, image.height, image.samples)


@pytest.mark.parametrize('case', [0, 1, 2, 3, 'edit'])
def test_native_pages_match_independent_original_or_authored_edit_in_both_renderers(tmp_path, case):
    if not shutil.which('pdflatex') or not shutil.which('pdftoppm'):
        pytest.skip('Independent TeX compiler and Poppler are optional')
    body = CASES[0 if case == 'edit' else case]
    path = source(tmp_path, body)
    original = path.read_bytes()
    document = read_document(path).document
    reference = path
    if case == 'edit':
        document.sections[0].blocks[1].properties[KEY]['rules'][1][0] = [2, 3]
        document.sections[0].blocks[1].rows[0].cells[0].blocks[0].content = [od.TextRun('Edited A')]
        reference = tmp_path/'authored-edit.tex'
        reference.write_bytes(original.replace(b'\\cline{1-2}', b'\\cline{2-3}', 1).replace(b'A&B&C', b'Edited A&B&C', 1))
    expected = rendered(reference, tmp_path)
    evidence = {'case': case, 'dpi': 108, 'masks': None, 'pixel_tolerance': 0,
                'source_sha256': hashlib.sha256(original).hexdigest(),
                'reference_sha256': hashlib.sha256(reference.read_bytes()).hexdigest(), 'cycles': []}
    for cycle in range(2):
        target = tmp_path/f'cycle-{cycle}.tex'
        document = od.document_from_json(od.document_to_json(document))
        before = od.document_to_json(document)
        report = write_document(document, target)
        assert report.success and report.metrics['latex_route'] == 'native-table-v1', report.issues
        assert od.document_to_json(document) == before
        assert rendered(target, tmp_path) == expected
        evidence['cycles'].append({'source_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                                   'mupdf_exact_pages': 1, 'poppler_exact_pages': 1, 'image_objects': 0})
        document = read_document(target).document
    assert path.read_bytes() == original
    evidence['source_unchanged'] = True
    (tmp_path/'cline-evidence.json').write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
