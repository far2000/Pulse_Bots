"""In-process async cache (TTL + LRU bound).

Replaces the previous Redis-backed cache. Used for:
  - Article / media dedup hits (Postgres unique constraints are still truth).
  - Gemini summary cache (optimization; missing means re-call the API).

Single-process only — fine for the current single-container deployment.
If we later need multi-instance, swap in a Redis-backed impl with the
same async surface area (get/set/exists/delete with `ex=` TTL).
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict


class InMemoryCache:
    """Bounded async TTL cache. Thread-safe via a single asyncio lock.

    Values are stored as `bytes | str` to mirror Redis's behavior when callers
    JSON-serialize before put. None means "not present".
    """

    def __init__(self, *, max_entries: int = 50_000) -> None:
        self._data: OrderedDict[str, tuple[bytes | str, float | None]] = OrderedDict()
        self._max = max_entries
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> bytes | str | None:
        async with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            value, expires_at = item
            if expires_at is not None and expires_at < time.monotonic():
                self._data.pop(key, None)
                return None
            # LRU touch
            self._data.move_to_end(key)
            return value

    async def set(
        self,
        key: str,
        value: bytes | str,
        *,
        ex: int | None = None,
    ) -> None:
        expires_at = time.monotonic() + ex if ex else None
        async with self._lock:
            self._data[key] = (value, expires_at)
            self._data.move_to_end(key)
            self._evict_locked()

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    def _evict_locked(self) -> None:
        # LRU eviction. Also do a small opportunistic TTL sweep.
        now = time.monotonic()
        # Drop a handful of expired entries from the front (cheap).
        for _ in range(min(8, len(self._data))):
            try:
                key, (_, exp) = next(iter(self._data.items()))
            except StopIteration:
                break
            if exp is not None and exp < now:
                self._data.pop(key, None)
            else:
                break
        while len(self._data) > self._max:
            self._data.popitem(last=False)


_default: InMemoryCache | None = None


def get_cache() -> InMemoryCache:
    """Process-wide singleton cache."""
    global _default
    if _default is None:
        _default = InMemoryCache()
    return _default
