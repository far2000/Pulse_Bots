"""DestinationChannel and PublishLog — channels we publish to + audit trail."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.config import BotType
from shared.db.base import Base, TimestampMixin


class PublishStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"
    SKIPPED = "skipped"


class DestinationChannel(Base, TimestampMixin):
    __tablename__ = "destination_channels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    bot_type: Mapped[BotType] = mapped_column(
        SAEnum(BotType, name="bot_type"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )


class PublishLog(Base):
    __tablename__ = "publish_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Nullable so we can log skipped/failed publishes even if the article was deleted.
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="SET NULL"),
        nullable=True,
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("destination_channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    status: Mapped[PublishStatus] = mapped_column(
        SAEnum(PublishStatus, name="publish_status"), nullable=False
    )
    error: Mapped[str | None] = mapped_column(String(2048), nullable=True)
