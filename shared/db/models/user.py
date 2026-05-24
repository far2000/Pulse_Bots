"""User and UserBotSession — Telegram users that interact with our bots."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Enum as SAEnum, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.config import BotType
from shared.db.base import Base


class User(Base):
    __tablename__ = "users"

    # Telegram user ids are 64-bit ints — use them as the PK directly.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    first_seen_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    last_active_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    __table_args__ = (Index("ix_users_last_active_at", "last_active_at"),)


class UserBotSession(Base):
    """Per-(user, bot) interaction state — used for personalization later."""

    __tablename__ = "user_bot_sessions"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    bot_type: Mapped[BotType] = mapped_column(
        SAEnum(BotType, name="bot_type"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    last_interaction_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    interaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
