"""Media type detection and storage key construction."""

from __future__ import annotations

from datetime import datetime

from shared.config import BotType
from shared.db.models.media import MediaType

IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/heic", "image/heif"}
VIDEO_MIMES = {"video/mp4", "video/quicktime", "video/x-matroska", "video/webm"}


def detect_media_type(mime_type: str | None, filename: str | None = None) -> MediaType:
    """Best-effort media type from MIME (preferred) or filename extension."""
    if mime_type:
        m = mime_type.lower()
        if m in IMAGE_MIMES or m.startswith("image/"):
            return MediaType.IMAGE
        if m in VIDEO_MIMES or m.startswith("video/"):
            return MediaType.VIDEO
        return MediaType.DOCUMENT

    if filename:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in {"jpg", "jpeg", "png", "webp", "gif", "heic", "heif"}:
            return MediaType.IMAGE
        if ext in {"mp4", "mov", "mkv", "webm", "avi"}:
            return MediaType.VIDEO
    return MediaType.DOCUMENT


def build_storage_key(
    bot_type: BotType,
    content_hash: str,
    *,
    extension: str,
    when: datetime,
    suffix: str = "",
) -> str:
    """`{bot_type}/{yyyy}/{mm}/{dd}/{hash}{suffix}.{ext}`."""
    ext = extension.lstrip(".").lower()
    return (
        f"{bot_type.value}/{when.year:04d}/{when.month:02d}/{when.day:02d}/"
        f"{content_hash}{suffix}.{ext}"
    )
