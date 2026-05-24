"""Publish an Article to a Telegram channel via aiogram (Bot API).

Notes:
- Telegram channel rate limit: ~1 message/sec per chat (faster bursts often
  succeed but cause `RetryAfter`). We throttle ourselves at the configured rate
  and additionally honor any `RetryAfter` we get back.
- Albums: when an article has ≥2 media files of the same kind (image OR video)
  we send a media group; otherwise we send a single photo/video or a plain text
  message.
- We never fetch media bytes here — we send the public URL of the stored asset
  so Telegram can pull from our CDN. That keeps egress on MinIO, not the bot.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError
from aiogram.types import (
    InputMediaPhoto,
    InputMediaVideo,
    URLInputFile,
)
from loguru import logger

from shared.db.models.article import Article
from shared.db.models.media import MediaType
from shared.db.models.source import SourceChannel
from shared.publishers.base import Publisher, PublishResult
from shared.publishers.formatters import format_article_html


class TelegramPublisher(Publisher):
    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        *,
        rate_per_second: float = 1.0,
        max_album_size: int = 10,
    ) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self._min_gap = 1.0 / max(0.1, rate_per_second)
        self._max_album = max_album_size
        self._last_send_at: float = 0.0
        self._send_lock = asyncio.Lock()

    async def _throttle(self) -> None:
        async with self._send_lock:
            now = asyncio.get_event_loop().time()
            wait = self._min_gap - (now - self._last_send_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_send_at = asyncio.get_event_loop().time()

    async def publish(
        self, article: Article, *, source: SourceChannel | None = None
    ) -> PublishResult:
        caption = format_article_html(article, source=source)

        media_urls: list[tuple[str, MediaType]] = []
        for link in article.media_links[: self._max_album]:
            url = link.media.public_url
            if not url:
                continue
            media_urls.append((url, link.media.media_type))

        try:
            await self._throttle()
            msg_id = await self._send(caption, media_urls)
            return PublishResult(success=True, telegram_message_id=msg_id)
        except TelegramRetryAfter as exc:
            wait = float(exc.retry_after) + 1.0
            logger.warning("Telegram rate-limited, sleeping {}s and retrying once", wait)
            await asyncio.sleep(wait)
            try:
                await self._throttle()
                msg_id = await self._send(caption, media_urls)
                return PublishResult(success=True, telegram_message_id=msg_id)
            except TelegramAPIError as exc2:
                return PublishResult(success=False, error=str(exc2))
        except TelegramAPIError as exc:
            return PublishResult(success=False, error=str(exc))

    async def _send(
        self, caption: str, media: list[tuple[str, MediaType]]
    ) -> int | None:
        if not media:
            msg = await self.bot.send_message(
                chat_id=self.chat_id,
                text=caption or "—",
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
            return msg.message_id

        if len(media) == 1:
            url, mtype = media[0]
            if mtype == MediaType.IMAGE:
                msg = await self.bot.send_photo(
                    chat_id=self.chat_id,
                    photo=URLInputFile(url),
                    caption=caption or None,
                    parse_mode="HTML",
                )
            elif mtype == MediaType.VIDEO:
                msg = await self.bot.send_video(
                    chat_id=self.chat_id,
                    video=URLInputFile(url),
                    caption=caption or None,
                    parse_mode="HTML",
                )
            else:
                msg = await self.bot.send_document(
                    chat_id=self.chat_id,
                    document=URLInputFile(url),
                    caption=caption or None,
                    parse_mode="HTML",
                )
            return msg.message_id

        # Multi-media: build a media group. Caption goes on the first item only.
        group: list[InputMediaPhoto | InputMediaVideo] = []
        for i, (url, mtype) in enumerate(media):
            kwargs = {"media": URLInputFile(url)}
            if i == 0:
                kwargs["caption"] = caption or None
                kwargs["parse_mode"] = "HTML"
            if mtype == MediaType.VIDEO:
                group.append(InputMediaVideo(**kwargs))
            else:
                # Treat documents as photos for albums isn't valid — fall back to photo
                # only for actual images; documents shouldn't reach here in MVP.
                group.append(InputMediaPhoto(**kwargs))

        msgs = await self.bot.send_media_group(chat_id=self.chat_id, media=group)
        return msgs[0].message_id if msgs else None
