"""Finite physical directory/padding audit; observations never repair or certify fonts."""

import builtins
import json
import struct
import sys
from dataclasses import asdict
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from opendoc_formats.native.sfnt import SfntLimits, inspect_sfnt_structure
from tests.binary_fixtures import own_placement_font, zip_bytes
from tests.test_native_font_collection import collection
from tests.test_sfnt_inspection import wrapper


def program(tags=(b'OWN ', b'fvar')):
    data = bytearray(wrapper(tags=tags))
    count = len(tags)
    selector = count.bit_length()-1
    search = 16*(1 << selector)
    struct.pack_into('>3H', data, 6, search, selector, 16*count-search)
    return data


@pytest.mark.parametrize('kind', ['synthetic', 'real', 'opaque-trailer'])
def test_healthy_structure_does_not_require_font_engine_or_imply_complete_validation(monkeypatch, kind):
    source = own_placement_font() if kind == 'real' else bytes(program())
    if kind == 'opaque-trailer':
        source += b'Unknown opaque trailer'
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(('fontTools', 'pymupdf', 'PIL')):
            pytest.fail('Physical structure audit imported a font or rendering engine')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    report = inspect_sfnt_structure(source)
    assert not report.findings and not report.assessment_complete
    plain = inspect_binary(source, capture=True)
    audited = inspect_binary(source, capture=True, sfnt_structure=True)
    assert plain.items == audited.items and audited.items[0].payload == source
    assert dict(audited.details)['structure'] == asdict(report)


@pytest.mark.parametrize('defect,code', [('order', 'sfnt.directory.order'), ('search', 'sfnt.directory.search'),
                                     ('tag', 'sfnt.directory.tag-spaces'), ('blank-tag', 'sfnt.directory.tag-spaces'),
                                     ('padding', 'sfnt.padding.nonzero'), ('truncated', 'sfnt.padding.truncated'),
                                     ('overlap', 'sfnt.table.overlap')])
def test_physical_defects_are_located_without_mutating_source(tmp_path, defect, code):
    data = program()
    if defect == 'order':
        data[12:16], data[28:32] = data[28:32], data[12:16]
    elif defect == 'search':
        struct.pack_into('>3H', data, 6, 0, 0, 0)
    elif defect in ('tag', 'blank-tag'):
        data[12:16] = b'A B ' if defect == 'tag' else b'    '
    elif defect == 'padding':
        data[47] = 1
    elif defect == 'truncated':
        data = data[:-1]
    else:
        struct.pack_into('>I', data, 36, 44)
    source = bytes(data)
    path = tmp_path/'own.ttf'
    path.write_bytes(source)
    report = inspect_sfnt_structure(path)
    assert [value.code for value in report.findings] == [code]
    assert all(0 <= value.offset <= len(source) for value in report.findings)
    assert path.read_bytes() == source


def test_nested_overlaps_have_representative_partner_and_empty_tables_are_not_overlaps():
    data = program((b'AAA ', b'BBB ', b'CCC '))
    struct.pack_into('>I', data, 24, 11)
    findings = inspect_sfnt_structure(bytes(data)).findings
    assert [(value.code, value.offset) for value in findings] == [('sfnt.table.overlap', 64), ('sfnt.table.overlap', 68)]
    data = program()
    struct.pack_into('>2I', data, 36, 44, 0)
    assert not inspect_sfnt_structure(bytes(data)).findings


@pytest.mark.parametrize('face', [0, 1])
def test_explicit_collection_face_uses_absolute_locations_and_retains_scope(face):
    data = collection(version=2, signed=True)
    report = inspect_sfnt_structure(data, face_index=face)
    snapshot = inspect_binary(data, sfnt_face_index=face, sfnt_structure=True, capture=True)
    assert report.face_index == face and report.directory_offset == struct.unpack_from('>I', data, 12+4*face)[0]
    assert not report.findings and not report.assessment_complete
    assert dict(snapshot.details)['structure'] == asdict(report) and snapshot.items[0].payload == data


def test_findings_charge_native_and_shared_remaining_budget():
    source = wrapper()  # Deliberately wrong directory search fields.
    with pytest.raises(ResourceLimitError, match='max_findings'):
        inspect_sfnt_structure(source, limits=SfntLimits(max_findings=0))
    assert len(inspect_sfnt_structure(source, limits=SfntLimits(max_findings=1)).findings) == 1
    with pytest.raises(ResourceLimitError, match='max_findings'):
        inspect_binary(source, sfnt_structure=True, limits=AnatomyLimits(max_items=3))
    assert inspect_binary(source, sfnt_structure=True, limits=AnatomyLimits(max_items=4)).items
    assert not inspect_sfnt_structure(bytes(program()), limits=SfntLimits(max_findings=0)).findings


@pytest.mark.parametrize('value', [None, 1, 'true'])
def test_structure_flag_is_strict_before_reading_source(value):
    with pytest.raises(TypeError, match='boolean'):
        inspect_binary('missing.ttf', sfnt_structure=value)


def test_structure_option_cannot_be_ignored_on_other_formats():
    with pytest.raises(ValueError, match='requires the sfnt'):
        inspect_binary(zip_bytes([('own', b'Own')]), sfnt_structure=True)


def test_cancel_after_finding_does_not_publish_partial_structure(tmp_path, monkeypatch):
    import opendoc_formats.native.sfnt as native

    source = wrapper()
    path = tmp_path/'own.ttf'
    path.write_bytes(source)
    original, stop = native.SfntFinding, Event()

    def interrupted(*args):
        finding = original(*args)
        stop.set()
        return finding

    monkeypatch.setattr(native, 'SfntFinding', interrupted)
    with pytest.raises(OperationCancelledError):
        inspect_binary(path, sfnt_structure=True, cancelled=stop.is_set)
    assert path.read_bytes() == source


@pytest.mark.parametrize('capture', [False, True])
def test_cli_reports_structure_with_comparison_and_unchanged_source(tmp_path, monkeypatch, capture):
    from tools.document_anatomy import main

    path, output = tmp_path/'own.ttf', tmp_path/'report'
    source = wrapper()
    path.write_bytes(source)
    args = ['document_anatomy', str(path), '--sfnt-structure', '--compare', str(path), '--output', str(output)]
    if not capture:
        args.append('--no-payloads')
    monkeypatch.setattr(sys, 'argv', args)
    main()
    report = json.loads((output/'inventory.json').read_text(encoding='utf-8'))
    assert report['details']['structure']['findings'][0]['code'] == 'sfnt.directory.search'
    assert report['comparison']['binary_identical'] and path.read_bytes() == source
