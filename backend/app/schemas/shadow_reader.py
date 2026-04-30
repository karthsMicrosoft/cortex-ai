"""
Pydantic schemas for Shadow Reader API endpoints.
"""
from typing import Optional
from pydantic import BaseModel


class ShadowReaderAnswer(BaseModel):
    """Payload for POST /api/notes/{id}/shadow-reader/answer."""
    answer: str


class ShadowReaderQuestionsOut(BaseModel):
    """Response for GET /api/notes/{id}/shadow-reader."""
    status: str
    questions: list[str] = []


class ShadowReaderSettings(BaseModel):
    """Payload for PUT /api/users/me/shadow-reader/settings."""
    enabled: bool
    disabled_categories: list[str] = []
