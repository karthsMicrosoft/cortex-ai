"""
Notes CRUD routes.

Endpoints:
  POST   /api/notes              → 201 NoteOut; pipeline scheduled
  GET    /api/notes              → 200 NoteListResponse (paginated + filtered)
  GET    /api/notes/{id}         → 200 NoteOut | 404
  PUT    /api/notes/{id}         → 200 NoteOut | 404 | 422
  DELETE /api/notes/{id}         → 204 | 404
  POST   /api/ai/process/{note_id} → 202 (manual pipeline re-trigger; idempotent)

Ownership: all queries filter by current_user. Cross-user access returns 404 (not 403)
to avoid leaking the existence of a note (Task 5.5 / B8).
"""
import logging
import uuid
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api._note_serializers import _note_to_out
from app.auth.jwt import get_current_user, require_scope
from app.config import settings
from app.database import get_db
from app.models.note import Note
from app.models.note_deletion import NoteDeletion
from app.models.tag import Tag, note_tags as note_tags_table
from app.pipeline.ocr import process_image_note
from app.pipeline.processor import AIPipeline
from app.schemas.note import NoteCreate, NoteListResponse, NoteOut, NoteUpdate
from app.utils.db_helpers import get_or_create_tags_batch

logger = logging.getLogger(__name__)

router = APIRouter()

# AI pipeline + OCR router — registered separately in main.py
ai_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_or_create_tags(
    db: AsyncSession, user_id: uuid.UUID, tag_names: list[str]
) -> list[Tag]:
    """Return Tag objects for *tag_names*, creating any that don't exist.

    Delegates to get_or_create_tags_batch (PERF-01 fix): uses one SELECT + one
    batch INSERT instead of one SELECT+INSERT per tag name.
    """
    return await get_or_create_tags_batch(db, user_id, tag_names, is_auto=False)


async def _fetch_note(
    db: AsyncSession,
    note_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Note:
    """
    Fetch a note by ID that belongs to *user_id*.
    Raises HTTP 404 if not found or belongs to a different user (ownership isolation).
    """
    result = await db.execute(
        select(Note)
        .options(selectinload(Note.tags))
        .where(Note.id == note_id, Note.user_id == user_id)
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


# ---------------------------------------------------------------------------
# POST /api/notes
# ---------------------------------------------------------------------------

@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate,
    background_tasks: BackgroundTasks,
    current_user_id: uuid.UUID = Depends(require_scope({None, "clip"})),
    db: AsyncSession = Depends(get_db),
) -> NoteOut:
    """Create a new note for the authenticated user.

    - text notes: status='raw', pipeline scheduled (Stage 1 + Stage 2).
    - voice notes with audio_url: status='transcribed', pipeline scheduled.
    - image notes with image_url: OCR scheduled first (sets status='transcribed'),
      then pipeline Stage 2 (Stage 1 skipped for images).

    Bug 21 (2026-05-01): if a note with the same client_id already exists for
    this user, return the existing note instead of creating a duplicate. This
    prevents the double-create that occurs when /api/voice/upload creates a note
    and syncManager.pushChanges() subsequently pushes the same local note via
    this endpoint.
    """
    # Bug 21 dedup: if a note with the same client_id already exists, return it.
    if payload.client_id:
        existing_result = await db.execute(
            select(Note)
            .options(selectinload(Note.tags))
            .where(Note.client_id == payload.client_id, Note.user_id == current_user_id)
        )
        existing_note = existing_result.scalar_one_or_none()
        if existing_note is not None:
            return _note_to_out(existing_note)

    # Determine initial processing_status
    if payload.audio_url and payload.source_type == "voice":
        initial_status = "transcribed"
    elif payload.source_type == "image" and payload.image_url:
        initial_status = "raw"  # OCR will advance to 'transcribed'
    else:
        initial_status = "raw"

    note = Note(
        user_id=current_user_id,
        content=payload.content,
        source_type=payload.source_type,
        category=payload.category,
        audio_url=payload.audio_url,
        image_url=payload.image_url,
        client_id=payload.client_id,
        processing_status=initial_status,
    )
    db.add(note)
    await db.flush()

    # Handle tags
    # Bug 15 fix (2026-05-01): image notes always get an 'image' tag so users
    # can find/filter them at a glance. Merge with any caller-supplied tags;
    # de-dup by case-insensitive name.
    initial_tags = list(payload.tags or [])
    if payload.source_type == "image" and not any(
        (t or "").strip().lower() == "image" for t in initial_tags
    ):
        initial_tags.append("image")

    # Insert directly into the note_tags association table instead of using the
    # ORM relationship assignment which would trigger a lazy load on the new note.
    if initial_tags:
        tag_objs = await _get_or_create_tags(db, current_user_id, initial_tags)
        if tag_objs:
            await db.execute(
                insert(note_tags_table),
                [{"note_id": note.id, "tag_id": t.id} for t in tag_objs],
            )
        await db.flush()

    await db.refresh(note)
    note_id = note.id
    image_url_for_ocr = note.image_url  # capture before session closes

    # QA-06 fix: commit BEFORE scheduling background tasks so the note row is
    # fully visible in any fresh DB session the background task opens.
    await db.commit()

    # Eagerly load tags for the response (re-fetch after commit)
    result = await db.execute(
        select(Note).options(selectinload(Note.tags)).where(Note.id == note_id)
    )
    note = result.scalar_one()

    # Schedule background tasks:
    # Image notes: OCR first (sets status='transcribed'), then pipeline
    if payload.source_type == "image" and payload.image_url:
        background_tasks.add_task(_run_ocr_and_pipeline, note_id, image_url_for_ocr)
    else:
        # text / voice: run pipeline directly
        background_tasks.add_task(_run_pipeline, note_id)

    return _note_to_out(note)


# ---------------------------------------------------------------------------
# GET /api/notes
# ---------------------------------------------------------------------------

@router.get("", response_model=NoteListResponse)
async def list_notes(
    category: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    q: Optional[str] = Query(default=None),  # full-text search stub (US-2)
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NoteListResponse:
    """List notes for the authenticated user with optional filters and pagination."""
    # Base query — always filter by owner
    base_q = (
        select(Note)
        .options(selectinload(Note.tags))
        .where(Note.user_id == current_user_id)
    )

    # Category filter
    if category:
        base_q = base_q.where(Note.category == category)

    # Tag filter — notes that have a tag with the given name
    if tag:
        base_q = base_q.where(
            Note.id.in_(
                select(note_tags_table.c.note_id)
                .join(Tag, Tag.id == note_tags_table.c.tag_id)
                .where(Tag.user_id == current_user_id, Tag.name == tag)
            )
        )

    # Date filters
    if date_from:
        date_from_dt = datetime.combine(date_from, datetime.min.time())
        base_q = base_q.where(Note.created_at >= date_from_dt)
    if date_to:
        date_to_dt = datetime.combine(date_to, datetime.max.time())
        base_q = base_q.where(Note.created_at <= date_to_dt)

    # Total count (without pagination)
    count_q = select(func.count()).select_from(base_q.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    # Paginated items — newest first
    items_q = base_q.order_by(Note.created_at.desc()).offset(offset).limit(limit)
    items_result = await db.execute(items_q)
    notes = items_result.scalars().all()

    return NoteListResponse(
        items=[_note_to_out(n) for n in notes],
        total=total,
    )


# ---------------------------------------------------------------------------
# GET /api/notes/{id}
# ---------------------------------------------------------------------------

@router.get("/{note_id}", response_model=NoteOut)
async def get_note(
    note_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NoteOut:
    """Return a single note owned by the authenticated user."""
    note = await _fetch_note(db, note_id, current_user_id)
    return _note_to_out(note)


# ---------------------------------------------------------------------------
# PUT /api/notes/{id}
# ---------------------------------------------------------------------------

@router.put("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: uuid.UUID,
    payload: NoteUpdate,
    background_tasks: BackgroundTasks,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NoteOut:
    """
    Partial update. Uses model_dump(exclude_unset=True) to distinguish
    absent fields from explicit None (B8 / mitigation #6).

    Rules:
    - Changing `content` → resets processing_status to 'raw' AND schedules
      the AI pipeline so semantic links + tags + embedding are recomputed
      (Round 32 — G1 fix: previously the status reset never triggered a
      re-pipeline, so edited notes silently lost their auto-links).
    - Changing category/tags/mood/music_metadata → does NOT re-trigger pipeline.
    """
    note = await _fetch_note(db, note_id, current_user_id)
    updates = payload.model_dump(exclude_unset=True)

    # Handle tags separately (delta-apply)
    new_tags: Optional[list[str]] = updates.pop("tags", None)

    # Apply scalar field updates
    content_changed = False
    for field, value in updates.items():
        if field == "content" and value != note.content:
            content_changed = True
        setattr(note, field, value)

    # If content changed, reset pipeline status AND schedule a re-run so
    # the AI pipeline regenerates the embedding + semantic links + tags.
    if content_changed:
        note.processing_status = "raw"
        background_tasks.add_task(_run_pipeline, note_id)

    # Delta-apply tags if provided
    if new_tags is not None:
        tag_objs = await _get_or_create_tags(db, current_user_id, new_tags)
        note.tags = tag_objs

    await db.flush()

    # Reload with tags
    result = await db.execute(
        select(Note).options(selectinload(Note.tags)).where(Note.id == note_id)
    )
    note = result.scalar_one()
    return _note_to_out(note)


# ---------------------------------------------------------------------------
# DELETE /api/notes/{id}
# ---------------------------------------------------------------------------

def _blob_path_from_url(url: Optional[str]) -> Optional[str]:
    """Extract the blob_path (e.g. 'audio/<uuid>/<file>.webm') from a SAS URL.

    Returns None if the URL is not from our blob container.
    """
    if not url:
        return None
    import re

    container = settings.AZURE_STORAGE_CONTAINER
    # SAS URLs look like https://<account>.blob.core.windows.net/<container>/<path>?<token>
    match = re.search(rf"/{re.escape(container)}/([^?]+)", url)
    return match.group(1) if match else None


async def _purge_note_blobs(note: Note) -> None:
    """Delete the audio/image blobs associated with *note* (best-effort)."""
    from app.services.blob_storage import delete_blob

    for url in (note.audio_url, note.image_url):
        path = _blob_path_from_url(url)
        if not path:
            continue
        try:
            await delete_blob(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("delete_note: blob purge failed path=%s err=%s", path, exc)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a note owned by the authenticated user. Returns 204.

    2026-05-01 (bug 3): also purge the audio/image blobs from Storage so a
    deleted note does not leave orphaned media behind.
    2026-05-01 (bug 19): write a NoteDeletion tombstone in the same transaction
    so sync pull can propagate the deletion to other browsers.
    """
    note = await _fetch_note(db, note_id, current_user_id)
    # Capture ids BEFORE delete so the tombstone references the correct note.
    deleted_note_id = note.id
    deleted_user_id = note.user_id
    await _purge_note_blobs(note)
    await db.delete(note)
    db.add(NoteDeletion(id=deleted_note_id, user_id=deleted_user_id))
    await db.flush()


# ---------------------------------------------------------------------------
# POST /api/notes/bulk-delete  — multi-note delete from the Library page
# ---------------------------------------------------------------------------

class BulkDeleteRequest(BaseModel):
    """Body for POST /api/notes/bulk-delete (Bug 3)."""

    ids: list[uuid.UUID] = Field(..., max_length=200)


@router.post("/bulk-delete", status_code=status.HTTP_200_OK)
async def bulk_delete(
    payload: BulkDeleteRequest,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete every note in payload.ids that belongs to the authenticated
    user. Notes owned by other users (or non-existent ids) are silently
    skipped — the response returns the count actually deleted.
    """
    if not payload.ids:
        return {"deleted": 0}
    result = await db.execute(
        select(Note).where(
            Note.id.in_(payload.ids),
            Note.user_id == current_user_id,
        )
    )
    notes = list(result.scalars().all())
    for note in notes:
        # Capture ids BEFORE delete for the tombstone.
        deleted_note_id = note.id
        deleted_user_id = note.user_id
        await _purge_note_blobs(note)
        await db.delete(note)
        db.add(NoteDeletion(id=deleted_note_id, user_id=deleted_user_id))
    await db.flush()
    return {"deleted": len(notes)}


# ---------------------------------------------------------------------------
# POST /api/ai/process/{note_id}  — manual pipeline re-trigger (task 4.6)
# ---------------------------------------------------------------------------

@ai_router.post("/process/{note_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_pipeline(
    note_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually re-trigger the AI pipeline for *note_id* (idempotent).

    Resumes from the note's current processing_status:
    - 'raw' / 'transcribed' → runs Stage 1 + Stage 2.
    - 'processed'           → runs Stage 2 only.
    - 'enriched'            → no-op (already complete).
    - 'failed'              → restarts from last checkpoint.
    """
    # Verify ownership
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.user_id == current_user_id)
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    if note.processing_status == "enriched":
        return {"detail": "Pipeline already complete", "note_id": str(note_id)}

    background_tasks.add_task(_run_pipeline, note_id)
    logger.info("trigger_pipeline: scheduled note_id=%s status=%s", note_id, note.processing_status)
    return {"detail": "Pipeline scheduled", "note_id": str(note_id)}


# ---------------------------------------------------------------------------
# POST /api/notes/relink-all  — bulk semantic-link rebuild (Round 32 / G2+G4)
# ---------------------------------------------------------------------------

@router.post("/relink-all", status_code=status.HTTP_200_OK)
async def relink_all(
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Rebuild semantic links for every note owned by the caller.

    Use cases:
      - After a bulk import (``scripts/import_notes.py`` calls this
        automatically once all POSTs complete) so the oldest imported
        notes -- which had no peers to link to at create time -- finally
        get their composite-scored links.
      - Operator / cron rebuild after a model upgrade or threshold tweak.

    Rate-limited to one call per user per 5 minutes (see
    ``app.services.semantic_links.rebuild_user_links``). A subsequent call
    inside the window returns ``200`` with ``skipped_recent=true`` so
    clients can retry without burning auth.

    Returns: ``{created, updated, duration_ms, skipped_recent}``.
    """
    from app.services.semantic_links import rebuild_user_links

    result = await rebuild_user_links(db, current_user_id)
    await db.commit()
    return result.to_dict()


# ---------------------------------------------------------------------------
# Background task helpers
# ---------------------------------------------------------------------------

async def _run_pipeline(note_id: uuid.UUID) -> None:
    """Run AI pipeline for *note_id* in a fresh DB session."""
    from app.database import SessionLocal
    from app.services.openai_client import get_openai_client

    async with SessionLocal() as db:
        pipeline = AIPipeline(openai_client=get_openai_client(), db=db)
        await pipeline.process_note(note_id)


async def _run_ocr_and_pipeline(note_id: uuid.UUID, image_url: str) -> None:
    """Run OCR then AI pipeline for an image note.

    QA-06 fix: create_note now commits before scheduling this task, so the note
    is guaranteed to be visible in the fresh session below.  If the note is not
    found in the fresh session, log an error and abort rather than proceeding
    with missing data.
    """
    from app.database import SessionLocal
    from app.services.openai_client import get_openai_client

    async with SessionLocal() as db:
        result = await db.execute(select(Note).where(Note.id == note_id))
        note = result.scalar_one_or_none()
        if note is None:
            logger.error(
                "_run_ocr_and_pipeline: note_id=%s not found in DB — aborting OCR",
                note_id,
            )
            return

        # Stage 0.5: OCR — sets status to 'transcribed'
        await process_image_note(note, db)

        # Stage 1 + 2: main pipeline
        pipeline = AIPipeline(openai_client=get_openai_client(), db=db)
        await pipeline.process_note(note_id)
