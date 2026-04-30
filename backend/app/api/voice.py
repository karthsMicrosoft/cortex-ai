"""
Voice endpoints.

Endpoints:
  POST /api/voice/upload  — multipart audio → STT → NoteOut (pipeline scheduled)
  WS   /api/voice/stream  — real-time streaming STT (US-9; stub here)

The POST upload route:
1. Validates file size (≤ 50 MB).
2. Computes SHA-256 for idempotency (logged, not enforced client-side in MVP).
3. Uploads audio to Azure Blob Storage → SAS URL.
4. Calls speech.transcribe_audio_file() → raw_transcription.
5. Inserts Note with source_type='voice', raw_transcription, audio_url,
   processing_status='transcribed'.
6. Schedules process_note as FastAPI BackgroundTask.
7. Returns NoteOut.
"""
import hashlib
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user
from app.config import settings
from app.database import get_db
from app.models.note import Note
from app.pipeline.processor import AIPipeline
from app.schemas.note import NoteOut
from app.services.blob_storage import upload_blob
from app.services.speech import transcribe_audio_file

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_AUDIO_SIZE = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# POST /api/voice/upload
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def voice_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NoteOut:
    """Upload audio, transcribe via Azure Speech, create note, schedule pipeline.

    Returns NoteOut with processing_status='transcribed' immediately.
    The AI pipeline (Stage 1 + Stage 2) runs as a background task.
    """
    # 1. Read + validate
    audio_bytes = await file.read()
    if len(audio_bytes) > _MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file exceeds 50 MB limit",
        )

    # 2. SHA-256 for idempotency logging
    sha256 = hashlib.sha256(audio_bytes).hexdigest()
    logger.info("voice_upload: user=%s sha256=%s size=%d", current_user_id, sha256, len(audio_bytes))

    # 3. Upload to blob storage
    content_type = file.content_type or "audio/webm"
    ext = _audio_ext(content_type, file.filename)
    blob_path = f"audio/{current_user_id}/{uuid.uuid4()}{ext}"
    audio_url = await upload_blob(
        container=settings.AZURE_STORAGE_CONTAINER,
        blob_path=blob_path,
        data=audio_bytes,
        content_type=content_type,
    )

    # 4. Transcribe
    raw_transcription = await transcribe_audio_file(audio_bytes)

    # 5. Create note
    note = Note(
        user_id=current_user_id,
        content=raw_transcription or "",  # content is not-null; will be cleaned by pipeline
        raw_transcription=raw_transcription,
        audio_url=audio_url,
        source_type="voice",
        processing_status="transcribed",
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)

    note_id = note.id

    # 6. Schedule pipeline as BackgroundTask
    background_tasks.add_task(_run_pipeline, note_id)

    # 7. Return NoteOut (reload with tags eagerly)
    result = await db.execute(
        select(Note).options(selectinload(Note.tags)).where(Note.id == note_id)
    )
    note = result.scalar_one()
    return _note_to_out(note)


# ---------------------------------------------------------------------------
# WS /api/voice/stream  (stub — implemented in US-9)
# ---------------------------------------------------------------------------

# The WebSocket streaming endpoint is added in US-9. The route definition
# is deliberately absent here to avoid confusing testers in US-2.


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _run_pipeline(note_id: uuid.UUID) -> None:
    """Kick off the AI pipeline for *note_id* in a fresh DB session."""
    from app.database import SessionLocal
    from app.services.openai_client import get_openai_client

    async with SessionLocal() as db:
        pipeline = AIPipeline(openai_client=get_openai_client(), db=db)
        await pipeline.process_note(note_id)


def _note_to_out(note: Note) -> NoteOut:
    """Convert ORM Note to NoteOut schema."""
    tag_names = [t.name for t in note.tags] if note.tags else []
    return NoteOut(
        id=note.id,
        user_id=note.user_id,
        content=note.content,
        raw_transcription=note.raw_transcription,
        summary=note.summary,
        source_type=note.source_type,
        category=note.category,
        audio_url=note.audio_url,
        image_url=note.image_url,
        audio_duration_seconds=note.audio_duration_seconds,
        mood=note.mood,
        music_metadata=note.music_metadata or {},
        processing_status=note.processing_status,
        sync_status=note.sync_status,
        client_id=note.client_id,
        tags=tag_names,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _audio_ext(content_type: str, filename: str | None) -> str:
    """Return file extension for audio content type."""
    mapping = {
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mp4": ".mp4",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
    }
    if content_type in mapping:
        return mapping[content_type]
    if filename:
        import os
        _, ext = os.path.splitext(filename)
        if ext:
            return ext
    return ".webm"
