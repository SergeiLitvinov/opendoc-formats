"""Native TeX text semantics without Office, and conservative bridge selection."""

from dataclasses import replace

import pytest
from opendoc_model import (
    DocumentModel,
    Length,
    Paragraph,
    Section,
    TextRun,
    TextStyle,
    document_from_json,
    document_to_json,
)

from opendoc_formats import read_document, write_document


def model():
    return DocumentModel(sections=[Section(blocks=[
        Paragraph(content=[TextRun('Own [text] {braces} % # $ & _ ^ ~ \\input{inert} … Кириллица')]),
        Paragraph(content=[TextRun('Bold', style=TextStyle(bold=True)), TextRun(' and '),
                           TextRun('italic', style=TextStyle(italic=True, underline=True))]),
    ])])


def test_two_native_tex_cycles_preserve_text_styles_and_leave_input_unchanged(tmp_path, monkeypatch):
    import builtins

    original_import = builtins.__import__

    def no_office(name, *args, **kwargs):
        if name.split('.')[0] in {'docx', 'lxml'}:
            raise AssertionError('Native text route imported an Office engine')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_office)
    document = model()
    texts = [p.plain_text for p in document.sections[0].blocks]
    for index in range(2):
        before = document_to_json(document)
        output = tmp_path / f'cycle-{index}.tex'
        result = write_document(document, output)
        assert result.success, result.issues
        assert result.metrics['latex_route'] == 'native-text-v1'
        assert not result.lossless and result.metrics['assessment_complete'] is False
        assert document_to_json(document) == before
        source = output.read_text(encoding='utf-8')
        assert r'\input{inert}' not in source and r'\[' not in source
        document = document_from_json(document_to_json(read_document(output).document))
        paragraphs = document.sections[0].blocks
        assert [p.plain_text for p in paragraphs] == texts
        assert next(r for r in paragraphs[1].content if r.text == 'Bold').style.bold
        italic = next(r for r in paragraphs[1].content if r.text == 'italic')
        assert italic.style.italic and italic.style.underline


@pytest.mark.parametrize('edit', ['whitespace', 'control', 'layout', 'font', 'property', 'link'])
def test_objects_outside_native_profile_require_bridge_and_preserve_previous_file(tmp_path, monkeypatch, edit):
    document = model()
    paragraph = document.sections[0].blocks[0]
    run = paragraph.content[0]
    if edit == 'whitespace':
        run.text = 'Repeated  whitespace'
    elif edit == 'control':
        run.text = 'Control\x7ftext'
    elif edit == 'layout':
        document.sections[0].page = replace(document.sections[0].page, margin_top=Length(40))
    elif edit == 'font':
        run.style.font_family = 'Own family'
    elif edit == 'property':
        paragraph.properties['unknown_layout'] = True
    else:
        run.link = 'https://example.org/'
    monkeypatch.setattr('opendoc_formats.support.backends.missing_backends', lambda requirements: ['docx'])
    # The registry has no blanket Office requirement; the writer chooses the route.
    from opendoc_formats.writers.latex_writer import write_latex_model

    output = tmp_path / 'previous.tex'
    output.write_bytes(b'previous')
    result = write_latex_model(document, output)
    assert not result.success and output.read_bytes() == b'previous'
    assert any(i.feature == 'latex.docx-bridge' for i in result.issues)


def test_unknown_source_body_is_not_mistaken_for_repeated_preamble(tmp_path, monkeypatch):
    from opendoc_formats.support.latex import PREAMBLE

    source = tmp_path / 'unknown.tex'
    source.write_text(PREAMBLE+r'\begin{document}Text \input{private}\end{document}', encoding='utf-8')
    document = read_document(source).document
    monkeypatch.setattr('opendoc_formats.support.backends.missing_backends',
                        lambda requirements: ['docx'] if requirements else [])
    output = tmp_path / 'previous.tex'
    output.write_bytes(b'previous')
    result = write_document(document, output)
    assert not result.success and output.read_bytes() == b'previous'
    assert any(i.feature == 'latex.docx-bridge' for i in result.issues)


def test_known_preamble_with_windows_line_endings_retains_native_route(tmp_path):
    output = tmp_path / 'windows.tex'
    assert write_document(model(), output).success
    output.write_bytes(output.read_bytes().replace(b'\n', b'\r\n'))
    document = read_document(output).document
    result = write_document(document, tmp_path / 'second.tex')
    assert result.success and result.metrics['latex_route'] == 'native-text-v1'


def test_table_retains_established_bridge_when_docx_is_available(tmp_path):
    pytest.importorskip('docx')
    from opendoc_model import Table, TableCell, TableRow

    document = DocumentModel(sections=[Section(blocks=[
        Table(rows=[TableRow(cells=[TableCell(blocks=[Paragraph(content=[TextRun('Own cell')])])])]),
    ])])
    output = tmp_path / 'table.tex'
    result = write_document(document, output)
    assert result.success, result.issues
    assert result.metrics['latex_route'] == 'docx-bridge'
    assert r'\begin{tabular}' in output.read_text(encoding='utf-8')
    assert 'Own cell' in output.read_text(encoding='utf-8')


def test_direct_native_writer_obeys_selected_node_budget(tmp_path):
    from opendoc_model import ArtifactLimitError, DocumentLimits

    from opendoc_formats.writers.latex_writer import write_latex_model

    output = tmp_path / 'previous.tex'
    output.write_bytes(b'previous')
    with pytest.raises(ArtifactLimitError):
        write_latex_model(model(), output, limits=DocumentLimits(max_nodes=1))
    assert output.read_bytes() == b'previous'
