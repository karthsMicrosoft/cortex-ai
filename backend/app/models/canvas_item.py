"""
SQLAlchemy ORM model for `canvas_items` (Phase 7 Visual Thinking Canvas).

`note_id` is nullable + ON DELETE SET NULL so cards survive note deletion
as "ghost cards" — `last_known_title` is snapshotted at insert time so the
UI can still render something for orphaned cards.

`version` powers optimistic concurrency on PATCH / batch updates.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text as sa_text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CanvasItem(Base):
    __tablename__ = "canvas_items"
    __table_args__ = (
        CheckConstraint(
            "item_type IN ('note','group','text')",
            name="ck_canvas_items_item_type",
        ),
        CheckConstraint(
            "width IS NULL OR width > 0",
            name="ck_canvas_items_width_positive",
        ),
        CheckConstraint(
            "height IS NULL OR height > 0",
            name="ck_canvas_items_height_positive",
        ),
        # Partial unique index — a note can appear at most once per canvas.
        Index(
            "uq_canvas_items_canvas_note",
            "canvas_id",
            "note_id",
            unique=True,
            postgresql_where=sa_text("note_id IS NOT NULL"),
            sqlite_where=sa_text("note_id IS NOT NULL"),
        ),
        Index("ix_canvas_items_canvas_id", "canvas_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("canvases.id", ondelete="CASCADE"),
        nullable=False,
    )
    note_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notes.id", ondelete="SET NULL"),
        nullable=True,
    )
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    position_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    width: Mapped[float | None] = mapped_column(Float, nullable=True)
    height: Mapped[float | None] = mapped_column(Float, nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    z_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_known_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    canvas: Mapped["Canvas"] = relationship(  # noqa: F821
        "Canvas", back_populates="items"
    )
    note: Mapped["Note | None"] = relationship("Note")  # noqa: F821
    outgoing_edges: Mapped[list["CanvasEdge"]] = relationship(  # noqa: F821
        "CanvasEdge",
        foreign_keys="CanvasEdge.source_item_id",
        cascade="all, delete-orphan",
        overlaps="source_item",
    )
    incoming_edges: Mapped[list["CanvasEdge"]] = relationship(  # noqa: F821
        "CanvasEdge",
        foreign_keys="CanvasEdge.target_item_id",
        cascade="all, delete-orphan",
        overlaps="target_item",
    )
