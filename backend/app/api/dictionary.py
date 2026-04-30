"""
Personal Dictionary API.

Endpoints:
  GET    /api/dictionary          — list all terms (filterable by term_type)
  POST   /api/dictionary          — add a term (201; 400 on limit; 409 on duplicate)
  PUT    /api/dictionary/{id}     — update a term (200; 404 if not found)
  DELETE /api/dictionary/{id}     — remove a term (204)
  POST   /api/dictionary/bulk     — bulk import JSON array (≤500; 400 if larger)
  GET    /api/dictionary/export   — full JSON export

Hard limit: 2000 terms per user (enforced on POST and bulk).
"""
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.vocabulary import UserVocabulary
from app.schemas.dictionary import (
    BulkImportResponse,
    VocabularyTerm,
    VocabularyTermOut,
    VocabularyTermUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dictionary"])

MAX_TERMS_PER_USER = 2000
MAX_BULK_TERMS = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_term_count(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Return the number of vocabulary terms the user currently has."""
    return await db.scalar(
        select(func.count()).select_from(UserVocabulary).where(
            UserVocabulary.user_id == user_id
        )
    ) or 0


async def _get_term_or_404(
    term_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> UserVocabulary:
    result = await db.execute(
        select(UserVocabulary).where(
            UserVocabulary.id == term_id,
            UserVocabulary.user_id == user_id,
        )
    )
    term = result.scalar_one_or_none()
    if term is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Term not found")
    return term


# ---------------------------------------------------------------------------
# GET /api/dictionary
# ---------------------------------------------------------------------------

@router.get("", response_model=list[VocabularyTermOut])
async def list_terms(
    term_type: Optional[str] = None,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[VocabularyTermOut]:
    """List all vocabulary terms for the current user, ordered by usage_count DESC."""
    query = select(UserVocabulary).where(UserVocabulary.user_id == current_user_id)
    if term_type:
        query = query.where(UserVocabulary.term_type == term_type)
    query = query.order_by(UserVocabulary.usage_count.desc())
    result = await db.execute(query)
    return result.scalars().all()


# ---------------------------------------------------------------------------
# POST /api/dictionary
# ---------------------------------------------------------------------------

@router.post("", response_model=VocabularyTermOut, status_code=status.HTTP_201_CREATED)
async def add_term(
    payload: VocabularyTerm,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VocabularyTermOut:
    """Add a vocabulary term.  Returns 400 if the 2000-term limit is reached;
    returns 409 if the term already exists for this user."""
    count = await _get_user_term_count(current_user_id, db)
    if count >= MAX_TERMS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dictionary limit of {MAX_TERMS_PER_USER} terms reached",
        )

    vocab = UserVocabulary(
        user_id=current_user_id,
        term=payload.term,
        term_type=payload.term_type,
        pronunciation_hint=payload.pronunciation_hint,
        boost_weight=payload.boost_weight,
    )
    db.add(vocab)
    try:
        await db.commit()
        await db.refresh(vocab)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Term already exists in your dictionary",
        )
    logger.info("dictionary: added term=%r for user=%s", vocab.term, current_user_id)
    return vocab


# ---------------------------------------------------------------------------
# PUT /api/dictionary/{id}
# ---------------------------------------------------------------------------

@router.put("/{term_id}", response_model=VocabularyTermOut)
async def update_term(
    term_id: uuid.UUID,
    payload: VocabularyTermUpdate,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VocabularyTermOut:
    """Update a vocabulary term's fields.  404 if not found."""
    term = await _get_term_or_404(term_id, current_user_id, db)

    if payload.term is not None:
        term.term = payload.term
    if payload.term_type is not None:
        term.term_type = payload.term_type
    if payload.pronunciation_hint is not None:
        term.pronunciation_hint = payload.pronunciation_hint
    if payload.boost_weight is not None:
        term.boost_weight = payload.boost_weight

    try:
        await db.commit()
        await db.refresh(term)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A term with that name already exists in your dictionary",
        )
    return term


# ---------------------------------------------------------------------------
# DELETE /api/dictionary/{id}
# ---------------------------------------------------------------------------

@router.delete("/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_term(
    term_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a vocabulary term.  Silently succeeds even if not found."""
    await db.execute(
        delete(UserVocabulary).where(
            UserVocabulary.id == term_id,
            UserVocabulary.user_id == current_user_id,
        )
    )
    await db.commit()


# ---------------------------------------------------------------------------
# POST /api/dictionary/bulk
# ---------------------------------------------------------------------------

@router.post("/bulk", response_model=BulkImportResponse, status_code=status.HTTP_201_CREATED)
async def bulk_import(
    terms: list[VocabularyTerm],
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkImportResponse:
    """Bulk import up to 500 terms.  Returns 400 if list exceeds 500 entries.
    Duplicate terms are skipped (not treated as errors)."""
    if len(terms) > MAX_BULK_TERMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bulk import limited to {MAX_BULK_TERMS} terms per request",
        )

    inserted = 0
    for t in terms:
        vocab = UserVocabulary(
            user_id=current_user_id,
            term=t.term,
            term_type=t.term_type,
            pronunciation_hint=t.pronunciation_hint,
            boost_weight=t.boost_weight,
        )
        db.add(vocab)
        try:
            await db.commit()
            inserted += 1
        except IntegrityError:
            await db.rollback()

    logger.info(
        "dictionary bulk_import: user=%s inserted=%d total=%d",
        current_user_id,
        inserted,
        len(terms),
    )
    return BulkImportResponse(inserted=inserted, total=len(terms))


# ---------------------------------------------------------------------------
# GET /api/dictionary/export
# ---------------------------------------------------------------------------

@router.get("/export", response_model=list[VocabularyTermOut])
async def export_terms(
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[VocabularyTermOut]:
    """Export all vocabulary terms as a JSON list."""
    result = await db.execute(
        select(UserVocabulary)
        .where(UserVocabulary.user_id == current_user_id)
        .order_by(UserVocabulary.usage_count.desc())
    )
    return result.scalars().all()
