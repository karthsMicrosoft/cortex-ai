"""
Backlinks API — PR 6.1.

Single endpoint:
  GET /api/notes/{note_id}/links

Returns the outgoing links (this note → others) and incoming links
(others → this note), each enriched with the OTHER end's title, summary,
and category.

Sort order: link_type priority (manual > wiki > semantic) then by score desc.

Privacy:
  - 401 if not authenticated.
  - 404 if the note doesn't exist or isn't owned by the caller (no leak).
  - Any link whose other-end note belongs to a different user is filtered
    out silently.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
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
