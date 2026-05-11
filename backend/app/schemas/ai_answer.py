"""
Pydantic schemas for POST /api/ai/answer (RAG endpoint, PR 4.1).

AnswerRequest    — request body
AnswerFilters    — optional retrieval filters (category / tags / since / until)
PriorMessage     — accepted in this PR but UNUSED (PR 4.5 will consume it)
AnswerCitation   — single grounded citation surfaced with the answer
AnswerResponse   — response body
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Same canonical category set as schemas/search.py.
_CATEGORY_TYPE = Literal[
    "Music", "Fitness", "Journal", "Ideas", "Spiritual", "Learning"
]


class AnswerFilters(BaseModel):
    """Optional retrieval filters forwarded to the hybrid search helper."""

    category: Optional[_CATEGORY_TYPE] = None
    tags: Optional[list[str]] = None
    since: Optional[datetime] = None
    until: Optional[datetime] = None


class PriorMessage(BaseModel):
    """A turn from earlier in the conversation.

    Accepted for forward compatibility but NOT forwarded to OpenAI in this PR;
    PR 4.5 will wire prior_messages into a multi-turn prompt.
    """

    role: Literal["user", "assistant", "system"]
    content: str = Field(..., max_length=4000)


class AnswerRequest(BaseModel):
    """POST /api/ai/answer body."""

    query: str = Field(..., min_length=1, max_length=1000)
    max_results: int = Field(default=8, ge=1, le=20)
    filters: Optional[AnswerFilters] = None
    prior_messages: Optional[list[PriorMessage]] = None


class AnswerCitation(BaseModel):
    """A single note-grounded citation returned with the answer."""

    note_id: uuid.UUID
    title: str
    snippet: str
    relevance: float


class AnswerResponse(BaseModel):
    """POST /api/ai/answer response body."""

    answer: str
    citations: list[AnswerCitation]
    model: str
    retrieval_count: int
    elapsed_ms: int
