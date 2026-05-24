"""aiogram middlewares: user tracking + simple per-user throttle."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser
from loguru import logger

from bots.news.config import BOT_TYPE
from shared.db import get_session
from shared.db.repositories import UserRepository

# In-process throttle: per-user min gap between updates.
_THROTTLE_GAP_SECONDS = 0.5
_last_seen: dict[int, float] = {}


class UserTrackingMiddleware(BaseMiddleware):
    """Upsert user + per-bot session on every message and callback."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None and isinstance(event, (Message, CallbackQuery)):
            tg_user = event.from_user
        if tg_user is None:
            return await handler(event, data)

        # Throttle (in-process, cheap).
        now = time.monotonic()
        last = _last_seen.get(tg_user.id, 0.0)
        if now - last < _THROTTLE_GAP_SECONDS:
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer()
                except Exception:
                    pass
            return None
        _last_seen[tg_user.id] = now

        try:
            async with get_session() as session:
                repo = UserRepository(session)
                await repo.upsert_user(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                    language_code=tg_user.language_code,
                    is_premium=bool(tg_user.is_premium),
                )
                await repo.touch_session(tg_user.id, BOT_TYPE)
        except Exception:
            # Tracking must never block user interaction.
            logger.exception("User tracking failed for {}", tg_user.id)

        return await handler(event, data)
