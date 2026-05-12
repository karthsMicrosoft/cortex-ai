"""011 — revoked_jtis

Persistent JWT revocation list. Round 19 / SEC-07 follow-up.

Replaces the in-memory `_revoked_jtis` set in `app.auth.jwt` (which was lost
on every Container App restart) with a Postgres table so that:

  * explicit `/api/auth/logout` revokes survive restarts.
  * refresh-token rotation revocations survive restarts.

Schema:
  jti         VARCHAR(64) PRIMARY KEY
  revoked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
  expires_at  TIMESTAMPTZ NOT NULL  -- copied from the token's `exp` claim;
                                    -- rows past `expires_at` are safe to
                                    -- prune since the JWT signature check
                                    -- would reject them anyway.

Index `idx_revoked_jtis_expires_at` accelerates the prune query.

Revision ID: 011_revoked_jtis (kept short; varchar(32) revision column lesson
from Round 18).
Revises: 010_title_aliases
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa


revision = "011_revoked_jtis"
down_revision = "010_title_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revoked_jtis",
        sa.Column("jti", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_revoked_jtis_expires_at",
        "revoked_jtis",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_revoked_jtis_expires_at", table_name="revoked_jtis")
    op.drop_table("revoked_jtis")
