"""Current ObjStm scalar witnesses survive inheritance and never authorize stale decoded members."""

import hashlib
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from tests.native.test_pdf_extends import collection, xref
from tests.native.test_pdf_source_integers import inspect, own_pdf
from tests.native.test_pdf_xref_state import latest


def revised(field='Length', *, state='same', inherited=False):
    original, _, values = own_pdf(indirect=(field,))
    number = {'N': 5, 'First': 6, 'Length': 7}[field]
    source = bytearray(original)
    records = {}
    offset = len(source)
    if not inherited:
        generation = 1 if state == 'generation' else 0
        header = 77 if state == 'header' else number
        value = values[field]+1 if state == 'changed' else values[field]
        body = {'unsupported': b'true', 'unterminated': b'42 43'}.get(state, str(value).encode())
        source += f'{header} {generation} obj\n'.encode()+body+b'\nendobj\n'
        records[number] = {'free': (0, 0, 1), 'unknown': (7, 0, 0), 'compressed': (2, 4, 0)}.get(
            state, (1, offset, generation))
    current = len(source)
    records[10] = (1, current, 0)
    raw = b''.join(bytes([kind])+target.to_bytes(4, 'big')+extra.to_bytes(2, 'big')
                   for kind, target, extra in records.values())
    ranges = ' '.join(f'{item} 1' for item in records)
    source += (f'10 0 obj\n<< /Type /XRef /Size 11 /Root 1 0 R /Info 8 0 R /W [1 4 2] '
               f'/Index [{ranges}] /Prev {latest(original)} /Length {len(raw)} >>\nstream\n'.encode()+raw
               +f'\nendstream\nendobj\nstartxref\n{current}\n%%EOF\n'.encode())
    return bytes(source), latest(original), current, offset, values[field]


@pytest.mark.parametrize('field', ['N', 'First', 'Length'])
@pytest.mark.parametrize('inherited', [False, True])
def test_current_equal_parameters_have_exact_xref_range_and_payload_witnesses(field, inherited):
    source, previous, current, offset, expected = revised(field, inherited=inherited)
    snapshot = inspect(source, capture=True)
    details = dict(snapshot.details)
    row, = details['compressed_object_current_links']
    assert row['status'] == 'matched-declared-member'
    assessment = row['current_parameters']
    assert assessment['status'] == 'matched-decoded-parameters'
    assert assessment['current_parameter_values'] == assessment['decoded_parameter_values'] == {field: expected}
    observation, = assessment['source_integer_observations'][field]
    assert observation['primary_xref'] == observation['context_xref'] == current
    assert observation['selected_xref'] == (previous if inherited else current)
    if not inherited:
        assert observation['offset'] == offset
    assert observation['sha256'] == hashlib.sha256(source[observation['offset']:observation['end']]).hexdigest()
    assert not observation['ownership_proven'] and not row['object_resolved']
    old_observation, = dict(next(item for item in snapshot.items if item.kind == 'pdf-object-stream').details)[
        'source_integer_observations'][field]
    assert old_observation['context_xref'] == previous
    pypdf = pytest.importorskip('pypdf')
    assert pypdf.PdfReader(BytesIO(source), strict=True).metadata.title == 'Own indirect parameters'


@pytest.mark.parametrize('field', ['N', 'First', 'Length'])
def test_changed_parameters_do_not_reuse_historical_decoded_members(field):
    source, _, _, _, old = revised(field, state='changed')
    details = dict(inspect(source).details)
    row, = details['compressed_object_current_links']
    assert row['status'] == 'container-changed-from-decoded-parameters'
    assert row['current_parameters']['current_parameter_values'][field] == old+1
    assert 'member_locator' not in row and not row['object_resolved']
    assert details['compressed_object_links'][0]['status'] == 'matched-declared-member'


@pytest.mark.parametrize('state', ['free', 'unknown', 'compressed', 'generation', 'header', 'unsupported', 'unterminated'])
def test_invalid_current_parameters_have_explicit_refusals_without_lexical_or_prev_repair(state):
    source, _, _, _, _ = revised(state=state)
    details = dict(inspect(source).details)
    row, = [item for item in details['compressed_object_current_links'] if item['object'] == 8]
    suffix = 'unsupported-current-parameter' if state in {'unsupported', 'compressed'} else 'invalid-current-parameter'
    assert row['status'] == 'container-'+suffix
    assert row['current_parameters']['parameter'] == 'Length'
    assert row['current_parameters']['parameter_reference'] == {'object': 7, 'generation': 0}
    assert row['current_parameters']['error'] and 'member_locator' not in row
    historical, = [item for item in details['compressed_object_links'] if item['object'] == 8]
    assert historical['status'] == 'matched-declared-member'


@pytest.mark.parametrize('state', ['same', 'unsupported'])
@pytest.mark.parametrize('field', ['max_items', 'max_total_bytes', 'max_pdf_tokens'])
def test_current_success_and_failed_parse_attempts_share_exact_global_quotas(state, field, monkeypatch):
    from opendoc_formats.native import pdf_object_streams

    source = revised(state=state)[0]
    actual, measured = pdf_object_streams.declared_object_links, {}

    def observed(sections, references, items, budget, maximum, **kwargs):
        result = actual(sections, references, items, budget, maximum, **kwargs)
        measured['tokens'] = budget.tokens
        return result

    monkeypatch.setattr(pdf_object_streams, 'declared_object_links', observed)
    baseline = inspect(source)
    details = dict(baseline.details)
    xrefs = [item for item in baseline.items if item.kind == 'pdf-xref-stream']
    if field == 'max_items':
        maximum = sum(1+len(dict(item.details)['entries']) for item in xrefs)
        maximum += sum(item.kind in {'pdf-object-stream', 'pdf-compressed-object'} for item in baseline.items)
        maximum += details['source_integer_work_items']+details['object_stream_link_work_items']
        maximum += details['object_stream_extends_work_items']
    elif field == 'max_total_bytes':
        maximum = sum(item.size for item in xrefs)+details['xref_decode_work_bytes']+details['object_stream_work_bytes']
    else:
        maximum = measured['tokens']
    assert inspect(source, limits=replace(AnatomyLimits(), **{field: maximum})).to_dict() == baseline.to_dict()
    with pytest.raises(ResourceLimitError, match=field):
        inspect(source, limits=replace(AnatomyLimits(), **{field: maximum-1}))


def test_cancel_during_current_scalar_read_is_not_converted_to_a_parameter_status(monkeypatch):
    from opendoc_formats.native.pdf_source_integers import SourceIntegers

    source = revised()[0]
    before, stop = bytes(source), Event()
    actual = SourceIntegers.read

    def read(self, *args, **kwargs):
        result = actual(self, *args, **kwargs)
        if kwargs.get('explicit_primary'):
            stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(SourceIntegers, 'read', read)
        with pytest.raises(OperationCancelledError):
            inspect(source, cancelled=stop.is_set)
    assert stop.is_set() and source == before
    assert dict(inspect(source).details)['compressed_object_current_links'][0]['status'] == 'matched-declared-member'


@pytest.mark.parametrize('changed', [False, True])
def test_historical_extends_discovery_does_not_merge_current_scalar_values_into_old_decode(changed):
    original, _, previous = collection()
    source = bytearray(original)
    raw = b'100 0 << /Title (New indirect) >>'
    container = len(source)
    source += b'4 0 obj\n<< /Type /ObjStm /N 1 /First 6 /Length 12 0 R >>\nstream\n'+raw+b'\nendstream\nendobj\n'
    scalar = len(source)
    source += b'12 0 obj\n'+str(len(raw)).encode()+b'\nendobj\n'
    source, declared = xref(source, 13, {4: (1, container, 0), 12: (1, scalar, 0)}, previous=previous)
    current_scalar = len(source)
    source += b'12 0 obj\n'+str(0 if changed else len(raw)).encode()+b'\nendobj\n'
    source, current = xref(source, 14, {12: (1, current_scalar, 0)}, previous=declared)
    snapshot = inspect(source)
    physical = next(item for item in snapshot.items if item.kind == 'pdf-object-stream'
                    and dict(item.details)['offset'] == container)
    details = dict(physical.details)
    assert details['xref_sections'] == sorted([declared, current])
    assert details['parameter_xref_contexts'] == [declared]
    assert details['source_integer_observations']['Length'][0]['value'] == len(raw)
    row, = dict(snapshot.details)['compressed_object_current_links']
    assert row['current_parameters']['source_integer_observations']['Length'][0]['offset'] == current_scalar
    assert row['status'] == ('container-changed-from-decoded-parameters' if changed else 'matched-declared-member')
    assert ('member_locator' in row) is not changed
