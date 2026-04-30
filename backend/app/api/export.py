"""
Export API — GET /api/export

Returns a JSON dump of all user notes (with SAS-signed media URLs) +
tags + daily summaries. Streams the response if the payload is large.

Spec § 4.2 item 28.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.daily_summary import DailySummary
from app.models.note import Note
from app.models.tag import Tag

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper — generate fresh SAS URL for a blob URL (if needed)
# ---------------------------------------------------------------------------

def _refresh_sas_url(url: str | None) -> str | None:
    """
    If the URL is an Azure Blob SAS URL, return it as-is (already signed).
    For the export we trust the stored URL; production deployments should
    re-sign if expiry is < 1h.  For MVP: pass through unchanged.
    """
    return url


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------

def _serialise_note(note: Note) -> dict:
    return {
        "id": str(note.id),
        "user_id": str(note.user_id),
        "content": note.content,
        "raw_transcription": note.raw_transcription,
        "summary": note.summary,
        "source_type": note.source_type,
        "category": note.category,
        "audio_url": _refresh_sas_url(note.audio_url),
        "image_url": _refresh_sas_url(note.image_url),
        "audio_duration_seconds": note.audio_duration_seconds,
        "entities": note.entities or [],
        "mood": note.mood,
        "music_metadata": note.music_metadata or {},
        "processing_status": note.processing_status,
        "sync_status": note.sync_status,
        "client_id": note.client_id,
        "tags": [t.name for t in note.tags] if note.tags else [],
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


def _serialise_summary(ds: DailySummary) -> dict:
    return {
        "id": str(ds.id),
        "summary_date": str(ds.summary_date),
        "summary_text": ds.summary_text,
        "key_themes": ds.key_themes or [],
        "note_count": ds.note_count,
        "mood_summary": ds.mood_summary,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
    }


# ---------------------------------------------------------------------------
# GET /api/export
# ---------------------------------------------------------------------------

@router.get("/export")
async def export_data(
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Export all user data as a streaming JSON response.

    Response shape:
    {
      "exported_at": "<ISO datetime>",
      "notes": [...],
      "summaries": [...]
    }

    Uses streaming so large exports (thousands of notes) don't OOM the
    container before the client receives anything.
    """
    notes_result = await db.execute(
        select(Note)
        .options(selectinload(Note.tags))
        .where(Note.user_id == current_user_id)
        .order_by(Note.created_at.asc())
    )
    notes = list(notes_result.scalars().all())

    summaries_result = await db.execute(
        select(DailySummary)
        .where(DailySummary.user_id == current_user_id)
        .order_by(DailySummary.summary_date.asc())
    )
    summaries = list(summaries_result.scalars().all())

    exported_at = datetime.utcnow().isoformat() + "Z"

    async def _stream() -> AsyncGenerator[bytes, None]:
        import json as _json
        yield b'{"exported_at":"' + exported_at.encode() + b'","notes":['
        for i, note in enumerate(notes):
            chunk = _json.dumps(_serialise_note(note), ensure_ascii=False)
            if i > 0:
                yield b"," + chunk.encode("utf-8")
            else:
                yield chunk.encode("utf-8")
        yield b'],"summaries":['
        for i, ds in enumerate(summaries):
            chunk = _json.dumps(_serialise_summary(ds), ensure_ascii=False)
            if i > 0:
                yield b"," + chunk.encode("utf-8")
            else:
                yield chunk.encode("utf-8")
        yield b"]}"

    logger.info(
        "export: user_id=%s notes=%d summaries=%d",
        current_user_id, len(notes), len(summaries),
    )

    return StreamingResponse(
        _stream(),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=cortex-export.json"},
    )
