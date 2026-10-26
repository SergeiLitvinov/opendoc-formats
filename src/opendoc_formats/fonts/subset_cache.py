"""Process-local LRU bounded by retained font/text payload and entry count."""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock

from opendoc_formats.native.common import positive_int

SubsetKey = tuple[bytes, str, str]


class SubsetCache:
    def __init__(self, *, maximum_bytes: int = 32*1024*1024, maximum_entries: int = 32) -> None:
        positive_int(maximum_bytes, 'maximum_bytes', zero=True)
        positive_int(maximum_entries, 'maximum_entries', zero=True)
        self.maximum_bytes, self.maximum_entries = maximum_bytes, maximum_entries
        self._entries: OrderedDict[SubsetKey, bytes] = OrderedDict()
        self._bytes = 0
        self._engine: tuple[object, ...] | None = None
        self._lock = RLock()

    @staticmethod
    def _cost(key: SubsetKey, result: bytes) -> int:
        # Charge four bytes per character without allocating another encoded copy.
        return len(key[0])+4*len(key[1])+4*len(key[2])+len(result)

    def _select_engine(self, engine: tuple[object, ...]) -> None:
        if self._engine != engine:
            self._entries.clear()
            self._bytes = 0
            self._engine = engine

    def get(self, key: SubsetKey, engine: tuple[object, ...]) -> bytes | None:
        with self._lock:
            self._select_engine(engine)
            value = self._entries.get(key)
            if value is not None:
                self._entries.move_to_end(key)
            return value

    def put(self, key: SubsetKey, engine: tuple[object, ...], result: bytes) -> bool:
        cost = self._cost(key, result)
        with self._lock:
            self._select_engine(engine)
            if key in self._entries or cost > self.maximum_bytes or not self.maximum_entries or not self.maximum_bytes:
                return False
            while self._entries and (self._bytes+cost > self.maximum_bytes or len(self._entries) >= self.maximum_entries):
                old_key, old_result = self._entries.popitem(last=False)
                self._bytes -= self._cost(old_key, old_result)
            self._entries[key] = result
            self._bytes += cost
            return True

    def discard(self, key: SubsetKey, engine: tuple[object, ...]) -> None:
        with self._lock:
            if self._engine == engine:
                result = self._entries.pop(key, None)
                if result is not None:
                    self._bytes -= self._cost(key, result)
