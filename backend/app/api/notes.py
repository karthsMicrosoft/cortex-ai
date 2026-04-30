"""
Notes CRUD routes.

Endpoints:
  POST   /api/notes              → 201 NoteOut
  GET    /api/notes              → 200 NoteListResponse (paginated + filtered)
  GET    /api/notes/{id}         → 200 NoteOut | 404
  PUT    /api/notes/{id}         → 200 NoteOut | 404 | 422
  DELETE /api/notes/{id}         → 204 | 404

Ownership: all queries filter by current_user. Cross-user access returns 404 (not 403)
to avoid leaking the existence of a note (Task 5.5 / B8).
"""
import uuid
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.note import Note
from app.models.tag import Tag, note_tags as note_tags_table
from app.schemas.note import NoteCreate, NoteListResponse, NoteOut, NoteUpdate

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_or_create_tags(
    db: AsyncSession, user_id: uuid.UUID, tag_names: list[str]
) -> list[Tag]:
    """Return Tag objects for *tag_names*, creating any that don't exist."""
    tags: list[Tag] = []
    for name in tag_names:
        result = await db.execute(
            select(Tag).where(Tag.user_id == user_id, Tag.name == name)
        )
        tag = result.scalar_one_or_none()
        if tag is None:
            tag = Tag(user_id=user_id, name=name, is_auto=False)
            db.add(tag)
            await db.flush()
        tags.append(tag)
    return tags


def _note_to_out(note: Note) -> NoteOut:
    """Convert Note ORM object to NoteOut schema, building tags list."""
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
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NoteOut:
    """Create a new note for the authenticated user."""
    # Determine initial processing_status per task 5.2 spec:
    # text → 'raw'; voice with audio_url → 'transcribed'; otherwise 'raw'
    if payload.audio_url and payload.source_type == "voice":
        initial_status = "transcribed"
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
    if payload.tags:
        tag_objs = await _get_or_create_tags(db, current_user_id, payload.tags)
        note.tags = tag_objs
        await db.flush()

    await db.refresh(note)
    # Eagerly load tags after refresh
    result = await db.execute(
        select(Note).options(selectinload(Note.tags)).where(Note.id == note.id)
    )
    note = result.scalar_one()
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
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NoteOut:
    """
    Partial update. Uses model_dump(exclude_unset=True) to distinguish
    absent fields from explicit None (B8 / mitigation #6).

    Rules:
    - Changing `content` → resets processing_status to 'raw' (re-pipeline trigger).
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

    # If content changed, reset pipeline status
    if content_changed:
        note.processing_status = "raw"

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

@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a note owned by the authenticated user. Returns 204."""
    note = await _fetch_note(db, note_id, current_user_id)
    await db.delete(note)
    await db.flush()
