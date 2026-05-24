"""Storage backend interface — any S3-compatible or local fs implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class StoredObject:
    key: str
    public_url: str | None
    size: int
    content_type: str


class StorageBackend(ABC):
    @abstractmethod
    async def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        cache_control: str | None = "public, max-age=31536000, immutable",
    ) -> StoredObject:
        """Upload bytes. Returns metadata including public URL if available."""

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    def public_url(self, key: str) -> str | None:
        """Return a publicly resolvable URL for the object, or None if not public."""

    async def ensure_ready(self) -> None:
        """Optional setup hook (bucket creation, etc.). Idempotent."""
        return None
