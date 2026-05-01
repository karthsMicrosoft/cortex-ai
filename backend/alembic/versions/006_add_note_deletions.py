"""006 — Add note_deletions tombstone table (Bug 19)

Creates the note_deletions table so that DELETE /api/notes/{id} can write a
tombstone row and GET /api/sync/pull can propagate deletions to other browsers
via the `deletions` array instead of always returning [].

Schema:
  note_deletions (
    id          uuid        PK  -- mirrors the deleted note's id
    user_id     uuid        FK -> users(id) ON DELETE CASCADE
    deleted_at  timestamptz DEFAULT now()
  )
  INDEX idx_note_deletions_user_deleted ON note_deletions(user_id, deleted_at)

Revision ID: 006
Revises: 005
Create Date: 2026-05-01
"""
import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "note_deletions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_note_deletions_user_deleted",
        "note_deletions",
        ["user_id", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_note_deletions_user_deleted", table_name="note_deletions")
    op.drop_table("note_deletions")
