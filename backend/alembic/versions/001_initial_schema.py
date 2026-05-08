"""001 — Initial schema

Creates extensions uuid-ossp and vector (pgvector), then all Phase 1 tables:
  users, notes, tags, note_tags, note_links, daily_summaries.
Includes HNSW index on notes.embedding with m=16, ef_construction=64.

Phase 2 columns (shadow_reader_*, user_vocabulary) are inlined here because
this is a green-field build; they appear in the schema from day one.

Revision ID: 001
Revises: (none)
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # Extensions — B3 resolution: use 'vector' (lowercase), not 'pgvector'.
    # -----------------------------------------------------------------------
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # -----------------------------------------------------------------------
    # users
    # -----------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("shadow_reader_enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column(
            "shadow_reader_disabled_categories",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
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
    )

    # -----------------------------------------------------------------------
    # notes
    # -----------------------------------------------------------------------
    op.create_table(
        "notes",
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
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("raw_transcription", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("category", sa.String(30), nullable=False, server_default="Ideas"),
        sa.Column("audio_url", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("audio_duration_seconds", sa.Float(), nullable=True),
        sa.Column("entities", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("mood", sa.String(30), nullable=True),
        sa.Column("music_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("processing_status", sa.String(20), server_default="raw"),
        # embedding column is added below via raw DDL — pgvector's vector(1536)
        # type isn't natively known to SQLAlchemy DDL, so we add it after create_table.
        sa.Column("sync_status", sa.String(20), server_default="synced"),
        sa.Column("client_id", sa.String(100), nullable=True),
        # Phase 2 — Shadow Reader (inlined per design)
        sa.Column("shadow_reader_questions", postgresql.JSONB(), nullable=True),
        sa.Column("shadow_reader_answer", sa.Text(), nullable=True),
        sa.Column("shadow_reader_status", sa.String(20), server_default="pending"),
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
        # CHECK constraints
        sa.CheckConstraint(
            "source_type IN ('voice','text','image')", name="ck_notes_source_type"
        ),
        sa.CheckConstraint(
            "category IN ('Music','Fitness','Journal','Ideas','Spiritual','Learning')",
            name="ck_notes_category",
        ),
        sa.CheckConstraint(
            "processing_status IN ('raw','transcribed','processed','enriched','failed')",
            name="ck_notes_processing_status",
        ),
        sa.CheckConstraint(
            "sync_status IN ('pending','synced','conflict')",
            name="ck_notes_sync_status",
        ),
        sa.CheckConstraint(
            "shadow_reader_status IN ('pending','asked','answer_pending','answered','dismissed','skipped')",
            name="ck_notes_shadow_reader_status",
        ),
    )

    # Add the embedding column directly as vector(1536) — pgvector's vector type
    # isn't natively known to SQLAlchemy DDL, so it's added here via raw SQL
    # after op.create_table. (SA-M1 cleanup: previously created as TEXT placeholder
    # then dropped + re-added; now done in a single ALTER TABLE statement.)
    op.execute("ALTER TABLE notes ADD COLUMN embedding vector(1536)")

    # Notes indexes
    op.create_index("idx_notes_user_id", "notes", ["user_id"])
    op.create_index("idx_notes_category", "notes", ["user_id", "category"])
    op.create_index(
        "idx_notes_created_at",
        "notes",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_notes_processing", "notes", ["processing_status"])
    op.create_index("idx_notes_sync", "notes", ["sync_status"])
    op.create_index("idx_notes_source", "notes", ["source_type"])
    # HNSW index for pgvector cosine similarity
    op.execute(
        "CREATE INDEX idx_notes_embedding ON notes "
        "USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)"
    )

    # -----------------------------------------------------------------------
    # tags
    # -----------------------------------------------------------------------
    op.create_table(
        "tags",
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
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_auto", sa.Boolean(), server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
    )

    # -----------------------------------------------------------------------
    # note_tags  (association)
    # -----------------------------------------------------------------------
    op.create_table(
        "note_tags",
        sa.Column(
            "note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # -----------------------------------------------------------------------
    # note_links
    # -----------------------------------------------------------------------
    op.create_table(
        "note_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "source_note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("link_type", sa.String(30), server_default="semantic"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("source_note_id", "target_note_id", name="uq_note_links_pair"),
    )
    op.create_index("idx_note_links_source", "note_links", ["source_note_id"])
    op.create_index("idx_note_links_target", "note_links", ["target_note_id"])

    # -----------------------------------------------------------------------
    # daily_summaries
    # -----------------------------------------------------------------------
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
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("user_id", "summary_date", name="uq_daily_summaries_user_date"),
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("daily_summaries")
    op.drop_index("idx_note_links_target", "note_links")
    op.drop_index("idx_note_links_source", "note_links")
    op.drop_table("note_links")
    op.drop_table("note_tags")
    op.drop_table("tags")
    op.execute("DROP INDEX IF EXISTS idx_notes_embedding")
    op.drop_index("idx_notes_source", "notes")
    op.drop_index("idx_notes_sync", "notes")
    op.drop_index("idx_notes_processing", "notes")
    op.drop_index("idx_notes_created_at", "notes")
    op.drop_index("idx_notes_category", "notes")
    op.drop_index("idx_notes_user_id", "notes")
    op.drop_table("notes")
    op.drop_table("users")
    # Note: extensions are left enabled — dropping them could break other DBs on the same server.
