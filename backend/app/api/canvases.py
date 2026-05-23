"""
Phase 7 — Visual Thinking Canvas REST API.

12 endpoints under /api/canvases. All require Bearer auth; ownership is
enforced on every request and cross-user access returns 404 (never 403)
so existence isn't leaked.

Key behaviours:
  * Optimistic concurrency on item PATCH + batch via `version` column.
  * Cross-canvas edge validation (both endpoints must share canvas_id).
  * Ghost-card support: when a note is added we snapshot its title into
    `last_known_title`; if the note is later deleted the FK ON DELETE
    SET NULL keeps the card and the UI renders the snapshot.
  * Batch updates are transactional — any version conflict rolls back
    the entire batch and returns 409 with the list of conflicting ids.
  * Auto-layout: simple force-directed-ish grid arrangement (no
    d3-force dependency on the backend), bumps all item versions.
"""
from __future__ import annotations

import math
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.canvas import Canvas
from app.models.canvas_edge import CanvasEdge
from app.models.canvas_item import CanvasItem
from app.models.note import Note
from app.schemas.canvas import (
    BatchItemUpdateRequest,
    BatchUpdateResponse,
    CanvasCreate,
    CanvasDetailOut,
    CanvasEdgeCreate,
    CanvasEdgeOut,
    CanvasItemCreate,
    CanvasItemOut,
    CanvasItemUpdate,
    CanvasListResponse,
    CanvasOut,
    CanvasUpdate,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_owned_canvas(
    db: AsyncSession, canvas_id: uuid.UUID, user_id: uuid.UUID
) -> Canvas:
    """Load a canvas owned by user_id or raise 404 (no existence leak)."""
    row = await db.execute(
        select(Canvas).where(Canvas.id == canvas_id, Canvas.user_id == user_id)
    )
    canvas = row.scalar_one_or_none()
    if canvas is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Canvas not found"
        )
    return canvas


def _item_to_out(item: CanvasItem) -> CanvasItemOut:
    """Build CanvasItemOut, inlining note metadata when the FK is live."""
    note = getattr(item, "note", None)
    return CanvasItemOut(
        id=item.id,
        canvas_id=item.canvas_id,
        note_id=item.note_id,
        item_type=item.item_type,
        position_x=item.position_x,
        position_y=item.position_y,
        width=item.width,
        height=item.height,
        color=item.color,
        label=item.label,
        z_index=item.z_index,
        version=item.version,
        last_known_title=item.last_known_title,
        note_title=(note.title if note is not None else None),
        note_summary=(note.summary if note is not None else None),
        note_content=(note.content if note is not None else None),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _edge_to_out(edge: CanvasEdge) -> CanvasEdgeOut:
    return CanvasEdgeOut.model_validate(edge)


# ---------------------------------------------------------------------------
# Canvas CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=CanvasListResponse)
async def list_canvases(
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasListResponse:
    """List the caller's canvases (most-recently-updated first), with item counts."""
    rows = await db.execute(
        select(Canvas, func.count(CanvasItem.id))
        .outerjoin(CanvasItem, CanvasItem.canvas_id == Canvas.id)
        .where(Canvas.user_id == current_user_id)
        .group_by(Canvas.id)
        .order_by(Canvas.updated_at.desc())
    )
    items: list[CanvasOut] = []
    for canvas, item_count in rows.all():
        out = CanvasOut.model_validate(canvas)
        out.item_count = int(item_count or 0)
        items.append(out)
    return CanvasListResponse(items=items, total=len(items))


@router.post("", response_model=CanvasOut, status_code=status.HTTP_201_CREATED)
async def create_canvas(
    payload: CanvasCreate,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasOut:
    canvas = Canvas(
        user_id=current_user_id,
        title=payload.title,
        description=payload.description,
    )
    db.add(canvas)
    await db.commit()
    await db.refresh(canvas)
    return CanvasOut.model_validate(canvas)


@router.get("/{canvas_id}", response_model=CanvasDetailOut)
async def get_canvas(
    canvas_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasDetailOut:
    """Return the canvas plus all items (with inlined note metadata) and edges."""
    row = await db.execute(
        select(Canvas)
        .options(
            selectinload(Canvas.items).selectinload(CanvasItem.note),
            selectinload(Canvas.edges),
        )
        .where(Canvas.id == canvas_id, Canvas.user_id == current_user_id)
    )
    canvas = row.scalar_one_or_none()
    if canvas is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Canvas not found"
        )

    detail = CanvasDetailOut.model_validate(canvas)
    detail.item_count = len(canvas.items)
    detail.items = [_item_to_out(it) for it in canvas.items]
    detail.edges = [_edge_to_out(e) for e in canvas.edges]
    return detail


@router.patch("/{canvas_id}", response_model=CanvasOut)
async def update_canvas(
    canvas_id: uuid.UUID,
    payload: CanvasUpdate,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasOut:
    canvas = await _get_owned_canvas(db, canvas_id, current_user_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(canvas, key, value)
    await db.commit()
    await db.refresh(canvas)
    return CanvasOut.model_validate(canvas)


@router.delete("/{canvas_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_canvas(
    canvas_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    canvas = await _get_owned_canvas(db, canvas_id, current_user_id)
    await db.delete(canvas)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

@router.post(
    "/{canvas_id}/items",
    response_model=CanvasItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_item(
    canvas_id: uuid.UUID,
    payload: CanvasItemCreate,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasItemOut:
    canvas = await _get_owned_canvas(db, canvas_id, current_user_id)

    last_known_title: Optional[str] = None
    note_obj: Optional[Note] = None
    if payload.note_id is not None:
        note_row = await db.execute(
            select(Note).where(
                Note.id == payload.note_id, Note.user_id == current_user_id
            )
        )
        note_obj = note_row.scalar_one_or_none()
        if note_obj is None:
            # Note must exist AND be owned by the caller — 404 to avoid leak.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Note not found"
            )
        last_known_title = note_obj.title

    item = CanvasItem(
        canvas_id=canvas.id,
        note_id=payload.note_id,
        item_type=payload.item_type,
        position_x=payload.position_x,
        position_y=payload.position_y,
        width=payload.width,
        height=payload.height,
        color=payload.color,
        label=payload.label,
        z_index=payload.z_index,
        last_known_title=last_known_title,
    )
    db.add(item)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Most likely the partial unique index on (canvas_id, note_id) tripped.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Item with this note already exists on the canvas",
        )
    await db.refresh(item)
    # Attach note for serialization (avoid extra round-trip).
    if note_obj is not None:
        item.note = note_obj  # type: ignore[assignment]
    return _item_to_out(item)


@router.patch(
    "/{canvas_id}/items/{item_id}",
    response_model=CanvasItemOut,
)
async def update_item(
    canvas_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: CanvasItemUpdate,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasItemOut:
    await _get_owned_canvas(db, canvas_id, current_user_id)
    row = await db.execute(
        select(CanvasItem)
        .options(selectinload(CanvasItem.note))
        .where(CanvasItem.id == item_id, CanvasItem.canvas_id == canvas_id)
    )
    item = row.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    if item.version != payload.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Version conflict",
                "current_version": item.version,
            },
        )

    data = payload.model_dump(exclude_unset=True, exclude={"version"})
    for key, value in data.items():
        setattr(item, key, value)
    item.version = item.version + 1
    await db.commit()
    await db.refresh(item)
    return _item_to_out(item)


@router.post(
    "/{canvas_id}/items/batch",
    response_model=BatchUpdateResponse,
)
async def batch_update_items(
    canvas_id: uuid.UUID,
    payload: BatchItemUpdateRequest,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BatchUpdateResponse:
    """Transactional batch update of item positions/sizes/z-index.

    Each entry MUST include its `version`. If any version mismatches the
    DB row we roll back the entire batch and return 409 with the list of
    conflicts.
    """
    await _get_owned_canvas(db, canvas_id, current_user_id)

    if not payload.items:
        return BatchUpdateResponse(items=[])

    ids = [entry.id for entry in payload.items]
    rows = await db.execute(
        select(CanvasItem)
        .options(selectinload(CanvasItem.note))
        .where(CanvasItem.canvas_id == canvas_id, CanvasItem.id.in_(ids))
    )
    items_by_id = {it.id: it for it in rows.scalars().all()}

    # Validate all entries up-front BEFORE mutating anything.
    conflicts: list[dict] = []
    missing: list[str] = []
    for entry in payload.items:
        item = items_by_id.get(entry.id)
        if item is None:
            missing.append(str(entry.id))
            continue
        if item.version != entry.version:
            conflicts.append(
                {
                    "id": str(entry.id),
                    "current_version": item.version,
                    "submitted_version": entry.version,
                }
            )

    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Items not found", "missing": missing},
        )

    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Version conflict", "conflicts": conflicts},
        )

    # All checks pass — mutate.
    updated: list[CanvasItem] = []
    for entry in payload.items:
        item = items_by_id[entry.id]
        data = entry.model_dump(exclude_unset=True, exclude={"id", "version"})
        for key, value in data.items():
            setattr(item, key, value)
        item.version = item.version + 1
        updated.append(item)

    await db.commit()
    for item in updated:
        await db.refresh(item)

    return BatchUpdateResponse(items=[_item_to_out(it) for it in updated])


@router.delete(
    "/{canvas_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_item(
    canvas_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _get_owned_canvas(db, canvas_id, current_user_id)
    row = await db.execute(
        select(CanvasItem).where(
            CanvasItem.id == item_id, CanvasItem.canvas_id == canvas_id
        )
    )
    item = row.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )
    await db.delete(item)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------

@router.post(
    "/{canvas_id}/edges",
    response_model=CanvasEdgeOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_edge(
    canvas_id: uuid.UUID,
    payload: CanvasEdgeCreate,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvasEdgeOut:
    await _get_owned_canvas(db, canvas_id, current_user_id)

    if payload.source_item_id == payload.target_item_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="An edge cannot connect an item to itself",
        )

    # Both endpoints must exist AND belong to the same canvas as the URL.
    rows = await db.execute(
        select(CanvasItem.id).where(
            CanvasItem.id.in_([payload.source_item_id, payload.target_item_id]),
            CanvasItem.canvas_id == canvas_id,
        )
    )
    found_ids = {row[0] for row in rows.all()}
    if (
        payload.source_item_id not in found_ids
        or payload.target_item_id not in found_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Source and target items must both belong to this canvas",
        )

    edge = CanvasEdge(
        canvas_id=canvas_id,
        source_item_id=payload.source_item_id,
        target_item_id=payload.target_item_id,
        label=payload.label,
        style=payload.style,
    )
    db.add(edge)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An edge with this source and target already exists",
        )
    await db.refresh(edge)
    return _edge_to_out(edge)


@router.delete(
    "/{canvas_id}/edges/{edge_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_edge(
    canvas_id: uuid.UUID,
    edge_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _get_owned_canvas(db, canvas_id, current_user_id)
    row = await db.execute(
        select(CanvasEdge).where(
            CanvasEdge.id == edge_id, CanvasEdge.canvas_id == canvas_id
        )
    )
    edge = row.scalar_one_or_none()
    if edge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Edge not found"
        )
    await db.delete(edge)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Auto-layout
# ---------------------------------------------------------------------------

@router.post("/{canvas_id}/auto-layout", response_model=BatchUpdateResponse)
async def auto_layout(
    canvas_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BatchUpdateResponse:
    """Re-arrange items using a deterministic grid layout.

    A simple grid is plenty for the backend: the frontend can still run
    d3-force locally if it wants a richer layout. We bump every item's
    `version` so any in-flight PATCH from the client will 409 cleanly.
    """
    await _get_owned_canvas(db, canvas_id, current_user_id)
    rows = await db.execute(
        select(CanvasItem)
        .options(selectinload(CanvasItem.note))
        .where(CanvasItem.canvas_id == canvas_id)
        .order_by(CanvasItem.created_at)
    )
    items = list(rows.scalars().all())

    if not items:
        return BatchUpdateResponse(items=[])

    # Grid layout — sqrt columns, fixed 250x180 cells with 50px padding.
    cols = max(1, int(math.ceil(math.sqrt(len(items)))))
    cell_w, cell_h = 250.0, 180.0
    pad_x, pad_y = 50.0, 50.0

    for idx, item in enumerate(items):
        row = idx // cols
        col = idx % cols
        item.position_x = pad_x + col * (cell_w + pad_x)
        item.position_y = pad_y + row * (cell_h + pad_y)
        item.version = item.version + 1

    await db.commit()
    for item in items:
        await db.refresh(item)

    return BatchUpdateResponse(items=[_item_to_out(it) for it in items])
