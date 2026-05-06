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

# revision identifiers
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # users table — add shadow reader settings columns
    # ------------------------------------------------------------------

    # shadow_reader_enabled
    op.execute(sa.text(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS shadow_reader_enabled BOOLEAN DEFAULT TRUE
        """
    ))

    # shadow_reader_disabled_categories
    op.execute(sa.text(
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
    op.execute(sa.text(
        """
        ALTER TABLE notes
        ADD COLUMN IF NOT EXISTS shadow_reader_questions JSONB DEFAULT NULL
        """
    ))

    # shadow_reader_answer
    op.execute(sa.text(
        """
        ALTER TABLE notes
        ADD COLUMN IF NOT EXISTS shadow_reader_answer TEXT DEFAULT NULL
        """
    ))

    # shadow_reader_status
    op.execute(sa.text(
        """
        ALTER TABLE notes
        ADD COLUMN IF NOT EXISTS shadow_reader_status
            VARCHAR(20) DEFAULT 'pending'
        """
    ))

    # CHECK constraint on shadow_reader_status (add only if missing).
    # 'answer_pending' is included as the intermediate state used while the
    # background merge task runs (QA-04 fix).
    op.execute(sa.text(
        """
        DO $$
        BEGIN
            -- Drop old constraint if it exists (may not include answer_pending)
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_notes_shadow_reader_status'
                  AND conrelid = 'notes'::regclass
            ) THEN
                ALTER TABLE notes DROP CONSTRAINT ck_notes_shadow_reader_status;
            END IF;
            ALTER TABLE notes ADD CONSTRAINT ck_notes_shadow_reader_status
                CHECK (shadow_reader_status IN
                       ('pending','asked','answer_pending','answered','dismissed','skipped'));
        END
        $$
        """
    ))


def downgrade() -> None:
    # Drop CHECK constraint first
    op.execute(sa.text(
        """
        ALTER TABLE notes
        DROP CONSTRAINT IF EXISTS ck_notes_shadow_reader_status
        """
    ))

    # notes columns
    op.execute(sa.text("ALTER TABLE notes DROP COLUMN IF EXISTS shadow_reader_status"))
    op.execute(sa.text("ALTER TABLE notes DROP COLUMN IF EXISTS shadow_reader_answer"))
    op.execute(sa.text("ALTER TABLE notes DROP COLUMN IF EXISTS shadow_reader_questions"))

    # users columns
    op.execute(sa.text(
        "ALTER TABLE users DROP COLUMN IF EXISTS shadow_reader_disabled_categories"
    ))
    op.execute(sa.text(
        "ALTER TABLE users DROP COLUMN IF EXISTS shadow_reader_enabled"
    ))
