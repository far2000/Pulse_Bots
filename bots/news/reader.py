"""Telethon-side reader.

Two paths feed the pipeline:
  1. Real-time `events.NewMessage` for connected sources.
  2. Periodic `catch_up()` sweep that fetches messages since `last_message_id`
     for each source (covers gaps when the userbot was offline).

Album handling: Telegram delivers an album as multiple `NewMessage` events
sharing a `grouped_id`. We buffer by `(channel_id, grouped_id)` for a short
window, then submit the buffered batch as a single article.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.custom.message import Message

from bots.news.config import ALBUM_FLUSH_DELAY_SECONDS
from bots.news.pipeline import IngestPipeline
from shared.config import BotType, get_settings
from shared.db import get_session
from shared.db.models.source import SourceChannel
from shared.db.repositories import SourceRepository
from shared.ingest.message_parser import parse_message


@dataclass
class _AlbumBuffer:
    messages: list[Message] = field(default_factory=list)
    flush_task: asyncio.Task[None] | None = None


class TelethonReader:
    def __init__(
        self,
        *,
        bot_type: BotType,
        client: TelegramClient,
        pipeline: IngestPipeline,
    ) -> None:
        self.bot_type = bot_type
        self.client = client
        self.pipeline = pipeline
        # (source_id, grouped_id) → buffer
        self._albums: dict[tuple[uuid.UUID, int], _AlbumBuffer] = defaultdict(_AlbumBuffer)
        self._albums_lock = asyncio.Lock()
        # entity_id → SourceChannel.id
        self._entity_map: dict[int, uuid.UUID] = {}
        self._handler: Any = None

    async def start(self) -> None:
        await self._refresh_sources()
        await self._register_event_handler()
        # First-run catch-up: pull everything missed since last_message_id.
        asyncio.create_task(self.catch_up(), name="initial-catch-up")

    async def stop(self) -> None:
        if self._handler:
            self.client.remove_event_handler(self._handler)
            self._handler = None
        # Drain pending album flushes.
        async with self._albums_lock:
            tasks = [b.flush_task for b in self._albums.values() if b.flush_task]
        for t in tasks:
            try:
                await t
            except Exception:
                pass

    async def _refresh_sources(self) -> list[SourceChannel]:
        """Reload enabled sources and resolve Telegram entity ids."""
        async with get_session() as session:
            repo = SourceRepository(session)
            sources = await repo.list_enabled(self.bot_type)

        resolved: list[SourceChannel] = []
        new_map: dict[int, uuid.UUID] = {}
        for s in sources:
            try:
                entity = await self.client.get_entity(
                    int(s.channel_username_or_id)
                    if s.channel_username_or_id.lstrip("-").isdigit()
                    else s.channel_username_or_id
                )
                eid = getattr(entity, "id", None)
                if eid is not None:
                    new_map[int(eid)] = s.id
                    if s.telegram_channel_id != int(eid):
                        async with get_session() as session2:
                            await SourceRepository(session2).update_resolved_id(
                                s.id, int(eid)
                            )
                    resolved.append(s)
                else:
                    logger.warning("Could not resolve source {}", s.channel_username_or_id)
            except FloodWaitError as exc:
                logger.warning("FloodWait while resolving {}: {}s", s.channel_username_or_id, exc.seconds)
                await asyncio.sleep(min(60, exc.seconds))
            except Exception as exc:
                logger.exception("Failed to resolve source {}: {}", s.channel_username_or_id, exc)

        self._entity_map = new_map
        logger.info("Resolved {} source channels", len(self._entity_map))
        return resolved

    async def _register_event_handler(self) -> None:
        if self._handler:
            self.client.remove_event_handler(self._handler)
        if not self._entity_map:
            logger.warning("No source channels resolved — event handler not registered")
            return

        chats = list(self._entity_map.keys())

        @self.client.on(events.NewMessage(chats=chats))
        async def _on_new_message(event: events.NewMessage.Event) -> None:  # noqa: ARG001
            try:
                await self._handle_message(event.message)
            except Exception:  # one bad message must NOT kill the loop
                logger.exception("Reader failed on message {}", event.message.id)

        self._handler = _on_new_message

    async def _resolve_source_id(self, message: Message) -> uuid.UUID | None:
        chat = message.chat_id
        if chat is None:
            return None
        # Telethon often returns -100<id> for channels; map both forms.
        candidates = {int(chat), int(str(chat).lstrip("-")), abs(int(chat))}
        if str(chat).startswith("-100"):
            candidates.add(int(str(chat)[4:]))
        for c in candidates:
            if c in self._entity_map:
                return self._entity_map[c]
        return None

    async def _handle_message(self, message: Message) -> None:
        source_id = await self._resolve_source_id(message)
        if source_id is None:
            logger.debug("Message {} from unknown chat {}", message.id, message.chat_id)
            return

        # Album buffering. Telegram delivers each piece as its own event but
        # they share `grouped_id`; we coalesce.
        if message.grouped_id:
            await self._buffer_album(source_id, message)
            return

        await self.pipeline.process_message(source_id=source_id, messages=[message])

    async def _buffer_album(self, source_id: uuid.UUID, message: Message) -> None:
        key = (source_id, int(message.grouped_id))
        async with self._albums_lock:
            buf = self._albums[key]
            buf.messages.append(message)
            if buf.flush_task is None:
                buf.flush_task = asyncio.create_task(
                    self._flush_album_after_delay(key), name=f"album-flush-{key[1]}"
                )

    async def _flush_album_after_delay(
        self, key: tuple[uuid.UUID, int]
    ) -> None:
        await asyncio.sleep(ALBUM_FLUSH_DELAY_SECONDS)
        async with self._albums_lock:
            buf = self._albums.pop(key, None)
        if not buf or not buf.messages:
            return
        # Sort by message id for stable media order.
        msgs = sorted(buf.messages, key=lambda m: m.id)
        try:
            await self.pipeline.process_message(source_id=key[0], messages=msgs)
        except Exception:
            logger.exception("Failed to flush album for source {}", key[0])

    async def catch_up(self) -> None:
        """Fetch messages newer than `last_message_id` for every enabled source."""
        settings = get_settings()
        logger.info("Starting catch-up sweep…")
        await self._refresh_sources()

        async with get_session() as session:
            sources = await SourceRepository(session).list_enabled(self.bot_type)

        for src in sources:
            try:
                await self._catch_up_source(src, settings.catchup_lookback_messages)
            except FloodWaitError as exc:
                logger.warning("FloodWait on catch-up {}: {}s", src.title, exc.seconds)
                await asyncio.sleep(min(120, exc.seconds))
            except Exception:
                logger.exception("Catch-up failed for source {}", src.id)
        logger.info("Catch-up sweep complete.")

    async def _catch_up_source(self, src: SourceChannel, lookback: int) -> None:
        if src.telegram_channel_id is None:
            return
        entity = src.telegram_channel_id
        min_id = src.last_message_id or 0

        gathered: list[Message] = []
        # iter_messages returns newest first; we want to keep messages with id > min_id.
        async for msg in self.client.iter_messages(entity, limit=lookback):
            if msg.id <= min_id:
                break
            gathered.append(msg)

        if not gathered:
            return

        gathered.sort(key=lambda m: m.id)  # oldest → newest
        # Group by grouped_id for albums.
        bucket: dict[int | None, list[Message]] = defaultdict(list)
        for m in gathered:
            bucket[getattr(m, "grouped_id", None)].append(m)

        for grouped_id, msgs in bucket.items():
            if grouped_id is None:
                for m in msgs:
                    await self.pipeline.process_message(source_id=src.id, messages=[m])
            else:
                await self.pipeline.process_message(source_id=src.id, messages=msgs)
