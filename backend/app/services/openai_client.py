"""
Azure OpenAI singleton client and FastAPI dependency.

Exposes:
- `get_openai_client()` → AsyncAzureOpenAI   (module-level singleton getter)
- `get_openai()`        → FastAPI Depends-compatible dependency
"""
import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from openai import AsyncAzureOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_openai_client() -> AsyncAzureOpenAI:
    """Return the singleton AsyncAzureOpenAI client.

    Configured from:
    - AZURE_OPENAI_ENDPOINT
    - AZURE_OPENAI_API_KEY
    - AZURE_OPENAI_API_VERSION  (default: 2024-10-21)
    """
    client = AsyncAzureOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_key=settings.AZURE_OPENAI_API_KEY,
        api_version=settings.AZURE_OPENAI_API_VERSION,
    )
    logger.info("Azure OpenAI client initialised (endpoint=%s)", settings.AZURE_OPENAI_ENDPOINT)
    return client


async def get_openai() -> AsyncAzureOpenAI:
    """FastAPI dependency — yields the singleton Azure OpenAI client."""
    return get_openai_client()


# Type alias for use with Annotated[..., Depends(get_openai)]
OpenAIDep = Annotated[AsyncAzureOpenAI, Depends(get_openai)]
