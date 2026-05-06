"""
Users API endpoints.

Routes:
  PUT /api/users/me/shadow-reader/settings  — update shadow reader settings

US-8: Shadow Reader settings endpoint that updates
  users.shadow_reader_enabled and users.shadow_reader_disabled_categories.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.shadow_reader import ShadowReaderSettings

router = APIRouter(tags=["users"])

# ---------------------------------------------------------------------------
# PUT /api/users/me/shadow-reader/settings
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {"Music", "Fitness", "Journal", "Ideas", "Spiritual", "Learning"}


@router.put("/me/shadow-reader/settings")
async def update_shadow_reader_settings(
    payload: ShadowReaderSettings,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update shadow reader enabled flag and per-category opt-outs for the
    authenticated user.

    Validates that disabled_categories contains only valid category names.
    """
    # Validate categories
    invalid = [c for c in payload.disabled_categories if c not in VALID_CATEGORIES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid categories: {invalid}. Must be one of {sorted(VALID_CATEGORIES)}",
        )

    result = await db.execute(select(User).where(User.id == current_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.shadow_reader_enabled = payload.enabled
    user.shadow_reader_disabled_categories = payload.disabled_categories
    await db.commit()

    return {
        "enabled": user.shadow_reader_enabled,
        "disabled_categories": user.shadow_reader_disabled_categories,
    }
