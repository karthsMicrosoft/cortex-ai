"""004 — Add patterns cache columns to users

Adds two columns to the `users` table for caching the GET /api/insights/patterns
GPT response so it is regenerated at most once per 24 h (PERF-04 fix).

  patterns_cached_json  TEXT       — JSON string of the last patterns response
  patterns_cached_at    TIMESTAMPTZ — UTC timestamp of the last cache fill

Revision ID: 004
Revises: 003
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS patterns_cached_json TEXT DEFAULT NULL
        """
    ))
    op.execute(sa.text(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS patterns_cached_at TIMESTAMPTZ DEFAULT NULL
        """
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE users DROP COLUMN IF EXISTS patterns_cached_at"
    ))
    op.execute(sa.text(
        "ALTER TABLE users DROP COLUMN IF EXISTS patterns_cached_json"
    ))
