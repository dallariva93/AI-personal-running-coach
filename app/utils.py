"""Small shared utilities (kept dependency-free)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from app.logging_config import get_logger

T = TypeVar("T")
logger = get_logger("app.retry")


def retry_call(
    func: Callable[[], T],
    *,
    retries: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    description: str = "operation",
) -> T:
    """Call ``func`` with exponential backoff.

    Retries up to ``retries`` times on the given exceptions, sleeping
    ``base_delay * 2**attempt`` seconds between attempts. Re-raises the last
    exception if all attempts fail.
    """
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return func()
        except exceptions as exc:  # noqa: PERF203
            last_exc = exc
            if attempt == retries - 1:
                break
            delay = base_delay * (2**attempt)
            logger.warning(
                "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                description, attempt + 1, retries, exc, delay,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
