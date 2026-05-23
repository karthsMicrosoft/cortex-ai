"""012 — canvas tables (Phase 7 Visual Thinking Canvas)

Adds three tables to back the Visual Thinking Canvas feature:
  * canvases       — top-level board owned by a user; stores viewport.
  * canvas_items   — placed objects on the board (note / group / text);
                     `note_id` is nullable so cards survive note deletion
                     ("ghost cards" via `last_known_title`). Carries a
                     `version` column for optimistic concurrency.
  * canvas_edges   — directed connection between two canvas_items; both
                     endpoints must belong to the same canvas
                     (enforced at the API layer; the (canvas_id, source,
                     target) UNIQUE prevents duplicates).

Revision ID: 012_canvas_tables
Revises: 011_revoked_jtis
Create Date: 2026-05-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "012_canvas_tables"
down_revision = "011_revoked_jtis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------- canvases ----------------
    op.create_table(
        "canvases",
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
        sa.Column(
            "title",
            sa.String(length=200),
            nullable=False,
            server_default=sa.text("'Untitled Canvas'"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("viewport_x", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("viewport_y", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "viewport_zoom", sa.Float(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_canvases_user_updated",
        "canvases",
        ["user_id", sa.text("updated_at DESC")],
    )

    # ---------------- canvas_items ----------------
    op.create_table(
        "canvas_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "canvas_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canvases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column(
            "position_x", sa.Float(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "position_y", sa.Float(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("width", sa.Float(), nullable=True),
        sa.Column("height", sa.Float(), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("z_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "version", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("last_known_title", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "item_type IN ('note','group','text')",
            name="ck_canvas_items_item_type",
        ),
        sa.CheckConstraint(
            "width IS NULL OR width > 0",
            name="ck_canvas_items_width_positive",
        ),
        sa.CheckConstraint(
            "height IS NULL OR height > 0",
            name="ck_canvas_items_height_positive",
        ),
    )
    op.create_index(
        "ix_canvas_items_canvas_id", "canvas_items", ["canvas_id"]
    )
    # Partial unique index: a given note can appear at most once per canvas.
    op.create_index(
        "uq_canvas_items_canvas_note",
        "canvas_items",
        ["canvas_id", "note_id"],
        unique=True,
        postgresql_where=sa.text("note_id IS NOT NULL"),
    )

    # ---------------- canvas_edges ----------------
    op.create_table(
        "canvas_edges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "canvas_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canvases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canvas_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canvas_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column(
            "style",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'default'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "style IN ('default','dashed','bold')",
            name="ck_canvas_edges_style",
        ),
        sa.UniqueConstraint(
            "canvas_id",
            "source_item_id",
            "target_item_id",
            name="uq_canvas_edges_triple",
        ),
    )
    op.create_index(
        "ix_canvas_edges_canvas_id", "canvas_edges", ["canvas_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_canvas_edges_canvas_id", table_name="canvas_edges")
    op.drop_table("canvas_edges")
    op.drop_index("uq_canvas_items_canvas_note", table_name="canvas_items")
    op.drop_index("ix_canvas_items_canvas_id", table_name="canvas_items")
    op.drop_table("canvas_items")
    op.drop_index("ix_canvases_user_updated", table_name="canvases")
    op.drop_table("canvases")
