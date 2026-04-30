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
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notes_content_fts
        ON notes USING gin(to_tsvector('english', content))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notes_content_fts")
