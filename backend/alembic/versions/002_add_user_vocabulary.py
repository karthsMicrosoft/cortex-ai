"""002 — Add user_vocabulary (Personal Dictionary)

Creates the `user_vocabulary` table with all columns, CHECK constraint on
term_type, UNIQUE constraint on (user_id, term), and two indexes:
  - idx_vocabulary_user  ON user_vocabulary(user_id)
  - idx_vocabulary_type  ON user_vocabulary(user_id, term_type)

Revision ID: 002
Revises: 001
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_vocabulary",
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
        sa.Column("term", sa.String(200), nullable=False),
        sa.Column(
            "term_type",
            sa.String(30),
            nullable=False,
            server_default="general",
        ),
        sa.Column("pronunciation_hint", sa.String(500), nullable=True),
        sa.Column(
            "boost_weight",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column(
            "usage_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        # CHECK constraint on term_type enum values
        sa.CheckConstraint(
            "term_type IN ('name', 'music_term', 'technical', 'place', 'acronym', 'general')",
            name="ck_vocabulary_term_type",
        ),
        # UNIQUE per (user_id, term) — prevents duplicates per user
        sa.UniqueConstraint("user_id", "term", name="uq_vocabulary_user_term"),
    )

    # idx_vocabulary_user — primary lookup by user
    op.create_index("idx_vocabulary_user", "user_vocabulary", ["user_id"])

    # idx_vocabulary_type — lookup by user + type (for filtered list)
    op.create_index("idx_vocabulary_type", "user_vocabulary", ["user_id", "term_type"])


def downgrade() -> None:
    op.drop_index("idx_vocabulary_type", table_name="user_vocabulary")
    op.drop_index("idx_vocabulary_user", table_name="user_vocabulary")
    op.drop_table("user_vocabulary")
