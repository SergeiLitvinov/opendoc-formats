"""Original binary names and trees, independently authored rather than sorted by the reader."""

import struct
from threading import Event

import pytest

from opendoc_formats.anatomy import inspect_binary
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.native.cfbf_names import _name_key
from tests.binary_fixtures import own_cfbf


def original(names=('Middle', 'A', 'Longest'), *, pointers=(), version=3):
    source = bytearray(own_cfbf(version=version)[0])
    base = 1024 if version == 3 else 8192
    for index, name in enumerate(names, 1):
        encoded = (name+'\0').encode('utf-16-le')
        assert len(encoded) <= 64
        offset = base+index*128
        source[offset:offset+64] = encoded.ljust(64, b'\0')
        struct.pack_into('<H', source, offset+64, len(encoded))
        source[offset+67] = 1
    for index, field, value in pointers:
        struct.pack_into('<I', source, base+index*128+field, value)
    return bytes(source)


@pytest.mark.parametrize('version', [3, 4])
@pytest.mark.parametrize('names', [
    ('Middle', 'A', 'Longest'), ('Z', 'A', 'AA'), ('ÿ', 'Ā', 'ZZ'),
    ('ß', 'Z', 'SS'), ('ᾀ', 'Ω', 'ZZ'), ('𐐨', 'Z', 'AAA'),
])
def test_length_then_simple_uppercase_utf16_order_keeps_exact_originals(version, names):
    source = original(names, version=version)
    snapshot = inspect_binary(source, capture=True)
    details = dict(snapshot.details)
    assert details['directory_links_valid'] and details['directory_color_constraints_valid']
    assert details['directory_name_order_assessed'] and details['directory_name_order_valid']
    assert details['directory_name_order_findings'] == ()
    assert details['directory_name_comparison_unicode_version']
    assert not details['directory_tree_assessed'] and not details['assessment_complete']
    assert b''.join(item.payload for item in snapshot.items if item.kind == 'cfbf-physical-sector') == source


def test_simple_uppercase_does_not_expand_fold_or_case_convert_surrogate_pairs():
    assert _name_key('ᾀ') == _name_key('ᾈ')  # Simple uppercase; full upper would produce ΑΙ.
    assert _name_key('ß')[0] < _name_key('SS')[0]
    assert _name_key('ß') != _name_key('ẞ')  # No invented reverse uppercase mapping.
    assert _name_key('é') != _name_key('e\u0301')  # No Unicode normalization.
    assert _name_key('𐐨') != _name_key('𐐀')  # Deseret case pair stays distinct UTF-16 units.
    assert _name_key('ſ') == _name_key('S') and _name_key('ı') == _name_key('I')


@pytest.mark.parametrize('first,second', [('same', 'SAME'), ('ᾀ', 'ᾈ'), ('ſ', 'S'), ('ı', 'I')])
def test_duplicate_sibling_names_are_found_after_comparison(first, second):
    snapshot = inspect_binary(original((first, second, 'Longest')), capture=True)
    details = dict(snapshot.details)
    assert details['directory_links_valid'] and not details['directory_name_order_valid']
    found = next(item for item in details['directory_name_order_findings'] if item['code'] == 'duplicate-sibling-name')
    assert found['location'] == 'cfbf:directory=1/name' and found['related_directory'] == 2
    assert found['offset'] == 1152 and found['storage_owner'] == 0


def test_ancestor_order_is_checked_not_only_each_immediate_edge():
    # Root M has left C, and C has right Z. C < M and C < Z, but Z is outside M's left subtree range.
    source = original(('M', 'C', 'Z'), pointers=((1, 72, 0xffffffff), (2, 72, 3)))
    details = dict(inspect_binary(source).details)
    assert details['directory_links_valid']
    assert details['directory_name_order_findings'] == ({
        'code': 'sibling-name-order', 'location': 'cfbf:directory=1/name',
        'offset': 1152, 'name': 'M', 'related_directory': 3, 'storage_owner': 0},)


def test_duplicates_do_not_need_to_be_adjacent_in_an_already_misordered_tree():
    details = dict(inspect_binary(original(('M', 'A', 'a'))).details)
    found = next(item for item in details['directory_name_order_findings'] if item['code'] == 'duplicate-sibling-name')
    assert found['location'] == 'cfbf:directory=3/name' and found['related_directory'] == 2


def test_identical_names_in_different_storages_are_permitted():
    # Folder's child A has same name as an ordinary child of the root storage.
    source = bytearray(original(('A', 'A', 'Folder'), version=4,
                                pointers=((1, 68, 0xffffffff), (3, 76, 2))))
    details = dict(inspect_binary(bytes(source)).details)
    assert details['directory_links_valid'] and details['directory_name_order_valid']


def test_invalid_pointer_graph_reports_name_order_unknown_without_following_cycles():
    source = original(pointers=((2, 72, 1),))
    details = dict(inspect_binary(source).details)
    assert not details['directory_links_valid']
    assert not details['directory_name_order_assessed'] and details['directory_name_order_valid'] is None
    assert details['directory_name_order_findings'] == ()


def test_cancellation_inside_name_audit_preserves_original_and_scope(tmp_path, monkeypatch):
    import opendoc_formats.native.cfbf_names as names

    source = original()
    path = tmp_path/'own.cfb'
    path.write_bytes(source)
    stop = Event()
    checkpoint = names.checkpoint
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        if calls == 7:
            stop.set()
        checkpoint()

    with monkeypatch.context() as context:
        context.setattr(names, 'checkpoint', cancel)
        with pytest.raises(OperationCancelledError):
            inspect_binary(path, cancelled=stop.is_set)
    assert path.read_bytes() == source and calls == 7
    assert dict(inspect_binary(path).details)['directory_name_order_valid']
