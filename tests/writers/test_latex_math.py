"""Native formula objects, exact source and modes through JSON/TeX, without Office."""

import base64
import builtins
from dataclasses import replace

import pytest
from opendoc_model import (
    DocumentLimits,
    DocumentModel,
    Formula,
    FormulaFormat,
    Paragraph,
    Section,
    TextRun,
    document_from_json,
    document_to_json,
    get_anchor,
    get_list_item,
)

from opendoc_formats import ImportOptions, read_document, write_document
from opendoc_formats.errors import InvalidDocumentError


def structure(document):
    rows = []
    for paragraph in document.sections[0].blocks:
        content = []
        for run in paragraph.content:
            if isinstance(run, Formula):
                content.append(('formula', run.format, run.value, run.display, run.fallback_text))
            elif content and content[-1][0] == 'text':
                content[-1] = ('text', content[-1][1]+run.text)
            else:
                content.append(('text', run.text))
        rows.append((get_anchor(paragraph), get_list_item(paragraph), content))
    return rows


def cycles(document, tmp_path):
    # TextRun splitting is format-local; preserve the ordered text/formula boundaries.
    expected = structure(document)
    for index in range(2):
        before = document_to_json(document)
        path = tmp_path / f'formula-{index}.tex'
        report = write_document(document, path)
        assert report.success and report.metrics['latex_route'] == 'native-text-v1', report.issues
        assert document_to_json(document) == before
        document = document_from_json(document_to_json(read_document(path).document))
        assert structure(document) == expected
    return document


def test_source_formulas_in_paragraph_and_list_keep_value_mode_boundaries_and_roles(tmp_path, monkeypatch):
    source = tmp_path / 'source.tex'
    source.write_text(r'\begin{document}Before $x^2$ and \(\frac{a}{b}\).'
                      r'\[\begin{pmatrix}1&2\\3&4\end{pmatrix}\]After.'
                      r'\begin{enumerate}\item $a+b$\par \[\sqrt[3]{x}\]'
                      r'\item\begin{itemize}\item $$\sum_{i=1}^{n}i$$\end{itemize}'
                      r'\end{enumerate}\end{document}', encoding='utf-8')
    document = read_document(source).document
    original_import = builtins.__import__

    def no_office(name, *args, **kwargs):
        if name.split('.')[0] in {'docx', 'lxml'}:
            raise AssertionError('Native math imported Office')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_office)
    cycles(document, tmp_path)


@pytest.mark.parametrize('fallback', ['', 'own accessible text', 'x^2', r'\input{inert}'])
def test_generic_formula_fallback_and_inline_display_edits_survive(tmp_path, fallback):
    document = DocumentModel(sections=[Section(blocks=[Paragraph(content=[
        Formula('x^2', FormulaFormat.LATEX, fallback_text=fallback),
    ])])])
    restored = cycles(document, tmp_path)
    formula = restored.sections[0].blocks[0].content[0]
    formula.display = True  # Source delimiter witness must not override the public field.
    formula.value = r'\frac{x+1}{2}'
    cycles(restored, tmp_path)
    restored.sections[0].blocks[0].content = [TextRun('Removed')]
    assert cycles(restored, tmp_path).sections[0].blocks[0].plain_text == 'Removed'


def test_generic_mixed_paragraph_keeps_ordered_text_and_formulas(tmp_path):
    paragraph = Paragraph(content=[TextRun('Before '), Formula('x^2', FormulaFormat.LATEX),
                                   TextRun(' and after.'), Formula('y', FormulaFormat.LATEX, display=True),
                                   TextRun('Outside.')])
    cycles(DocumentModel(sections=[Section(blocks=[paragraph])]), tmp_path)


@pytest.mark.parametrize('value', [r'\input{private}', r'\write18{command}', r'\csname input\endcsname',
                                 r'\def\x{1}', r'\end{document}', r'x\)text\(y', '$x$', r'\href{a}{b}',
                                 r'\frac{x}', r'\sqrt{x', r'\left(x', r'\begin{pmatrix}x\end{bmatrix}',
                                 r'\unknown{x}', 'x\n\ny', 'α+β', 'x % no newline', '^^5cinput{private}'])
def test_unsupported_formula_refuses_atomically_even_with_office(tmp_path, value):
    document = DocumentModel(sections=[Section(blocks=[Paragraph(content=[Formula(value, FormulaFormat.LATEX)])])])
    path = tmp_path / 'previous.tex'
    path.write_bytes(b'previous')
    report = write_document(document, path)
    assert not report.success and path.read_bytes() == b'previous'
    assert any(i.feature == 'latex.formula-profile' for i in report.issues)


@pytest.mark.parametrize('edit', ['format', 'property', 'paragraph-layout'])
def test_unsupported_formula_declarations_do_not_use_bridge(tmp_path, edit):
    formula = Formula('x', FormulaFormat.LATEX)
    paragraph = Paragraph(content=[formula])
    if edit == 'format':
        formula.format, formula.value = FormulaFormat.MATHML, '<math><mi>x</mi></math>'
    elif edit == 'property':
        formula.properties['unknown-math'] = True
    else:
        paragraph.alignment = 'center'
    document = DocumentModel(sections=[Section(blocks=[paragraph])])
    path = tmp_path / 'previous.tex'
    path.write_bytes(b'previous')
    result = write_document(document, path)
    assert not result.success and path.read_bytes() == b'previous'


def test_math_metadata_is_inert_strict_and_bounded(tmp_path):
    path = tmp_path / 'own.tex'
    for payload in ['!', base64.urlsafe_b64encode(b'{"fallback_text":"a","fallback_text":"b"}').decode(),
                    base64.urlsafe_b64encode(b'[["fallback_text","a"]]').decode()]:
        path.write_text('% opendoc-math-v1:'+payload+'\n$x$', encoding='utf-8')
        with pytest.raises(InvalidDocumentError):
            read_document(path)
    path.write_text('% opendoc-math-v2:future\n$x$', encoding='utf-8')
    with pytest.raises(InvalidDocumentError):
        read_document(path)
    marker = '% opendoc-math-v1:'+base64.urlsafe_b64encode(b'{"fallback_text":""}').decode()+'\n'
    path.write_text(marker+'$x$'+marker+'$y$', encoding='utf-8')
    result = read_document(path, options=ImportOptions(document_limits=replace(DocumentLimits(), max_nodes=1)))
    assert not result.success and result.issues[0].code == 'import.document-limit'


def test_escaped_metadata_percent_is_text_and_formula_comments_remain_exact(tmp_path):
    path = tmp_path / 'source.tex'
    path.write_text(r'\% opendoc-math-v2:inert $x % comment'+'\n+y$', encoding='utf-8')
    document = read_document(path).document
    cycles(document, tmp_path)


def test_opaque_numbered_equation_never_uses_docx_bridge(tmp_path):
    path = tmp_path / 'numbered.tex'
    path.write_text(r'\begin{document}\begin{equation}x=1\label{own}\end{equation}\end{document}', encoding='utf-8')
    document = read_document(path).document
    target = tmp_path / 'previous.tex'
    target.write_bytes(b'previous')
    result = write_document(document, target)
    assert not result.success and any(i.feature == 'latex.formula-profile' for i in result.issues)
    assert target.read_bytes() == b'previous'


@pytest.mark.parametrize('display', [False, True])
def test_standalone_formula_block_is_not_converted_to_a_paragraph(tmp_path, display):
    source = tmp_path / 'list.tex'
    source.write_text(r'\begin{enumerate}\item First\end{enumerate}', encoding='utf-8')
    document = read_document(source).document
    document.sections[0].blocks += [Formula(r'\frac{x}{2}', FormulaFormat.LATEX, display=display,
                                           fallback_text='own block'), Paragraph(content=[TextRun('Outside')])]
    for index in range(2):
        path = tmp_path / f'block-{index}.tex'
        report = write_document(document, path)
        assert report.success, report.issues
        document = document_from_json(document_to_json(read_document(path).document))
        first, block, last = document.sections[0].blocks
        assert get_list_item(first) is not None and last.plain_text == 'Outside'
        assert isinstance(block, Formula)
        assert (block.value, block.display, block.fallback_text) == (r'\frac{x}{2}', display, 'own block')


@pytest.mark.parametrize('surroundings', ['Before {marker}$x$', '{marker}$x$After',
                                       r'\begin{itemize}\item {marker}$x$\end{itemize}'])
def test_block_annotation_cannot_discard_surrounding_text_or_item_scope(tmp_path, surroundings):
    payload = base64.urlsafe_b64encode(b'{"fallback_text":"","placement":"block"}').decode()
    marker = '% opendoc-math-v1:'+payload+'\n'
    path = tmp_path / 'invalid-block.tex'
    path.write_text(surroundings.replace('{marker}', marker), encoding='utf-8')
    with pytest.raises(InvalidDocumentError):
        read_document(path)
