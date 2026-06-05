"""Pydantic schemas for task list endpoints."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TaskOut(BaseModel):
    id: uuid.UUID
    title: Optional[str] = None
    content: str
    due_at: Optional[datetime] = None
    priority: Optional[int] = None
    recurring: Optional[str] = None
    done_at: Optional[datetime] = None
    category: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    items: list[TaskOut]
    total: int
