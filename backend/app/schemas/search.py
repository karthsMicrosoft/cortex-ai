"""
Pydantic schemas for search endpoints.

SearchRequest  — POST /api/search body
SearchResultItem — individual search result
"""
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

_CATEGORY_TYPE = Literal["Music", "Fitness", "Journal", "Ideas", "Spiritual", "Learning"]


class SearchRequest(BaseModel):
    """Hybrid search request body.

    - query:     Natural language search query (required).
    - category:  Optional category filter.
    - tags:      Optional tag filter — note must have at least one of these tags
                 (drives the EXISTS subquery in the canonical B7 SQL).
    - date_from: Optional lower bound on note created_at.
    - date_to:   Optional upper bound on note created_at.
    - limit:     Maximum number of results (default 20).
    - offset:    Pagination offset (default 0).
    """

    query: str = Field(..., min_length=1, max_length=500)
    category: Optional[_CATEGORY_TYPE] = None
    tags: Optional[list[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchResultItem(BaseModel):
    """A single search result as returned by POST /api/search."""

    id: uuid.UUID
    content: str
    summary: Optional[str] = None
    category: str
    created_at: datetime
    semantic_score: float
    text_score: float
    combined_score: float

    model_config = {"from_attributes": True}
