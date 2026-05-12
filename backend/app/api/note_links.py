"""
Backlinks API — PR 6.1 + manual link CRUD — PR 6.3.

Endpoints:
  GET    /api/notes/{note_id}/links              (PR 6.1)
  POST   /api/notes/{note_id}/links              (PR 6.3 — manual link create)
  DELETE /api/notes/{note_id}/links/{link_id}    (PR 6.3 — manual link delete)

The GET endpoint returns outgoing links (this note → others) and incoming
links (others → this note), each enriched with the OTHER end's title,
summary, and category.

Sort order: link_type priority (manual > wiki > semantic) then by score desc.

Manual link CRUD (PR 6.3):
  - Only link_type='manual' may be created/deleted via these endpoints.
    Wiki links come from the parser and semantic links come from the
    ingestion pipeline; they're managed elsewhere.
  - POST is idempotent: if the (source, target, manual) row already exists
    we return 200 with the existing row (no UNIQUE-violation surfacing).
  - DELETE on a non-manual link → 403 (semantic / wiki links cannot be
    removed via the user-facing UI).

Privacy:
  - 401 if not authenticated.
  - 404 if the source note doesn't exist or isn't owned by the caller (no
    leak). For POST, the target note must also be owned by the caller — a
    foreign target also yields 404.
  - Any link whose other-end note belongs to a different user is filtered
    out silently from GET responses.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.note import Note
from app.models.note_link import NoteLink

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LinkItem(BaseModel):
    # The link row's own id — used by the frontend to call DELETE on manual
    # links (added in PR 6.3). Existing PR 6.1 clients ignore this field.
    link_id: Optional[str] = None
    note_id: str
    title: Optional[str] = None
    summary: Optional[str] = None
    category: str
    link_type: str
    score: Optional[float] = None


class LinksResponse(BaseModel):
    outgoing: list[LinkItem]
    incoming: list[LinkItem]


# ---------------------------------------------------------------------------
# Sorting helpers
# ---------------------------------------------------------------------------

# Lower number = higher priority (sorted ascending).
_LINK_TYPE_PRIORITY = {"manual": 0, "wiki": 1, "semantic": 2}


def _sort_key(item: LinkItem) -> tuple[int, float]:
    """Sort by (priority, -score). Items without a score sort as 0."""
    priority = _LINK_TYPE_PRIORITY.get(item.link_type, 99)
    score = item.score if item.score is not None else 0.0
    return (priority, -score)


def _to_item(other: Note, link: NoteLink) -> LinkItem:
    """Build a LinkItem from the OTHER-end note + the link row.

    Score is exposed for semantic links only; for manual/wiki the
    similarity_score column is a placeholder so we surface null.
    """
    return LinkItem(
        link_id=str(link.id),
        note_id=str(other.id),
        title=other.title,
        summary=other.summary,
        category=other.category,
        link_type=link.link_type,
        score=link.similarity_score if link.link_type == "semantic" else None,
    )


# ---------------------------------------------------------------------------
# GET /api/notes/{note_id}/links
# ---------------------------------------------------------------------------

@router.get("/{note_id}/links", response_model=LinksResponse)
async def get_note_links(
    note_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinksResponse:
    """Return outgoing + incoming links for a note owned by the current user."""
    # Ownership check — 404 if missing OR owned by another user (no leak).
    owner_check = await db.execute(
        select(Note.id).where(Note.id == note_id, Note.user_id == current_user_id)
    )
    if owner_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    # Outgoing: links where source = note_id, joined with the target Note row.
    outgoing_rows = await db.execute(
        select(NoteLink, Note)
        .join(Note, Note.id == NoteLink.target_note_id)
        .where(
            NoteLink.source_note_id == note_id,
            Note.user_id == current_user_id,  # privacy filter
        )
    )
    outgoing = [_to_item(other, link) for link, other in outgoing_rows.all()]

    # Incoming: links where target = note_id, joined with the source Note row.
    incoming_rows = await db.execute(
        select(NoteLink, Note)
        .join(Note, Note.id == NoteLink.source_note_id)
        .where(
            NoteLink.target_note_id == note_id,
            Note.user_id == current_user_id,  # privacy filter
        )
    )
    incoming = [_to_item(other, link) for link, other in incoming_rows.all()]

    outgoing.sort(key=_sort_key)
    incoming.sort(key=_sort_key)

    return LinksResponse(outgoing=outgoing, incoming=incoming)


# ---------------------------------------------------------------------------
# PR 6.3 — Manual link create + delete
# ---------------------------------------------------------------------------

class CreateLinkRequest(BaseModel):
    target_note_id: uuid.UUID
    link_type: str = Field(default="manual")


class CreatedLink(BaseModel):
    id: uuid.UUID
    source_note_id: uuid.UUID
    target_note_id: uuid.UUID
    link_type: str
    score: Optional[float] = None
    created_at: Optional[datetime] = None


def _to_created(link: NoteLink) -> CreatedLink:
    return CreatedLink(
        id=link.id,
        source_note_id=link.source_note_id,
        target_note_id=link.target_note_id,
        link_type=link.link_type,
        score=link.similarity_score if link.link_type == "semantic" else None,
        created_at=link.created_at,
    )


async def _assert_owns_note(
    db: AsyncSession, note_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Raise 404 unless `note_id` exists AND belongs to `user_id`."""
    row = await db.execute(
        select(Note.id).where(Note.id == note_id, Note.user_id == user_id)
    )
    if row.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")


@router.post("/{note_id}/links", response_model=CreatedLink)
async def create_manual_link(
    note_id: uuid.UUID,
    payload: CreateLinkRequest,
    response: Response,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreatedLink:
    """Create a user-authored manual link from `note_id` → `target_note_id`.

    Returns 201 on insert, 200 if a (source, target, manual) row already
    exists (idempotent). 400 for self-links or non-'manual' link_type.
    404 if either endpoint isn't a note owned by the caller.
    """
    if payload.link_type != "manual":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="link_type must be 'manual' for this endpoint",
        )
    if payload.target_note_id == note_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A note cannot link to itself",
        )

    # Ownership: both source AND target must belong to the caller.
    await _assert_owns_note(db, note_id, current_user_id)
    await _assert_owns_note(db, payload.target_note_id, current_user_id)

    # Idempotency: if the triple already exists, return it with 200.
    existing_row = await db.execute(
        select(NoteLink).where(
            NoteLink.source_note_id == note_id,
            NoteLink.target_note_id == payload.target_note_id,
            NoteLink.link_type == "manual",
        )
    )
    existing = existing_row.scalar_one_or_none()
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _to_created(existing)

    link = NoteLink(
        source_note_id=note_id,
        target_note_id=payload.target_note_id,
        similarity_score=0.0,  # placeholder; manual links surface score=null
        link_type="manual",
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    response.status_code = status.HTTP_201_CREATED
    return _to_created(link)


@router.delete("/{note_id}/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_manual_link(
    note_id: uuid.UUID,
    link_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a manual link owned by the current user.

    - 404 if the source note isn't owned by the caller, or the link row
      doesn't exist under that source note.
    - 403 if the link exists but isn't `link_type='manual'` (semantic /
      wiki links are managed by the pipeline / parser, not the UI).
    - 204 on success.
    """
    # Source ownership first — leaks nothing about other-user notes.
    await _assert_owns_note(db, note_id, current_user_id)

    row = await db.execute(
        select(NoteLink).where(
            NoteLink.id == link_id,
            NoteLink.source_note_id == note_id,
        )
    )
    link = row.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    if link.link_type != "manual":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only manual links can be removed via this endpoint",
        )

    await db.delete(link)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
