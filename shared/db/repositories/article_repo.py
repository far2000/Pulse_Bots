"""Idempotent article writes + read helpers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.config import BotType
from shared.db.models.article import (
    Article,
    ArticleMedia,
    ArticleRole,
    ArticleStatus,
)


class ArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists_by_source_message(
        self, source_channel_id: uuid.UUID, source_message_id: int
    ) -> bool:
        stmt = select(Article.id).where(
            Article.source_channel_id == source_channel_id,
            Article.source_message_id == source_message_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def exists_by_content_hash(
        self, bot_type: BotType, content_hash: str
    ) -> bool:
        stmt = select(Article.id).where(
            Article.bot_type == bot_type, Article.content_hash == content_hash
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def get_by_grouped(
        self, source_channel_id: uuid.UUID, grouped_id: int
    ) -> Article | None:
        stmt = (
            select(Article)
            .where(
                Article.source_channel_id == source_channel_id,
                Article.grouped_id == grouped_id,
            )
            .options(selectinload(Article.media_links))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def insert_idempotent(self, article: Article) -> Article | None:
        """Insert ON CONFLICT DO NOTHING on (source_channel_id, source_message_id).

        Returns the inserted row, or None if it was a duplicate.
        """
        values = {
            "id": article.id,
            "bot_type": article.bot_type,
            "source_channel_id": article.source_channel_id,
            "source_message_id": article.source_message_id,
            "source_url": article.source_url,
            "content_hash": article.content_hash,
            "original_text": article.original_text,
            "title": article.title,
            "summary": article.summary,
            "summary_model": article.summary_model,
            "summary_prompt_version": article.summary_prompt_version,
            "posted_at_source": article.posted_at_source,
            "status": article.status,
            "importance": article.importance,
            "tags": article.tags,
            "grouped_id": article.grouped_id,
        }
        stmt = (
            pg_insert(Article)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["source_channel_id", "source_message_id"]
            )
            .returning(Article.id)
        )
        result = await self.session.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is None:
            return None
        return await self.session.get(Article, inserted_id)

    async def attach_media(
        self,
        article_id: uuid.UUID,
        media_ids: Iterable[uuid.UUID],
        *,
        hero_first: bool = True,
    ) -> None:
        rows = []
        for i, mid in enumerate(media_ids):
            rows.append(
                {
                    "article_id": article_id,
                    "media_id": mid,
                    "position": i,
                    "role": ArticleRole.HERO if i == 0 and hero_first else ArticleRole.GALLERY,
                }
            )
        if not rows:
            return
        stmt = pg_insert(ArticleMedia).values(rows).on_conflict_do_nothing()
        await self.session.execute(stmt)

    async def update_summary(
        self,
        article_id: uuid.UUID,
        *,
        title: str | None,
        summary: str,
        importance: int,
        tags: list[str],
        model: str,
        prompt_version: str,
    ) -> None:
        await self.session.execute(
            update(Article)
            .where(Article.id == article_id)
            .values(
                title=title,
                summary=summary,
                importance=importance,
                tags=tags,
                summary_model=model,
                summary_prompt_version=prompt_version,
                status=ArticleStatus.SUMMARIZED,
            )
        )

    async def mark_failed(self, article_id: uuid.UUID, reason: str) -> None:
        await self.session.execute(
            update(Article)
            .where(Article.id == article_id)
            .values(status=ArticleStatus.FAILED, extra=Article.extra.op("||")(
                {"error": reason}
            ))
        )

    async def mark_published(
        self, article_id: uuid.UUID, published_at: datetime
    ) -> None:
        await self.session.execute(
            update(Article)
            .where(Article.id == article_id)
            .values(status=ArticleStatus.PUBLISHED, published_at=published_at)
        )

    async def list_pending_publish(
        self, bot_type: BotType, *, min_importance: int, limit: int = 20
    ) -> list[Article]:
        stmt = (
            select(Article)
            .where(
                Article.bot_type == bot_type,
                Article.status == ArticleStatus.SUMMARIZED,
                Article.importance >= min_importance,
            )
            .order_by(Article.posted_at_source.asc().nullsfirst(), Article.ingested_at.asc())
            .limit(limit)
            .options(selectinload(Article.media_links))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_failed_summaries(
        self, bot_type: BotType, *, limit: int = 50
    ) -> list[Article]:
        """Articles ingested but never summarized — for retry job."""
        stmt = (
            select(Article)
            .where(
                Article.bot_type == bot_type,
                Article.status.in_([ArticleStatus.INGESTED, ArticleStatus.FAILED]),
            )
            .order_by(Article.ingested_at.asc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def latest_published(
        self, bot_type: BotType, *, limit: int = 5
    ) -> list[Article]:
        stmt = (
            select(Article)
            .where(
                Article.bot_type == bot_type,
                Article.status == ArticleStatus.PUBLISHED,
            )
            .order_by(Article.published_at.desc())
            .limit(limit)
            .options(selectinload(Article.media_links))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_today(self, bot_type: BotType, day_start: datetime) -> dict[str, int]:
        """Quick stats: ingested / published since `day_start`."""
        from sqlalchemy import func

        stmt = select(Article.status, func.count()).where(
            Article.bot_type == bot_type,
            Article.ingested_at >= day_start,
        ).group_by(Article.status)
        rows = (await self.session.execute(stmt)).all()
        return {status.value: int(count) for status, count in rows}
