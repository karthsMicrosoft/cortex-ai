"""
Tombstone table for deleted notes — enables sync pull to propagate deletions
to other browsers (Bug 19).

When a note is hard-deleted, a NoteDeletion row is inserted in the same
transaction so that GET /api/sync/pull can query `deleted_at >= since` and
return a populated `deletions` list instead of always [].
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    """Return current UTC time. Used as Python-side default for deleted_at so
    the value is timezone-aware in both Postgres and SQLite test environments
    (server_default=func.now() returns a naive string in SQLite, which breaks
    timezone-aware comparisons in sync pull)."""
    return datetime.now(tz=timezone.utc)


class NoteDeletion(Base):
    __tablename__ = "note_deletions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        comment="Mirrors the original note.id so the client can identify which note was deleted.",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
