"""Reuse only successful byte-identical font/character/settings inputs, with bounded retention."""

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from threading import Event, Thread

import pytest
from fontTools import subset
from fontTools.ttLib import TTFont

from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.fonts import embedding
from opendoc_formats.fonts.embedding import FontUsage, subset_font
from opendoc_formats.fonts.subset_cache import SubsetCache
from opendoc_formats.support.cancellation import cancellation_scope


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    monkeypatch.setattr(embedding, '_SUBSET_CACHE', SubsetCache())


def usage_at(tmp_path):
    source = (Path(__file__).parent/'native/data/ligature-post3.ttf').read_bytes()
    path = tmp_path/'own.ttf'
    path.write_bytes(source)
    return FontUsage('Own', path, False, False, frozenset('fi'), True, True)


def count_engine_calls(monkeypatch):
    calls, original = [], subset.Subsetter.subset

    def observed(self, font):
        calls.append(True)
        return original(self, font)

    monkeypatch.setattr(subset.Subsetter, 'subset', observed)
    return calls


def names(data):
    with TTFont(BytesIO(data)) as font:
        return sorted((record.platformID, record.platEncID, record.langID, record.nameID, record.string)
                      for record in font['name'].names)


def test_repeated_program_and_characters_avoid_engine_work_and_preserve_bytes_notices(tmp_path, monkeypatch):
    usage = usage_at(tmp_path)
    source, calls = usage.path.read_bytes(), count_engine_calls(monkeypatch)
    first = subset_font(usage)
    other = tmp_path/'same-program.ttf'
    other.write_bytes(source)
    second = subset_font(replace(usage, path=other, family='Another label', bold=True))
    assert first == second and calls == [True]
    assert names(first) == names(source) and any(record[3] == 13 for record in names(first))
    monkeypatch.setattr(embedding, '_SUBSET_CACHE', SubsetCache(maximum_entries=0))
    assert subset_font(usage) == first and calls == [True, True]
    assert usage.path.read_bytes() == other.read_bytes() == source


def test_changed_program_characters_and_settings_are_not_reused(tmp_path, monkeypatch):
    usage = usage_at(tmp_path)
    calls = count_engine_calls(monkeypatch)
    subset_font(usage)
    subset_font(replace(usage, characters=frozenset('ti')))
    with TTFont(usage.path, recalcTimestamp=False) as font:
        font['name'].setName('Copyright 2026 Own changed notice', 0, 3, 1, 0x409)
        font.save(usage.path)
    changed = subset_font(usage)
    assert names(changed) == names(usage.path.read_bytes())
    monkeypatch.setattr(subset.Options, '_layout_features_default', [])
    subset_font(usage)
    assert len(calls) == 4


def test_no_subset_permission_returns_full_program_even_after_a_cached_subset(tmp_path, monkeypatch):
    usage = usage_at(tmp_path)
    calls = count_engine_calls(monkeypatch)
    subset_font(usage)
    assert subset_font(replace(usage, subsettable=False)) == usage.path.read_bytes()
    assert subset_font(replace(usage, characters=frozenset())) == usage.path.read_bytes()
    assert calls == [True]


def test_unknown_setting_objects_bypass_cache_without_replacing_the_engine_result(tmp_path, monkeypatch):
    usage = usage_at(tmp_path)
    calls = count_engine_calls(monkeypatch)
    original = subset.Options.__init__

    def unfamiliar(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.own_unrecognized_option = object()

    monkeypatch.setattr(subset.Options, '__init__', unfamiliar)
    assert subset_font(usage) == subset_font(usage)
    assert calls == [True, True]


def test_engine_error_does_not_poison_the_cache(tmp_path, monkeypatch):
    usage = usage_at(tmp_path)
    calls, original = [], subset.Subsetter.subset

    def once(self, font):
        calls.append(True)
        if len(calls) == 1:
            raise ValueError('Own unsupported engine attempt')
        return original(self, font)

    monkeypatch.setattr(subset.Subsetter, 'subset', once)
    assert subset_font(usage) == usage.path.read_bytes()
    successful = subset_font(usage)
    assert subset_font(usage) == successful and calls == [True, True]


def test_cache_does_not_bypass_a_fresh_source_read(tmp_path):
    usage = usage_at(tmp_path)
    assert subset_font(usage)
    usage.path.unlink()
    with pytest.raises(FileNotFoundError):
        subset_font(usage)


def test_child_cache_reset_preserves_output_and_retention_limits(tmp_path, monkeypatch):
    usage = usage_at(tmp_path)
    calls = count_engine_calls(monkeypatch)
    monkeypatch.setattr(embedding, '_SUBSET_CACHE', SubsetCache(maximum_bytes=8192, maximum_entries=1))
    before = subset_font(usage)
    embedding._reset_subset_cache_after_fork()
    assert embedding._SUBSET_CACHE.maximum_bytes == 8192 and embedding._SUBSET_CACHE.maximum_entries == 1
    assert subset_font(usage) == before and calls == [True, True]


def test_cancellation_after_cache_insert_removes_unpublished_result(tmp_path, monkeypatch):
    usage, stop = usage_at(tmp_path), Event()
    calls = count_engine_calls(monkeypatch)
    cache = embedding._SUBSET_CACHE
    original = cache.put

    def interrupted(*args):
        inserted = original(*args)
        stop.set()
        return inserted

    monkeypatch.setattr(cache, 'put', interrupted)
    with cancellation_scope(stop.is_set, 'Own cache commit'):
        with pytest.raises(OperationCancelledError):
            subset_font(usage)
        stop.clear()
    monkeypatch.setattr(cache, 'put', original)
    assert subset_font(usage) and calls == [True, True]


def test_cancellation_on_cache_hit_is_not_swallowed(tmp_path, monkeypatch):
    usage, stop = usage_at(tmp_path), Event()
    calls = count_engine_calls(monkeypatch)
    expected = subset_font(usage)
    cache = embedding._SUBSET_CACHE
    original = cache.get

    def interrupted(*args):
        result = original(*args)
        stop.set()
        return result

    monkeypatch.setattr(cache, 'get', interrupted)
    with cancellation_scope(stop.is_set, 'Own cache read'):
        with pytest.raises(OperationCancelledError):
            subset_font(usage)
        stop.clear()
    monkeypatch.setattr(cache, 'get', original)
    assert subset_font(usage) == expected and calls == [True]


def test_cache_limits_and_lru_eviction_and_engine_generation():
    cache = SubsetCache(maximum_bytes=128, maximum_entries=2)
    first, second = (b'A'*40, 'AB', '{}'), (b'B'*40, 'AB', '{}')
    engine = (object(),)
    assert cache.put(first, engine, b'R'*40)
    assert cache.put(second, engine, b'R'*40)
    assert cache.get(first, engine) is None and cache.get(second, engine) == b'R'*40
    assert cache.get(second, (object(),)) is None
    cache = SubsetCache(maximum_bytes=10000, maximum_entries=2)
    third = (b'C', 'AB', '{}')
    assert cache.put(first, engine, b'1') and cache.put(second, engine, b'2')
    assert cache.get(first, engine) == b'1'
    assert cache.put(third, engine, b'3')
    assert cache.get(second, engine) is None and cache.get(first, engine) == b'1'


@pytest.mark.parametrize('cache', [SubsetCache(maximum_bytes=0), SubsetCache(maximum_entries=0),
                                SubsetCache(maximum_bytes=1)])
def test_disabled_or_oversized_results_are_not_retained(cache):
    key, engine = (b'Own', 'AB', '{}'), (object(),)
    assert not cache.put(key, engine, b'Result') and cache.get(key, engine) is None


def test_concurrent_cache_access_preserves_immutable_results():
    cache = SubsetCache()
    key, engine = (b'Own', 'AB', '{}'), (object(),)

    def consume(_):
        cache.put(key, engine, b'Result')
        return cache.get(key, engine)

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(consume, range(32))) == [b'Result']*32


@pytest.mark.skipif(not hasattr(os, 'fork'), reason='POSIX fork is unavailable')
def test_forked_child_subsets_normally_while_parent_cache_is_locked(tmp_path):
    import signal

    usage = usage_at(tmp_path)
    expected = subset_font(usage)
    cache = embedding._SUBSET_CACHE
    held, release = Event(), Event()

    def hold_parent_cache():
        with cache._lock:
            held.set()
            release.wait(10)

    worker = Thread(target=hold_parent_cache, daemon=True)
    worker.start()
    assert held.wait(5)
    try:
        child = os.fork()
        if child == 0:
            signal.alarm(5)
            try:
                actual = subset_font(usage)
                os._exit(0 if actual == expected else 2)
            except BaseException:  # noqa: BLE001 - child must exit, never re-enter the inherited pytest runner
                os._exit(3)
        _, status = os.waitpid(child, 0)
        assert os.waitstatus_to_exitcode(status) == 0
    finally:
        release.set()
        worker.join(5)
