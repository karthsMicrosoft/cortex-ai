"""
Pydantic schemas for Notes endpoints.

B8 resolution: NoteUpdate uses explicit optional fields with model_dump(exclude_unset=True)
so absence is distinguished from explicit None.
"""
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

_CATEGORY_TYPE = Literal["Music", "Fitness", "Journal", "Ideas", "Spiritual", "Learning"]
_SOURCE_TYPE = Literal["voice", "text", "image"]
_PROCESSING_STATUS = Literal["raw", "transcribed", "processed", "enriched", "failed"]
_SHADOW_READER_STATUS = Literal["pending", "asked", "answered", "dismissed", "skipped"]


class NoteCreate(BaseModel):
    content: str
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
    content: Optional[str] = None
    category: Optional[_CATEGORY_TYPE] = None
    tags: Optional[list[str]] = None        # delta-applied
    mood: Optional[str] = None              # manual mood override (mitigation #6)
    music_metadata: Optional[dict] = None  # manual music-metadata override (mitigation #6)
    image_url: Optional[str] = None
    audio_url: Optional[str] = None


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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteListResponse(BaseModel):
    items: list[NoteOut]
    total: int
