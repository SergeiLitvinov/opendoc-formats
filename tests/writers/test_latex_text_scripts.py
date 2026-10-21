"""Common text script roles survive native TeX without an Office bridge."""

import builtins
from dataclasses import replace

import pytest
from opendoc_model import (
    DocumentModel,
    Paragraph,
    Section,
    Table,
    TableCell,
    TableRow,
    TextRun,
    TextStyle,
    document_from_json,
    document_to_json,
    get_heading,
    get_list_item,
)

from opendoc_formats import read_document, write_document


def _source(tmp_path, body):
    path = tmp_path / 'own.tex'
    path.write_text('\\begin{document}\n' + body + '\n\\end{document}\n', encoding='utf-8')
    result = read_document(path)
    assert result.document is not None
    return result


def _roles(model):
    return [(get_heading(block), get_list_item(block), [
        (run.text, bool(run.style.superscript), bool(run.style.subscript), bool(run.style.bold), bool(run.style.italic))
        for run in block.content
    ]) for block in model.sections[0].blocks]


@pytest.mark.parametrize('body', [
    r'Water H\textsubscript{2}O and 1\textsuperscript{st} place.',
    r'\textbf{Own \textsuperscript{B}} and \textsubscript{\textit{i}}.',
    r'\section{Own\textsuperscript{2}}Before.\begin{enumerate}\item H\textsubscript{2}O'
    r'\par After\textsuperscript{1}.\item Last.\end{enumerate}Outside.',
    r'\textsuperscript{\bfseries B\normalfont N} and \textsubscript{\itshape i\normalfont n}.',
])
def test_native_scripts_survive_two_cycles_and_never_import_office(tmp_path, monkeypatch, body):
    original_import = builtins.__import__

    def no_office(name, *args, **kwargs):
        if name.split('.')[0] in {'docx', 'lxml'}:
            raise AssertionError('Text script route imported Office')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_office)
    result = _source(tmp_path, body)
    assert not any(issue.reason in {'unknown-command', 'text-script-nesting'} for issue in result.issues)
    model, expected = result.document, _roles(result.document)
    assert any(sup or sub for _, _, runs in expected for _, sup, sub, _, _ in runs)
    for index in range(2):
        before = document_to_json(model)
        target = tmp_path / f'cycle-{index}.tex'
        report = write_document(document_from_json(before), target)
        assert report.success and report.metrics['latex_route'] == 'native-text-v1', report.issues
        assert document_to_json(model) == before
        model = read_document(target).document
        assert _roles(model) == expected


def test_model_role_edits_and_removal_are_authoritative(tmp_path):
    model = _source(tmp_path, r'Before\textsuperscript{raised}after.').document
    block = model.sections[0].blocks[0]
    run = next(run for run in block.content if run.style.superscript)
    run.style = replace(run.style, superscript=None, subscript=True)
    for index in range(2):
        target = tmp_path / f'edited-{index}.tex'
        assert write_document(document_from_json(document_to_json(model)), target).success
        assert r'\textsubscript{raised}' in target.read_text(encoding='utf-8')
        model = read_document(target).document
        run = next(run for run in model.sections[0].blocks[0].content if run.style.subscript)
    run.style = replace(run.style, subscript=None)
    target = tmp_path / 'removed.tex'
    assert write_document(model, target).success
    assert r'\textsubscript' not in target.read_text(encoding='utf-8')
    assert read_document(target).document.sections[0].blocks[0].plain_text == 'Beforeraisedafter.'


@pytest.mark.parametrize('body', [
    r'\textsuperscript{\textsubscript{x}}', r'\textsuperscript{\textsuperscript{x}}',
    r'\underline{\textsubscript{x}}', r'\textsuperscript{\underline{x}}',
])
def test_unsupported_nesting_is_located_retained_and_refused(tmp_path, body):
    imported = _source(tmp_path, body)
    issue = next(issue for issue in imported.issues if issue.reason == 'text-script-nesting')
    assert str(tmp_path / 'own.tex') in issue.location
    assert imported.document.resources['latex-original-source'].data == (tmp_path / 'own.tex').read_bytes()
    target = tmp_path / 'kept.tex'
    target.write_bytes(b'previous')
    report = write_document(imported.document, target)
    assert not report.success and any(issue.feature == 'latex.text-script-profile' for issue in report.issues)
    assert target.read_bytes() == b'previous'


@pytest.mark.parametrize('style', [TextStyle(superscript=True, subscript=True),
                                  TextStyle(superscript=True, underline=True),
                                  TextStyle(subscript=True, font_family='monospace')])
def test_out_of_profile_script_style_never_falls_back_to_bridge(tmp_path, style):
    model = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun('own', style=style)])])])
    path = tmp_path / 'kept.tex'
    path.write_bytes(b'previous')
    result = write_document(model, path)
    assert not result.success
    assert path.read_bytes() == b'previous'


def test_script_in_table_refuses_lossy_bridge(tmp_path):
    model = DocumentModel(sections=[Section(blocks=[Table([TableRow([TableCell([
        Paragraph([TextRun('own', style=TextStyle(subscript=True))]),
    ])])])])])
    path = tmp_path / 'kept.tex'
    path.write_bytes(b'previous')
    result = write_document(model, path)
    assert not result.success and any(issue.feature == 'latex.text-script-profile' for issue in result.issues)
    assert path.read_bytes() == b'previous'


def test_run_split_keeps_one_script_scope_with_authoritative_style_edit(tmp_path):
    model = _source(tmp_path, r'A\textsuperscript{BC}D.').document
    paragraph = model.sections[0].blocks[0]
    index = next(i for i, run in enumerate(paragraph.content) if run.style.superscript)
    run = paragraph.content[index]
    paragraph.content[index:index+1] = [replace(run, text='B'), replace(run, text='C', style=replace(run.style, bold=True))]
    target = tmp_path / 'split.tex'
    assert write_document(document_from_json(document_to_json(model)), target).success
    text = target.read_text(encoding='utf-8')
    assert r'\textsuperscript{B\textbf{C}}' in text
    assert text.count(r'\textsuperscript') == 1


@pytest.mark.parametrize('scope', [[], {'kind': [], 'id': 'x'}, {'kind': 'superscript', 'id': ''},
                                  {'kind': 'superscript', 'id': 'x', 'unknown': True},
                                  {'kind': 'superscript', 'id': 'x'*257}, {'kind': 'subscript', 'id': 17}])
def test_invalid_native_script_scope_refuses_atomically(tmp_path, scope):
    run = TextRun('own', style=TextStyle(superscript=True), properties={'latex_text_script_scope': scope})
    model = DocumentModel(sections=[Section(blocks=[Paragraph([run])])])
    path = tmp_path / 'kept.tex'
    path.write_bytes(b'previous')
    result = write_document(model, path)
    assert not result.success and any(issue.feature == 'latex.text-script-profile' for issue in result.issues)
    assert path.read_bytes() == b'previous'


@pytest.mark.parametrize('body', [r'A\textsuperscript{}B.', r'A\textsubscript{a\par b}B.'])
def test_empty_or_block_script_is_not_silently_lost(tmp_path, body):
    result = _source(tmp_path, body)
    assert any(issue.reason == 'text-script-empty-or-block' for issue in result.issues)
    path = tmp_path / 'kept.tex'
    path.write_bytes(b'previous')
    report = write_document(result.document, path)
    assert not report.success and any(issue.feature == 'latex.text-script-profile' for issue in report.issues)
    assert path.read_bytes() == b'previous'


def test_nested_emphasis_in_script_is_located_and_not_claimed_native(tmp_path):
    result = _source(tmp_path, r'A\textsubscript{\textit{\emph{n}}}B.')
    assert any(issue.reason == 'text-script-emphasis' for issue in result.issues)
    path = tmp_path / 'kept.tex'
    path.write_bytes(b'previous')
    report = write_document(result.document, path)
    assert not report.success and path.read_bytes() == b'previous'


def test_separate_source_scopes_do_not_merge_at_the_same_character_offset(tmp_path):
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    models = [_source(folder, r'\textsuperscript{A}').document for folder in (first, second)]
    runs = [model.sections[0].blocks[0].content[0] for model in models]
    assert runs[0].properties['latex_text_script_scope']['id'] != runs[1].properties['latex_text_script_scope']['id']
    model = DocumentModel(sections=[Section(blocks=[Paragraph(runs)])])
    target = tmp_path / 'merged.tex'
    assert write_document(model, target).success
    assert target.read_text(encoding='utf-8').count(r'\textsuperscript{A}') == 2
