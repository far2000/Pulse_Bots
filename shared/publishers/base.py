"""Publisher interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from shared.db.models.article import Article


@dataclass(slots=True)
class PublishResult:
    success: bool
    telegram_message_id: int | None = None
    error: str | None = None


class Publisher(ABC):
    @abstractmethod
    async def publish(self, article: Article) -> PublishResult: ...
