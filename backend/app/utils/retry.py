"""
Tenacity-based retry decorator for all Azure service adapters.

Usage:
    from app.utils.retry import azure_retry

    @azure_retry
    async def my_azure_call():
        ...

Strategy:
- Exponential backoff: 1s, 2s, 4s (max 3 attempts).
- Retries on any Exception EXCEPT FastAPI's HTTPException
  (which represents intentional 4xx/5xx responses — retrying would be wrong).
"""
import logging

from fastapi import HTTPException
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Return True for every exception except HTTPException."""
    return not isinstance(exc, HTTPException)


azure_retry = retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
"""Decorator: exponential backoff, max 3 attempts, skips HTTPException."""
