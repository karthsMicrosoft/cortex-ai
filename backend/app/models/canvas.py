"""
SQLAlchemy ORM model for the `canvases` table (Phase 7 Visual Thinking Canvas).

Note: Uses sa.Uuid for SQLite test compatibility; production migrations
use postgresql.UUID via Alembic 012.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Canvas(Base):
    __tablename__ = "canvases"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, default="Untitled Canvas"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    viewport_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    viewport_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    viewport_zoom: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User")  # noqa: F821
    items: Mapped[list["CanvasItem"]] = relationship(  # noqa: F821
        "CanvasItem",
        back_populates="canvas",
        cascade="all, delete-orphan",
    )
    edges: Mapped[list["CanvasEdge"]] = relationship(  # noqa: F821
        "CanvasEdge",
        back_populates="canvas",
        cascade="all, delete-orphan",
    )
