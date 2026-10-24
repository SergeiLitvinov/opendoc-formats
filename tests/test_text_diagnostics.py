"""Legacy views retain source uncertainty without inheriting target preservation claims."""

import json
from dataclasses import replace

import pytest
from opendoc_model import (
    Anchor,
    ArtifactLimitError,
    DiagnosticIssue,
    DocumentLimits,
    DocumentModel,
    IntegrationModel,
    IssueSeverity,
    Paragraph,
    PreservationRecord,
    PreservationState,
    Provenance,
    Section,
    document_from_json,
    document_to_json,
    get_integration,
    integration_from_dict,
    set_anchor,
    set_integration,
)

from opendoc_formats.readers import pdf
from opendoc_formats.support.document_adapters import document_to_text, text_to_document
from opendoc_formats.support.text_diagnostics import append_text_warning
from opendoc_formats.types import Block, BlockType, DocFormat, Text


def own_text():
    text = Text(plain='Own text', blocks=[Block(BlockType.PARAGRAPH, 'Own text')], source_format=DocFormat.PDF, pages=2)
    for page in (1, 2):
        append_text_warning(text, DiagnosticIssue(
            'pdf.own-warning', IssueSeverity.LOSS, 'Own repeated warning', f'own.pdf#page={page}',
            {'own_nested': {'values': [page]}}, 'own-source-uncertainty',
        ), Provenance('pdf', 'own.pdf', page=page, object_id=f'own-object-{page}'))
    return text


def test_two_text_model_json_cycles_retain_distinct_source_occurrences(tmp_path):
    from opendoc_formats import read_document

    text = own_text()
    original = text.to_dict()
    for _ in range(2):
        document = document_from_json(document_to_json(text_to_document(text)))
        text = document_to_text(document)
        assert text.to_dict() == original
        assert not text.diagnostics.assessment_complete
        assert [r.provenance.page for r in text.diagnostics.preservation] == [1, 2]
    path = tmp_path/'own.json'
    path.write_text(document_to_json(document), encoding='utf-8')
    result = read_document(path)
    assert result.success and not result.lossless and not result.assessment_complete
    assert len([i for i in result.issues if i.code == 'pdf.own-warning']) == 2


def test_text_dict_uses_public_model_envelope_and_detaches_nested_values():
    text = own_text()
    encoded = text.to_dict()['diagnostics']
    assert encoded['format'] == 'opendoc.integration' and encoded['version'] == 1
    restored = integration_from_dict(json.loads(json.dumps(encoded)))
    assert restored == text.diagnostics
    restored.preservation[0].issue.measurement['own_nested']['values'].append(99)
    assert text.diagnostics.preservation[0].issue.measurement['own_nested']['values'] == [1]
    assert replace(text, diagnostics=integration_from_dict(encoded)).to_dict() == text.to_dict()


@pytest.mark.parametrize('carrier', ['extra', 'measurement'])
@pytest.mark.parametrize('export', ['dict', 'model'])
def test_consumer_rejects_non_json_diagnostics_before_copy_hooks(carrier, export):
    class CopyAsJSON:
        calls = 0

        def __deepcopy__(self, memo):
            self.calls += 1
            return {'silently_coerced': True}

    foreign = CopyAsJSON()
    text = own_text()
    if carrier == 'extra':
        text.diagnostics.extra['own_foreign'] = foreign
    else:
        text.diagnostics.preservation[0].issue.measurement['own_foreign'] = foreign
    original = text.diagnostics
    with pytest.raises(ValueError, match='JSON value'):
        if export == 'dict':
            text.to_dict()
        else:
            text_to_document(text)
    assert foreign.calls == 0
    assert text.diagnostics is original and text.plain == 'Own text'
    values = original.extra if carrier == 'extra' else original.preservation[0].issue.measurement
    assert values['own_foreign'] is foreign


def test_legacy_dict_without_diagnostics_keeps_existing_shape():
    assert set(Text().to_dict()) == {
        'blocks', 'tables', 'plain', 'language', 'source_format', 'engine', 'warnings', 'pages',
    }
    assert not own_text().diagnostics.assessment_complete
    assert not Text(diagnostics=own_text().diagnostics)


def test_rich_projection_drops_positive_claims_and_detaches_source_node_refs():
    document = DocumentModel(source_format='html', metadata={
        'warnings': ['Own repeated warning'],
        'html': {'warnings': [{'message': 'Own repeated warning', 'feature': 'html.own', 'unknown': [7]}]},
    })
    node = Paragraph()
    set_anchor(node, Anchor('source-node'))
    document.sections = [Section(blocks=[node])]
    negative = PreservationRecord(
        DiagnosticIssue('html.own', IssueSeverity.LOSS, 'Own repeated warning', 'own.html#img',
                        {'legacy_warning_path': 'metadata.html.warnings[0]'}, 'own-unsupported'),
        PreservationState.LOST, node_id='source-node', provenance=Provenance('html', 'own.html'),
        extra={'unknown_record': {'items': [1]}},
    )
    positive = replace(negative, state=PreservationState.SEMANTIC)
    set_integration(document, IntegrationModel(preservation=(negative, positive), assessed_features=('html.own',),
                                               assessment_complete=True,
                                               extra={'unknown_integration': [2]}))
    text = document_to_text(document)
    assert text.warnings[:2] == ['Own repeated warning']*2
    source = next(record for record in text.diagnostics.preservation if record.issue.code == 'html.own')
    unassessed = next(record for record in text.diagnostics.preservation if record.issue.reason == 'legacy-warning-unassessed')
    assert source.state is PreservationState.LOST and source.node_id is None
    assert source.extra['opendoc_formats.legacy_source_node_id'] == 'source-node'
    assert source.issue.measurement['legacy_warning_path'] == 'metadata.warnings[1]'
    assert unassessed.state is PreservationState.OPAQUE
    assert unassessed.issue.reason == 'legacy-warning-unassessed'
    assert unassessed.issue.measurement['legacy_warning_path'] == 'metadata.warnings[0]'
    assert text.diagnostics.extra['unknown_integration'] == [2]
    assert not text.diagnostics.assessment_complete
    source.extra['unknown_record']['items'].append(3)
    text.diagnostics.extra['unknown_integration'].append(4)
    assert get_integration(document).preservation[0].extra['unknown_record']['items'] == [1]
    assert get_integration(document).extra['unknown_integration'] == [2]


def test_untyped_structured_warning_keeps_unknown_data_and_no_invented_provenance():
    warning = {'message': 'Own CSS uncertainty', 'feature': 'html.css', 'location': 'own.html#p', 'unknown': [1]}
    document = DocumentModel(source_format='html', metadata={'html': {'warnings': [warning]}})
    text = document_to_text(document)
    record = text.diagnostics.preservation[0]
    assert record.extra['source_warning'] == warning
    assert record.provenance.source_path is None and record.provenance.page is None
    warning['unknown'].append(2)
    assert record.extra['source_warning']['unknown'] == [1]


@pytest.mark.parametrize('warnings', [None, 'Own warning', [7], [{'feature': 'html.own'}]])
def test_invalid_legacy_warning_carrier_is_not_silently_discarded(warnings):
    with pytest.raises(ValueError, match='warnings'):
        document_to_text(DocumentModel(source_format='html', metadata={'warnings': warnings}))


@pytest.mark.parametrize('operation', ['text_dict', 'text_to_model', 'model_to_text'])
def test_selected_model_budget_is_enforced_for_diagnostics(operation):
    text, limits = own_text(), DocumentLimits(max_nodes=1)
    with pytest.raises(ArtifactLimitError):
        if operation == 'text_dict':
            text.to_dict(limits=limits)
        elif operation == 'text_to_model':
            text_to_document(text, limits=limits)
        else:
            document_to_text(text_to_document(text), limits=limits)


@pytest.mark.parametrize('available', [False, True])
def test_empty_pdf_result_distinguishes_unavailable_backends_from_no_content(monkeypatch, available):
    monkeypatch.setattr(pdf, 'missing_backends', lambda names: [] if available else list(names))
    for name in ('_with_pdfplumber', '_with_pypdf', '_with_pymupdf'):
        monkeypatch.setattr(pdf, name, lambda path: Text(source_format=DocFormat.PDF, pages=2))
    result = pdf.read_pdf('own.pdf')
    assert not result
    record = result.diagnostics.preservation[0]
    assert record.issue.code == ('pdf.text-no-content' if available else 'pdf.text-backend-unavailable')
    assert record.state is PreservationState.OPAQUE
    assert record.provenance.source_path == 'own.pdf'


def test_fallback_rebases_prior_and_page_diagnostics_without_message_deduplication(monkeypatch):
    first, second = own_text(), own_text()
    first.plain = ''
    first.blocks = []
    monkeypatch.setattr(pdf, 'missing_backends', lambda names: [])
    monkeypatch.setattr(pdf, '_with_pdfplumber', lambda path: first)
    monkeypatch.setattr(pdf, '_with_pypdf', lambda path: second)
    result = pdf.read_pdf('own.pdf')
    assert result.warnings == ['Own repeated warning']*4
    assert [r.issue.measurement['legacy_warning_path'] for r in result.diagnostics.preservation] == [
        f'metadata.warnings[{i}]' for i in range(4)
    ]


@pytest.mark.parametrize('format_name', ['html', 'epub'])
def test_missing_text_backend_has_typed_source_diagnostics(tmp_path, monkeypatch, format_name):
    import builtins

    from opendoc_formats.readers.epub import read_epub
    from opendoc_formats.readers.html_text import read_html

    original_import = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == 'bs4':
            raise ImportError('Own absent backend')
        return original_import(name, *args, **kwargs)

    source = tmp_path/f'own.{format_name}'
    source.write_text('<p>Own text</p>', encoding='utf-8')
    original = source.read_bytes()
    monkeypatch.setattr(builtins, '__import__', unavailable)
    result = (read_html if format_name == 'html' else read_epub)(source)
    assert not result
    record = result.diagnostics.preservation[0]
    assert record.issue.code == f'{format_name}.text-backend-unavailable'
    assert record.provenance.source_path == str(source)
    assert source.read_bytes() == original


def test_pypdf_decoding_cleanup_is_explicit_uncertainty(monkeypatch):
    import sys
    from types import SimpleNamespace

    pages = [SimpleNamespace(extract_text=lambda: 'Own\x00\x00\x00\ufffdtext')]
    monkeypatch.setitem(sys.modules, 'pypdf', SimpleNamespace(PdfReader=lambda path: SimpleNamespace(pages=pages)))
    result = pdf._with_pypdf('own.pdf')
    assert result.plain == 'Owntext'
    record = result.diagnostics.preservation[0]
    assert record.issue.code == 'pdf.text-decoding-cleanup'
    assert record.issue.measurement['nul_count'] == 3
    assert record.issue.measurement['replacement_count'] == 1
    assert record.state is PreservationState.OPAQUE
