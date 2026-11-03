"""Official semantic Heading, source numbering and authoritative edits in native TeX."""

import builtins

import pytest
from opendoc_model import (
    DocumentModel,
    Formula,
    Heading,
    Paragraph,
    Section,
    TextRun,
    document_from_json,
    document_to_json,
    get_heading,
    set_heading,
)

from opendoc_formats import read_document, write_document

COMMANDS = ('section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph')


@pytest.mark.parametrize('star', ['', '*'])
def test_five_source_heading_levels_and_numbering_survive_two_native_cycles(tmp_path, monkeypatch, star):
    original_import = builtins.__import__

    def no_office(name, *args, **kwargs):
        if name.split('.')[0] in {'docx', 'lxml'}:
            raise AssertionError('Heading route imported an Office backend')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_office)
    source = tmp_path / 'headings.tex'
    source.write_text(r'\documentclass{article}\begin{document}'
                      + ''.join('\\'+command+star+'{Own '+str(level)+'}' for level, command in enumerate(COMMANDS, 1))
                      + r'\end{document}', encoding='utf-8')
    document = read_document(source).document
    for cycle in range(2):
        before = document_to_json(document)
        destination = tmp_path / f'cycle-{cycle}.tex'
        result = write_document(document, destination)
        assert result.success and result.metrics['latex_route'] == 'native-text-v1', result.issues
        assert document_to_json(document) == before
        text = destination.read_text(encoding='utf-8')
        for level, command in enumerate(COMMANDS, 1):
            assert '\\'+command+star+'{Own '+str(level)+'}' in text
        document = document_from_json(document_to_json(read_document(destination).document))
        assert [get_heading(p) for p in document.sections[0].blocks] == [Heading(i) for i in range(1, 6)]
        assert [p.plain_text for p in document.sections[0].blocks] == [f'Own {i}' for i in range(1, 6)]


def test_sdk_edit_and_removal_do_not_resurrect_source_heading_or_style(tmp_path):
    source = tmp_path / 'source.tex'
    source.write_text(r'\begin{document}\section{First}\subsection*{Second}\end{document}', encoding='utf-8')
    document = read_document(source).document
    first, second = document.sections[0].blocks
    set_heading(first, Heading(3))
    first.properties['latex_heading_level'] = 5  # Stale native witness cannot override the SDK edit.
    set_heading(second, None)
    for cycle in range(2):
        destination = tmp_path / f'edited-{cycle}.tex'
        result = write_document(document, destination)
        assert result.success and result.metrics['latex_route'] == 'native-text-v1'
        text = destination.read_text(encoding='utf-8')
        assert r'\subsubsection{First}' in text
        assert '{Second}' not in text and 'Second' in text
        document = document_from_json(document_to_json(read_document(destination).document))
        first, second = document.sections[0].blocks
        assert get_heading(first) == Heading(3) and get_heading(second) is None


def test_format_neutral_heading_uses_explicit_unnumbered_policy(tmp_path):
    paragraph = Paragraph(content=[TextRun('Own heading')])
    set_heading(paragraph, Heading(2))
    destination = tmp_path / 'generic.tex'
    assert write_document(DocumentModel(sections=[Section(blocks=[paragraph])]), destination).success
    assert r'\subsection*{Own heading}' in destination.read_text(encoding='utf-8')
    assert get_heading(read_document(destination).document.sections[0].blocks[0]) == Heading(2)


@pytest.mark.parametrize('command', [r'\section[Short]{Full}', r'\chapter{Full}'])
def test_unrepresented_heading_source_uses_explicit_bridge_fallback(tmp_path, monkeypatch, command):
    source = tmp_path / 'unsupported.tex'
    source.write_text(r'\begin{document}'+command+r'\end{document}', encoding='utf-8')
    document = read_document(source).document
    monkeypatch.setattr('opendoc_formats.support.backends.missing_backends',
                        lambda requirements: ['docx'] if requirements else [])
    destination = tmp_path / 'previous.tex'
    destination.write_bytes(b'previous')
    result = write_document(document, destination)
    assert not result.success and destination.read_bytes() == b'previous'
    assert any(i.feature == 'latex.docx-bridge' for i in result.issues)


@pytest.mark.parametrize('star', ['', '*'])
def test_inline_formulas_in_five_heading_levels_survive_edits_and_two_cycles(tmp_path, monkeypatch, star):
    source = tmp_path / 'math-headings.tex'
    source.write_text(r'\begin{document}'+''.join(
        '\\'+command+star+r'{Own $x^2$ and \(\frac{1}{2}\)}'
        for command in COMMANDS)+r'\end{document}', encoding='utf-8')
    document = read_document(source).document
    original_import = builtins.__import__

    def no_office(name, *args, **kwargs):
        if name.split('.')[0] in {'docx', 'lxml'}:
            raise AssertionError('Heading math imported Office')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_office)
    first, second, *_ = document.sections[0].blocks
    set_heading(first, Heading(3))
    set_heading(second, None)
    formula = next(run for run in first.content if isinstance(run, Formula))
    formula.value, formula.fallback_text = r'\sqrt{x+1}', 'own root'
    for cycle in range(2):
        before = document_to_json(document)
        path = tmp_path / f'heading-math-{cycle}.tex'
        report = write_document(document, path)
        assert report.success and report.metrics['latex_route'] == 'native-text-v1', report.issues
        assert document_to_json(document) == before
        document = document_from_json(document_to_json(read_document(path).document))
        assert [get_heading(p) for p in document.sections[0].blocks] == [Heading(3), None, Heading(3), Heading(4), Heading(5)]
        assert [[(f.value, f.display, f.fallback_text) for f in p.content if isinstance(f, Formula)]
                for p in document.sections[0].blocks] == [
            [(r'\sqrt{x+1}', False, 'own root'), (r'\frac{1}{2}', False, r'\frac{1}{2}')],
            *[[('x^2', False, 'x^2'), (r'\frac{1}{2}', False, r'\frac{1}{2}')]]*4,
        ]


def test_display_math_in_heading_is_atomic_refusal(tmp_path):
    from opendoc_model import FormulaFormat

    paragraph = Paragraph(content=[Formula('x', FormulaFormat.LATEX, display=True)])
    set_heading(paragraph, Heading(1))
    path = tmp_path / 'previous.tex'
    path.write_bytes(b'previous')
    report = write_document(DocumentModel(sections=[Section(blocks=[paragraph])]), path)
    assert not report.success and path.read_bytes() == b'previous'
    assert any(issue.feature == 'latex.formula-profile' for issue in report.issues)
