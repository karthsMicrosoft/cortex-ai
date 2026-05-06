"""
Pydantic schemas for sync push/pull endpoints.

SyncOperation  — one queued operation from a client
SyncPushRequest, SyncPushResponse  — POST /api/sync/push
SyncPullResponse                   — GET  /api/sync/pull
"""
import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel

from app.schemas.note import NoteOut


class SyncOperation(BaseModel):
    """A single offline operation to be applied server-side."""

    operation: Literal["create", "update", "delete"]
    entity_type: Literal["note", "tag"]
    client_id: Optional[str] = None
    payload: Optional[dict[str, Any]] = None


class SyncPushRequest(BaseModel):
    """Body for POST /api/sync/push."""

    operations: list[SyncOperation]


class SyncConflict(BaseModel):
    """Describes a sync conflict (placeholder — conflicts always empty in MVP)."""

    client_id: Optional[str] = None
    reason: str = "conflict"


class SyncPushResponse(BaseModel):
    """Response for POST /api/sync/push."""

    synced_count: int
    conflicts: list[SyncConflict] = []


class SyncPullResponse(BaseModel):
    """Response for GET /api/sync/pull."""

    notes: list[NoteOut]
    deletions: list[uuid.UUID]
    server_time: datetime
