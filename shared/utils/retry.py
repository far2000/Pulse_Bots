"""Async retry helpers using `tenacity`.

Use the pre-built `network_retry` decorator for any IO that touches the network.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from loguru import logger
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
import logging

T = TypeVar("T")

_stdlib_logger = logging.getLogger("retry")


def network_retry(
    attempts: int = 4,
    min_wait: float = 1.0,
    max_wait: float = 16.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: exponential backoff on transient errors.

    Default catches broad Exception — narrow it with `exceptions=` when callers
    can pinpoint the transient class (httpx.NetworkError, asyncpg errors, etc.).
    """

    return retry(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=min_wait, max=max_wait),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(_stdlib_logger, logging.WARNING),
        reraise=True,
    )


async def run_with_retry(
    fn: Callable[..., T],
    *args: object,
    attempts: int = 4,
    min_wait: float = 1.0,
    max_wait: float = 16.0,
    **kwargs: object,
) -> T:
    """Imperative variant for one-off calls."""
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=min_wait, max=max_wait),
            reraise=True,
        ):
            with attempt:
                return await fn(*args, **kwargs)  # type: ignore[misc]
    except RetryError as exc:
        logger.error("All retry attempts exhausted: {}", exc)
        raise
    raise RuntimeError("unreachable")
