"""Application settings loaded from environment via pydantic-settings.

A single `Settings` object is shared across the userbot reader, the aiogram
publisher, the scheduler, and the scripts. Treat it as read-only at runtime.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotType(str, Enum):
    """Discriminator used to scope rows in shared tables to a specific bot."""

    NEWS = "news"
    SPORTS = "sports"
    CARS = "cars"
    PRICES = "prices"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── General ────────────────────────────────────────────────────────────
    app_env: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    bot_type: BotType = BotType.NEWS

    # ── PostgreSQL ─────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://pulse:pulse@localhost:5432/pulse_bots"
    )
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_echo: bool = False

    # ── MinIO ──────────────────────────────────────────────────────────────
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "pulse-bots"
    minio_region: str = "us-east-1"
    minio_public_domain: str = "http://localhost:9000/pulse-bots"
    minio_use_ssl: bool = False

    # ── Telethon userbot ───────────────────────────────────────────────────
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telethon_session: str = ""

    # ── aiogram bot ────────────────────────────────────────────────────────
    bot_token: str = ""
    destination_channel_id: int = 0
    admin_ids: list[int] = Field(default_factory=list)

    # ── LLM (Avalai — OpenAI-compatible gateway) ───────────────────────────
    avalai_api_key: str = ""
    avalai_base_url: str = "https://api.avalai.ir/v1"
    llm_model: str = "gemini-2.0-flash"
    llm_timeout_seconds: int = 30

    # ── Pipeline tuning ────────────────────────────────────────────────────
    min_publish_importance: int = 2
    summary_language: str = "fa"
    publish_rate_per_second: float = 1.0
    catchup_interval_minutes: int = 15
    catchup_lookback_messages: int = 50

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, v: str | list[int]) -> list[int]:
        if isinstance(v, str):
            return [int(x) for x in v.split(",") if x.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()
