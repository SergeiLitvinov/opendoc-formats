"""MS-CFB color rules, separately from name order, payload validity and application semantics."""

import struct
from threading import Event

import pytest

from opendoc_formats.anatomy import inspect_binary
from opendoc_formats.errors import OperationCancelledError
from tests.binary_fixtures import own_cfbf


def modified(version=3, *, colors=(), pointers=()):
    source = bytearray(own_cfbf(version=version)[0])
    base = 1024 if version == 3 else 8192
    for index, value in colors:
        source[base+128*index+67] = value
    for index, field, value in pointers:
        struct.pack_into('<I', source, base+128*index+field, value)
    return bytes(source)


@pytest.mark.parametrize('version', [3, 4])
@pytest.mark.parametrize('root_color', [0, 1])
def test_root_directory_color_is_irrelevant_and_all_black_unequal_height_is_legal(version, root_color):
    # Small -> Large -> Folder, an unbalanced all-black sibling tree.
    source = modified(version, colors=((0, root_color), (1, 1), (2, 1), (3, 1)),
                      pointers=((1, 72, 0xffffffff), (2, 68, 3)))
    snapshot = inspect_binary(source, capture=True)
    details = dict(snapshot.details)
    assert details['directory_links_valid']
    assert details['directory_colors_assessed'] and details['directory_color_constraints_valid']
    assert details['directory_color_findings'] == ()
    assert not details['directory_tree_assessed'] and not details['assessment_complete']
    assert b''.join(item.payload for item in snapshot.items if item.kind == 'cfbf-physical-sector') == source


@pytest.mark.parametrize('index', [0, 1, 2, 3])
@pytest.mark.parametrize('color', [2, 255])
def test_invalid_color_is_located_at_original_byte_without_losing_any_payload(index, color):
    source = modified(colors=((index, color),))
    snapshot = inspect_binary(source, capture=True)
    details = dict(snapshot.details)
    assert details['directory_links_valid'] and not details['directory_color_constraints_valid']
    assert {'code': 'invalid-color-flag', 'location': f'cfbf:directory={index}/color',
            'offset': 1024+128*index+67, 'value': color,
            'related_directory': None, 'relation': None} in details['directory_color_findings']
    assert b''.join(item.payload for item in snapshot.items if item.kind == 'cfbf-physical-sector') == source


def test_consecutive_red_edges_are_sibling_edges_not_storage_containment():
    # Folder is red in its parent's sibling tree; its own child Large is black.
    source = modified(colors=((2, 1),), pointers=((1, 68, 0xffffffff), (3, 76, 2)))
    assert dict(inspect_binary(source).details)['directory_color_constraints_valid']
    # Large becomes red: this violates the child-tree-root rule, not a red/red sibling rule.
    source = modified(pointers=((1, 68, 0xffffffff), (3, 76, 2)))
    findings = dict(inspect_binary(source).details)['directory_color_findings']
    assert [item['code'] for item in findings] == ['red-sibling-tree-root']
    assert findings[0]['related_directory'] == 3 and findings[0]['location'] == 'cfbf:directory=2/color'


@pytest.mark.parametrize('field,relation', [(68, 'left_sibling'), (72, 'right_sibling')])
def test_consecutive_red_siblings_and_red_tree_top_have_distinct_findings(field, relation):
    source = modified(pointers=((1, 72, 0xffffffff), (2, field, 3)))
    details = dict(inspect_binary(source).details)
    assert details['directory_links_valid']
    assert details['directory_color_findings'] == ({
        'code': 'consecutive-red-siblings', 'location': 'cfbf:directory=3/color', 'offset': 1475,
        'value': 0, 'related_directory': 2, 'relation': relation},)
    source = modified(colors=((1, 0),))
    codes = [item['code'] for item in dict(inspect_binary(source).details)['directory_color_findings']]
    assert codes.count('red-sibling-tree-root') == 1 and codes.count('consecutive-red-siblings') == 2


def test_disconnected_cycles_and_invalid_targets_remain_bounded_and_separately_diagnosed():
    source = modified(pointers=((0, 76, 0xffffffff), (1, 68, 99), (2, 72, 3), (3, 68, 2)))
    details = dict(inspect_binary(source).details)
    assert not details['directory_links_valid'] and not details['directory_color_constraints_valid']
    assert [item['related_directory'] for item in details['directory_color_findings']] == [2, 3]
    assert details['directory_unreached_entries'] == (1, 2, 3)


def test_color_audit_can_cancel_without_touching_original_or_leaking_cancellation(tmp_path, monkeypatch):
    from opendoc_formats.native.cfbf import _Reader

    source = own_cfbf()[0]
    path = tmp_path/'own.cfb'
    path.write_bytes(source)
    stop = Event()
    original = _Reader.directory_colors

    def cancel(self, entries):
        stop.set()
        return original(self, entries)

    with monkeypatch.context() as context:
        context.setattr(_Reader, 'directory_colors', cancel)
        with pytest.raises(OperationCancelledError):
            inspect_binary(path, cancelled=stop.is_set)
    assert path.read_bytes() == source
    assert dict(inspect_binary(path).details)['directory_color_constraints_valid']
