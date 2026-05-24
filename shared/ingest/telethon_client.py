"""Telethon userbot bootstrap.

The session string is created once locally via `scripts/login_telethon.py`
and placed in env (`TELETHON_SESSION`). A dedicated, NON-personal Telegram
account is strongly recommended — reading other channels via a user account
can violate Telegram's ToS and may result in account bans.
"""

from __future__ import annotations

from telethon import TelegramClient
from telethon.sessions import StringSession

from shared.config import get_settings


def build_telethon_client(*, session_string: str | None = None) -> TelegramClient:
    """Build a TelegramClient bound to the configured user session.

    Pass `session_string=""` (or no env var) to fall back to an in-memory session —
    only useful from the interactive login script.
    """
    settings = get_settings()
    session = StringSession(
        session_string if session_string is not None else settings.telethon_session
    )
    client = TelegramClient(
        session=session,
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        # Conservative auto-reconnect knobs — Telethon retries forever by default.
        auto_reconnect=True,
        retry_delay=2,
        request_retries=5,
        connection_retries=10,
        flood_sleep_threshold=120,
        receive_updates=True,
        # Pretend to be a fairly recent mobile client to reduce ban risk.
        device_model="PulseBots",
        system_version="1.0",
        app_version="0.1.0",
    )
    return client
