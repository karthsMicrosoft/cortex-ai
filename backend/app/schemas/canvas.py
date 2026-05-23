"""
Pydantic schemas for Phase 7 Visual Thinking Canvas endpoints.
"""
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


_ITEM_TYPE = Literal["note", "group", "text"]
_EDGE_STYLE = Literal["default", "dashed", "bold"]


# ---------------------------------------------------------------------------
# Canvas — request
# ---------------------------------------------------------------------------

class CanvasCreate(BaseModel):
    title: str = Field(default="Untitled Canvas", max_length=200)
    description: Optional[str] = None


class CanvasUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = None
    viewport_x: Optional[float] = None
    viewport_y: Optional[float] = None
    viewport_zoom: Optional[float] = Field(default=None, ge=0.1, le=5.0)


# ---------------------------------------------------------------------------
# Canvas items — request
# ---------------------------------------------------------------------------

class CanvasItemCreate(BaseModel):
    note_id: Optional[uuid.UUID] = None
    item_type: _ITEM_TYPE
    position_x: float = 0.0
    position_y: float = 0.0
    width: Optional[float] = Field(default=None, gt=0)
    height: Optional[float] = Field(default=None, gt=0)
    color: Optional[str] = Field(default=None, max_length=20)
    label: Optional[str] = None
    z_index: int = 0


class CanvasItemUpdate(BaseModel):
    """Single-item PATCH. `version` is REQUIRED for optimistic concurrency."""
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    width: Optional[float] = Field(default=None, gt=0)
    height: Optional[float] = Field(default=None, gt=0)
    color: Optional[str] = Field(default=None, max_length=20)
    label: Optional[str] = None
    z_index: Optional[int] = None
    version: int


class BatchItemEntry(BaseModel):
    """One entry inside a batch position-update request."""
    id: uuid.UUID
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    width: Optional[float] = Field(default=None, gt=0)
    height: Optional[float] = Field(default=None, gt=0)
    z_index: Optional[int] = None
    version: int


class BatchItemUpdateRequest(BaseModel):
    items: list[BatchItemEntry]


# ---------------------------------------------------------------------------
# Edges — request
# ---------------------------------------------------------------------------

class CanvasEdgeCreate(BaseModel):
    source_item_id: uuid.UUID
    target_item_id: uuid.UUID
    label: Optional[str] = None
    style: _EDGE_STYLE = "default"


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class CanvasItemOut(BaseModel):
    id: uuid.UUID
    canvas_id: uuid.UUID
    note_id: Optional[uuid.UUID] = None
    item_type: str
    position_x: float
    position_y: float
    width: Optional[float] = None
    height: Optional[float] = None
    color: Optional[str] = None
    label: Optional[str] = None
    z_index: int
    version: int
    last_known_title: Optional[str] = None
    # Inlined for the frontend's render-from-canvas-payload path.
    note_title: Optional[str] = None
    note_summary: Optional[str] = None
    note_content: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CanvasEdgeOut(BaseModel):
    id: uuid.UUID
    canvas_id: uuid.UUID
    source_item_id: uuid.UUID
    target_item_id: uuid.UUID
    label: Optional[str] = None
    style: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CanvasOut(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    viewport_x: float
    viewport_y: float
    viewport_zoom: float
    item_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CanvasDetailOut(CanvasOut):
    items: list[CanvasItemOut] = []
    edges: list[CanvasEdgeOut] = []


class CanvasListResponse(BaseModel):
    items: list[CanvasOut]
    total: int


class BatchUpdateResponse(BaseModel):
    items: list[CanvasItemOut]
