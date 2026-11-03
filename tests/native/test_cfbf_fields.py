"""Literal v3/v4 directory-field mutations retain bytes and distinguish MUST/SHOULD/compatibility."""

import builtins
import json
import struct
from dataclasses import replace
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from tests.binary_fixtures import own_cfbf


def original(version=3, *, patches=(), names=(), free=False, high_size_bits=0):
    source = bytearray(own_cfbf(version=version, high_size_bits=high_size_bits)[0])
    base = 1024 if version == 3 else 8192
    # The older physical fixture uses ENDOFCHAIN in its storage's unused start
    # field. Author a field-conforming original without changing that fixture.
    struct.pack_into('<I', source, base+3*128+116, 0)
    if free:
        source[base+3*128:base+4*128] = b'\0'*68+b'\xff'*12+b'\0'*48
        struct.pack_into('<I', source, base+128+72, 0xffffffff)
    for index, name in names:
        encoded = (name+'\0').encode('utf-16-le')
        assert len(encoded) <= 64
        offset = base+index*128
        source[offset:offset+64] = encoded.ljust(64, b'\0')
        struct.pack_into('<H', source, offset+64, len(encoded))
    for index, relative, value in patches:
        offset = base+index*128+relative
        source[offset:offset+len(value)] = value
    return bytes(source), base


@pytest.mark.parametrize('version', [3, 4])
def test_confirmed_field_profile_preserves_original_and_does_not_claim_full_conformance(version):
    source, _ = original(version, free=True)
    snapshot = inspect_binary(source, capture=True)
    details = dict(snapshot.details)
    assert details['directory_fields_assessed'] and details['directory_field_constraints_valid']
    assert details['directory_field_recommendations_met'] and details['directory_field_findings'] == ()
    assert not details['directory_tree_assessed'] and not details['assessment_complete']
    assert b''.join(item.payload for item in snapshot.items if item.kind == 'cfbf-physical-sector') == source
    json.dumps(snapshot.to_dict())


@pytest.mark.parametrize('version', [3, 4])
@pytest.mark.parametrize('character', ['/', '\\', ':', '!'])
def test_illegal_name_unit_after_surrogate_pair_has_exact_source_byte_range(version, character):
    source, base = original(version, names=((1, '😀'+character+'Own'),))
    snapshot = inspect_binary(source, capture=True)
    details = dict(snapshot.details)
    finding, = details['directory_field_findings']
    assert finding['code'] == 'illegal-name-character' and finding['rule'] == 'must'
    assert finding['location'] == 'cfbf:directory=1/name'
    assert finding['byte_range'] == {'offset': base+128+4, 'length': 2}
    assert source[base+128+4:base+128+6] == character.encode('utf-16-le')
    assert not details['directory_field_constraints_valid']
    retained = next(dict(item.details)['name'] for item in snapshot.items if item.locator == 'cfbf:directory=1')
    assert retained == '😀'+character+'Own'


@pytest.mark.parametrize('version', [3, 4])
@pytest.mark.parametrize('index,name,code,relative', [(1, 'A\0B', 'embedded-name-terminator', 2),
                                                  (0, 'root entry', 'invalid-root-name', 0)])
def test_name_terminator_and_exact_root_name_are_independent_of_order(version, index, name, code, relative):
    source, base = original(version, names=((index, name),))
    details = dict(inspect_binary(source).details)
    finding, = details['directory_field_findings']
    assert finding['code'] == code and finding['byte_range']['offset'] == base+index*128+relative
    assert not details['directory_field_constraints_valid']


@pytest.mark.parametrize('version', [3, 4])
@pytest.mark.parametrize('index,relative,size,code', [(1, 80, 16, 'nonzero-stream-field'),
                                                  (1, 100, 8, 'nonzero-stream-field'),
                                                  (1, 108, 8, 'nonzero-stream-field'),
                                                  (0, 100, 8, 'nonzero-root-creation-time'),
                                                  (3, 116, 4, 'nonzero-storage-field'),
                                                  (3, 120, 8, 'nonzero-storage-field')])
def test_mandatory_field_values_are_located_without_discarding_payload(version, index, relative, size, code):
    source, base = original(version, patches=((index, relative, b'\x01'+b'\0'*(size-1)),))
    snapshot = inspect_binary(source, capture=True)
    details = dict(snapshot.details)
    finding, = details['directory_field_findings']
    assert finding['code'] == code and finding['rule'] == 'must'
    assert finding['byte_range'] == {'offset': base+index*128+relative, 'length': size}
    assert not details['directory_field_constraints_valid']
    assert b''.join(item.payload for item in snapshot.items if item.kind == 'cfbf-physical-sector') == source


@pytest.mark.parametrize('version', [3, 4])
def test_user_defined_storage_fields_and_root_modified_time_are_not_forced_to_zero(version):
    source, _ = original(version, patches=((0, 80, b'\x01'*16), (0, 96, b'\x02'*4), (0, 108, b'\x03'*8),
                                           (3, 80, b'\x04'*16), (3, 96, b'\x05'*4),
                                           (3, 100, b'\x06'*8), (3, 108, b'\x07'*8)))
    assert dict(inspect_binary(source).details)['directory_field_findings'] == ()


@pytest.mark.parametrize('version', [3, 4])
def test_stream_state_bits_are_a_recommendation_and_do_not_invalidate_must_constraints(version):
    source, _ = original(version, patches=((1, 96, b'\x01\0\0\0'),))
    details = dict(inspect_binary(source).details)
    finding, = details['directory_field_findings']
    assert finding['code'] == 'nonzero-stream-state-bits' and finding['rule'] == 'should'
    assert details['directory_field_constraints_valid'] and not details['directory_field_recommendations_met']


def test_v3_high_size_dwords_remain_accepted_compatibility_observations():
    source, _ = original(high_size_bits=0xfacebeef, patches=((0, 124, b'\x01\0\0\0'),))
    snapshot = inspect_binary(source, capture=True)
    details = dict(snapshot.details)
    assert details['directory_field_constraints_valid'] and details['directory_field_recommendations_met']
    assert len(details['directory_field_findings']) == 3
    assert all(finding['rule'] == 'compatibility' and finding['code'] == 'legacy-v3-size-high-dword'
               for finding in details['directory_field_findings'])
    assert len(next(item.payload for item in snapshot.items if item.kind == 'cfbf-root-mini-stream')) == 192


@pytest.mark.parametrize('version', [3, 4])
@pytest.mark.parametrize('relative,field', [(0, 'name'), (64, 'name_length'), (67, 'color'), (80, 'clsid'),
                                          (96, 'state_bits'), (100, 'creation_time'), (108, 'modified_time'),
                                          (116, 'starting_sector'), (120, 'stream_size'),
                                          (68, 'left_sibling'), (72, 'right_sibling'), (76, 'child')])
def test_unallocated_slot_fields_and_nostream_links_are_audited(version, relative, field):
    source, base = original(version, free=True, patches=((3, relative, b'\x01'),))
    details = dict(inspect_binary(source).details)
    finding, = details['directory_field_findings']
    assert finding['field'] == field and finding['byte_range']['offset'] == base+3*128+relative
    assert finding['code'] == ('unallocated-pointer-not-nostream' if relative in (68, 72, 76)
                               else 'nonzero-unallocated-field')
    assert not details['directory_field_constraints_valid']


def test_field_findings_have_a_bounded_item_count():
    source, _ = original(names=((0, '!'*31), (1, '!'*31), (2, '!'*31), (3, '!'*31)))
    with pytest.raises(ResourceLimitError, match='max_items.*field findings'):
        inspect_binary(source, limits=replace(AnatomyLimits(), max_items=30))


def test_cancel_in_field_audit_preserves_source_and_later_inspection(monkeypatch):
    from opendoc_formats.native.cfbf_fields import DirectoryFields

    source, _ = original(names=((1, '!!'),))
    before, stop = bytes(source), Event()
    actual = DirectoryFields.finding

    def first(self, *args, **kwargs):
        result = actual(self, *args, **kwargs)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(DirectoryFields, 'finding', first)
        with pytest.raises(OperationCancelledError):
            inspect_binary(source, cancelled=stop.is_set)
    assert source == before
    assert len(dict(inspect_binary(source).details)['directory_field_findings']) == 2


def test_field_audit_needs_no_optional_engine(monkeypatch):
    source, _ = original()
    actual = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in {'olefile', 'lxml', 'PIL', 'fontTools', 'fitz', 'pymupdf', 'docx'}:
            raise AssertionError('Unexpected binary audit backend: '+name)
        return actual(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    assert dict(inspect_binary(source).details)['directory_field_constraints_valid']
