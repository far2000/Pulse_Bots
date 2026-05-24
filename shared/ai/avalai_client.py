"""Summarizer that hits Avalai's OpenAI-compatible gateway.

Avalai (https://avalai.ir) is a proxy that exposes multiple LLM providers
behind a single OpenAI-API-compatible endpoint. We point the standard
`openai` async SDK at their base URL and use whatever model the user picked
in `LLM_MODEL` — defaults to `gemini-2.0-flash`.

If you ever want to swap providers (direct OpenAI, OpenRouter, Together, …)
just change `AVALAI_BASE_URL` + `AVALAI_API_KEY` + `LLM_MODEL` — no code
changes.
"""

from __future__ import annotations

import asyncio
import json
import re

import orjson
from loguru import logger
from openai import AsyncOpenAI, APIError, APITimeoutError

from shared.ai.prompts import (
    SUMMARIZATION_PROMPT_VERSION,
    render_summarization_prompt,
)
from shared.ai.summarizer import Summarizer, SummaryResult
from shared.cache.memory_cache import InMemoryCache
from shared.config import get_settings

CACHE_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days


class AvalaiSummarizationError(RuntimeError):
    pass


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(raw: str) -> dict[str, object]:
    """Pull a JSON object out of the model's response, tolerating markdown fences."""
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    m = _FENCED_JSON_RE.search(raw)
    if m:
        return json.loads(m.group(1))
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start : end + 1])
    raise AvalaiSummarizationError(f"Model output was not JSON-parseable: {raw[:200]!r}")


class AvalaiSummarizer(Summarizer):
    """OpenAI-protocol summarizer pointed at the Avalai gateway."""

    def __init__(
        self,
        cache: InMemoryCache,
        *,
        model: str | None = None,
        timeout_seconds: int | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        settings = get_settings()
        self.cache = cache
        self.model = model or settings.llm_model
        self.timeout = timeout_seconds or settings.llm_timeout_seconds
        self._client = AsyncOpenAI(
            api_key=api_key or settings.avalai_api_key,
            base_url=base_url or settings.avalai_base_url,
            timeout=self.timeout,
            max_retries=0,  # we handle retries in the pipeline's retry job
        )

    def _cache_key(self, content_hash: str, language: str) -> str:
        # Including the model name protects against caching answers from a
        # weaker/older model after we upgrade.
        return f"llm:sum:{self.model}:{SUMMARIZATION_PROMPT_VERSION}:{language}:{content_hash}"

    async def summarize(
        self,
        *,
        text: str,
        content_hash: str,
        language: str = "fa",
    ) -> SummaryResult:
        cache_key = self._cache_key(content_hash, language)
        cached = await self.cache.get(cache_key)
        if cached:
            data = orjson.loads(cached)
            return SummaryResult(
                title=data.get("title"),
                summary=data["summary"],
                importance=int(data.get("importance", 3)),
                tags=list(data.get("tags", [])),
                model=self.model,
                prompt_version=SUMMARIZATION_PROMPT_VERSION,
            )

        prompt = render_summarization_prompt(text=text, language=language)
        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a precise JSON-only API. "
                                "Respond with one JSON object and nothing else."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=512,
                    # Many OpenAI-compatible gateways honor json_object; if the
                    # backing model ignores it, the regex below still recovers JSON.
                    response_format={"type": "json_object"},
                ),
                timeout=self.timeout + 5,
            )
        except asyncio.TimeoutError as exc:
            raise AvalaiSummarizationError("LLM request timed out") from exc
        except APITimeoutError as exc:
            raise AvalaiSummarizationError(f"LLM timeout: {exc}") from exc
        except APIError as exc:
            raise AvalaiSummarizationError(f"LLM API error: {exc}") from exc
        except Exception as exc:
            raise AvalaiSummarizationError(f"LLM call failed: {exc}") from exc

        if not response.choices:
            raise AvalaiSummarizationError("Empty response (no choices)")
        raw_text = (response.choices[0].message.content or "").strip()
        if not raw_text:
            raise AvalaiSummarizationError("Empty response content")

        try:
            payload = _extract_json(raw_text)
        except (json.JSONDecodeError, AvalaiSummarizationError) as exc:
            logger.warning("LLM returned non-JSON, raw={!r}", raw_text[:300])
            raise AvalaiSummarizationError(str(exc)) from exc

        result = SummaryResult(
            title=(payload.get("title") or None),
            summary=str(payload.get("summary", "")).strip(),
            importance=max(1, min(5, int(payload.get("importance", 3)))),
            tags=[str(t).strip().lower() for t in payload.get("tags", []) if t][:6],
            model=self.model,
            prompt_version=SUMMARIZATION_PROMPT_VERSION,
        )
        if not result.summary:
            raise AvalaiSummarizationError("LLM returned empty summary")

        await self.cache.set(cache_key, orjson.dumps(payload), ex=CACHE_TTL_SECONDS)
        return result
