"""
SQLAlchemy ORM model for the `user_vocabulary` table.

Represents a single term in a user's Personal Dictionary.
Fields per addendum F1.2 verbatim.

Note: Uses sa.Uuid and sa.JSON for SQLite compatibility in tests.
The Alembic migration uses PostgreSQL-specific types for production.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Uuid, UniqueConstraint, func
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

_TERM_TYPES = ("name", "music_term", "technical", "place", "acronym", "general")


class UserVocabulary(Base):
    __tablename__ = "user_vocabulary"
    __table_args__ = (
        UniqueConstraint("user_id", "term", name="uq_user_vocabulary_user_term"),
    )

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
    term: Mapped[str] = mapped_column(String(200), nullable=False)
    term_type: Mapped[str] = mapped_column(String(30), default="general", nullable=False)
    pronunciation_hint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    boost_weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship back to owner (optional — not strictly required for CRUD)
    user: Mapped["User"] = relationship("User", back_populates="vocabulary")  # noqa: F821
