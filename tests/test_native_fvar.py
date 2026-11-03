"""Exact fvar records and unchanged base face fields, without selecting named instances."""

import builtins
import hashlib
import struct
from io import BytesIO

import pytest
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.fonts.resolver import _read_face
from opendoc_formats.native.fvar import inspect_fvar_table
from opendoc_formats.native.sfnt import read_face_metrics
from tests.binary_fixtures import own_placement_font
from tests.test_native_font_face import engine_face


def table(*, optional=True, offset=16):
    axes = ((b'wght', 100*65536, 400*65536, 900*65536, 0, 256),
            (b'slnt', -15*65536, 0, 0, 1, 257))
    instances = ((2, (400*65536, 0), 6), (258, (700*65536, -32768), 259))
    payload = bytearray(struct.pack('>8H', 1, 0, offset, 2, 2, 20, 2, 14 if optional else 12))
    payload.extend(bytes(offset-16))
    for axis in axes:
        payload.extend(struct.pack('>4s3i2H', *axis))
    for name, coordinates, postscript in instances:
        payload.extend(struct.pack('>2H2i', name, 0, *coordinates))
        if optional:
            payload.extend(struct.pack('>H', postscript))
    return bytes(payload)


def program(payload):
    output = BytesIO()
    with TTFont(BytesIO(own_placement_font()), recalcTimestamp=False) as font:
        raw = DefaultTable('fvar')
        raw.data = payload
        font['fvar'] = raw
        font.save(output)
    return output.getvalue()


@pytest.mark.parametrize('optional,offset', [(True, 16), (False, 16), (True, 24)])
def test_raw_axis_and_instance_values_match_engine_and_source(optional, offset):
    payload = table(optional=optional, offset=offset)
    parsed = inspect_fvar_table(memoryview(payload))
    assert parsed.table_sha256 == hashlib.sha256(payload).hexdigest()
    assert parsed.table_size == len(payload) and parsed.axes_offset == offset
    assert not parsed.assessment_complete
    assert parsed.axes[0].default == 400*65536 and parsed.axes[1].minimum == -15*65536
    assert parsed.instances[1].coordinates == (700*65536, -32768)
    assert parsed.instances[1].postscript_name_id == (259 if optional else None)
    with TTFont(BytesIO(program(payload)), lazy=True) as reference:
        source = reference['fvar']
        assert [(axis.tag, axis.minimum/65536, axis.default/65536, axis.maximum/65536, axis.flags, axis.name_id)
                for axis in parsed.axes] == [(axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue,
                                               axis.flags, axis.axisNameID) for axis in source.axes]
        for value, expected in zip(parsed.instances, source.instances):
            assert [coordinate/65536 for coordinate in value.coordinates] == list(expected.coordinates.values())


def test_default_metadata_matches_engine_without_import_or_named_instance_selection(tmp_path, monkeypatch):
    path = tmp_path/'own-variable.ttf'
    source = program(table())
    path.write_bytes(source)
    expected = engine_face(path)
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Base variable face imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert _read_face(path) == expected
    assert _read_face(path).weight == 400  # The named 700-weight instance is not selected.
    assert path.read_bytes() == source
    with pytest.raises(UnsupportedDocumentError, match='variation metadata'):
        read_face_metrics(source)
    assert read_face_metrics(source, default_variations=True).weight == 400


@pytest.mark.parametrize('offset,value,fmt,error', [
    (0, 2, '>H', UnsupportedDocumentError), (6, 3, '>H', UnsupportedDocumentError),
    (10, 18, '>H', UnsupportedDocumentError), (14, 13, '>H', UnsupportedDocumentError),
    (4, 65535, '>H', InvalidDocumentError), (16+8, 1000*65536, '>i', InvalidDocumentError),
    (16+16, 2, '>H', UnsupportedDocumentError), (56+2, 1, '>H', UnsupportedDocumentError),
    (56+4, 901*65536, '>i', UnsupportedDocumentError),
])
def test_malformed_or_future_profiles_never_return_partial_inventory(offset, value, fmt, error):
    data = bytearray(table())
    struct.pack_into(fmt, data, offset, value)
    with pytest.raises(error):
        inspect_fvar_table(bytes(data))


def test_duplicate_tags_and_truncated_records_are_rejected():
    data = bytearray(table())
    data[36:40] = b'wght'
    with pytest.raises(InvalidDocumentError, match='axis tag'):
        inspect_fvar_table(bytes(data))
    for payload in (b'', table()[:15], table()[:-1]):
        with pytest.raises(InvalidDocumentError):
            inspect_fvar_table(payload)


@pytest.mark.parametrize('limits', [{'max_bytes': 1}, {'max_axes': 1}, {'max_instances': 1}, {'max_coordinates': 3}])
def test_selected_work_and_input_limits_fail_before_partial_result(limits):
    with pytest.raises(ResourceLimitError):
        inspect_fvar_table(table(), **limits)


def test_cancel_inside_instance_coordinates_preserves_input():
    source, calls = table(), []

    def stop():
        calls.append(True)
        return len(calls) == 5

    with pytest.raises(OperationCancelledError):
        inspect_fvar_table(source, cancelled=stop)
    assert inspect_fvar_table(source).instances[0].coordinates == (400*65536, 0)


def test_bad_fvar_profile_keeps_existing_base_reader(tmp_path):
    data = bytearray(table())
    struct.pack_into('>H', data, 6, 3)
    path = tmp_path/'legacy-fvar.ttf'
    path.write_bytes(program(bytes(data)))
    assert _read_face(path) == engine_face(path)


def test_empty_axis_profile_is_observed_without_creating_a_named_selection():
    parsed = inspect_fvar_table(struct.pack('>8H', 1, 0, 16, 2, 0, 20, 0, 4),
                                max_axes=0, max_instances=0, max_coordinates=0)
    assert parsed.axes == () and parsed.instances == ()
