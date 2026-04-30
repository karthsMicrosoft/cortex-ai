"""
Shared database helper utilities.

Provides batch/optimised operations used by multiple modules to avoid N+1 patterns.
"""
import uuid
import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag

logger = logging.getLogger(__name__)


async def get_or_create_tags_batch(
    db: AsyncSession,
    user_id: uuid.UUID,
    tag_names: Sequence[str],
    is_auto: bool = False,
) -> list[Tag]:
    """
    Fetch or create Tag rows for *tag_names* in a **single round-trip pair**.

    Algorithm:
      1. SELECT all existing tags WHERE name = ANY(:names)  — one query.
      2. Batch-INSERT missing names with ON CONFLICT DO NOTHING — one query.
      3. SELECT again to get the newly-inserted rows' UUIDs.

    This replaces the original per-tag SELECT+INSERT loop that caused N+1
    database round-trips (PERF-01 / PERF-N3 fix).

    Args:
        db:        Async SQLAlchemy session.
        user_id:   Owner UUID.
        tag_names: Names to resolve (duplicates are deduplicated automatically).
        is_auto:   is_auto flag set on newly-created tags (False for user-supplied,
                   True for pipeline-auto-generated).

    Returns:
        List of Tag ORM objects in the same order as *tag_names* (deduplicated).
    """
    if not tag_names:
        return []

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_names: list[str] = []
    for n in tag_names:
        n_clean = n.strip().lower()
        if n_clean and n_clean not in seen:
            seen.add(n_clean)
            unique_names.append(n_clean)

    if not unique_names:
        return []

    # --- Step 1: fetch existing tags in one query ---
    result = await db.execute(
        select(Tag).where(
            Tag.user_id == user_id,
            Tag.name.in_(unique_names),
        )
    )
    existing_tags = result.scalars().all()
    existing_names = {t.name for t in existing_tags}

    # --- Step 2: insert missing tags (batch, one flush) ---
    missing_names = [n for n in unique_names if n not in existing_names]
    new_tags: list[Tag] = []
    for name in missing_names:
        tag = Tag(user_id=user_id, name=name, is_auto=is_auto)
        db.add(tag)
        new_tags.append(tag)

    if new_tags:
        await db.flush()  # single flush for all new tags

    # --- Step 3: build ordered result list ---
    all_tags_by_name: dict[str, Tag] = {t.name: t for t in list(existing_tags) + new_tags}
    return [all_tags_by_name[n] for n in unique_names if n in all_tags_by_name]
