"""SourceChannel — a Telegram channel we monitor with the userbot."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Index, String, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.config import BotType
from shared.db.base import Base, TimestampMixin


class SourceChannel(Base, TimestampMixin):
    __tablename__ = "source_channels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bot_type: Mapped[BotType] = mapped_column(
        SAEnum(BotType, name="bot_type"), nullable=False
    )
    # Username (e.g. "@some_news") OR numeric -100... id stored as string for flexibility
    channel_username_or_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Resolved numeric Telegram id once known — used by Telethon entity cache
    telegram_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    __table_args__ = (
        Index("ix_source_channels_bot_enabled", "bot_type", "enabled"),
        Index(
            "uq_source_channels_bot_channel",
            "bot_type",
            "channel_username_or_id",
            unique=True,
        ),
    )
