"""Versioned LLM prompts.

When you change wording, BUMP THE VERSION. The version is stored on the
Article so we can later re-summarize only rows produced by an older prompt.
"""

from __future__ import annotations

SUMMARIZATION_PROMPT_VERSION = "v1"

SUMMARIZATION_PROMPT_V1 = """\
You are an editorial assistant for a Telegram news channel.
You will be given the raw text of a news item (any language). Produce a faithful
rewrite — do NOT mirror the original verbatim, but preserve all facts.

Return ONLY valid JSON matching this schema (no markdown fences, no extra prose):

{{
  "title":       "<short headline in {language}, max 80 chars, no emojis>",
  "summary":     "<2-3 sentence rewrite in {language}>",
  "importance":  <integer 1-5 — 1 = trivial/clickbait, 5 = breaking/major>,
  "tags":        ["short", "lowercase", "topical", "tags"]
}}

Rules:
- Output language for `title` and `summary`: {language}.
- Do not invent facts not present in the source.
- If the input is empty or non-news (ads, promotional, single emoji), return
  importance=1 and a one-line summary describing why it is low-value.
- Strip URLs, source-channel branding, hashtags, and call-to-action lines.
- `tags` length: 2 to 6.

Source text:
---
{text}
---
"""


def render_summarization_prompt(*, text: str, language: str) -> str:
    return SUMMARIZATION_PROMPT_V1.format(text=text, language=language)
