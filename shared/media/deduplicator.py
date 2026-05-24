"""Two-tier dedup: in-memory TTL cache first, then Postgres unique constraint.

The cache is an optimization. Postgres is the source of truth — a stale or
evicted cache entry just means we round-trip to the DB.
"""

from __future__ import annotations

from shared.cache.memory_cache import InMemoryCache

# 30 days — aggressive enough to cover most dedup; stale keys fall back to DB.
DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 30


class MediaDeduplicator:
    def __init__(self, cache: InMemoryCache, *, namespace: str = "dedup") -> None:
        self.cache = cache
        self.namespace = namespace

    def _key(self, kind: str, hash_: str) -> str:
        return f"{self.namespace}:{kind}:{hash_}"

    async def seen(self, kind: str, hash_: str) -> bool:
        """True if we've already processed this hash recently."""
        return await self.cache.exists(self._key(kind, hash_))

    async def mark(self, kind: str, hash_: str, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        await self.cache.set(self._key(kind, hash_), "1", ex=ttl)
