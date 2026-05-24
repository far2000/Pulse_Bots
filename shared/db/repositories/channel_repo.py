"""DestinationChannel + PublishLog helpers."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import BotType
from shared.db.models.channel import (
    DestinationChannel,
    PublishLog,
    PublishStatus,
)


class ChannelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self, telegram_chat_id: int, bot_type: BotType, title: str | None = None
    ) -> DestinationChannel:
        stmt = select(DestinationChannel).where(
            DestinationChannel.telegram_chat_id == telegram_chat_id
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing
        row = DestinationChannel(
            telegram_chat_id=telegram_chat_id, bot_type=bot_type, title=title
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def log(
        self,
        *,
        channel_id: uuid.UUID,
        article_id: uuid.UUID | None,
        status: PublishStatus,
        telegram_message_id: int | None = None,
        error: str | None = None,
    ) -> None:
        await self.session.execute(
            pg_insert(PublishLog).values(
                channel_id=channel_id,
                article_id=article_id,
                status=status,
                telegram_message_id=telegram_message_id,
                error=error,
            )
        )
