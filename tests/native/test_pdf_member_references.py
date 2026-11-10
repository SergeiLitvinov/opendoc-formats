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
    target = next(item for item in snapshot.items if item.kind == 'pdf-compressed-object'
                  and dict(item.details)['object'] == 8)
    for row in rows:
        if row['status'] == 'matched-compressed-declaration':
            assert row['target_member_status'] == 'matched-declared-member'
            assert row['target_member_locator'] == target.locator
            assert row['target_member_sha256'] == target.sha256 == hashlib.sha256(b'(Own second member)').hexdigest()
            span = row['target_decoded_range']
            assert decoded[span['start']:span['end']] == b'(Own second member)'
    assert all(row['reference'] in references and row['source_member_locator'] == member.locator for row in rows)
    assert all(not row['target_body_resolved'] and not row['ownership_proven'] for row in rows)
    assert details['object_stream_target_header_work_bytes'] == len(b'1 0 obj\n')
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
        for row in (historical, active):
            assert row['target_header_status'] == 'matched-header'
            assert row['target_range_status'] == 'disjoint-from-inspected-ranges'
            assert row['target_header_range'] == {'offset': row['target_offset'], 'length': len(b'1 0 obj')}
            assert row['target_header_sha256'] == hashlib.sha256(b'1 0 obj').hexdigest()
    if state == 'compressed':
        # Index zero actually contains object 7, not object 1.
        assert active['target_object_stream'] == 4 and active['target_index'] == 0
        assert active['target_member_status'] == 'object-number-mismatch'
        assert 'target_member_locator' not in active


@pytest.mark.parametrize('prefix,status', [(b'2 0 obj', 'header-mismatch'), (b'1 1 obj', 'header-mismatch'),
                                          (b' 1 0 obj', 'header-mismatch'), (b'null', 'invalid-header-syntax')])
def test_uncompressed_target_checks_only_the_selected_offset(prefix, status):
    source, _, _ = custom_stream_pdf(members=[b'<< /Ref 1 0 R >>'], flate=False)
    offset = len(source)
    source, _ = xref(source+prefix+b'\nnull\nendobj\n', 10, {1: (1, offset, 0)}, previous=latest(source))
    historical, current = dict(inspect(source).details)['compressed_member_reference_declarations']
    assert historical['target_header_status'] == 'matched-header'
    assert current['status'] == 'matched-uncompressed-declaration'
    assert current['target_header_status'] == status and current['target_offset'] == offset
    assert 'target_header_range' not in current and not current['target_body_resolved']


@pytest.mark.parametrize('body,status', [
    (b'[null 2 0 R (literal endobj)]\nendobj', 'matched-ordinary-body'),
    (b'42\nendobj', 'matched-ordinary-body'),
    (b'null true\nendobj', 'missing-endobj'),
    (b'<< /X >>\nendobj', 'invalid-body-syntax'),
    (b'<< /Length 6 >>\nstream\nendobj\nendstream\nendobj', 'matched-stream-body'),
    (b'<< /Length 0 >>\r\nstream\r\nendstream\r\nendobj', 'matched-stream-body'),
    (b'<< /Length 2 >>\nstream\nendobj\nendstream\nendobj', 'invalid-body-syntax'),
    (b'<< /Length -1 >>\nstream\nendstream\nendobj', 'invalid-stream-length'),
    (b'<< /Length 7 0 R >>\nstream\nendstream\nendobj', 'unsupported-indirect-stream-length'),
    (b'<< /Length 0 /F (external.bin) >>\nstream\nendstream\nendobj', 'external-stream-not-assessed'),
])
def test_uncompressed_target_body_reports_exact_range_or_reason(body, status):
    source, _, _ = custom_stream_pdf(members=[b'<< /Ref 1 0 R >>'], flate=False)
    offset = len(source)
    target = b'1 0 obj\n'+body
    source, _ = xref(source+target+b'\n', 10, {1: (1, offset, 0)}, previous=latest(source))
    historical, current = dict(inspect(source).details)['compressed_member_reference_declarations']
    assert historical['target_body_status'] == 'matched-ordinary-body'
    assert current['target_header_status'] == 'matched-header' and current['target_body_status'] == status
    assert not current['target_body_resolved'] and not current['ownership_proven']
    if status in {'matched-ordinary-body', 'matched-stream-body'}:
        assert current['target_object_range'] == {'offset': offset, 'length': len(target)}
        assert current['target_object_sha256'] == hashlib.sha256(target).hexdigest()
    else:
        assert 'target_object_range' not in current
    if status == 'matched-stream-body':
        extent = current['target_stream_extent']
        expected = b'endobj' if b'/Length 6' in body else b''
        assert source[extent['encoded_start']:extent['encoded_end']] == expected
        assert extent['encoded_start'] == offset+target.index(b'stream')+len(b'stream')+(2 if b'\r\n' in body else 1)


@pytest.mark.parametrize('state', ['same', 'changed', 'free'])
def test_indirect_stream_length_uses_each_revision_selection(state):
    source, _, _ = custom_stream_pdf(members=[b'<< /Ref 1 0 R >>'], flate=False)
    previous = latest(source)
    target = len(source)
    source += b'1 0 obj\n<< /Length 5 0 R >>\nstream\nendobj\nendstream\nendobj\n'
    scalar = len(source)
    source += b'5 0 obj\n6\nendobj\n'
    source, intermediate = xref(source, 10, {1: (1, target, 0), 5: (1, scalar, 0), 7: (2, 4, 0)}, previous=previous)
    replacement = len(source)
    source += b'5 0 obj\n'+(b'5' if state == 'changed' else b'6')+b'\nendobj\n'
    record = (0, 0, 1) if state == 'free' else (1, replacement, 0)
    source, current = xref(source, 11, {5: record}, previous=intermediate)
    snapshot = inspect(source)
    details = dict(snapshot.details)
    rows = details['compressed_member_reference_declarations']
    historical, = [row for row in rows if row['primary_xref'] == intermediate]
    active, = [row for row in rows if row['primary_xref'] == current]
    assert historical['target_body_status'] == 'matched-stream-body'
    assert historical['target_stream_length_observation']['offset'] == scalar
    assert active['target_body_status'] == {'same': 'matched-stream-body', 'changed': 'invalid-body-syntax',
                                           'free': 'invalid-indirect-stream-length'}[state]
    if state != 'free':
        assert active['target_stream_length_observation']['offset'] == replacement
        assert active['target_stream_length_observation']['primary_xref'] == current
    if state == 'same':
        assert active['target_object_sha256'] == historical['target_object_sha256']
        maximum = sum(item.size for item in snapshot.items if item.kind == 'pdf-xref-stream')
        maximum += details['xref_decode_work_bytes']+details['object_stream_work_bytes']
        assert inspect(source, limits=replace(AnatomyLimits(), max_total_bytes=maximum)).to_dict() == snapshot.to_dict()
        with pytest.raises(ResourceLimitError, match='max_total_bytes'):
            inspect(source, limits=replace(AnatomyLimits(), max_total_bytes=maximum-1))
    else:
        assert 'target_object_range' not in active


def test_stream_length_spelling_inside_its_payload_is_reported_as_overlapping():
    source, _, _ = custom_stream_pdf(members=[b'<< /Ref 1 0 R >>'], flate=False)
    previous = latest(source)
    template = b'5 0 obj\n%02d\nendobj'
    payload = template % len(template % 0)
    prefix = b'1 0 obj\n<< /Length 5 0 R >>\nstream\n'
    outer = len(source)
    inner = outer+len(prefix)
    source, _ = xref(source+prefix+payload+b'\nendstream\nendobj\n', 10,
                     {1: (1, outer, 0), 5: (1, inner, 0)}, previous=previous)
    _, active = dict(inspect(source).details)['compressed_member_reference_declarations']
    assert active['target_body_status'] == 'matched-stream-body'
    assert active['target_range_status'] == active['target_stream_length_range_status'] == 'overlap'
    assert active['target_range_overlap'] == {'offset': inner, 'length': len(payload)}
    assert active['target_stream_length_range_overlap'] == active['target_object_range']
    assert not active['ownership_proven'] and not active['target_body_resolved']


def test_object_spelling_inside_known_stream_is_reported_as_overlapping():
    source, _, _ = custom_stream_pdf(members=[b'[1 0 R 2 0 R 6 0 R]'], flate=False)
    previous = latest(source)
    payload = b'1 0 obj\nnull\nendobj'
    prefix = f'2 0 obj\n<< /Length {len(payload)} >>\nstream\n'.encode()
    outer = len(source)
    inner = outer+len(prefix)
    source, _ = xref(source+prefix+payload+b'\nendstream\nendobj\n', 10,
                     {1: (1, inner, 0), 2: (1, outer, 0)}, previous=previous)
    rows = dict(inspect(source).details)['compressed_member_reference_declarations']
    selected = {row['reference']['object']: row for row in rows if row['source_context'] == 'current'}
    assert selected[1]['target_body_status'] == 'matched-ordinary-body'
    assert selected[2]['target_body_status'] == 'matched-stream-body'
    for obj, other in ((1, 2), (2, 1)):
        assert selected[obj]['target_range_status'] == 'overlap'
        assert selected[obj]['target_range_overlap'] == selected[other]['target_object_range']
        assert not selected[obj]['ownership_proven'] and not selected[obj]['target_body_resolved']
    assert selected[6]['target_body_status'] == 'matched-stream-body'
    assert selected[6]['target_range_status'] == 'disjoint-from-inspected-ranges'


@pytest.mark.parametrize('state', ['inherited', 'wrong-index', 'noninteger', 'wrong-generation'])
def test_stream_length_from_compressed_member_uses_selected_member_identity(state):
    value = b'true' if state == 'noninteger' else b'6'
    source, _, _ = custom_stream_pdf(members=[b'<< /Ref 1 0 R >>', value], flate=True)
    previous = latest(source)
    generation = b'1' if state == 'wrong-generation' else b'0'
    target = b'1 0 obj\n<< /Length 8 '+generation+b' R >>\nstream\nendobj\nendstream\nendobj'
    records = {1: (1, len(source), 0), 7: (2, 4, 0)}
    if state == 'wrong-index':
        records[8] = (2, 4, 0)
    source, current = xref(source+target+b'\n', 10, records, previous=previous)
    snapshot = inspect(source, capture=False)
    rows = dict(snapshot.details)['compressed_member_reference_declarations']
    status = {'inherited': 'matched-stream-body', 'wrong-index': 'invalid-indirect-stream-length',
              'noninteger': 'unsupported-indirect-stream-length', 'wrong-generation': 'invalid-indirect-stream-length'}[state]
    selected = [row for row in rows if row['primary_xref'] == current]
    assert {row['source_context'] for row in selected} == {'historical', 'current'}
    for row in selected:
        assert row['target_body_status'] == status
        if state == 'inherited':
            observation = row['target_stream_length_observation']
            assert observation['primary_xref'] == current and observation['selected_xref'] == previous
            assert observation['value'] == 6 and observation['sha256'] == hashlib.sha256(b'6').hexdigest()
            assert row['target_object_sha256'] == hashlib.sha256(target).hexdigest()
        else:
            assert 'target_object_range' not in row


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


def test_inherited_target_requires_a_member_check_in_the_same_projection():
    source, _, _ = custom_stream_pdf(members=[b'<< /Ref 8 0 R >>', b'<< /Ref 7 0 R >>'], flate=False)
    previous = latest(source)
    source, current = xref(source, 10, {7: (2, 4, 0)}, previous=previous)
    rows = dict(inspect(source).details)['compressed_member_reference_declarations']
    relevant = [row for row in rows if row['reference']['object'] == 8]
    assert [(row['source_context'], row['primary_xref'], row['target_member_status']) for row in relevant] == [
        ('historical', current, 'matched-declared-member'),
        ('historical', previous, 'matched-declared-member'),
        ('current', current, 'matched-declared-member'),
    ]
    assert len({row['target_member_locator'] for row in relevant}) == 1
    assert len(rows) == 5  # A target check does not traverse its own references.
    assert all(not row['target_body_resolved'] for row in rows)


@pytest.mark.parametrize('state', ['inherited', 'same', 'changed', 'unsupported'])
def test_intermediate_revision_requires_matching_scalar_value(state):
    from tests.native.test_pdf_source_integers import own_pdf

    original, _, values = own_pdf(indirect=('Length',))
    title = b'/Title (Own indirect parameters)'
    source = original.replace(title, b'/Ref 1 0 R'.ljust(len(title)))
    records = {8: (2, 4, 0)}
    scalar_offset = len(source)
    if state != 'inherited':
        records[7] = (1, scalar_offset, 0)
        value = 'true' if state == 'unsupported' else str(values['Length']+int(state == 'changed'))
        source += f'7 0 obj\n{value}\nendobj\n'.encode()
    source, intermediate = xref(source, 10, records, previous=latest(original))
    source, _ = xref(source, 11, {}, previous=intermediate)

    snapshot = inspect(source)
    details = dict(snapshot.details)
    row, = [row for row in details['compressed_object_links'] if row['primary_xref'] == intermediate]
    references = details['compressed_member_reference_declarations']
    assert any(ref['primary_xref'] == latest(original) for ref in references)
    matched = state in {'inherited', 'same'}
    assert any(ref['primary_xref'] == intermediate for ref in references) is matched
    assert ('member_locator' in row) is matched
    assert row['status'] == {'changed': 'container-changed-from-decoded-parameters',
                             'unsupported': 'container-unsupported-historical-parameter'}.get(
                                 state, 'matched-declared-member')
    if state in {'same', 'changed'}:
        assessment = row['historical_parameters']
        assert assessment['historical_parameter_values']['Length'] == int(value)
        observation, = assessment['source_integer_observations']['Length']
        assert observation['primary_xref'] == intermediate and observation['offset'] == scalar_offset
    elif state == 'unsupported':
        assert row['historical_parameters']['parameter'] == 'Length'
    if state == 'same':
        maximum = sum(1+len(dict(item.details)['entries']) for item in snapshot.items if item.kind == 'pdf-xref-stream')
        maximum += sum(item.kind in {'pdf-object-stream', 'pdf-compressed-object'} for item in snapshot.items)
        maximum += sum(details[field] for field in ('source_integer_work_items', 'object_stream_link_work_items',
                                                    'object_stream_extends_work_items', 'object_stream_member_reference_items'))
        assert inspect(source, limits=replace(AnatomyLimits(), max_items=maximum)).to_dict() == snapshot.to_dict()
        with pytest.raises(ResourceLimitError, match='max_items'):
            inspect(source, limits=replace(AnatomyLimits(), max_items=maximum-1))


@pytest.mark.parametrize('quota', ['max_items', 'max_pdf_tokens', 'max_total_bytes'])
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
    elif quota == 'max_items':
        maximum = sum(1+len(dict(item.details)['entries']) for item in baseline.items if item.kind == 'pdf-xref-stream')
        maximum += sum(item.kind in {'pdf-object-stream', 'pdf-compressed-object'} for item in baseline.items)
        maximum += details['source_integer_work_items']+details['object_stream_link_work_items']
        maximum += details['object_stream_extends_work_items']+details['object_stream_member_reference_items']
    else:
        maximum = sum(item.size for item in baseline.items if item.kind == 'pdf-xref-stream')
        maximum += details['xref_decode_work_bytes']+details['object_stream_work_bytes']
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
