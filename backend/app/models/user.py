"""
SQLAlchemy ORM model for the `users` table.
Phase 2 columns (shadow_reader_enabled, shadow_reader_disabled_categories) are inlined
per the design decision to build from a green-field schema.

Note: Uses sa.Uuid and sa.JSON for SQLite compatibility in tests.
The Alembic migration uses PostgreSQL-specific types for production.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Phase 2 — Shadow Reader settings (inlined for new builds per design)
    shadow_reader_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    shadow_reader_disabled_categories: Mapped[list] = mapped_column(
        JSON, default=list
    )

    # PERF-04 — Patterns cache (avoids on-demand GPT call on every page visit)
    patterns_cached_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    patterns_cached_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    notes: Mapped[list["Note"]] = relationship(  # noqa: F821
        "Note", back_populates="user", cascade="all, delete-orphan"
    )
    tags: Mapped[list["Tag"]] = relationship(  # noqa: F821
        "Tag", back_populates="user", cascade="all, delete-orphan"
    )
    daily_summaries: Mapped[list["DailySummary"]] = relationship(  # noqa: F821
        "DailySummary", back_populates="user", cascade="all, delete-orphan"
    )
    vocabulary: Mapped[list["UserVocabulary"]] = relationship(  # noqa: F821
        "UserVocabulary", back_populates="user", cascade="all, delete-orphan"
    )
