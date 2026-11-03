"""CFBF reserved header findings retain data and do not weaken allocation/profile rejection."""

import json
import struct
from threading import Event

import pytest

from opendoc_formats.anatomy import inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, UnsupportedDocumentError
from tests.binary_fixtures import own_cfbf


def original(version=3, *, patches=()):
    source = bytearray(own_cfbf(version=version)[0])
    for offset, value in patches:
        source[offset:offset+len(value)] = value
    return bytes(source)


@pytest.mark.parametrize('version', [3, 4])
def test_header_profile_has_separate_flags_and_preserves_physical_original(version):
    source = original(version)
    snapshot = inspect_binary(source, capture=True)
    details = dict(snapshot.details)
    assert details['header_fields_assessed'] and details['header_field_constraints_valid']
    assert details['header_field_recommendations_met'] and details['header_field_findings'] == ()
    assert not details['assessment_complete']
    assert b''.join(item.payload for item in snapshot.items if item.kind == 'cfbf-physical-sector') == source
    json.dumps(snapshot.to_dict())


@pytest.mark.parametrize('version', [3, 4])
@pytest.mark.parametrize('offset,field,begin,size', [(8, 'header_clsid', 8, 16), (23, 'header_clsid', 8, 16),
                                                 (34, 'reserved', 34, 6), (39, 'reserved', 34, 6)])
def test_nonzero_reserved_fields_have_exact_source_ranges_and_keep_stream_payload(version, offset, field, begin, size):
    source = original(version, patches=((offset, b'\x01'),))
    snapshot = inspect_binary(source, capture=True)
    details = dict(snapshot.details)
    finding, = details['header_field_findings']
    assert finding == {'code': 'nonzero-'+field.replace('_', '-'), 'field': field, 'rule': 'must',
                       'location': 'cfbf:header/'+field, 'byte_range': {'offset': begin, 'length': size}}
    assert not details['header_field_constraints_valid'] and details['header_field_recommendations_met']
    assert next(item.payload for item in snapshot.items if item.locator == 'cfbf:directory=1') == own_cfbf(version=version)[1]
    assert b''.join(item.payload for item in snapshot.items if item.kind == 'cfbf-physical-sector') == source


@pytest.mark.parametrize('offset', [512, 4095])
def test_v4_padding_is_part_of_header_not_an_allocation_sector(offset):
    source = original(4, patches=((offset, b'\x7f'),))
    details = dict(inspect_binary(source).details)
    finding, = details['header_field_findings']
    assert finding['code'] == 'nonzero-header-padding'
    assert finding['byte_range'] == {'offset': 512, 'length': 3584}
    assert not details['header_field_constraints_valid']


@pytest.mark.parametrize('version', [3, 4])
@pytest.mark.parametrize('minor', [0, 0x003f, 0xffff])
def test_minor_version_is_recommendation_not_structural_failure(version, minor):
    source = original(version, patches=((24, struct.pack('<H', minor)),))
    details = dict(inspect_binary(source).details)
    finding, = details['header_field_findings']
    assert finding['rule'] == 'should' and finding['code'] == 'unexpected-minor-version'
    assert finding['byte_range'] == {'offset': 24, 'length': 2}
    assert details['minor_version'] == minor
    assert details['header_field_constraints_valid'] and not details['header_field_recommendations_met']


@pytest.mark.parametrize('version', [3, 4])
def test_transaction_signature_is_not_declared_reserved_without_producer_evidence(version):
    source = original(version, patches=((52, struct.pack('<I', 0x12345678)),))
    snapshot = inspect_binary(source, capture=True)
    assert dict(snapshot.details)['header_field_findings'] == ()
    assert next(item.payload for item in snapshot.items if item.locator == 'cfbf:sector=-1')[:512] == source[:512]


def test_combined_mandatory_and_recommended_findings_do_not_hide_each_other():
    source = original(4, patches=((8, b'\x01'), (34, b'\x02'), (24, b'\0\0'), (512, b'\x03')))
    details = dict(inspect_binary(source).details)
    assert len(details['header_field_findings']) == 4
    assert not details['header_field_constraints_valid'] and not details['header_field_recommendations_met']
    assert {finding['rule'] for finding in details['header_field_findings']} == {'must', 'should'}


@pytest.mark.parametrize('offset,value,error', [(28, b'\xff\xfe', UnsupportedDocumentError),
                                               (32, b'\x07\0', UnsupportedDocumentError),
                                               (40, b'\x01\0\0\0', InvalidDocumentError),
                                               (56, b'\0\x20\0\0', UnsupportedDocumentError)])
def test_structural_profile_errors_are_still_rejected_instead_of_returning_partial_inventory(offset, value, error):
    source = original(patches=((offset, value),))
    with pytest.raises(error):
        inspect_binary(source)


def test_cancel_during_header_audit_does_not_publish_partial_snapshot_or_leak_scope(monkeypatch):
    from opendoc_formats.native import cfbf_fields

    source = original()
    before, stop, calls = bytes(source), Event(), []
    actual = cfbf_fields.checkpoint

    def first():
        actual()
        calls.append(True)
        stop.set()

    with monkeypatch.context() as context:
        context.setattr(cfbf_fields, 'checkpoint', first)
        with pytest.raises(OperationCancelledError):
            inspect_binary(source, cancelled=stop.is_set)
    assert calls == [True] and source == before
    assert dict(inspect_binary(source).details)['header_field_constraints_valid']
