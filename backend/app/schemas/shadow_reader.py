"""
Pydantic schemas for Shadow Reader API endpoints.
"""
from typing import Optional
from pydantic import BaseModel


class ShadowReaderAnswer(BaseModel):
    """Payload for POST /api/notes/{id}/shadow-reader/answer."""
    answer: str


class ShadowReaderAudioAnswerCreate(BaseModel):
    """Payload for POST /api/notes/{id}/shadow-reader/answer-audio.

    Round 15 / PR #26 — voice answer path (FR-8.4). The frontend uploads the
    recorded audio via the generic POST /api/upload endpoint first, then sends
    the resulting SAS ``audio_url`` (and the corresponding ``blob_path``) here
    so the backend can transcribe it via Azure Speech and feed the transcript
    into the same shadow-reader merge pipeline as the text-answer endpoint.
    """
    audio_url: str
    blob_path: str


class ShadowReaderQuestionsOut(BaseModel):
    """Response for GET /api/notes/{id}/shadow-reader."""
    status: str
    questions: list[str] = []


class ShadowReaderSettings(BaseModel):
    """Payload for PUT /api/users/me/shadow-reader/settings."""
    enabled: bool
    disabled_categories: list[str] = []
