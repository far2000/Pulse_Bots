"""Translate a Telethon Message into our pipeline's normalized form.

`ParsedMessage` is the boundary between Telethon-specific objects (which we
don't want leaking through the pipeline) and the rest of the system.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from datetime import datetime

from telethon.tl.custom.message import Message
from telethon.tl.types import (
    Document,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    MessageMediaDocument,
    MessageMediaPhoto,
    Photo,
)

from shared.db.models.media import MediaType
from shared.media.types import detect_media_type


@dataclass(slots=True)
class ParsedMedia:
    """Lightweight reference to a media item we'll download lazily."""

    media_type: MediaType
    mime_type: str | None
    filename: str | None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    # We keep the raw Telethon message around so the downloader can stream from it
    # without us touching MTProto types elsewhere.
    raw_message: Message | None = None


@dataclass(slots=True)
class ParsedMessage:
    source_message_id: int
    grouped_id: int | None
    text: str
    posted_at: datetime | None
    source_url: str | None
    media: list[ParsedMedia] = field(default_factory=list)


def _extract_doc_meta(doc: Document) -> tuple[str | None, str | None, int | None, int | None, float | None]:
    mime = getattr(doc, "mime_type", None)
    filename = None
    width = height = None
    duration = None
    for attr in doc.attributes or []:
        if isinstance(attr, DocumentAttributeFilename):
            filename = attr.file_name
        elif isinstance(attr, DocumentAttributeVideo):
            width = attr.w
            height = attr.h
            duration = float(attr.duration) if attr.duration is not None else None
    if not filename and mime:
        ext = mimetypes.guess_extension(mime) or ""
        filename = f"{doc.id}{ext}" if ext else None
    return mime, filename, width, height, duration


def parse_message(message: Message, *, source_channel_link: str | None = None) -> ParsedMessage:
    """Normalize a Telethon message. Non-media messages return media=[]."""

    text = (message.message or message.raw_text or "").strip()
    posted_at = message.date  # Telethon returns tz-aware UTC

    source_url: str | None = None
    if source_channel_link:
        # source_channel_link should already be the t.me path prefix (e.g. "t.me/foo")
        source_url = f"https://{source_channel_link.rstrip('/')}/{message.id}"

    media_items: list[ParsedMedia] = []
    media = message.media

    if isinstance(media, MessageMediaPhoto) and isinstance(media.photo, Photo):
        media_items.append(
            ParsedMedia(
                media_type=MediaType.IMAGE,
                mime_type="image/jpeg",
                filename=f"{media.photo.id}.jpg",
                raw_message=message,
            )
        )
    elif isinstance(media, MessageMediaDocument) and isinstance(media.document, Document):
        mime, filename, w, h, dur = _extract_doc_meta(media.document)
        mt = detect_media_type(mime, filename)
        media_items.append(
            ParsedMedia(
                media_type=mt,
                mime_type=mime,
                filename=filename,
                width=w,
                height=h,
                duration_seconds=dur,
                raw_message=message,
            )
        )

    return ParsedMessage(
        source_message_id=message.id,
        grouped_id=getattr(message, "grouped_id", None),
        text=text,
        posted_at=posted_at,
        source_url=source_url,
        media=media_items,
    )
