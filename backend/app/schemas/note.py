"""
Pydantic schemas for Notes endpoints.

B8 resolution: NoteUpdate uses explicit optional fields with model_dump(exclude_unset=True)
so absence is distinguished from explicit None.
"""
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

_CATEGORY_TYPE = Literal["Music", "Fitness", "Journal", "Ideas", "Spiritual", "Learning"]
_SOURCE_TYPE = Literal["voice", "text", "image"]
_PROCESSING_STATUS = Literal["raw", "transcribed", "processed", "enriched", "failed"]
_SHADOW_READER_STATUS = Literal[
    "pending",
    "asked",
    "answer_pending",  # QA-04 transient state — answer received, merge queued
    "answered",
    "dismissed",
    "skipped",
]


class NoteCreate(BaseModel):
    # SEC-05: cap content to prevent uncapped AI cost exposure and DoS against
    # Azure OpenAI budget (NFR-4: $150/month cap).
    content: str = Field(..., max_length=50_000)
    source_type: _SOURCE_TYPE = "text"
    category: _CATEGORY_TYPE = "Ideas"
    audio_url: Optional[str] = None
    image_url: Optional[str] = None
    client_id: Optional[str] = None
    tags: Optional[list[str]] = None


class NoteUpdate(BaseModel):
    """
    All fields optional — partial update.
    Use model_dump(exclude_unset=True) in the route to distinguish
    absence from explicit None (B8 / mitigation #6).
    """
    # SEC-05: same 50k cap as NoteCreate to prevent AI cost exposure on updates.
    content: Optional[str] = Field(default=None, max_length=50_000)
    category: Optional[_CATEGORY_TYPE] = None
    tags: Optional[list[str]] = None        # delta-applied
    mood: Optional[str] = None              # manual mood override (mitigation #6)
    music_metadata: Optional[dict] = None  # manual music-metadata override (mitigation #6)
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    # Phase 6 / PR 6.4 — Title + aliases editing.
    # title: nullable (matches DB column notes.title VARCHAR(120)).
    # aliases: optional; when provided we strip empty entries and dedupe
    # case-insensitively in the validator below.
    title: Optional[str] = Field(default=None, max_length=120)
    aliases: Optional[list[str]] = Field(default=None, max_length=20)

    @field_validator("aliases")
    @classmethod
    def _normalize_aliases(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        # Strip whitespace, drop empties, validate per-entry length.
        cleaned: list[str] = []
        for item in v:
            if not isinstance(item, str):
                raise ValueError("aliases entries must be strings")
            stripped = item.strip()
            if not stripped:
                continue
            if len(stripped) > 120:
                raise ValueError("aliases entries must be <= 120 characters")
            cleaned.append(stripped)
        # Dedupe case-insensitively, preserve first-occurrence order.
        seen: set[str] = set()
        out: list[str] = []
        for item in cleaned:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out


class NoteOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    content: str
    raw_transcription: Optional[str] = None
    summary: Optional[str] = None
    source_type: str
    category: str
    audio_url: Optional[str] = None
    image_url: Optional[str] = None
    audio_duration_seconds: Optional[float] = None
    mood: Optional[str] = None
    music_metadata: dict = {}
    processing_status: str
    sync_status: str
    client_id: Optional[str] = None
    tags: list[str] = []
    # Phase 2 — Shadow Reader fields
    shadow_reader_status: Optional[_SHADOW_READER_STATUS] = "pending"
    shadow_reader_questions: Optional[list[str]] = None
    shadow_reader_answer: Optional[str] = None
    # Phase 5 / PR 5.0 — Source provenance (scaffold; populated in Phase 5.1+).
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    source_parent_id: Optional[uuid.UUID] = None
    # Phase 6 / PR 6.0 — Title + aliases (for wiki-style linking).
    title: Optional[str] = None
    aliases: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteListResponse(BaseModel):
    items: list[NoteOut]
    total: int
