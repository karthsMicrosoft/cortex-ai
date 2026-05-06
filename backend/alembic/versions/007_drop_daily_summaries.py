"""007 — Drop daily_summaries table (cron removal)

The daily/weekly distill cron job and the underlying daily_summaries table
have been removed per a user product decision (2026-05-06). The table is
empty in production because SCHEDULER_ENABLED has been false since deploy
(see DECISIONS § 22y), so the drop is non-destructive.

Revision ID: 007
Revises: 006
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("daily_summaries")


def downgrade() -> None:
    op.create_table(
        "daily_summaries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("key_themes", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("note_count", sa.Integer(), server_default="0"),
        sa.Column("mood_summary", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "summary_date", name="uq_daily_summaries_user_date"),
    )
