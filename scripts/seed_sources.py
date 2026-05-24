"""Seed initial source channels for the news bot.

Edit `SOURCES` below, then run:

    uv run python scripts/seed_sources.py
"""

from __future__ import annotations

import asyncio

from loguru import logger

from shared.config import BotType
from shared.db import get_session
from shared.db.repositories import SourceRepository
from shared.logging import configure_logging

# (channel_username_or_id, optional_title)
SOURCES: list[tuple[str, str | None]] = [
    # ("@bbcpersian", "BBC Persian"),
    # ("@iranintl", "Iran International"),
]


async def main() -> None:
    configure_logging()
    if not SOURCES:
        logger.warning("No sources configured — edit scripts/seed_sources.py")
        return
    async with get_session() as session:
        repo = SourceRepository(session)
        for channel, title in SOURCES:
            row = await repo.add(BotType.NEWS, channel, title=title)
            logger.info("✓ {} ({})", row.channel_username_or_id, row.id)


if __name__ == "__main__":
    asyncio.run(main())
