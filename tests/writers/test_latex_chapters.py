"""Standard chapter hierarchy uses common Heading levels without Office conversion."""

import builtins

import pytest
from opendoc_model import (
    DocumentModel,
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

COMMANDS = ('chapter', 'section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph')


@pytest.mark.parametrize('document_class', ['book', 'report'])
@pytest.mark.parametrize('star', ['', '*'])
def test_six_levels_keep_class_numbering_styles_and_math_through_two_cycles(tmp_path, monkeypatch, document_class, star):
    original_import = builtins.__import__
    def no_office(name, *args, **kwargs):
        if name.split('.')[0] in {'docx', 'lxml', 'pptx', 'fontTools'}:
            raise AssertionError(f'Chapter profile imported {name}')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_office)
    source = tmp_path / 'original.tex'
    body = ''.join('\\' + command + star + '{Own ' + str(level) + r' $x^2$}'
                   for level, command in enumerate(COMMANDS, 1))
    original = ('\\documentclass{' + document_class + '}\\begin{document}' + body + r'\end{document}').encode()
    source.write_bytes(original)
    document = read_document(source).document
    for index in range(2):
        document = document_from_json(document_to_json(document))
        assert document.metadata['documentclass'] == document_class
        assert [get_heading(block) for block in document.sections[0].blocks] == [Heading(i) for i in range(1, 7)]
        assert [block.style_id for block in document.sections[0].blocks] == [f'Heading {i}' for i in range(1, 7)]
        before = document_to_json(document)
        target = tmp_path / f'cycle-{index}.tex'
        report = write_document(document, target)
        assert report.success and report.metrics['latex_route'] == 'native-text-v1', report.issues
        assert document_to_json(document) == before
        result = target.read_text(encoding='utf-8')
        assert result.startswith(r'\documentclass{' + document_class + '}')
        for level, command in enumerate(COMMANDS, 1):
            assert '\\' + command + star + '{Own ' + str(level) in result
        document = read_document(target).document
    assert source.read_bytes() == original


@pytest.mark.parametrize('document_class', ['book', 'report'])
def test_common_role_edits_and_removal_override_source_chapter_witness(tmp_path, document_class):
    source = tmp_path / 'original.tex'
    source.write_text('\\documentclass{' + document_class + r'}\begin{document}'
                      r'\chapter{First}\section{Second}\subparagraph*{Third}\end{document}', encoding='utf-8')
    document = read_document(source).document
    first, second, third = document.sections[0].blocks
    set_heading(first, Heading(3))
    first.properties['latex_heading_level'] = 1
    set_heading(second, Heading(6))
    set_heading(third, None)
    for index in range(2):
        path = tmp_path / f'edit-{index}.tex'
        report = write_document(document_from_json(document_to_json(document)), path)
        assert report.success and report.metrics['latex_route'] == 'native-text-v1', report.issues
        result = path.read_text(encoding='utf-8')
        assert r'\subsection{First}' in result and r'\subparagraph{Second}' in result
        assert r'\chapter{First}' not in result and r'\subparagraph*{Third}' not in result
        document = read_document(path).document
        assert [get_heading(block) for block in document.sections[0].blocks] == [Heading(3), Heading(6), None]


@pytest.mark.parametrize('document_class', ['book', 'report'])
def test_neutral_level_six_has_explicit_unnumbered_policy(tmp_path, document_class):
    block = Paragraph([TextRun('Own sixth level')])
    set_heading(block, Heading(6))
    document = DocumentModel([Section([block])], metadata={'documentclass': document_class})
    path = tmp_path / 'new.tex'
    report = write_document(document, path)
    assert report.success and report.metrics['latex_route'] == 'native-text-v1'
    assert r'\subparagraph*{Own sixth level}' in path.read_text(encoding='utf-8')
    assert get_heading(read_document(path).document.sections[0].blocks[0]) == Heading(6)


@pytest.mark.parametrize('value', [r'book}\input{evil', ['book'], {'class': 'book'}, True, None])
def test_metadata_never_becomes_an_executable_class_path(tmp_path, value):
    block = Paragraph([TextRun('Own safe heading')])
    set_heading(block, Heading(1))
    document = DocumentModel([Section([block])], metadata={'documentclass': value})
    path = tmp_path / 'safe.tex'
    report = write_document(document, path)
    assert report.success and path.read_text(encoding='utf-8').startswith(r'\documentclass[12pt,a4paper]{article}')
