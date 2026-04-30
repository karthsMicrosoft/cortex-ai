"""
Export API — GET /api/export

Returns a JSON dump of all user notes (with SAS-signed media URLs) +
tags + daily summaries. Streams the response if the payload is large.

Spec § 4.2 item 28.
"""
from __future__ import annotations

import datetime as _dt
import logging
import re
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user
from app.config import settings
from app.database import get_db
from app.models.daily_summary import DailySummary
from app.models.note import Note
from app.models.tag import Tag

logger = logging.getLogger(__name__)

router = APIRouter()

# Regex to detect Azure Blob Storage host pattern.
_AZURE_BLOB_RE = re.compile(r"https://([^.]+)\.blob\.core\.windows\.net/([^/]+)/(.+?)(?:\?.*)?$")


# ---------------------------------------------------------------------------
# Helper — generate fresh 1-hour SAS URL at export time (SEC-08)
# ---------------------------------------------------------------------------

def _refresh_sas_url(url: str | None) -> str | None:
    """
    Re-generate a short-lived (1h) SAS URL for the given blob URL.

    SEC-08: Stored SAS URLs were generated at upload time with a 24h TTL.
    At export time we re-sign them with a fresh 1h expiry so:
      - Expired URLs for old notes are no longer silently returned.
      - Even if a note is deleted after export, the SAS expires within 1h.

    Falls back to the original URL if the connection string is not configured
    (e.g. tests / local dev without blob storage).
    """
    if url is None:
        return None

    if not settings.AZURE_STORAGE_CONNECTION_STRING:
        # No storage configured — return stored URL as-is (dev / test mode).
        return url

    match = _AZURE_BLOB_RE.match(url)
    if not match:
        # Not a recognised Azure Blob URL pattern — return unchanged.
        return url

    _account_from_url, container_name, blob_name = match.groups()

    try:
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        # Parse account credentials from connection string.
        account_name: str | None = None
        account_key: str | None = None
        for part in settings.AZURE_STORAGE_CONNECTION_STRING.split(";"):
            if part.lower().startswith("accountname="):
                account_name = part.split("=", 1)[1]
            elif part.lower().startswith("accountkey="):
                account_key = part.split("=", 1)[1]

        if not account_name or not account_key:
            logger.warning("export: cannot re-sign SAS URL — missing account credentials")
            return url

        expiry = _dt.datetime.utcnow() + _dt.timedelta(hours=1)
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
        )
        return f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"

    except Exception as exc:  # noqa: BLE001
        logger.warning("export: SAS re-sign failed for %s: %s", url, exc)
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

    exported_at = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")

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
