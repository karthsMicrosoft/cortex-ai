"""
SQLAlchemy ORM model for the `notes` table.
Phase 2 shadow reader columns (shadow_reader_questions, shadow_reader_answer,
shadow_reader_status) are inlined per design.

Note: Uses sa.Uuid and sa.JSON for SQLite compatibility in tests.
The Alembic migration uses PostgreSQL-specific types for production.
The embedding column uses pgvector.Vector(1536) when pgvector is available,
falling back to Text for SQLite tests.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# pgvector integration — uses Vector(1536) on Postgres production, falls back
# to Text for SQLite test environments. Selected by inspecting the dialect at
# import time via env var (set by alembic env.py / app.config) — but the
# simplest reliable trigger is presence of pgvector AND a non-SQLite
# DATABASE_URL.
try:
    from pgvector.sqlalchemy import Vector  # type: ignore[import-not-found]
    _HAS_PGVECTOR = True
except ImportError:
    Vector = None  # type: ignore[assignment, misc]
    _HAS_PGVECTOR = False


def _embedding_column_type():  # noqa: ANN202
    """Pick the right SQLAlchemy column type for `embedding`.

    On Postgres (production) the column was created as `vector(1536)` by the
    alembic migration. The ORM model MUST declare it as the same type or
    INSERT statements bind the value as varchar and Postgres rejects with
    `column "embedding" is of type vector but expression is of type
    character varying`.

    On SQLite (test fixture) the column doesn't exist as `vector` — fall
    back to Text so unit tests using an in-memory SQLite DB still load.
    """
    import os
    db_url = os.getenv("DATABASE_URL", "")
    is_postgres = "postgres" in db_url or "asyncpg" in db_url
    if _HAS_PGVECTOR and is_postgres:
        return Vector(1536)
    return Text()


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('voice','text','image')", name="ck_notes_source_type"
        ),
        CheckConstraint(
            "category IN ('Music','Fitness','Journal','Ideas','Spiritual','Learning')",
            name="ck_notes_category",
        ),
        CheckConstraint(
            "processing_status IN ('raw','transcribed','processed','enriched','failed')",
            name="ck_notes_processing_status",
        ),
        CheckConstraint(
            "sync_status IN ('pending','synced','conflict')", name="ck_notes_sync_status"
        ),
        CheckConstraint(
            "shadow_reader_status IN ('pending','asked','answered','dismissed','skipped','answer_pending')",
            name="ck_notes_shadow_reader_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_transcription: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="Ideas")
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    entities: Mapped[list] = mapped_column(JSON, default=list)
    mood: Mapped[str | None] = mapped_column(String(30), nullable=True)
    music_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    processing_status: Mapped[str] = mapped_column(String(20), default="raw")
    # embedding: pgvector Vector(1536) in production, Text stub for SQLite tests.
    # MUST match the actual column type chosen by alembic migration 001 — using
    # Text on Postgres breaks INSERT with `column "embedding" is of type vector
    # but expression is of type character varying` (DatatypeMismatchError).
    embedding: Mapped[object | None] = mapped_column(_embedding_column_type(), nullable=True)  # type: ignore[type-arg]
    sync_status: Mapped[str] = mapped_column(String(20), default="synced")
    client_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Phase 2 — Shadow Reader (inlined per design)
    shadow_reader_questions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    shadow_reader_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    shadow_reader_status: Mapped[str] = mapped_column(String(20), default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notes")  # noqa: F821
    tags: Mapped[list["Tag"]] = relationship(  # noqa: F821
        "Tag", secondary="note_tags", back_populates="notes"
    )
    outgoing_links: Mapped[list["NoteLink"]] = relationship(  # noqa: F821
        "NoteLink",
        foreign_keys="NoteLink.source_note_id",
        back_populates="source_note",
        cascade="all, delete-orphan",
    )
    incoming_links: Mapped[list["NoteLink"]] = relationship(  # noqa: F821
        "NoteLink",
        foreign_keys="NoteLink.target_note_id",
        back_populates="target_note",
        cascade="all, delete-orphan",
    )
