"""
SQLAlchemy ORM model for the `revoked_jtis` table.

Round 19 / SEC-07 follow-up: persists revoked JWT IDs across Container App
restarts so that explicit logout (and refresh-token rotation) survive a
process restart.

Pruning: rows where `expires_at < now()` are safe to delete because the JWT
itself is already past its `exp` claim and would be rejected by the signature
check. Call ``app.auth.jwt.prune_expired_revoked_jtis(db)`` periodically
(future: Container Apps Job).
"""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RevokedJTI(Base):
    __tablename__ = "revoked_jtis"

    # JWT JTI is a uuid4 string (36 chars); reserve up to 64 to allow future
    # token formats (opaque IDs, etc.) without another migration.
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # Original `exp` claim from the token. Pruning walks this column.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
