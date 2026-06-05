"""Task list API backed by task/reminder fields on notes."""
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.note import Note
from app.schemas.task import TaskListResponse, TaskOut

router = APIRouter()

_TASK_STATUS = Literal["open", "overdue", "done", "all"]


def _task_to_out(note: Note) -> TaskOut:
    return TaskOut(
        id=note.id,
        title=note.title,
        content=note.content[:200],
        due_at=note.due_at,
        priority=note.priority,
        recurring=note.recurring,
        done_at=note.done_at,
        category=note.category,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.get("", response_model=TaskListResponse)
@router.get("/", response_model=TaskListResponse, include_in_schema=False)
async def list_tasks(
    status: _TASK_STATUS = "open",
    priority: Optional[int] = Query(default=None, ge=1, le=3),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskListResponse:
    """List task-like notes for the authenticated user."""
    stmt = select(Note).where(Note.user_id == current_user_id)
    now = datetime.now(timezone.utc)

    if status == "open":
        stmt = stmt.where(Note.due_at.is_not(None), Note.done_at.is_(None))
        order_by = (Note.due_at.asc().nulls_last(),)
    elif status == "overdue":
        stmt = stmt.where(
            Note.due_at.is_not(None),
            Note.done_at.is_(None),
            Note.due_at < now,
        )
        order_by = (Note.due_at.asc().nulls_last(),)
    elif status == "done":
        stmt = stmt.where(Note.done_at.is_not(None))
        order_by = (Note.done_at.desc(),)
    else:
        stmt = stmt.where(or_(Note.due_at.is_not(None), Note.done_at.is_not(None)))
        order_by = (Note.due_at.asc().nulls_last(), Note.created_at.desc())

    if priority is not None:
        stmt = stmt.where(Note.priority == priority)

    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()

    items_result = await db.execute(stmt.order_by(*order_by).offset(offset).limit(limit))
    notes = items_result.scalars().all()
    return TaskListResponse(items=[_task_to_out(note) for note in notes], total=total)
