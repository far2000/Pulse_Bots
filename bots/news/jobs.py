"""APScheduler jobs: catch-up sweep, retry failed summaries, health log."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from bots.news.pipeline import IngestPipeline
from bots.news.reader import TelethonReader
from shared.config import get_settings


def register_jobs(
    scheduler: AsyncIOScheduler,
    *,
    reader: TelethonReader,
    pipeline: IngestPipeline,
) -> None:
    settings = get_settings()

    scheduler.add_job(
        reader.catch_up,
        "interval",
        minutes=settings.catchup_interval_minutes,
        id="catch_up",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        pipeline.retry_failed_summaries,
        "interval",
        minutes=10,
        id="retry_failed_summaries",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        _heartbeat,
        "interval",
        minutes=5,
        id="heartbeat",
    )

    logger.info(
        "Scheduled jobs: catch_up every {}m, retry_failed_summaries every 10m, heartbeat every 5m",
        settings.catchup_interval_minutes,
    )


async def _heartbeat() -> None:
    logger.info("heartbeat: ok")
