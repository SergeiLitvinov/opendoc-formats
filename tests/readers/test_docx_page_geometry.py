"""Physical omissions, partial geometry and explicit edits use independent XML/ZIP originals."""

from threading import Event
from zipfile import ZipFile

import opendoc_model as od
import pytest
from lxml import etree

from opendoc_formats import ExportOptions, read_document, write_document
from opendoc_formats.ooxml.page_geometry import KEY, W, unresolved
from tools.docx_page_acceptance import cases, original


def declarations(path):
    with ZipFile(path) as archive:
        root = etree.fromstring(archive.read('word/document.xml'))
    sections = list(root.findall('.//'+W+'pPr/'+W+'sectPr'))
    sections.append(root.find(W+'body/'+W+'sectPr'))
    return [None if section is None else {
        name: None if (node := section.find(W+name)) is None else dict(node.attrib)
        for name in ('pgSz', 'pgMar')} for section in sections]


@pytest.mark.parametrize('name,sections', cases().items())
def test_source_omissions_and_partial_declarations_survive_two_public_cycles(tmp_path, name, sections):
    source = tmp_path/(name+'.docx')
    data = original(sections)
    source.write_bytes(data)
    expected = declarations(source)
    result = read_document(source)
    assert result.success, result.issues
    model = result.document
    assert len(model.sections) == len(sections)
    for index, section in enumerate(model.sections):
        state = section.properties[KEY]
        assert state['section_present'] == (sections[index] is not None)
        if state['unresolved']:
            assert any(issue.code == 'docx.page-geometry' and f'section={index+1}:' in issue.location for issue in result.issues)
    for cycle in range(2):
        before = od.document_to_json(model)
        path = tmp_path/f'cycle-{cycle}.json'
        assert write_document(model, path).success
        result = read_document(path)
        assert result.success, result.issues
        target = tmp_path/f'cycle-{cycle}.docx'
        report = write_document(result.document, target)
        assert report.success, report.issues
        assert od.document_to_json(result.document) == before
        assert declarations(target) == expected
        with ZipFile(target) as archive:
            root = etree.fromstring(archive.read('word/document.xml'))
        assert len(root.findall('.//'+W+'p')) == len(sections)
        result = read_document(target)
        assert result.success, result.issues
        model = result.document
    assert source.read_bytes() == data


def test_missing_size_is_word_section_projection_not_model_a4_or_inherited_prior_size(tmp_path):
    source = tmp_path/'source.docx'
    source.write_bytes(original(cases()['a4-then-missing']))
    model = read_document(source).document
    assert model.sections[0].page.width.pt == 595.3
    assert (model.sections[1].page.width.pt, model.sections[1].page.height.pt) == (612, 792)
    assert unresolved(model.sections[1]) == ['width', 'height']


@pytest.mark.parametrize('tag', ['pgSz', 'pgMar'])
def test_duplicate_page_declarations_refuse_instead_of_dropping_one(tmp_path, tag):
    from opendoc_formats.errors import UnsupportedDocumentError

    source = tmp_path/'ambiguous.docx'
    data = original([f'<w:{tag}/><w:{tag}/>'])
    source.write_bytes(data)
    with pytest.raises(UnsupportedDocumentError, match='duplicate '+tag):
        read_document(source)
    assert source.read_bytes() == data


def test_edit_width_preserves_missing_height_and_accepts_unchanged_other_fields(tmp_path):
    source = tmp_path/'source.docx'
    source.write_bytes(original(cases()['missing-size']))
    model = read_document(source).document
    model.sections[0].page.width = od.Length(700)
    assert unresolved(model.sections[0]) == ['height']
    before = od.document_to_json(model)
    target = tmp_path/'edited.docx'
    report = write_document(model, target)
    assert report.success, report.issues
    assert od.document_to_json(model) == before
    assert declarations(target)[0]['pgSz'] == {W+'w': '14000'}
    reread = read_document(target).document
    assert reread.sections[0].page.width.pt == 700
    assert unresolved(reread.sections[0]) == ['height']


def test_edit_implicit_section_materializes_explicit_size_without_inventing_margins(tmp_path):
    source = tmp_path/'source.docx'
    source.write_bytes(original(cases()['missing-section']))
    model = read_document(source).document
    model.sections[0].page.width = od.Length(600)
    model.sections[0].page.height = od.Length(800)
    target = tmp_path/'edited.docx'
    report = write_document(model, target)
    assert report.success, report.issues
    assert declarations(target) == [{'pgSz': {W+'w': '12000', W+'h': '16000'}, 'pgMar': None}]


@pytest.mark.parametrize('damage', ['version', 'bool-version', 'doctype', 'wrong-root', 'nodes', 'contradiction'])
def test_source_page_profile_xml_policy_and_budget_refuse_atomically(tmp_path, damage):
    source = tmp_path/'source.docx'
    source.write_bytes(original(cases()['missing-size']))
    model = read_document(source).document
    state = model.sections[0].properties[KEY]
    if damage in ('version', 'bool-version'):
        state['version'] = 2 if damage == 'version' else True
    elif damage == 'doctype':
        state['size'] = '<!DOCTYPE pgSz [<!ENTITY own "untrusted">]>'+f'<w:pgSz xmlns:w="{W[1:-1]}"/>'
    elif damage == 'wrong-root':
        state['size'] = f'<w:settings xmlns:w="{W[1:-1]}"/>'
    elif damage == 'nodes':
        state['size'] = f'<w:pgSz xmlns:w="{W[1:-1]}">'+('<!--own-->'*1000)+'</w:pgSz>'
    else:
        state['section_present'] = False
    target = tmp_path/'refused.docx'
    target.write_bytes(b'previous output')
    budget = od.DocumentLimits(max_nodes=500) if damage == 'nodes' else od.DocumentLimits()
    before = od.document_to_json(model)
    report = write_document(model, target, options=ExportOptions(document_limits=budget))
    assert not report.success and any(issue.feature == 'docx.page-geometry' for issue in report.issues)
    assert target.read_bytes() == b'previous output' and od.document_to_json(model) == before


def test_cancel_inside_page_xml_retains_model_and_destination(tmp_path, monkeypatch):
    from opendoc_formats import anatomy

    source = tmp_path/'source.docx'
    source.write_bytes(original(cases()['explicit-a4']))
    model = read_document(source).document
    target = tmp_path/'cancelled.docx'
    target.write_bytes(b'previous output')
    before = od.document_to_json(model)
    stop = Event()
    real = anatomy.checkpoint
    def cancel():
        stop.set()
        real()
    monkeypatch.setattr(anatomy, 'checkpoint', cancel)
    report = write_document(model, target, options=ExportOptions(cancelled=stop.is_set))
    assert not report.success
    assert target.read_bytes() == b'previous output' and od.document_to_json(model) == before


def test_layout_export_reports_unknown_page_projection_and_txt_does_not_claim_layout_loss(tmp_path):
    pytest.importorskip('pymupdf')
    source = tmp_path/'source.docx'
    source.write_bytes(original(cases()['missing-size']))
    model = read_document(source).document
    before = od.document_to_json(model)
    pdf = write_document(model, tmp_path/'rendered.pdf')
    assert pdf.success, pdf.issues
    assert any(issue.feature == 'docx.page-geometry' and 'width, height' in issue.message for issue in pdf.issues)
    txt = write_document(model, tmp_path/'visible.txt')
    assert txt.success and not any(issue.feature == 'docx.page-geometry' for issue in txt.issues)
    assert od.document_to_json(model) == before
