"""
Phase 5 / PR 5.0 — Source provenance schema (notes.source_url / source_title /
source_parent_id).

These tests verify the new ORM fields round-trip cleanly through SQLAlchemy
on the SQLite test fixture. The columns are scaffolding only — no API or UI
uses them yet (Phase 5.2+ adds clipping/import).
"""
import uuid

import pytest
from sqlalchemy import select


pytestmark = pytest.mark.asyncio


async def _make_user(db_session):
    from app.models.user import User

    user = User(
        email=f"prov_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x" * 60,
        display_name="Provenance Test",
    )
    db_session.add(user)
    await db_session.flush()
    return user


class TestNoteSourceProvenance:
    async def test_note_with_source_url_and_title_round_trips(self, db_session):
        from app.models.note import Note

        user = await _make_user(db_session)
        note = Note(
            user_id=user.id,
            content="Clipped article body.",
            source_type="text",
            source_url="https://example.com/article",
            source_title="Example Article",
            source_parent_id=None,
        )
        db_session.add(note)
        await db_session.flush()
        await db_session.refresh(note)

        assert note.source_url == "https://example.com/article"
        assert note.source_title == "Example Article"
        assert note.source_parent_id is None

    async def test_note_default_provenance_is_null(self, db_session):
        """Existing-style notes (no provenance) keep working — fields default None."""
        from app.models.note import Note

        user = await _make_user(db_session)
        note = Note(user_id=user.id, content="Plain note.", source_type="text")
        db_session.add(note)
        await db_session.flush()
        await db_session.refresh(note)

        assert note.source_url is None
        assert note.source_title is None
        assert note.source_parent_id is None

    async def test_chunk_note_self_references_parent(self, db_session):
        """source_parent_id self-FK persists and resolves to the parent note."""
        from app.models.note import Note

        user = await _make_user(db_session)
        parent = Note(
            user_id=user.id,
            content="PDF body — full doc",
            source_type="text",
            source_url="blob://cortexks-blob/pdfs/abc.pdf",
            source_title="ABC PDF",
        )
        db_session.add(parent)
        await db_session.flush()

        chunk = Note(
            user_id=user.id,
            content="Chunk 1 of PDF",
            source_type="text",
            source_url="blob://cortexks-blob/pdfs/abc.pdf",
            source_title="ABC PDF",
            source_parent_id=parent.id,
        )
        db_session.add(chunk)
        await db_session.flush()
        await db_session.refresh(chunk)

        assert chunk.source_parent_id == parent.id

        # Look it up fresh to confirm the FK persisted
        result = await db_session.execute(
            select(Note).where(Note.id == chunk.id)
        )
        fetched = result.scalar_one()
        assert fetched.source_parent_id == parent.id
