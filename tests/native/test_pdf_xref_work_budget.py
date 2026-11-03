"""Source syntax and selected-index traversal must consume one bounded operation budget."""

import builtins
from dataclasses import replace

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import ResourceLimitError
from tests.binary_fixtures import own_pdf
from tests.native.test_pdf_xref_state import append_classic, hybrid_pdf
from tests.native.test_pdf_xref_streams import own_stream_pdf


def fixture(kind):
    if kind == 'stream':
        return own_stream_pdf()[0]
    if kind == 'hybrid':
        return hybrid_pdf(table_entry='direct')[0]
    source = own_pdf()[0]
    if kind == 'incremental':
        source = append_classic(source)[0]
        source = append_classic(source, generation=1, free=True)[0]
    return source


def inspect(source, maximum=200_000, *, resolve=True):
    return inspect_binary(source, pdf_source=True, pdf_decode_xrefs=True, pdf_resolve_xrefs=resolve,
                          limits=replace(AnatomyLimits(), max_pdf_tokens=maximum))


def syntax_threshold(source):
    low, high = 0, 200_000
    while low + 1 < high:
        middle = (low + high) // 2
        try:
            inspect(source, middle, resolve=False)
        except ResourceLimitError as error:
            assert 'max_pdf_tokens' in str(error)
            low = middle
        else:
            high = middle
    return high


@pytest.mark.parametrize('kind', ['classic', 'stream', 'incremental', 'hybrid'])
def test_selection_adds_exact_shared_work_after_source_syntax(kind):
    source = fixture(kind)
    baseline = inspect(source)
    details = dict(baseline.details)
    sections = {dict(item.details)['offset']: dict(item.details) for item in baseline.items
                if item.kind in ('pdf-classic-xref', 'pdf-xref-stream')}
    # Work is per visited primary and per examined source record, including shadowed entries.
    extra = sum(len(sections[entry['xref_offset']]['entries']) + (entry['role'] == 'primary')
                for entry in details['xref_search_order'])
    syntax = syntax_threshold(source)
    with pytest.raises(ResourceLimitError, match='max_pdf_tokens exceeded by xref lookup'):
        inspect(source, syntax)
    assert inspect(source, syntax + extra).to_dict() == baseline.to_dict()
    with pytest.raises(ResourceLimitError, match='max_pdf_tokens exceeded by xref lookup'):
        inspect(source, syntax + extra - 1)
    assert all(not entry['object_resolved'] and not entry['ownership_proven']
               for entry in details['effective_xref_entries'])


def test_late_index_quota_keeps_source_and_existing_dissection_unchanged(tmp_path, monkeypatch):
    from tools.document_anatomy import main
    source = fixture('hybrid')
    path, destination = tmp_path / 'own.pdf', tmp_path / 'previous'
    path.write_bytes(source)
    destination.mkdir()
    marker = destination / 'keep.txt'
    marker.write_bytes(b'Previous dissection')
    monkeypatch.setattr('sys.argv', ['document_anatomy', str(path), '--pdf-source', '--pdf-decode-xrefs',
                                     '--pdf-resolve-xrefs', '--max-pdf-tokens', str(syntax_threshold(source)),
                                     '--output', str(destination)])
    with pytest.raises(ResourceLimitError, match='xref lookup'):
        main()
    assert path.read_bytes() == source and marker.read_bytes() == b'Previous dissection'
    assert list(destination.iterdir()) == [marker]


def test_source_index_budget_never_imports_pdf_or_image_backend(monkeypatch):
    source = fixture('incremental')
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in {'pypdf', 'pymupdf', 'fitz', 'PIL', 'pdfplumber', 'fontTools'}:
            raise AssertionError('Unexpected source-inspection backend: ' + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    assert dict(inspect(source).details)['xref_record_selection_complete']
