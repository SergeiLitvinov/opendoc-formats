"""SDK list links survive native TeX, independent of Office and stale source witnesses."""

import builtins
from dataclasses import replace

import pytest
from opendoc_model import (
    Anchor,
    DocumentModel,
    ListItem,
    Paragraph,
    Section,
    TextRun,
    document_from_json,
    document_to_json,
    get_anchor,
    get_list_item,
    iter_list_numbers,
    set_anchor,
    set_list_item,
)

from opendoc_formats import ExportOptions, read_document, write_document
from opendoc_formats.errors import InvalidDocumentError

BODY = (r'Before.\begin{enumerate}\item First.\par Continuation.\item'
        r'\begin{itemize}\item Child.\end{itemize}\par After child.\item Last.\end{enumerate}Outside.')


def read_source(tmp_path, body=BODY):
    source = tmp_path / 'source.tex'
    source.write_text('\\begin{document}'+body+'\\end{document}', encoding='utf-8')
    return read_document(source).document


def structure(document):
    return [(p.plain_text, get_anchor(p), get_list_item(p)) for p in document.sections[0].blocks]


def cycle(document, tmp_path):
    before = structure(document)
    for index in range(2):
        original = document_to_json(document)
        destination = tmp_path / f'cycle-{index}.tex'
        result = write_document(document, destination)
        assert result.success and result.metrics['latex_route'] == 'native-text-v1', result.issues
        assert document_to_json(document) == original
        document = document_from_json(document_to_json(read_document(destination).document))
        assert structure(document) == before
    return document


def test_nested_empty_parent_continuations_and_outside_survive_without_office(tmp_path, monkeypatch):
    original_import = builtins.__import__

    def no_office(name, *args, **kwargs):
        if name.split('.')[0] in {'docx', 'lxml'}:
            raise AssertionError('Native list route imported Office')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_office)
    document = read_source(tmp_path)
    rows = document.sections[0].blocks
    assert get_list_item(rows[2]).continuation_of == get_anchor(rows[1]).id
    assert rows[3].plain_text == '' and get_list_item(rows[4]).parent_id == get_anchor(rows[3]).id
    assert get_list_item(rows[5]).continuation_of == get_anchor(rows[3]).id
    restored = cycle(document, tmp_path)
    assert [x.number for x in iter_list_numbers(restored)] == [1, None, 2, None, None, 3]


def test_sdk_edit_continuation_and_remove_role_do_not_restore_native_properties(tmp_path):
    document = read_source(tmp_path, r'\begin{enumerate}\item First.\par Second.\item Last.\end{enumerate}')
    first, second, last = document.sections[0].blocks
    set_list_item(second, replace(get_list_item(second), continuation_of=None, restart=7))
    set_list_item(last, None)
    second.properties['list_kind'] = 'stale-witness'
    restored = cycle(document, tmp_path)
    assert [x.number for x in iter_list_numbers(restored)] == [1, 7]
    assert get_list_item(restored.sections[0].blocks[-1]) is None


@pytest.mark.parametrize('suffix', ['txt', 'html', 'epub'])
def test_other_projections_report_list_loss_and_quality_gate_preserves_output(tmp_path, suffix):
    document = read_source(tmp_path)
    destination = tmp_path / ('other.'+suffix)
    report = write_document(document, destination)
    assert report.success and any(issue.feature == 'list-structure' for issue in report.issues)
    destination.write_bytes(b'keep original')
    rejected = write_document(document, destination, options=ExportOptions(
        quality_gate=lambda report, path: not any(issue.feature == 'list-structure' for issue in report.issues)))
    assert not rejected.success and destination.read_bytes() == b'keep original'


@pytest.mark.parametrize('restart', [None, 9])
def test_start_restart_parent_removal_and_resumed_group_are_preserved(tmp_path, restart):
    root = Paragraph(content=[TextRun('Root')])
    child = Paragraph(content=[TextRun('Child')])
    outside = Paragraph(content=[TextRun('Outside')])
    resumed = Paragraph(content=[TextRun('Resumed')])
    set_anchor(root, Anchor('own-root'))
    set_anchor(child, Anchor('own-child'))
    set_anchor(resumed, Anchor('own-resumed'))
    set_list_item(root, ListItem('own-list', start=3))
    set_list_item(child, ListItem('own-child-list', kind='unordered', parent_id='own-root'))
    set_list_item(resumed, ListItem('own-list', start=3, restart=restart))
    document = DocumentModel(sections=[Section(blocks=[root, child, outside, resumed])])
    cycle(document, tmp_path)
    set_list_item(child, replace(get_list_item(child), parent_id=None))
    restored = cycle(document, tmp_path)
    assert get_list_item(restored.sections[0].blocks[1]).parent_id is None
    assert [x.number for x in iter_list_numbers(restored)] == [3, None, restart or 4]


def test_source_counters_and_empty_leaf_item_have_native_roles(tmp_path):
    document = read_source(tmp_path, r'\begin{enumerate}\setcounter{enumi}{2}\item First'
                           r'\setcounter{enumi}{7}\item Second\item\end{enumerate}')
    assert [x.number for x in iter_list_numbers(document)] == [3, 8, 9]
    cycle(document, tmp_path)


@pytest.mark.parametrize('kind', ['custom-label', 'unknown-property', 'dangling', 'noncontiguous'])
def test_unsupported_lists_refuse_atomically_even_with_office_installed(tmp_path, kind):
    if kind == 'custom-label':
        document = read_source(tmp_path, r'\begin{enumerate}\item[Own] Text\end{enumerate}')
    else:
        document = read_source(tmp_path, r'\begin{enumerate}\item First\par Continuation\end{enumerate}')
        if kind == 'unknown-property':
            document.sections[0].blocks[0].properties['unknown_layout'] = True
        elif kind == 'dangling':
            document.sections[0].blocks.pop(0)
        else:
            document.sections[0].blocks.insert(1, Paragraph(content=[TextRun('Outside')]))
    destination = tmp_path / 'previous.tex'
    destination.write_bytes(b'previous')
    result = write_document(document, destination)
    assert not result.success and destination.read_bytes() == b'previous'


def test_contradictory_identity_annotations_are_not_authoritative_over_native_counters(tmp_path):
    document = read_source(tmp_path, r'\begin{enumerate}\item First\end{enumerate}')
    target = tmp_path / 'own.tex'
    assert write_document(document, target).success
    text = target.read_text(encoding='utf-8').replace(r'\setcounter{enumi}{0}', r'\setcounter{enumi}{5}')
    target.write_text(text, encoding='utf-8')
    with pytest.raises(InvalidDocumentError, match='contradicts native TeX counters'):
        read_document(target)


@pytest.mark.parametrize('payload', ['!', 'eyJhbmNob3IiOiJhIiwiYW5jaG9yIjoiYiJ9', 'future'])
def test_corrupt_duplicate_or_future_annotations_are_not_executed_or_silently_ignored(tmp_path, payload):
    marker = '% opendoc-par-v2:{}' if payload == 'future' else '% opendoc-par-v1:'+payload
    source = tmp_path / 'corrupt.tex'
    source.write_text('\\begin{document}\n'+marker+'\nText.\\end{document}', encoding='utf-8')
    with pytest.raises(InvalidDocumentError):
        read_document(source)
