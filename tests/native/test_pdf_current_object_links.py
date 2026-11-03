"""Current xref selection rebinds inherited users without rewriting historical evidence."""

import builtins
import hashlib
import json
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from tests.native.test_pdf_object_links import inspect
from tests.native.test_pdf_object_streams import custom_stream_pdf
from tests.native.test_pdf_source_integers import appended, own_pdf
from tests.native.test_pdf_xref_state import hybrid_pdf, latest


def inherited_revision(*, state='stream', member_state=None):
    original, _, locations = custom_stream_pdf(members=[b'(Old own member)'], flate=False)
    source = bytearray(original)
    target = len(source)
    generation = 2 if state == 'nonzero' else 0
    if state in ('stream', 'ordinary', 'nonzero'):
        raw = b'7 0 (New own member)'
        body = (b'<< /Type /ObjStm /N 1 /First 4 /Length '+str(len(raw)).encode()
                +b' >>\nstream\n'+raw+b'\nendstream') if state == 'stream' else b'42'
        source += f'4 {generation} obj\n'.encode()+body+b'\nendobj\n'
        record = (1, target, generation)
    else:
        record = {'free': (0, 0, 1), 'unknown': (7, 0, 0), 'compressed': (2, 4, 0)}[state]
    records = {4: record}
    if member_state is not None:
        records[7] = {'free': (0, 0, 1), 'unknown': (7, 0, 0), 'direct': (1, target, generation)}[member_state]
    current = len(source)
    records[11] = (1, current, 0)
    raw = b''.join(bytes([kind])+offset.to_bytes(4, 'big')+extra.to_bytes(2, 'big')
                   for kind, offset, extra in records.values())
    ranges = ' '.join(f'{number} 1' for number in records)
    source += (f'11 0 obj\n<< /Type /XRef /Size 12 /Root 1 0 R /Info 7 0 R /W [1 4 2] '
               f'/Index [{ranges}] /Prev {latest(original)} /Length {len(raw)} >>\nstream\n'.encode()+raw
               +f'\nendstream\nendobj\nstartxref\n{current}\n%%EOF\n'.encode())
    return bytes(source), latest(original), locations[4], target, current


def test_inherited_user_selects_new_container_in_current_context_and_keeps_old_evidence():
    source, previous, old_container, new_container, current = inherited_revision()
    before = hashlib.sha256(source).hexdigest()
    snapshot = inspect(source, capture=True)
    details = dict(snapshot.details)
    historical, = details['compressed_object_links']
    selected, = details['compressed_object_current_links']
    assert historical['xref_offset'] == selected['xref_offset'] == previous
    assert historical['container_offset'] == old_container
    assert selected['container_offset'] == new_container
    assert selected['context_xref'] == selected['primary_xref'] == selected['container_xref'] == current
    assert details['object_stream_current_links_xref'] == current
    assert details['object_stream_current_declared_links_assessed']
    items = {item.locator: item for item in snapshot.items}
    assert items[historical['member_locator']].payload == b'(Old own member)'
    assert items[selected['member_locator']].payload == b'(New own member)'
    assert selected['member_sha256'] == hashlib.sha256(b'(New own member)').hexdigest()
    assert not selected['object_resolved'] and not selected['ownership_proven']
    assert not details['assessment_complete'] and hashlib.sha256(source).hexdigest() == before
    assert inspect(source).to_dict() == snapshot.to_dict()
    json.dumps(snapshot.to_dict())
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(source), strict=True)
    assert reader.get_object(pypdf.generic.IndirectObject(7, 0, reader)) == 'New own member'


@pytest.mark.parametrize('state,status', [
    ('free', 'missing-container'), ('unknown', 'missing-container'),
    ('compressed', 'container-not-uncompressed'), ('ordinary', 'container-not-object-stream'),
    ('nonzero', 'nonzero-container-generation'),
])
def test_inherited_user_never_resurrects_a_replaced_or_missing_container(state, status):
    source, _, _, _, current = inherited_revision(state=state)
    details = dict(inspect(source).details)
    selected, = [row for row in details['compressed_object_current_links'] if row['object'] == 7]
    assert selected['status'] == status and selected['context_xref'] == current
    assert 'member_locator' not in selected
    historical, = [row for row in details['compressed_object_links'] if row['object'] == 7]
    assert historical['status'] == 'matched-declared-member'


@pytest.mark.parametrize('state', ['free', 'unknown', 'direct'])
def test_current_projection_omits_users_shadowed_by_noncompressed_records(state):
    source, _, _, _, _ = inherited_revision(member_state=state)
    details = dict(inspect(source).details)
    assert not details['compressed_object_current_links']
    assert details['compressed_object_links'][0]['status'] == 'matched-declared-member'


def test_inherited_indirect_parameters_require_current_context_evidence():
    original, locations, values = own_pdf()
    source, current = appended(original, locations, values, value=0, include_container=False)
    details = dict(inspect(source).details)
    row, = details['compressed_object_current_links']
    assert row['context_xref'] == current
    assert row['status'] == 'container-changed-from-decoded-parameters'
    assert row['current_parameters']['current_parameter_values']['Length'] == 0
    assert 'member_locator' not in row
    assert details['compressed_object_links'][0]['status'] == 'matched-declared-member'


@pytest.mark.parametrize('field', ['max_items', 'max_pdf_tokens'])
def test_current_projection_shares_exact_aggregate_quotas(field, monkeypatch):
    from opendoc_formats.native import pdf_object_streams

    actual = pdf_object_streams.declared_object_links
    measured = {}

    def observed(sections, references, items, budget, maximum, **kwargs):
        result = actual(sections, references, items, budget, maximum, **kwargs)
        measured['tokens'] = budget.tokens
        return result

    monkeypatch.setattr(pdf_object_streams, 'declared_object_links', observed)
    source, _, _, _, _ = inherited_revision()
    baseline = inspect(source)
    if field == 'max_items':
        details = dict(baseline.details)
        maximum = sum(1+len(dict(item.details)['entries']) for item in baseline.items if item.kind == 'pdf-xref-stream')
        maximum += sum(item.kind in {'pdf-object-stream', 'pdf-compressed-object'} for item in baseline.items)
        maximum += details['object_stream_link_work_items']+details['object_stream_extends_work_items']
    else:
        maximum = measured['tokens']
    assert inspect(source, limits=replace(AnatomyLimits(), **{field: maximum})).to_dict() == baseline.to_dict()
    with pytest.raises(ResourceLimitError):
        inspect(source, limits=replace(AnatomyLimits(), **{field: maximum-1}))


def test_current_projection_needs_no_optional_backend(monkeypatch):
    source = inherited_revision()[0]
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in {'pypdf', 'pymupdf', 'fitz', 'PIL', 'pdfplumber', 'fontTools', 'lxml'}:
            raise AssertionError('Unexpected native backend: '+name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    assert dict(inspect(source).details)['compressed_object_current_links'][0]['status'] == 'matched-declared-member'


@pytest.mark.parametrize('override', [None, 'direct', 'free'])
def test_current_projection_uses_explicit_hybrid_primary_priority(override):
    source, supplement, _ = hybrid_pdf(table_entry=override)
    details = dict(inspect(source).details)
    rows = details['compressed_object_current_links']
    if override is None:
        row, = rows
        assert row['xref_offset'] == supplement and row['primary_xref'] == latest(source)
        assert row['status'] == 'matched-declared-member'
    else:
        assert rows == []


def test_cancel_when_selecting_current_inherited_users_preserves_source_and_scope(monkeypatch):
    from opendoc_formats.native import pdf_object_links

    source, _, _, _, current = inherited_revision()
    before, stop = bytes(source), Event()
    actual = pdf_object_links.resolve_xrefs

    def selected(sections, primary, *args, **kwargs):
        result = actual(sections, primary, *args, **kwargs)
        if primary == current:
            stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(pdf_object_links, 'resolve_xrefs', selected)
        with pytest.raises(OperationCancelledError):
            inspect(source, cancelled=stop.is_set)
    assert stop.is_set() and source == before
    assert dict(inspect(source).details)['compressed_object_current_links'][0]['status'] == 'matched-declared-member'
