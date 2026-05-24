"""Abstract `Summarizer` so we can swap LLMs (Gemini today, others later)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(slots=True)
class SummaryResult:
    title: str | None
    summary: str
    importance: int  # 1-5
    tags: list[str] = field(default_factory=list)
    model: str = ""
    prompt_version: str = ""


class Summarizer(ABC):
    @abstractmethod
    async def summarize(
        self,
        *,
        text: str,
        content_hash: str,
        language: str = "fa",
    ) -> SummaryResult:
        """Return a structured summary. Should raise on hard failures so the
        pipeline can persist `status=failed` and the retry job can pick it up."""
