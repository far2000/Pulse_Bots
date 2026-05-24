"""NewsApp — composition root.

Builds singletons (DB, Telethon, aiogram, storage, summarizer, in-memory
cache, publisher), wires the Telethon reader and aiogram dispatcher, and
runs the APScheduler-driven maintenance jobs. Designed to be
cancellation-safe so SIGTERM from Coolify triggers a clean shutdown.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from telethon import TelegramClient

from bots.news.config import BOT_TYPE
from bots.news.handlers import admin as admin_handlers
from bots.news.handlers import callbacks as callback_handlers
from bots.news.handlers import commands as command_handlers
from bots.news.jobs import register_jobs
from bots.news.middlewares import UserTrackingMiddleware
from bots.news.pipeline import IngestPipeline, PublishLoop
from bots.news.reader import TelethonReader
from shared.ai.avalai_client import AvalaiSummarizer
from shared.cache.memory_cache import get_cache
from shared.config import get_settings
from shared.db import dispose_engine
from shared.ingest.telethon_client import build_telethon_client
from shared.media.deduplicator import MediaDeduplicator
from shared.media.processor import ImageProcessor
from shared.publishers.telegram_publisher import TelegramPublisher
from shared.storage import build_storage


class NewsApp:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.bot: Optional[Bot] = None
        self.dispatcher: Optional[Dispatcher] = None
        self.tele_client: Optional[TelegramClient] = None
        self.reader: Optional[TelethonReader] = None
        self.pipeline: Optional[IngestPipeline] = None
        self.publish_loop: Optional[PublishLoop] = None
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._aiogram_task: Optional[asyncio.Task[None]] = None
        self._publisher_task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        # ── Storage bucket bootstrap ──────────────────────────────────────
        storage = build_storage()
        await storage.ensure_ready()

        cache = get_cache()
        dedup = MediaDeduplicator(cache)
        image_processor = ImageProcessor()
        summarizer = AvalaiSummarizer(cache)

        # ── aiogram bot ───────────────────────────────────────────────────
        self.bot = Bot(
            token=self.settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.dispatcher = Dispatcher(storage=MemoryStorage())

        # Middlewares
        self.dispatcher.message.middleware(UserTrackingMiddleware())
        self.dispatcher.callback_query.middleware(UserTrackingMiddleware())

        # Routers
        self.dispatcher.include_router(command_handlers.router)
        self.dispatcher.include_router(callback_handlers.router)
        self.dispatcher.include_router(admin_handlers.router)

        # ── Publisher ─────────────────────────────────────────────────────
        publisher = TelegramPublisher(
            bot=self.bot,
            chat_id=self.settings.destination_channel_id,
            rate_per_second=self.settings.publish_rate_per_second,
        )

        # ── Telethon userbot ──────────────────────────────────────────────
        self.tele_client = build_telethon_client()

        self.pipeline = IngestPipeline(
            bot_type=BOT_TYPE,
            tele_client=self.tele_client,
            storage=storage,
            dedup=dedup,
            image_processor=image_processor,
            summarizer=summarizer,
        )
        self.reader = TelethonReader(
            bot_type=BOT_TYPE,
            client=self.tele_client,
            pipeline=self.pipeline,
        )
        self.publish_loop = PublishLoop(bot_type=BOT_TYPE, publisher=publisher)

        # ── Connect Telethon ──────────────────────────────────────────────
        await self.tele_client.start()  # uses session string — no interactive prompt
        me = await self.tele_client.get_me()
        logger.info("Telethon connected as: id={} username={}", me.id, getattr(me, "username", None))

        await self.reader.start()

        # ── Scheduler ─────────────────────────────────────────────────────
        self.scheduler = AsyncIOScheduler()
        register_jobs(
            self.scheduler,
            reader=self.reader,
            pipeline=self.pipeline,
        )
        self.scheduler.start()

        # ── Start aiogram polling + publish loop as background tasks ──────
        self._aiogram_task = asyncio.create_task(
            self.dispatcher.start_polling(self.bot, handle_signals=False),
            name="aiogram-polling",
        )
        self._publisher_task = asyncio.create_task(
            self.publish_loop.run(), name="publish-loop"
        )
        logger.info("All components started.")

    async def stop(self) -> None:
        logger.info("Shutting down…")

        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        if self.publish_loop:
            self.publish_loop.request_stop()
        if self._publisher_task:
            self._publisher_task.cancel()
            try:
                await self._publisher_task
            except (asyncio.CancelledError, Exception):
                pass

        if self.dispatcher:
            await self.dispatcher.stop_polling()
        if self._aiogram_task:
            self._aiogram_task.cancel()
            try:
                await self._aiogram_task
            except (asyncio.CancelledError, Exception):
                pass

        if self.reader:
            await self.reader.stop()
        if self.tele_client and self.tele_client.is_connected():
            await self.tele_client.disconnect()

        if self.bot:
            await self.bot.session.close()

        await dispose_engine()
