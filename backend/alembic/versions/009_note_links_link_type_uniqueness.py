"""009 — note_links uniqueness on (source, target, link_type)

Replaces the original `(source_note_id, target_note_id)` uniqueness on
`note_links` (created in migration 001 as `uq_note_links_pair`) with a
triple-uniqueness on `(source_note_id, target_note_id, link_type)`.

This unblocks Phase 6: a manual link, a semantic link, and a wiki link
can all coexist for the same A->B pair, while still preventing duplicates
of the same type.

Revision ID: 009_note_links_link_type_uniqueness
Revises: 008_source_provenance
Create Date: 2026-05-08
"""
from alembic import op


revision = "009_note_links_link_type_uniqueness"
down_revision = "008_source_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_note_links_pair", "note_links", type_="unique")
    op.create_unique_constraint(
        "uq_note_links_triple",
        "note_links",
        ["source_note_id", "target_note_id", "link_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_note_links_triple", "note_links", type_="unique")
    op.create_unique_constraint(
        "uq_note_links_pair",
        "note_links",
        ["source_note_id", "target_note_id"],
    )
