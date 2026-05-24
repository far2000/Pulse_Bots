"""One-time interactive Telethon login.

Run locally before deploying:

    uv run python scripts/login_telethon.py

You will be prompted for:
  - Phone number
  - Login code (sent to that Telegram account)
  - 2FA password (if enabled)

The script prints a `TELETHON_SESSION=...` line — copy the value into your
`.env` (or set it in Coolify). Treat the session string like a password.

⚠️  Use a DEDICATED Telegram account, NOT your personal one. Userbots that
read channels you don't own can be flagged by Telegram and banned. A burner
SIM / second account is strongly recommended.
"""

from __future__ import annotations

import asyncio
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession

from shared.config import get_settings


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        print(
            "❌ TELEGRAM_API_ID / TELEGRAM_API_HASH not set. "
            "Get them from https://my.telegram.org and put them in .env first.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("─" * 60)
    print("Telethon interactive login")
    print("Use a DEDICATED Telegram account — not your personal one.")
    print("─" * 60)

    async with TelegramClient(
        StringSession(),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    ) as client:
        session_string = client.session.save()  # type: ignore[union-attr]
        me = await client.get_me()
        print()
        print(f"✅ Logged in as: {me.first_name} (id={me.id}, username={me.username})")
        print()
        print("Paste this into your .env (or Coolify):")
        print()
        print(f"TELETHON_SESSION={session_string}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
