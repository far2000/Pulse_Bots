"""Idempotent MediaFile writes."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models.media import MediaFile


class MediaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_hash(self, content_hash: str) -> MediaFile | None:
        stmt = select(MediaFile).where(MediaFile.content_hash == content_hash)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert(self, media: MediaFile) -> MediaFile:
        """Insert; if dedup row already exists, return the existing one."""
        existing = await self.get_by_hash(media.content_hash)
        if existing is not None:
            return existing
        stmt = (
            pg_insert(MediaFile)
            .values(
                id=media.id,
                content_hash=media.content_hash,
                media_type=media.media_type,
                storage_key=media.storage_key,
                public_url=media.public_url,
                thumbnail_key=media.thumbnail_key,
                thumbnail_url=media.thumbnail_url,
                mime_type=media.mime_type,
                width=media.width,
                height=media.height,
                duration_seconds=media.duration_seconds,
                size_bytes=media.size_bytes,
                original_filename=media.original_filename,
            )
            .on_conflict_do_nothing(index_elements=["content_hash"])
            .returning(MediaFile.id)
        )
        result = await self.session.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is None:
            # raced — fetch the winner
            winner = await self.get_by_hash(media.content_hash)
            assert winner is not None
            return winner
        return await self.session.get(MediaFile, inserted_id)  # type: ignore[return-value]
