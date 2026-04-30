"""003 — Add shadow reader columns

Adds shadow reader columns to `users` and `notes` tables for deployments that
ran the initial schema WITHOUT the Phase 2 columns inlined.

For green-field installs where 001 already includes these columns, the
`IF NOT EXISTS` guards in the raw SQL make this a safe no-op.

Revision ID: 003
Revises: 002
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # users table — add shadow reader settings columns
    # ------------------------------------------------------------------
    conn = op.get_bind()

    # shadow_reader_enabled
    conn.execute(sa.text(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS shadow_reader_enabled BOOLEAN DEFAULT TRUE
        """
    ))

    # shadow_reader_disabled_categories
    conn.execute(sa.text(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS shadow_reader_disabled_categories
            JSONB DEFAULT '[]'::jsonb
        """
    ))

    # ------------------------------------------------------------------
    # notes table — add shadow reader state columns
    # ------------------------------------------------------------------

    # shadow_reader_questions
    conn.execute(sa.text(
        """
        ALTER TABLE notes
        ADD COLUMN IF NOT EXISTS shadow_reader_questions JSONB DEFAULT NULL
        """
    ))

    # shadow_reader_answer
    conn.execute(sa.text(
        """
        ALTER TABLE notes
        ADD COLUMN IF NOT EXISTS shadow_reader_answer TEXT DEFAULT NULL
        """
    ))

    # shadow_reader_status
    conn.execute(sa.text(
        """
        ALTER TABLE notes
        ADD COLUMN IF NOT EXISTS shadow_reader_status
            VARCHAR(20) DEFAULT 'pending'
        """
    ))

    # CHECK constraint on shadow_reader_status (add only if missing)
    conn.execute(sa.text(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_notes_shadow_reader_status'
                  AND conrelid = 'notes'::regclass
            ) THEN
                ALTER TABLE notes ADD CONSTRAINT ck_notes_shadow_reader_status
                    CHECK (shadow_reader_status IN
                           ('pending','asked','answered','dismissed','skipped'));
            END IF;
        END
        $$
        """
    ))


def downgrade() -> None:
    conn = op.get_bind()

    # Drop CHECK constraint first
    conn.execute(sa.text(
        """
        ALTER TABLE notes
        DROP CONSTRAINT IF EXISTS ck_notes_shadow_reader_status
        """
    ))

    # notes columns
    conn.execute(sa.text("ALTER TABLE notes DROP COLUMN IF EXISTS shadow_reader_status"))
    conn.execute(sa.text("ALTER TABLE notes DROP COLUMN IF EXISTS shadow_reader_answer"))
    conn.execute(sa.text("ALTER TABLE notes DROP COLUMN IF EXISTS shadow_reader_questions"))

    # users columns
    conn.execute(sa.text(
        "ALTER TABLE users DROP COLUMN IF EXISTS shadow_reader_disabled_categories"
    ))
    conn.execute(sa.text(
        "ALTER TABLE users DROP COLUMN IF EXISTS shadow_reader_enabled"
    ))
