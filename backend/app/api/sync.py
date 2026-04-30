"""
Sync push/pull endpoints for offline-first operation.

Endpoints:
  POST /api/sync/push  — apply queued offline operations
  GET  /api/sync/pull  — fetch notes updated since a timestamp

Auth required on all routes.

Design notes:
- push: accepts list of {operation, entity_type, client_id, payload};
  applies them; returns {synced_count, conflicts:[]} (no conflicts in MVP).
- pull: returns notes updated after ?since=<ISO8601>, a deletions list
  (empty in MVP — hard deletes not tracked), and server_time.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api._note_serializers import _note_to_out
from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.note import Note
from app.models.tag import Tag
from app.schemas.note import NoteCreate, NoteOut, NoteUpdate
from app.schemas.sync import SyncOperation, SyncPullResponse, SyncPushRequest, SyncPushResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /api/sync/push
# ---------------------------------------------------------------------------

@router.post("/push", response_model=SyncPushResponse)
async def sync_push(
    payload: SyncPushRequest,
    background_tasks: BackgroundTasks,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncPushResponse:
    """Apply a batch of offline operations to the server.

    Supported operations:
    - create / note: create a new note (pipeline scheduled)
    - update / note: update an existing note by client_id or payload.id
    - delete / note: delete a note by payload.id

    Returns synced_count and an empty conflicts list (MVP).
    """
    synced = 0

    for op in payload.operations:
        try:
            if op.entity_type == "note":
                await _apply_note_op(op, current_user_id, db, background_tasks)
                synced += 1
            else:
                logger.warning("sync_push: unsupported entity_type=%s", op.entity_type)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "sync_push: failed op=%s entity=%s error_class=%s",
                op.operation,
                op.entity_type,
                type(exc).__name__,
            )
            # Do not surface internal errors as conflicts in MVP; just skip

    return SyncPushResponse(synced_count=synced, conflicts=[])


# ---------------------------------------------------------------------------
# GET /api/sync/pull
# ---------------------------------------------------------------------------

@router.get("/pull", response_model=SyncPullResponse)
async def sync_pull(
    since: Optional[str] = Query(
        default=None,
        description="ISO 8601 timestamp — return notes updated after this time",
    ),
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncPullResponse:
    """Return notes updated since *since* and a deletions list.

    - since: ISO 8601 string (defaults to epoch if omitted → returns all notes).
    - deletions: always [] in MVP (hard-delete tracking not implemented).
    - server_time: UTC timestamp of this response.
    """
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid 'since' timestamp — expected ISO 8601 format",
            )
    else:
        # No since → return all notes (epoch)
        since_dt = datetime.fromtimestamp(0, tz=timezone.utc)

    result = await db.execute(
        select(Note)
        .options(selectinload(Note.tags))
        .where(Note.user_id == current_user_id, Note.updated_at > since_dt)
        .order_by(Note.updated_at.desc())
    )
    notes = result.scalars().all()

    return SyncPullResponse(
        notes=[_note_to_out(n) for n in notes],
        deletions=[],
        server_time=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _apply_note_op(
    op: SyncOperation,
    user_id: uuid.UUID,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> None:
    """Apply a single note sync operation."""
    payload = op.payload or {}

    if op.operation == "create":
        note = Note(
            user_id=user_id,
            content=payload.get("content", ""),
            source_type=payload.get("source_type", "text"),
            category=payload.get("category", "Ideas"),
            audio_url=payload.get("audio_url"),
            image_url=payload.get("image_url"),
            client_id=op.client_id or payload.get("client_id"),
            processing_status="raw",
        )
        db.add(note)
        await db.flush()
        # Schedule pipeline
        note_id = note.id
        background_tasks.add_task(_run_pipeline, note_id)

    elif op.operation == "update":
        note_id_str = payload.get("id")
        if not note_id_str:
            raise ValueError("Update operation missing payload.id")
        note_id = uuid.UUID(str(note_id_str))
        result = await db.execute(
            select(Note).where(Note.id == note_id, Note.user_id == user_id)
        )
        note = result.scalar_one_or_none()
        if note is None:
            raise ValueError(f"Note {note_id} not found")
        for field in ("content", "category", "mood", "music_metadata", "audio_url", "image_url"):
            if field in payload:
                setattr(note, field, payload[field])
        if "content" in payload:
            note.processing_status = "raw"  # re-trigger pipeline
        await db.flush()

    elif op.operation == "delete":
        note_id_str = payload.get("id")
        if not note_id_str:
            raise ValueError("Delete operation missing payload.id")
        note_id = uuid.UUID(str(note_id_str))
        result = await db.execute(
            select(Note).where(Note.id == note_id, Note.user_id == user_id)
        )
        note = result.scalar_one_or_none()
        if note is not None:
            await db.delete(note)
            await db.flush()

    else:
        raise ValueError(f"Unknown operation: {op.operation}")


async def _run_pipeline(note_id: uuid.UUID) -> None:
    """Run AI pipeline for *note_id* in a fresh DB session."""
    from app.database import SessionLocal
    from app.pipeline.processor import AIPipeline
    from app.services.openai_client import get_openai_client

    async with SessionLocal() as db:
        pipeline = AIPipeline(openai_client=get_openai_client(), db=db)
        await pipeline.process_note(note_id)


