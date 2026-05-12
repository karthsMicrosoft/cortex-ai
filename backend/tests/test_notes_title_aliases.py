"""
test_notes_title_aliases.py — PR 6.0

Verifies that `notes` has new columns `title` (nullable VARCHAR(120)) and
`aliases` (non-nullable list of strings, default []), and that migration 010
backfills `title` from `summary` / `content[:60]` for existing rows.
"""
import uuid
from pathlib import Path

import pytest

from app.models.note import Note
from app.models.user import User

pytestmark_async = pytest.mark.asyncio

BACKEND_DIR = Path(__file__).parent.parent
MIGRATION_010 = BACKEND_DIR / "alembic" / "versions" / "010_notes_title_aliases.py"


async def _make_user(db_session):
    user = User(
        email=f"title_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        display_name="Title Test",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytestmark_async
async def test_create_note_with_title(db_session):
    user = await _make_user(db_session)
    note = Note(user_id=user.id, content="hello", category="Ideas", title="My Note")
    db_session.add(note)
    await db_session.flush()
    assert note.title == "My Note"


@pytestmark_async
async def test_create_note_default_aliases_empty(db_session):
    user = await _make_user(db_session)
    note = Note(user_id=user.id, content="hello", category="Ideas")
    db_session.add(note)
    await db_session.flush()
    assert note.aliases == []


@pytestmark_async
async def test_set_aliases(db_session):
    user = await _make_user(db_session)
    note = Note(
        user_id=user.id, content="hello", category="Ideas", aliases=["foo", "bar"]
    )
    db_session.add(note)
    await db_session.flush()
    await db_session.refresh(note)
    assert list(note.aliases) == ["foo", "bar"]


def test_backfill_populates_title_for_existing_notes():
    """Static introspection: migration 010 must contain the title backfill UPDATE."""
    assert MIGRATION_010.exists(), f"Migration 010 not found: {MIGRATION_010}"
    body = MIGRATION_010.read_text(encoding="utf-8")
    assert "UPDATE notes SET title" in body, (
        "Migration 010 must backfill the title column for existing rows"
    )
    assert "COALESCE" in body, "Backfill must use COALESCE(NULLIF(summary,''), substring(...))"
    assert "summary" in body
    assert "content" in body


def test_migration_010_adds_title_and_aliases_columns():
    assert MIGRATION_010.exists()
    body = MIGRATION_010.read_text(encoding="utf-8")
    assert "add_column" in body
    assert '"notes"' in body or "'notes'" in body
    assert '"title"' in body or "'title'" in body
    assert '"aliases"' in body or "'aliases'" in body
    assert "ARRAY" in body, "aliases must be created as a postgres ARRAY column"


def test_migration_010_creates_lower_title_index():
    assert MIGRATION_010.exists()
    body = MIGRATION_010.read_text(encoding="utf-8")
    assert "idx_notes_title_lower" in body
    assert "lower(title)" in body
