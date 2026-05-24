"""Read/write helpers for SourceChannel."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import BotType
from shared.db.models.source import SourceChannel


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_enabled(self, bot_type: BotType) -> list[SourceChannel]:
        stmt = (
            select(SourceChannel)
            .where(SourceChannel.bot_type == bot_type, SourceChannel.enabled.is_(True))
            .order_by(SourceChannel.added_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_all(self, bot_type: BotType) -> list[SourceChannel]:
        stmt = (
            select(SourceChannel)
            .where(SourceChannel.bot_type == bot_type)
            .order_by(SourceChannel.added_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, source_id: uuid.UUID) -> SourceChannel | None:
        return await self.session.get(SourceChannel, source_id)

    async def get_by_channel(
        self, bot_type: BotType, channel: str
    ) -> SourceChannel | None:
        stmt = select(SourceChannel).where(
            SourceChannel.bot_type == bot_type,
            SourceChannel.channel_username_or_id == channel,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add(
        self,
        bot_type: BotType,
        channel: str,
        title: str | None = None,
    ) -> SourceChannel:
        existing = await self.get_by_channel(bot_type, channel)
        if existing is not None:
            return existing
        row = SourceChannel(
            bot_type=bot_type,
            channel_username_or_id=channel,
            title=title,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def set_enabled(self, source_id: uuid.UUID, enabled: bool) -> None:
        await self.session.execute(
            update(SourceChannel)
            .where(SourceChannel.id == source_id)
            .values(enabled=enabled)
        )

    async def update_last_message_id(
        self, source_id: uuid.UUID, message_id: int
    ) -> None:
        """Bump the last_message_id only forward."""
        await self.session.execute(
            update(SourceChannel)
            .where(
                SourceChannel.id == source_id,
                SourceChannel.last_message_id < message_id,
            )
            .values(last_message_id=message_id)
        )

    async def update_resolved_id(
        self, source_id: uuid.UUID, telegram_id: int
    ) -> None:
        await self.session.execute(
            update(SourceChannel)
            .where(SourceChannel.id == source_id)
            .values(telegram_channel_id=telegram_id)
        )
