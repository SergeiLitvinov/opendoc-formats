"""Same baseline arithmetic, without a font engine for standalone head/hhea."""

import builtins
import os
import struct
from io import BytesIO
from threading import Event

import pytest
from fontTools.ttLib import TTFont
from opendoc_model import Length, TextStyle

from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.fonts.word_metrics import _cached_metrics, _metrics, word_line_ascent, word_line_descent
from opendoc_formats.native.sfnt import inspect_sfnt
from opendoc_formats.support.cancellation import cancellation_scope
from tests.binary_fixtures import own_placement_font


@pytest.fixture(autouse=True)
def clear_metrics_cache():
    _cached_metrics.cache_clear()
    yield
    _cached_metrics.cache_clear()


def write_metrics_font(path, units=1000, ascent=800, descent=-200, gap=0, *, flavor=None):
    with TTFont(BytesIO(own_placement_font()), recalcTimestamp=False) as font:
        font['head'].unitsPerEm = units
        font['hhea'].ascent, font['hhea'].descent, font['hhea'].lineGap = ascent, descent, gap
        font.flavor = flavor
        font.save(path)
    return path


@pytest.mark.parametrize('units,ascent,descent,gap', [
    (1000, 800, -200, 0), (2048, 1900, -480, 120), (1000, 700, -300, -50),
    (16, 15, -4, 2), (16384, 16000, -4000, 32767), (1000, -100, 50, 0),
])
def test_standalone_native_metrics_match_independent_engine_without_importing_it(
    tmp_path, monkeypatch, units, ascent, descent, gap,
):
    path = write_metrics_font(tmp_path/'own.ttf', units, ascent, descent, gap)
    before = path.read_bytes()
    with TTFont(path, lazy=True) as reference:
        head, horizontal = reference['head'], reference['hhea']
        expected = ((horizontal.ascent+horizontal.lineGap)/head.unitsPerEm, -horizontal.descent/head.unitsPerEm)
    original = builtins.__import__

    def no_font_engine(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Standalone baseline imported the optional font engine')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_font_engine)
    assert _metrics(str(path)) == expected
    style = TextStyle(font_family='OwnPlacement', font_size=Length(12),
                      properties={'font_resolution': {'path': str(path)}})
    assert word_line_ascent(style) == expected[0]*12
    assert word_line_descent(style) == expected[1]*12
    assert path.read_bytes() == before


def test_compressed_woff_keeps_existing_optional_engine_behavior(tmp_path):
    path = write_metrics_font(tmp_path/'own.woff', 2048, 1500, -300, 100, flavor='woff')
    with TTFont(path, lazy=True) as reference:
        expected = ((reference['hhea'].ascent+reference['hhea'].lineGap)/reference['head'].unitsPerEm,
                    -reference['hhea'].descent/reference['head'].unitsPerEm)
    assert _metrics(str(path)) == expected


def test_lazy_engine_fallback_keeps_baseline_when_an_unrelated_table_is_outside_native_profile(tmp_path):
    path = write_metrics_font(tmp_path/'own.ttf')
    data = bytearray(path.read_bytes())
    name = next(table for table in inspect_sfnt(bytes(data)).tables if table.tag == 'name')
    struct.pack_into('>I', data, name.directory_offset+8, len(data)+4)
    path.write_bytes(data)
    # The established lazy metrics reader does not read the damaged unrelated name table.
    with TTFont(path, lazy=True) as reference:
        expected = ((reference['hhea'].ascent+reference['hhea'].lineGap)/reference['head'].unitsPerEm,
                    -reference['hhea'].descent/reference['head'].unitsPerEm)
    assert _metrics(str(path)) == expected


@pytest.mark.parametrize('source', [b'Not a font', b'\0\1\0\0'])
def test_unknown_or_truncated_program_stays_unknown(tmp_path, source):
    path = tmp_path/'bad.ttf'
    path.write_bytes(source)
    assert _metrics(str(path)) is None and path.read_bytes() == source


def test_missing_resolution_or_size_stays_unknown():
    assert word_line_ascent(TextStyle()) is None
    assert word_line_descent(TextStyle(font_family='Own')) is None


def test_cancellation_is_not_swallowed_as_missing_metrics_or_sent_to_fallback(tmp_path, monkeypatch):
    path = write_metrics_font(tmp_path/'own.ttf')
    stop = Event()
    original = builtins.__import__

    def no_fallback(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Cancellation entered the font engine fallback')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_fallback)
    with cancellation_scope(stop.is_set, 'Own baseline'):
        stop.set()
        with pytest.raises(OperationCancelledError):
            _metrics(str(path))
        stop.clear()
    assert _metrics(str(path)) == (0.8, 0.2)


@pytest.mark.parametrize('flavor', [None, 'woff'])
def test_same_path_replacement_with_restored_timestamp_never_reuses_old_metrics(tmp_path, flavor):
    path = write_metrics_font(tmp_path/'own.ttf', flavor=flavor)
    original = path.stat()
    assert _metrics(str(path)) == (0.8, 0.2)
    write_metrics_font(path, ascent=900, descent=-100, flavor=flavor)
    if flavor is None:
        assert path.stat().st_size == original.st_size
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    assert _metrics(str(path)) == (0.9, 0.1)
    path.unlink()
    assert _metrics(str(path)) is None


def test_identical_bytes_at_distinct_paths_reuse_decoder_but_always_read_source(tmp_path, monkeypatch):
    import opendoc_formats.fonts.word_metrics as module

    first = write_metrics_font(tmp_path/'first.ttf')
    second = tmp_path/'second.ttf'
    second.write_bytes(first.read_bytes())
    original, calls = module._native_metrics, []

    def decode(data):
        calls.append(data)
        return original(data)

    monkeypatch.setattr(module, '_native_metrics', decode)
    assert _metrics(str(first)) == _metrics(str(second)) == (0.8, 0.2)
    assert len(calls) == 1 and _cached_metrics.cache_info().hits == 1
    second.write_bytes(b'not a font')
    assert _metrics(str(second)) is None


def test_warm_metrics_still_observe_cancellation(tmp_path):
    path = write_metrics_font(tmp_path/'own.ttf')
    assert _metrics(str(path)) == (0.8, 0.2)
    stop = Event()
    with cancellation_scope(stop.is_set, 'Cached baseline'):
        stop.set()
        with pytest.raises(OperationCancelledError):
            _metrics(str(path))
        stop.clear()
    assert _metrics(str(path)) == (0.8, 0.2)


def test_cancellation_after_native_decode_does_not_cache_result(tmp_path, monkeypatch):
    import opendoc_formats.fonts.word_metrics as module

    path, stop = write_metrics_font(tmp_path/'own.ttf'), Event()
    original = module._native_metrics

    def decode(data):
        result = original(data)
        stop.set()
        return result

    monkeypatch.setattr(module, '_native_metrics', decode)
    with cancellation_scope(stop.is_set, 'Decoded baseline'):
        with pytest.raises(OperationCancelledError):
            _metrics(str(path))
        stop.clear()
    assert _cached_metrics.cache_info().currsize == 0


def test_cancellation_after_cache_hit_is_checked_before_return(tmp_path, monkeypatch):
    import opendoc_formats.fonts.word_metrics as module

    path, stop = write_metrics_font(tmp_path/'own.ttf'), Event()
    assert _metrics(str(path)) == (0.8, 0.2)

    def cached(data):
        result = _cached_metrics(data)
        stop.set()
        return result

    monkeypatch.setattr(module, '_cached_metrics', cached)
    with cancellation_scope(stop.is_set, 'Warm baseline return'):
        with pytest.raises(OperationCancelledError):
            _metrics(str(path))
        stop.clear()
    assert _cached_metrics.cache_info().hits == 1


def test_metrics_cache_eviction_and_oversized_entry_bypass(tmp_path, monkeypatch):
    import opendoc_formats.fonts.word_metrics as module

    path = write_metrics_font(tmp_path/'own.ttf')
    source = path.read_bytes()
    for index in range(65):
        path.write_bytes(source+bytes([index]))
        assert _metrics(str(path)) == (0.8, 0.2)
    assert _cached_metrics.cache_info().currsize == 64
    path.write_bytes(source+b'\0')
    misses = _cached_metrics.cache_info().misses
    assert _metrics(str(path)) == (0.8, 0.2)
    assert _cached_metrics.cache_info().misses == misses+1
    _cached_metrics.cache_clear()
    monkeypatch.setattr(module, '_CACHE_INPUT_BYTES', len(source)-1)
    path.write_bytes(source)
    assert _metrics(str(path)) == _metrics(str(path)) == (0.8, 0.2)
    assert _cached_metrics.cache_info().currsize == _cached_metrics.cache_info().misses == 0


def test_transient_engine_failure_is_not_cached(tmp_path, monkeypatch):
    import opendoc_formats.fonts.word_metrics as module

    path = write_metrics_font(tmp_path/'own.woff', flavor='woff')
    original, calls = module._engine_metrics, []

    def engine(source):
        calls.append(True)
        if len(calls) == 1:
            raise ValueError('Transient reader failure')
        return original(source)

    monkeypatch.setattr(module, '_engine_metrics', engine)
    assert _metrics(str(path)) is None
    assert _metrics(str(path)) == (0.8, 0.2)
    assert calls == [True, True]
