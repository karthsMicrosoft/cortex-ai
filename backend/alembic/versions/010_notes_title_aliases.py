"""010 — notes.title + notes.aliases

Adds two columns to `notes` to support Phase 6 wiki-style linking:

  - title    VARCHAR(120) NULL          — human-friendly title; backfilled
                                          from summary (or first 60 chars of
                                          content) for existing rows.
  - aliases  TEXT[] NOT NULL DEFAULT {} — alternate names a wiki-link can
                                          resolve to.

Plus a functional index `idx_notes_title_lower` on `lower(title)` for
case-insensitive wiki-link lookup. Postgres-specific; SQLite test fixtures
do not run migrations (they use Base.metadata.create_all), so this is safe.

Revision ID: 010_notes_title_aliases
Revises: 009_note_links_link_type_uniqueness
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "010_title_aliases"
down_revision = "009_links_uq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notes",
        sa.Column("title", sa.String(120), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.execute(
        "UPDATE notes SET title = COALESCE(NULLIF(summary, ''), substring(content, 1, 60)) "
        "WHERE title IS NULL"
    )
    op.create_index(
        "idx_notes_title_lower",
        "notes",
        [sa.text("lower(title)")],
    )


def downgrade() -> None:
    op.drop_index("idx_notes_title_lower", table_name="notes")
    op.drop_column("notes", "aliases")
    op.drop_column("notes", "title")
