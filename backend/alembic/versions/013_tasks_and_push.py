"""013 — tasks model (due_at, done_at, priority, recurring, reminder_sent_at)
        + push_subscriptions table (Round 35).

Adds task/reminder columns to the existing `notes` table so a note can BE a
task (one URL, one detail page, no joins). A new `push_subscriptions` table
stores per-device Web Push endpoints + VAPID keys so the reminders cron job
can notify subscribed browsers.

Indexes:
  * ix_notes_user_due_at        — drives the Tasks page query (user + window).
  * ix_notes_reminder_pending   — drives the dispatcher: WHERE due_at <= now()
                                  AND reminder_sent_at IS NULL AND done_at IS
                                  NULL. Partial index so the row set stays
                                  tiny even as the notes table grows.
  * ix_push_user                — lookup subscriptions for a user.
  * uq_push_user_endpoint       — endpoints are globally unique per user
                                  (prevents duplicate subscriptions when the
                                  PWA re-subscribes).

Revision ID: 013_tasks_and_push
Revises: 012_canvas_tables
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "013_tasks_and_push"
down_revision = "012_canvas_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------- notes: 5 new columns ----------------
    op.add_column(
        "notes",
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column("priority", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column("recurring", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
    )

    # priority must be 1 (high), 2 (medium), 3 (low), or NULL (no priority).
    op.create_check_constraint(
        "ck_notes_priority",
        "notes",
        "priority IS NULL OR priority IN (1, 2, 3)",
    )

    # recurring is a small enum; NULL means one-shot reminder.
    op.create_check_constraint(
        "ck_notes_recurring",
        "notes",
        "recurring IS NULL OR recurring IN ('daily', 'weekly', 'monthly')",
    )

    # Index for the Tasks page (user + due window scans).
    op.create_index(
        "ix_notes_user_due_at",
        "notes",
        ["user_id", "due_at"],
        postgresql_where=sa.text("due_at IS NOT NULL"),
    )

    # Partial index for the reminders dispatcher hot path.
    op.create_index(
        "ix_notes_reminder_pending",
        "notes",
        ["due_at"],
        postgresql_where=sa.text(
            "due_at IS NOT NULL AND reminder_sent_at IS NULL AND done_at IS NULL"
        ),
    )

    # ---------------- push_subscriptions ----------------
    op.create_table(
        "push_subscriptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Web Push endpoint URL (browser-vendor push service).
        sa.Column("endpoint", sa.Text(), nullable=False),
        # VAPID keys returned by PushManager.subscribe().
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        # Free-form user agent string for operator visibility.
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_push_subscriptions_user",
        "push_subscriptions",
        ["user_id"],
    )
    op.create_unique_constraint(
        "uq_push_subscriptions_user_endpoint",
        "push_subscriptions",
        ["user_id", "endpoint"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_push_subscriptions_user_endpoint",
        "push_subscriptions",
        type_="unique",
    )
    op.drop_index("ix_push_subscriptions_user", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")

    op.drop_index("ix_notes_reminder_pending", table_name="notes")
    op.drop_index("ix_notes_user_due_at", table_name="notes")
    op.drop_constraint("ck_notes_recurring", "notes", type_="check")
    op.drop_constraint("ck_notes_priority", "notes", type_="check")
    op.drop_column("notes", "reminder_sent_at")
    op.drop_column("notes", "recurring")
    op.drop_column("notes", "priority")
    op.drop_column("notes", "done_at")
    op.drop_column("notes", "due_at")
