"""User / UserBotSession upserts."""

from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import BotType
from shared.db.models.user import User, UserBotSession
from shared.utils.time import utcnow


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_user(
        self,
        *,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
        is_premium: bool = False,
    ) -> User:
        now = utcnow()
        stmt = (
            pg_insert(User)
            .values(
                id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=language_code,
                is_premium=is_premium,
                last_active_at=now,
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "language_code": language_code,
                    "is_premium": is_premium,
                    "last_active_at": now,
                },
            )
        )
        await self.session.execute(stmt)
        return await self.session.get(User, telegram_id)  # type: ignore[return-value]

    async def touch_session(self, user_id: int, bot_type: BotType) -> None:
        now = utcnow()
        stmt = (
            pg_insert(UserBotSession)
            .values(
                user_id=user_id,
                bot_type=bot_type,
                last_interaction_at=now,
                interaction_count=1,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "bot_type"],
                set_={
                    "last_interaction_at": now,
                    "interaction_count": UserBotSession.interaction_count + 1,
                },
            )
        )
        await self.session.execute(stmt)

    async def count_active(self, bot_type: BotType, since) -> int:
        stmt = select(func.count(UserBotSession.user_id)).where(
            UserBotSession.bot_type == bot_type,
            UserBotSession.last_interaction_at >= since,
        )
        return int((await self.session.execute(stmt)).scalar_one() or 0)
