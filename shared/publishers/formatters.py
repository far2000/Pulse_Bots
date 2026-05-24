"""Render an Article into HTML suitable for Telegram `parse_mode=HTML`.

Telegram caption limit = 1024 chars when sending media; plain message = 4096.
We target the tighter media-caption limit so the same formatter works for both.
"""

from __future__ import annotations

from shared.db.models.article import Article
from shared.db.models.source import SourceChannel
from shared.utils.text import escape_html, truncate

MAX_CAPTION_CHARS = 1024
RESERVED_FOR_FOOTER = 220  # space for title bolding + source link footer


def format_article_html(article: Article, source: SourceChannel | None = None) -> str:
    body_budget = MAX_CAPTION_CHARS - RESERVED_FOR_FOOTER

    title = escape_html(article.title.strip()) if article.title else ""
    summary = escape_html((article.summary or article.original_text or "").strip())
    summary = truncate(summary, body_budget)

    parts: list[str] = []
    if title:
        parts.append(f"<b>{title}</b>")
    if summary:
        parts.append(summary)

    footer_bits: list[str] = []
    if source and source.title:
        label = escape_html(source.title)
        if article.source_url:
            footer_bits.append(f'🔗 <a href="{escape_html(article.source_url)}">{label}</a>')
        else:
            footer_bits.append(f"🔗 {label}")
    elif article.source_url:
        footer_bits.append(f'<a href="{escape_html(article.source_url)}">منبع</a>')

    if article.tags:
        tag_str = " ".join(f"#{escape_html(t.replace(' ', '_'))}" for t in article.tags[:5])
        footer_bits.append(tag_str)

    if footer_bits:
        parts.append("\n".join(footer_bits))

    out = "\n\n".join(parts)
    return truncate(out, MAX_CAPTION_CHARS)
