"""005 — Add GIN full-text search index on notes.content

Creates a GIN index on to_tsvector('english', content) so that the hybrid
search query in _HYBRID_SQL can use an index scan instead of a sequential
full-text scan over all user notes (PERF-05 fix).

  idx_notes_content_fts  GIN  to_tsvector('english', content)

Revision ID: 005
Revises: 004
Create Date: 2026-04-30
"""
from alembic import op

# revision identifiers
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CONCURRENTLY removed: alembic wraps each migration in a transaction by default
    # and Postgres prohibits CONCURRENTLY inside a transaction block. For a fresh DB
    # the brief lock during a non-concurrent build is fine; for production schema
    # changes against a live notes table, run this as a separate manual operation
    # outside the alembic upgrade or set `transaction_per_migration=False` in env.py.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notes_content_fts
        ON notes USING gin(to_tsvector('english', content))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notes_content_fts")
