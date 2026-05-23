"""
SQLAlchemy ORM model for `canvas_edges` (Phase 7 Visual Thinking Canvas).

Directed connection between two canvas_items. Both endpoints MUST belong
to the same canvas — enforced at the API layer (the DB-level UNIQUE on
(canvas_id, source_item_id, target_item_id) only prevents duplicates).
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CanvasEdge(Base):
    __tablename__ = "canvas_edges"
    __table_args__ = (
        CheckConstraint(
            "style IN ('default','dashed','bold')",
            name="ck_canvas_edges_style",
        ),
        UniqueConstraint(
            "canvas_id",
            "source_item_id",
            "target_item_id",
            name="uq_canvas_edges_triple",
        ),
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
    source_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("canvas_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("canvas_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    style: Mapped[str] = mapped_column(String(20), nullable=False, default="default")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    canvas: Mapped["Canvas"] = relationship(  # noqa: F821
        "Canvas", back_populates="edges"
    )
    source_item: Mapped["CanvasItem"] = relationship(  # noqa: F821
        "CanvasItem", foreign_keys=[source_item_id], overlaps="outgoing_edges"
    )
    target_item: Mapped["CanvasItem"] = relationship(  # noqa: F821
        "CanvasItem", foreign_keys=[target_item_id], overlaps="incoming_edges"
    )
