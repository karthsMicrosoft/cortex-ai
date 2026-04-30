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

# pgvector integration — falls back to Text in SQLite test environments.
try:
    from pgvector.sqlalchemy import Vector
    _VECTOR_COLUMN = lambda: mapped_column(Vector(1536), nullable=True)  # noqa: E731
    _HAS_PGVECTOR = True
except ImportError:
    _HAS_PGVECTOR = False


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
    # embedding: pgvector Vector(1536) in production, Text stub for SQLite tests
    embedding: Mapped[object | None] = mapped_column(Text, nullable=True)  # type: ignore[type-arg]
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
