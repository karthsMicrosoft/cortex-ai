"""008 — Source provenance schema (Phase 5 / PR 5.0)

Adds three nullable columns to `notes` so future PRs can record where
clipped/imported content originated from:

  - source_url        TEXT NULL   — original URL (https://... or blob://...)
  - source_title      TEXT NULL   — extracted title (HTML <title> / PDF meta)
  - source_parent_id  UUID NULL   — self-FK to notes.id; chunked sources
                                    (e.g. PDFs split into multiple notes)
                                    point at the canonical parent.

Plus an index `idx_notes_source_parent` for fast "give me all chunks of this
parent" lookups.

Columns are nullable so existing notes (no provenance) remain valid. No API
or UI uses these yet — they are pure scaffolding for Phase 5.1+ (share
target, URL import, PDF ingestion).

Revision ID: 008_source_provenance
Revises: 007
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "008_source_provenance"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notes",
        sa.Column("source_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column("source_title", sa.Text(), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column(
            "source_parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_notes_source_parent",
        "notes",
        ["source_parent_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_notes_source_parent", table_name="notes")
    op.drop_column("notes", "source_parent_id")
    op.drop_column("notes", "source_title")
    op.drop_column("notes", "source_url")
