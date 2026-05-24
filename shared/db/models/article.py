"""Article — a normalized, deduped, summarized message from a source channel."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.config import BotType
from shared.db.base import Base
from shared.db.models.media import MediaFile


class ArticleStatus(str, enum.Enum):
    INGESTED = "ingested"      # text + media saved, awaiting summarization
    SUMMARIZED = "summarized"  # ready to publish
    PUBLISHED = "published"
    FAILED = "failed"


class ArticleRole(str, enum.Enum):
    HERO = "hero"
    GALLERY = "gallery"


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bot_type: Mapped[BotType] = mapped_column(
        SAEnum(BotType, name="bot_type"), nullable=False
    )
    source_channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # SHA-256 of normalized text — primary text dedup key
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    original_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    summary_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    summary_prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    posted_at_source: Mapped[datetime | None] = mapped_column(nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)

    status: Mapped[ArticleStatus] = mapped_column(
        SAEnum(ArticleStatus, name="article_status"),
        nullable=False,
        default=ArticleStatus.INGESTED,
    )
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    # Media group key from Telegram (grouped_id) for album reassembly.
    grouped_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    media_links: Mapped[list["ArticleMedia"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="ArticleMedia.position",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "bot_type", "content_hash", name="uq_articles_bot_content_hash"
        ),
        UniqueConstraint(
            "source_channel_id",
            "source_message_id",
            name="uq_articles_source_message",
        ),
        Index("ix_articles_bot_status_ingested", "bot_type", "status", "ingested_at"),
        Index("ix_articles_bot_published", "bot_type", "published_at"),
        Index("ix_articles_grouped", "source_channel_id", "grouped_id"),
    )


class ArticleMedia(Base):
    """M2M link between Article and MediaFile with ordering + role."""

    __tablename__ = "article_media"

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("media_files.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    role: Mapped[ArticleRole] = mapped_column(
        SAEnum(ArticleRole, name="article_media_role"),
        nullable=False,
        default=ArticleRole.GALLERY,
    )

    article: Mapped["Article"] = relationship(back_populates="media_links")
    media: Mapped[MediaFile] = relationship(lazy="joined")
