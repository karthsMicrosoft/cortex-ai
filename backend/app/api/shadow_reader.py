"""
Shadow Reader API endpoints.

Routes (prefix: /api/notes):
  GET    /{note_id}/shadow-reader          — poll status + questions
  POST   /{note_id}/shadow-reader/answer   — submit answer (409 if not 'asked')
  POST   /{note_id}/shadow-reader/dismiss  — dismiss (mark 'dismissed')

The answer endpoint schedules merge_answer_into_note as a BackgroundTask so
the HTTP response returns immediately while embedding regeneration runs async.
"""
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.note import Note
from app.pipeline.shadow_reader import merge_answer_into_note
from app.schemas.shadow_reader import ShadowReaderAnswer, ShadowReaderQuestionsOut
from app.services.openai_client import get_openai_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["shadow_reader"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_note_or_404(
    db: AsyncSession,
    note_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Note:
    """Fetch note owned by user_id or raise HTTP 404."""
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
# GET /{note_id}/shadow-reader
# ---------------------------------------------------------------------------


@router.get("/{note_id}/shadow-reader", response_model=ShadowReaderQuestionsOut)
async def get_shadow_reader_questions(
    note_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShadowReaderQuestionsOut:
    """Poll for shadow reader status and questions for a note.

    Frontend polls this endpoint with the B17 tiered schedule:
      - 10 polls × 2s (0–20s), then 5 polls × 5s (20–45s).
    Returns immediately with current status; no blocking.
    """
    note = await _get_note_or_404(db, note_id, current_user_id)
    return ShadowReaderQuestionsOut(
        status=note.shadow_reader_status or "pending",
        questions=note.shadow_reader_questions or [],
    )


# ---------------------------------------------------------------------------
# POST /{note_id}/shadow-reader/answer
# ---------------------------------------------------------------------------


@router.post("/{note_id}/shadow-reader/answer")
async def answer_shadow_reader(
    note_id: uuid.UUID,
    payload: ShadowReaderAnswer,
    background_tasks: BackgroundTasks,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Submit an answer to shadow reader questions.

    Raises 409 if the note is not in 'asked' state.
    Schedules merge_answer_into_note as a background task so the response
    returns immediately (embedding regeneration is async).
    """
    note = await _get_note_or_404(db, note_id, current_user_id)

    if note.shadow_reader_status != "asked":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shadow reader not in asked state",
        )

    # Set status to answered optimistically so the GET endpoint reflects it
    # even before the background task completes embedding regen.
    note.shadow_reader_answer = payload.answer
    note.shadow_reader_status = "answered"
    await db.commit()

    openai_client = get_openai_client()

    # Schedule the full merge (embedding + re-link) as a background task
    background_tasks.add_task(
        _merge_in_background,
        note_id=note_id,
        answer=payload.answer,
        openai_client=openai_client,
    )

    return {"status": "answered"}


async def _merge_in_background(note_id: uuid.UUID, answer: str, openai_client) -> None:
    """Background task: full merge with SERIALIZABLE transaction."""
    from app.database import SessionLocal
    from sqlalchemy import select

    async with SessionLocal() as bg_db:
        try:
            result = await bg_db.execute(select(Note).where(Note.id == note_id))
            note = result.scalar_one_or_none()
            if note is None:
                logger.error("merge_background: note %s not found", note_id)
                return
            await merge_answer_into_note(note, answer, openai_client, bg_db)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "merge_background_failed: note_id=%s error_class=%s",
                note_id,
                type(exc).__name__,
            )


# ---------------------------------------------------------------------------
# POST /{note_id}/shadow-reader/dismiss
# ---------------------------------------------------------------------------


@router.post("/{note_id}/shadow-reader/dismiss")
async def dismiss_shadow_reader(
    note_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dismiss shadow reader for this note (sets status to 'dismissed').

    Dismissing one note never affects future notes.
    """
    note = await _get_note_or_404(db, note_id, current_user_id)
    note.shadow_reader_status = "dismissed"
    await db.commit()
    return {"status": "dismissed"}
