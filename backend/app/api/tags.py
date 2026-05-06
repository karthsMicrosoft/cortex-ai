"""
Tags endpoints — B6 dedicated module.

Endpoints:
  GET  /api/tags  — list all tags for the authenticated user
  POST /api/tags  — create a manual tag (is_auto=False)

Auth required on all routes.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.tag import Tag

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas (local — tags are simple enough not to need a separate schema file)
# ---------------------------------------------------------------------------

class TagOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    is_auto: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TagCreate(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# GET /api/tags
# ---------------------------------------------------------------------------

@router.get("", response_model=list[TagOut])
async def list_tags(
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TagOut]:
    """Return all tags belonging to the authenticated user, ordered by name."""
    result = await db.execute(
        select(Tag)
        .where(Tag.user_id == current_user_id)
        .order_by(Tag.name)
    )
    tags = result.scalars().all()
    return [TagOut.model_validate(t) for t in tags]


# ---------------------------------------------------------------------------
# POST /api/tags
# ---------------------------------------------------------------------------

@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    payload: TagCreate,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TagOut:
    """Create a manual tag for the authenticated user (is_auto=False).

    Returns 409 if a tag with the same name already exists for this user.
    """
    name = payload.name.strip().lower()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tag name cannot be empty",
        )

    # Check for duplicate
    result = await db.execute(
        select(Tag).where(Tag.user_id == current_user_id, Tag.name == name)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tag '{name}' already exists",
        )

    tag = Tag(user_id=current_user_id, name=name, is_auto=False)
    db.add(tag)
    await db.flush()
    await db.refresh(tag)
    return TagOut.model_validate(tag)
