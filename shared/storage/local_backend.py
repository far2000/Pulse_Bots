"""Filesystem storage backend — handy for local tests without MinIO running."""

from __future__ import annotations

import asyncio
from pathlib import Path

from shared.storage.base import StorageBackend, StoredObject


class LocalStorage(StorageBackend):
    def __init__(self, root: str | Path, public_base_url: str | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None

    def _path_for(self, key: str) -> Path:
        return self.root / key

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        cache_control: str | None = "public, max-age=31536000, immutable",
    ) -> StoredObject:
        target = self._path_for(key)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, data)
        return StoredObject(
            key=key,
            public_url=self.public_url(key),
            size=len(data),
            content_type=content_type,
        )

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path_for(key).exists)

    async def delete(self, key: str) -> None:
        path = self._path_for(key)
        if await asyncio.to_thread(path.exists):
            await asyncio.to_thread(path.unlink)

    def public_url(self, key: str) -> str | None:
        if self.public_base_url is None:
            return None
        return f"{self.public_base_url}/{key}"
