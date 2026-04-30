"""
Pydantic schemas for the Personal Dictionary (user_vocabulary) endpoints.

Shapes per addendum F1.2.
"""
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Allowed term_type values — kept as a Literal union for strict validation.
TermType = Literal["name", "music_term", "technical", "place", "acronym", "general"]


class VocabularyTerm(BaseModel):
    """Request body for POST /api/dictionary and individual entries in bulk import."""

    term: str = Field(..., min_length=1, max_length=200)
    term_type: TermType = Field(default="general")
    pronunciation_hint: Optional[str] = Field(default=None, max_length=500)
    boost_weight: float = Field(default=1.0, ge=0.0, le=2.0)


class VocabularyTermUpdate(BaseModel):
    """Request body for PUT /api/dictionary/{id} — all fields optional."""

    term: Optional[str] = Field(default=None, min_length=1, max_length=200)
    term_type: Optional[TermType] = None
    pronunciation_hint: Optional[str] = Field(default=None, max_length=500)
    boost_weight: Optional[float] = Field(default=None, ge=0.0, le=2.0)


class VocabularyTermOut(BaseModel):
    """Response shape for a single vocabulary term."""

    id: uuid.UUID
    user_id: uuid.UUID
    term: str
    term_type: str
    pronunciation_hint: Optional[str] = None
    boost_weight: float
    usage_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BulkImportRequest(BaseModel):
    """Request body for POST /api/dictionary/bulk."""

    terms: list[VocabularyTerm]


class BulkImportResponse(BaseModel):
    """Response for bulk import — reports inserted count vs total submitted."""

    inserted: int
    total: int
