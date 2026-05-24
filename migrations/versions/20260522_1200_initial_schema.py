"""initial schema

Revision ID: 20260522_initial
Revises:
Create Date: 2026-05-22 12:00:00

This migration creates the full initial schema. After this, prefer
`alembic revision --autogenerate` for incremental changes.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260522_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


bot_type_enum = sa.Enum("news", "sports", "cars", "prices", name="bot_type")
media_type_enum = sa.Enum("image", "video", "document", name="media_type")
article_status_enum = sa.Enum(
    "ingested", "summarized", "published", "failed", name="article_status"
)
article_media_role_enum = sa.Enum("hero", "gallery", name="article_media_role")
publish_status_enum = sa.Enum(
    "pending", "published", "failed", "skipped", name="publish_status"
)


def upgrade() -> None:
    bind = op.get_bind()
    for e in (
        bot_type_enum,
        media_type_enum,
        article_status_enum,
        article_media_role_enum,
        publish_status_enum,
    ):
        e.create(bind, checkfirst=True)

    # ── source_channels ──────────────────────────────────────────────────
    op.create_table(
        "source_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bot_type", bot_type_enum, nullable=False),
        sa.Column("channel_username_or_id", sa.String(255), nullable=False),
        sa.Column("telegram_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_message_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("added_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_source_channels_bot_enabled", "source_channels", ["bot_type", "enabled"]
    )
    op.create_index(
        "uq_source_channels_bot_channel",
        "source_channels",
        ["bot_type", "channel_username_or_id"],
        unique=True,
    )

    # ── media_files ──────────────────────────────────────────────────────
    op.create_table(
        "media_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("media_type", media_type_enum, nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("public_url", sa.String(2048), nullable=True),
        sa.Column("thumbnail_key", sa.String(1024), nullable=True),
        sa.Column("thumbnail_url", sa.String(2048), nullable=True),
        sa.Column("mime_type", sa.String(127), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("original_filename", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.UniqueConstraint("content_hash", name="uq_media_files_content_hash"),
    )
    op.create_index("ix_media_files_content_hash", "media_files", ["content_hash"])

    # ── articles ─────────────────────────────────────────────────────────
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bot_type", bot_type_enum, nullable=False),
        sa.Column(
            "source_channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_message_id", sa.BigInteger(), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("summary_model", sa.String(128), nullable=True),
        sa.Column("summary_prompt_version", sa.String(32), nullable=True),
        sa.Column("posted_at_source", sa.DateTime(timezone=False), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("status", article_status_enum, nullable=False, server_default="ingested"),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("grouped_id", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("bot_type", "content_hash", name="uq_articles_bot_content_hash"),
        sa.UniqueConstraint("source_channel_id", "source_message_id", name="uq_articles_source_message"),
    )
    op.create_index(
        "ix_articles_bot_status_ingested",
        "articles",
        ["bot_type", "status", "ingested_at"],
    )
    op.create_index(
        "ix_articles_bot_published", "articles", ["bot_type", "published_at"]
    )
    op.create_index(
        "ix_articles_grouped", "articles", ["source_channel_id", "grouped_id"]
    )

    # ── article_media ────────────────────────────────────────────────────
    op.create_table(
        "article_media",
        sa.Column(
            "article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "media_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media_files.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("role", article_media_role_enum, nullable=False, server_default="gallery"),
    )

    # ── users ────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("language_code", sa.String(16), nullable=True),
        sa.Column("is_premium", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_seen_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("last_active_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.create_index("ix_users_last_active_at", "users", ["last_active_at"])

    # ── user_bot_sessions ────────────────────────────────────────────────
    op.create_table(
        "user_bot_sessions",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("bot_type", bot_type_enum, primary_key=True),
        sa.Column("joined_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("last_interaction_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("interaction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )

    # ── destination_channels ─────────────────────────────────────────────
    op.create_table(
        "destination_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("bot_type", bot_type_enum, nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
    )

    # ── publish_logs ─────────────────────────────────────────────────────
    op.create_table(
        "publish_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("articles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("destination_channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("status", publish_status_enum, nullable=False),
        sa.Column("error", sa.String(2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("publish_logs")
    op.drop_table("destination_channels")
    op.drop_table("user_bot_sessions")
    op.drop_table("users")
    op.drop_table("article_media")
    op.drop_table("articles")
    op.drop_table("media_files")
    op.drop_table("source_channels")
    bind = op.get_bind()
    for e in (
        publish_status_enum,
        article_media_role_enum,
        article_status_enum,
        media_type_enum,
        bot_type_enum,
    ):
        e.drop(bind, checkfirst=True)
