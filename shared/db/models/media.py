"""MediaFile — physical file stored in object storage, deduped by content hash."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Enum as SAEnum, Float, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db.base import Base


class MediaType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # SHA-256 of the original file bytes — unique, used for dedup.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    media_type: Mapped[MediaType] = mapped_column(
        SAEnum(MediaType, name="media_type"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    public_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    mime_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    __table_args__ = (Index("ix_media_files_content_hash", "content_hash"),)
