"""EPUB diagnostic staging has an explicit quota and preserves the SDK's final atomic budget checks."""

from threading import Event

import pytest
from opendoc_model import ArtifactLimitError, DocumentLimits, DocumentModel, document_to_json

from opendoc_formats import ImportOptions, read_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.readers.epub_diagnostics import EpubDiagnostics
from opendoc_formats.readers.epub_model import read_epub_model
from tests.readers.test_epub_interactive_diagnostics import source_book


@pytest.mark.parametrize('limits,maximum', [(None, 10_000), (DocumentLimits(max_nodes=2), 2)])
def test_staging_accepts_exact_record_count_and_refuses_next_without_appending(tmp_path, limits, maximum):
    diagnostics = EpubDiagnostics(tmp_path/'own.epub', limits=limits)
    for _ in range(maximum):
        diagnostics.lost('epub.control', 'unsupported-control', 'Own unsupported object', 'chapter.xhtml')
    before = tuple(diagnostics.records)
    with pytest.raises(ArtifactLimitError) as captured:
        diagnostics.lost('epub.control', 'unsupported-control', 'Next object', 'chapter.xhtml')
    error = captured.value
    assert (error.quota, error.maximum, error.path) == ('diagnostic objects', maximum, f'epub.diagnostics[{maximum}]')
    assert tuple(diagnostics.records) == before


def test_selected_limits_reach_direct_and_registered_reader_with_located_failure(tmp_path):
    source = tmp_path/'limits.epub'
    original = source_book(source, '<input id="one"/><input id="two"/>')
    limits = DocumentLimits(max_nodes=2)
    with pytest.raises(ArtifactLimitError) as captured:
        read_epub_model(source, limits=limits)
    assert captured.value.quota == 'diagnostic objects' and captured.value.maximum == 2
    result = read_document(source, options=ImportOptions(document_limits=limits))
    assert not result.success and result.document is None
    issue, = result.issues
    assert issue.code == 'import.document-limit' and issue.reason == 'document-limit'
    assert issue.location == f'{source}#epub.diagnostics[2]'
    assert issue.measurement['quota'] == 'diagnostic objects' and issue.measurement['maximum'] == 2
    assert source.read_bytes() == original
    assert read_document(source).success


def test_attach_inherits_selected_sdk_budget_and_keeps_model_unchanged_on_failure(tmp_path):
    diagnostics = EpubDiagnostics(tmp_path/'own.epub', limits=DocumentLimits(max_bytes=1))
    diagnostics.lost('epub.control', 'unsupported-control', 'Own unsupported object', 'chapter.xhtml')
    model = DocumentModel()
    before = document_to_json(model)
    with pytest.raises(ArtifactLimitError):
        diagnostics.attach(model)
    assert document_to_json(model) == before


def test_cancellation_is_not_reclassified_as_staging_limit(tmp_path):
    stop = Event()
    diagnostics = EpubDiagnostics(tmp_path/'own.epub', limits=DocumentLimits(max_nodes=1), cancelled=stop.is_set)
    diagnostics.lost('epub.control', 'unsupported-control', 'Own unsupported object', 'chapter.xhtml')
    stop.set()
    with pytest.raises(OperationCancelledError):
        diagnostics.lost('epub.control', 'unsupported-control', 'Next object', 'chapter.xhtml')
    assert len(diagnostics.records) == 1
