"""End-to-end ingest pipeline + publish loop.

Pipeline stages for one message (or grouped album):

  1. Parse Telethon message → normalized form.
  2. Skip if duplicate by (source_channel, source_message) — DB-side idempotent.
  3. Compute content_hash; skip if seen (in-memory cache → DB).
  4. Download each media item from Telethon to memory.
     - Images: resize/WebP/EXIF strip + thumb, dedupe by file hash, upload.
     - Videos: dedupe by file hash, upload as-is.
  5. Persist Article + ArticleMedia (`status=ingested`).
  6. Summarize via Gemini → update Article (`status=summarized`).
  7. Publisher loop picks up `summarized` rows and posts them.

A failure at any stage downgrades the Article to `failed` (or leaves it
`ingested` if media succeeded but the LLM didn't) — never crashes.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Iterable

from loguru import logger
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.custom.message import Message

from bots.news.config import INGEST_WORKER_CONCURRENCY, PUBLISH_IDLE_SLEEP_SECONDS
from shared.ai.avalai_client import AvalaiSummarizationError
from shared.ai.summarizer import Summarizer
from shared.config import BotType, get_settings
from shared.db import get_session
from shared.db.models.article import Article, ArticleStatus
from shared.db.models.media import MediaFile, MediaType
from shared.db.models.channel import PublishStatus
from shared.db.repositories import (
    ArticleRepository,
    ChannelRepository,
    MediaRepository,
    SourceRepository,
)
from shared.ingest.message_parser import ParsedMedia, ParsedMessage, parse_message
from shared.media.deduplicator import MediaDeduplicator
from shared.media.processor import ImageProcessor
from shared.media.types import build_storage_key
from shared.publishers.telegram_publisher import TelegramPublisher
from shared.storage.base import StorageBackend
from shared.utils.text import content_hash as text_hash
from shared.utils.text import file_hash
from shared.utils.time import utcnow


class IngestPipeline:
    def __init__(
        self,
        *,
        bot_type: BotType,
        tele_client: TelegramClient,
        storage: StorageBackend,
        dedup: MediaDeduplicator,
        image_processor: ImageProcessor,
        summarizer: Summarizer,
    ) -> None:
        self.bot_type = bot_type
        self.client = tele_client
        self.storage = storage
        self.dedup = dedup
        self.images = image_processor
        self.summarizer = summarizer
        self._sem = asyncio.Semaphore(INGEST_WORKER_CONCURRENCY)

    # ─── Public entrypoint ────────────────────────────────────────────────

    async def process_message(
        self, *, source_id: uuid.UUID, messages: list[Message]
    ) -> None:
        """Fire-and-forget: schedule the heavy work, return immediately.

        Telethon's event loop must keep draining incoming updates; never block.
        """
        asyncio.create_task(
            self._run_with_limit(source_id, messages),
            name=f"ingest-{messages[0].id if messages else '?'}",
        )

    async def _run_with_limit(
        self, source_id: uuid.UUID, messages: list[Message]
    ) -> None:
        async with self._sem:
            try:
                await self._process(source_id, messages)
            except Exception:
                logger.exception("Pipeline failed for source {}", source_id)

    # ─── Core processing ──────────────────────────────────────────────────

    async def _process(self, source_id: uuid.UUID, messages: list[Message]) -> None:
        if not messages:
            return

        # The "head" message owns the text; album members may have empty text.
        head = max(messages, key=lambda m: len(m.message or ""))
        async with get_session() as session:
            source = await SourceRepository(session).get(source_id)
        if source is None:
            logger.warning("Source {} vanished during processing", source_id)
            return

        source_link = self._source_link(source.channel_username_or_id)
        parsed_head: ParsedMessage = parse_message(head, source_channel_link=source_link)
        # Collect media across all messages of the album.
        all_media: list[ParsedMedia] = []
        for m in messages:
            pm = parse_message(m, source_channel_link=source_link)
            all_media.extend(pm.media)
        parsed_head.media = all_media

        # Skip silent non-content messages (no text, no media).
        if not parsed_head.text and not parsed_head.media:
            await self._bump_last_id(source_id, head.id)
            return

        # Idempotency on (source, msg_id).
        async with get_session() as session:
            if await ArticleRepository(session).exists_by_source_message(
                source_id, head.id
            ):
                logger.debug("Skipping already-ingested msg {} from source {}", head.id, source_id)
                await SourceRepository(session).update_last_message_id(source_id, max(m.id for m in messages))
                return

        # Content-hash dedup (cross-source).
        c_hash = text_hash(parsed_head.text) if parsed_head.text else f"empty:{head.id}"
        if parsed_head.text and await self.dedup.seen("article", c_hash):
            logger.debug("Cache dedup hit for content {}", c_hash[:12])
            await self._bump_last_id(source_id, max(m.id for m in messages))
            return

        async with get_session() as session:
            if parsed_head.text and await ArticleRepository(session).exists_by_content_hash(
                self.bot_type, c_hash
            ):
                await self.dedup.mark("article", c_hash)
                await SourceRepository(session).update_last_message_id(source_id, max(m.id for m in messages))
                return

        # Download + persist media.
        media_rows: list[MediaFile] = []
        for pm in parsed_head.media:
            try:
                row = await self._ingest_media(pm)
                if row is not None:
                    media_rows.append(row)
            except Exception:
                logger.exception("Media ingest failed for msg {}", head.id)

        # Persist article.
        article = Article(
            bot_type=self.bot_type,
            source_channel_id=source_id,
            source_message_id=head.id,
            source_url=parsed_head.source_url,
            content_hash=c_hash,
            original_text=parsed_head.text,
            posted_at_source=parsed_head.posted_at,
            status=ArticleStatus.INGESTED,
            grouped_id=parsed_head.grouped_id,
        )
        async with get_session() as session:
            repo = ArticleRepository(session)
            inserted = await repo.insert_idempotent(article)
            if inserted is None:
                logger.debug("Article race lost (already inserted), skipping")
                return
            await repo.attach_media(inserted.id, [m.id for m in media_rows])
            await SourceRepository(session).update_last_message_id(
                source_id, max(m.id for m in messages)
            )
            article_id = inserted.id

        if parsed_head.text:
            await self.dedup.mark("article", c_hash)

        # Summarize (best-effort).
        await self._summarize(article_id=article_id, text=parsed_head.text, content_hash=c_hash)

    # ─── Helpers ──────────────────────────────────────────────────────────

    async def _bump_last_id(self, source_id: uuid.UUID, msg_id: int) -> None:
        async with get_session() as session:
            await SourceRepository(session).update_last_message_id(source_id, msg_id)

    def _source_link(self, channel: str) -> str | None:
        c = channel.lstrip("@")
        if c.lstrip("-").isdigit():
            return None  # private channel — no public t.me link
        return f"t.me/{c}"

    async def _ingest_media(self, pm: ParsedMedia) -> MediaFile | None:
        if pm.raw_message is None:
            return None

        try:
            raw: bytes = await self.client.download_media(pm.raw_message, file=bytes)
        except FloodWaitError as exc:
            logger.warning("FloodWait downloading media: {}s — skipping", exc.seconds)
            await asyncio.sleep(min(60, exc.seconds))
            return None
        except Exception:
            logger.exception("Failed to download media")
            return None

        if not raw:
            return None

        f_hash = file_hash(raw)

        # File-level dedup.
        async with get_session() as session:
            existing = await MediaRepository(session).get_by_hash(f_hash)
            if existing is not None:
                return existing

        when = utcnow()

        if pm.media_type == MediaType.IMAGE:
            processed = await self.images.process(raw)
            key_full = build_storage_key(
                self.bot_type, f_hash, extension=processed.full_ext, when=when
            )
            key_thumb = build_storage_key(
                self.bot_type, f_hash, extension=processed.thumb_ext, when=when, suffix="_thumb"
            )
            full_obj = await self.storage.put(
                key_full, processed.full_bytes, content_type=processed.full_mime
            )
            thumb_obj = await self.storage.put(
                key_thumb, processed.thumb_bytes, content_type=processed.thumb_mime
            )
            media = MediaFile(
                content_hash=f_hash,
                media_type=MediaType.IMAGE,
                storage_key=full_obj.key,
                public_url=full_obj.public_url,
                thumbnail_key=thumb_obj.key,
                thumbnail_url=thumb_obj.public_url,
                mime_type=processed.full_mime,
                width=processed.width,
                height=processed.height,
                size_bytes=full_obj.size,
                original_filename=pm.filename,
            )
        else:
            # Video or document: store as-is.
            ext = (pm.filename or "").rsplit(".", 1)[-1].lower() if pm.filename and "." in pm.filename else "bin"
            key = build_storage_key(self.bot_type, f_hash, extension=ext, when=when)
            obj = await self.storage.put(
                key, raw, content_type=pm.mime_type or "application/octet-stream"
            )
            media = MediaFile(
                content_hash=f_hash,
                media_type=pm.media_type,
                storage_key=obj.key,
                public_url=obj.public_url,
                mime_type=pm.mime_type,
                width=pm.width,
                height=pm.height,
                duration_seconds=pm.duration_seconds,
                size_bytes=obj.size,
                original_filename=pm.filename,
            )

        async with get_session() as session:
            return await MediaRepository(session).upsert(media)

    async def _summarize(self, *, article_id: uuid.UUID, text: str, content_hash: str) -> None:
        settings = get_settings()
        if not text:
            # Media-only post: leave as `ingested` — nothing to summarize.
            return
        try:
            result = await self.summarizer.summarize(
                text=text,
                content_hash=content_hash,
                language=settings.summary_language,
            )
        except AvalaiSummarizationError as exc:
            logger.warning("Summarization failed for article {}: {}", article_id, exc)
            async with get_session() as session:
                await ArticleRepository(session).mark_failed(article_id, str(exc))
            return
        except Exception as exc:
            logger.exception("Unexpected summarizer error: {}", exc)
            async with get_session() as session:
                await ArticleRepository(session).mark_failed(article_id, repr(exc))
            return

        async with get_session() as session:
            await ArticleRepository(session).update_summary(
                article_id,
                title=result.title,
                summary=result.summary,
                importance=result.importance,
                tags=result.tags,
                model=result.model,
                prompt_version=result.prompt_version,
            )

    # ─── Retry helpers used by the scheduler ──────────────────────────────

    async def retry_failed_summaries(self) -> None:
        async with get_session() as session:
            failed = await ArticleRepository(session).list_failed_summaries(
                self.bot_type
            )
        if not failed:
            return
        logger.info("Retrying {} failed summarizations", len(failed))
        for a in failed:
            await self._summarize(article_id=a.id, text=a.original_text, content_hash=a.content_hash)


class PublishLoop:
    """Continuous outbound loop: pulls `summarized` Articles and publishes them."""

    def __init__(self, *, bot_type: BotType, publisher: TelegramPublisher) -> None:
        self.bot_type = bot_type
        self.publisher = publisher
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        settings = get_settings()
        logger.info("Publish loop started (importance>={}).", settings.min_publish_importance)
        while not self._stop.is_set():
            try:
                published = await self._tick(settings.min_publish_importance)
                if not published:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=PUBLISH_IDLE_SLEEP_SECONDS
                    )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Publish loop iteration failed")
                await asyncio.sleep(2.0)

    async def _tick(self, min_importance: int) -> int:
        async with get_session() as session:
            articles = await ArticleRepository(session).list_pending_publish(
                self.bot_type, min_importance=min_importance, limit=10
            )

        if not articles:
            return 0

        settings = get_settings()
        async with get_session() as session:
            channel = await ChannelRepository(session).get_or_create(
                telegram_chat_id=settings.destination_channel_id,
                bot_type=self.bot_type,
            )
            channel_id = channel.id

        published_count = 0
        for article in articles:
            source = None
            async with get_session() as session:
                source = await SourceRepository(session).get(article.source_channel_id)

            try:
                result = await self.publisher.publish(article, source=source)
            except Exception as exc:
                logger.exception("Publisher raised on article {}", article.id)
                async with get_session() as session:
                    await ChannelRepository(session).log(
                        channel_id=channel_id,
                        article_id=article.id,
                        status=PublishStatus.FAILED,
                        error=repr(exc),
                    )
                continue

            async with get_session() as session:
                if result.success:
                    await ArticleRepository(session).mark_published(article.id, utcnow())
                    await ChannelRepository(session).log(
                        channel_id=channel_id,
                        article_id=article.id,
                        status=PublishStatus.PUBLISHED,
                        telegram_message_id=result.telegram_message_id,
                    )
                    published_count += 1
                else:
                    await ChannelRepository(session).log(
                        channel_id=channel_id,
                        article_id=article.id,
                        status=PublishStatus.FAILED,
                        error=result.error,
                    )

        return published_count
