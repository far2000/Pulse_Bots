"""Top-level orchestrator. Wires components and runs the userbot + bot together."""

from __future__ import annotations

import asyncio
import signal

from loguru import logger

from bots.news.app import NewsApp
from shared.logging import configure_logging


async def main() -> None:
    configure_logging()
    logger.info("Starting news bot…")

    app = NewsApp()
    stop_event = asyncio.Event()

    def _request_stop() -> None:
        logger.info("Received shutdown signal")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:  # pragma: no cover — Windows
            pass

    try:
        await app.start()
        await stop_event.wait()
    finally:
        await app.stop()
        logger.info("News bot stopped.")


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
