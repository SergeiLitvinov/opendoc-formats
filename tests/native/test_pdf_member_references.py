"""Decoded references bind declarations in their own xref context, never target bodies."""

import hashlib
import json
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from tests.native.test_pdf_extends import xref
from tests.native.test_pdf_object_links import inspect
from tests.native.test_pdf_object_streams import custom_stream_pdf
from tests.native.test_pdf_xref_state import latest


@pytest.mark.parametrize('flate', [False, True])
@pytest.mark.parametrize('capture', [False, True])
def test_exact_reference_ranges_ignore_strings_hex_names_and_comments(flate, capture):
    body = (b'<< /Title (Own references) /Literal (8 0 R) /Hex <3820302052> /Name /8#200#20R '
            b'/Refs [% 9 0 R\n1 0 R 8 0 R 0 0 R 9 0 R 1 1 R 8 1 R] >>')
    source, decoded, _ = custom_stream_pdf(members=[body, b'(Own second member)'], flate=flate)
    original = bytes(source)
    snapshot = inspect(source, capture=capture)
    member = next(item for item in snapshot.items if item.kind == 'pdf-compressed-object'
                  and dict(item.details)['object'] == 7)
    references = dict(member.details)['indirect_references']
    expected = [b'1 0 R', b'8 0 R', b'0 0 R', b'9 0 R', b'1 1 R', b'8 1 R']
    assert len(references) == len(expected)
    for reference, spelling in zip(references, expected, strict=True):
        assert decoded[reference['decoded_start']:reference['decoded_end']] == spelling
        assert reference['sha256'] == hashlib.sha256(spelling).hexdigest()
    details = dict(snapshot.details)
    assert details['object_stream_member_reference_items'] == 6
    rows = details['compressed_member_reference_declarations']
    for context in ('historical', 'current'):
        assert [row['status'] for row in rows if row['source_context'] == context] == [
            'matched-uncompressed-declaration', 'matched-compressed-declaration', 'free-target',
            'missing-target', 'generation-mismatch', 'generation-mismatch',
        ]
    assert all(row['reference'] in references and row['source_member_locator'] == member.locator for row in rows)
    assert all(not row['target_body_resolved'] and not row['ownership_proven'] for row in rows)
    assert not details['object_stream_reference_links_assessed']
    assert details['object_stream_bound_member_reference_declarations_assessed']
    assert json.loads(json.dumps(snapshot.to_dict()))['details']['compressed_member_reference_declarations'] == rows
    pypdf = pytest.importorskip('pypdf')
    assert pypdf.PdfReader(BytesIO(source), strict=True).metadata.title == 'Own references'
    assert source == original


@pytest.mark.parametrize('state', ['same', 'changed-generation', 'free', 'unknown', 'compressed'])
def test_inherited_source_references_select_current_target_without_overwriting_history(state):
    source, _, _ = custom_stream_pdf(members=[b'<< /Title (Own source) /Ref 1 0 R >>'], flate=False)
    previous = latest(source)
    changed_offset = len(source)
    generation = 1 if state == 'changed-generation' else 0
    source += f'1 {generation} obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n'.encode()
    record = {'free': (0, 0, 1), 'unknown': (7, 0, 0), 'compressed': (2, 4, 0)}.get(
        state, (1, changed_offset, generation))
    source, current = xref(source, 10, {1: record}, previous=previous)
    rows = dict(inspect(source).details)['compressed_member_reference_declarations']
    historical, = [row for row in rows if row['source_context'] == 'historical']
    active, = [row for row in rows if row['source_context'] == 'current']
    assert historical['primary_xref'] == historical['target_xref'] == previous
    assert historical['status'] == 'matched-uncompressed-declaration'
    assert active['primary_xref'] == active['target_xref'] == current
    assert active['source_xref'] == previous
    assert active['status'] == {'same': 'matched-uncompressed-declaration',
                                'changed-generation': 'generation-mismatch', 'free': 'free-target',
                                'unknown': 'unknown-target', 'compressed': 'matched-compressed-declaration'}[state]
    assert not active['target_body_resolved']
    if state == 'same':
        assert active['target_offset'] == changed_offset != historical['target_offset']
    if state == 'compressed':
        # Declaration only: index zero actually contains object 7, not object 1.
        assert active['target_object_stream'] == 4 and active['target_index'] == 0


@pytest.mark.parametrize('state', ['same', 'changed', 'unsupported'])
def test_current_reference_projection_requires_confirmed_source_container_parameters(state):
    from tests.native.test_pdf_current_parameters import revised

    source = revised(state=state)[0]
    old = b'/Title (Own indirect parameters)'
    replacement = b'/Title (Own) /Ref 1 0 R'
    source = source.replace(old, replacement.ljust(len(old)))
    details = dict(inspect(source).details)
    rows = details['compressed_member_reference_declarations']
    assert len([row for row in rows if row['source_context'] == 'historical']) == 1
    assert len([row for row in rows if row['source_context'] == 'current']) == (1 if state == 'same' else 0)
    if state != 'same':
        assert details['compressed_object_current_links'][0]['status'].startswith('container-')


def test_free_source_member_does_not_create_current_reference_observations():
    source, _, _ = custom_stream_pdf(members=[b'<< /Ref 1 0 R >>'], flate=False)
    source, _ = xref(source, 10, {7: (0, 0, 1)}, previous=latest(source))
    rows = dict(inspect(source).details)['compressed_member_reference_declarations']
    assert len(rows) == 1 and rows[0]['source_context'] == 'historical'


@pytest.mark.parametrize('quota', ['max_items', 'max_pdf_tokens'])
def test_reference_inventory_and_projections_share_exact_global_quotas(monkeypatch, quota):
    from opendoc_formats.native import pdf_object_streams

    source, _, _ = custom_stream_pdf(members=[b'<< /Title (Own) /Refs [1 0 R 7 0 R] >>'], flate=False)
    original, measured = pdf_object_streams.declared_object_links, {}

    def observe(*args, **kwargs):
        result = original(*args, **kwargs)
        measured['tokens'] = args[3].tokens
        return result

    monkeypatch.setattr(pdf_object_streams, 'declared_object_links', observe)
    baseline = inspect(source)
    details = dict(baseline.details)
    if quota == 'max_pdf_tokens':
        maximum = measured['tokens']
    else:
        maximum = sum(1+len(dict(item.details)['entries']) for item in baseline.items if item.kind == 'pdf-xref-stream')
        maximum += sum(item.kind in {'pdf-object-stream', 'pdf-compressed-object'} for item in baseline.items)
        maximum += details['source_integer_work_items']+details['object_stream_link_work_items']
        maximum += details['object_stream_extends_work_items']+details['object_stream_member_reference_items']
    assert inspect(source, limits=replace(AnatomyLimits(), **{quota: maximum})).to_dict() == baseline.to_dict()
    with pytest.raises(ResourceLimitError, match=quota):
        inspect(source, limits=replace(AnatomyLimits(), **{quota: maximum-1}))


def test_cancel_during_member_reference_observation_preserves_source(monkeypatch):
    from opendoc_formats.native.pdf_syntax import Parser

    source, _, _ = custom_stream_pdf(members=[b'[1 0 R 7 0 R]'], flate=False)
    original, stop, initialize = bytes(source), Event(), Parser.__init__

    def initialize_observer(self, *args, **kwargs):
        observer = kwargs.get('reference_observer')
        if observer:
            def cancel(*values):
                observer(*values)
                stop.set()
            kwargs['reference_observer'] = cancel
        initialize(self, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Parser, '__init__', initialize_observer)
        with pytest.raises(OperationCancelledError):
            inspect(source, cancelled=stop.is_set)
    assert stop.is_set() and source == original
    assert dict(inspect(source).details)['object_stream_member_reference_items'] == 2
