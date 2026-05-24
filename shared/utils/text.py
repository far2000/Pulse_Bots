"""Text normalization and hashing helpers."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WS_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Normalize text for dedup hashing.

    - NFKC unicode normalize
    - strip URLs (often differ between forwards)
    - collapse whitespace
    - lowercase, strip
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text)
    s = _URL_RE.sub("", s)
    s = _WS_RE.sub(" ", s)
    return s.strip().lower()


def content_hash(text: str) -> str:
    """SHA-256 of normalized text — stable across forwards/whitespace tweaks."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def file_hash(data: bytes) -> str:
    """SHA-256 of raw file bytes — used for media dedup."""
    return hashlib.sha256(data).hexdigest()


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(suffix))] + suffix


def escape_html(text: str) -> str:
    """Minimal HTML escape for Telegram parse_mode=HTML."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
