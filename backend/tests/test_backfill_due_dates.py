"""Tests for scripts/backfill_due_dates.py (Round 35).

Pattern mirrors tests/test_backfill_titles.py — uses the `db_session` fixture
and monkey-patches ``app.database.SessionLocal`` so the script picks up the
in-memory test session.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.note import Note
from app.models.user import User
from scripts import backfill_due_dates as script


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_unknown_email_exits_1(monkeypatch, db_session):
    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))

    rc = await script.backfill("missing@example.com")

    assert rc == 1


@pytest.mark.asyncio
async def test_dry_run_does_not_write(monkeypatch, db_session):
    email = f"dry_due_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash="x", display_name="Dry Due")
    db_session.add(user)
    await db_session.flush()
    note = Note(user_id=user.id, content="Call mom by tonight", category="Ideas")
    db_session.add(note)
    await db_session.flush()
    original_due_at = note.due_at  # None

    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))

    rc = await script.backfill(email, dry_run=True)

    assert rc == 0
    assert note.due_at == original_due_at


@pytest.mark.asyncio
async def test_backfill_skips_notes_with_existing_due_at(monkeypatch, db_session):
    email = f"existing_due_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash="x", display_name="Existing Due")
    db_session.add(user)
    await db_session.flush()

    fixed_due = datetime(2026, 7, 15, 17, 0, tzinfo=timezone.utc)
    note = Note(
        user_id=user.id,
        content="Submit report by tomorrow",
        category="Ideas",
        due_at=fixed_due,
    )
    db_session.add(note)
    await db_session.flush()

    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))

    rc = await script.backfill(email, dry_run=False)

    assert rc == 0
    await db_session.refresh(note)
    # SQLite returns naive datetimes on refresh — compare as naive UTC.
    assert note.due_at.replace(tzinfo=None) == fixed_due.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_backfill_fills_regex_matches(monkeypatch, db_session):
    email = f"regex_fill_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash="x", display_name="Regex Fill")
    db_session.add(user)
    await db_session.flush()

    note = Note(
        user_id=user.id,
        content="Submit expense report by tomorrow",
        category="Ideas",
    )
    db_session.add(note)
    await db_session.flush()

    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))

    rc = await script.backfill(email, dry_run=False, tz="UTC")

    assert rc == 0
    await db_session.refresh(note)
    assert note.due_at is not None
    # SQLite returns naive datetimes — compare as naive.
    naive_due = note.due_at.replace(tzinfo=None) if note.due_at.tzinfo else note.due_at
    assert naive_due > datetime.utcnow()


@pytest.mark.asyncio
async def test_backfill_skips_empty_content(monkeypatch, db_session):
    email = f"empty_due_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash="x", display_name="Empty Due")
    db_session.add(user)
    await db_session.flush()
    note = Note(user_id=user.id, content="", category="Ideas")
    db_session.add(note)
    await db_session.flush()

    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))

    rc = await script.backfill(email, dry_run=False)

    assert rc == 0
    # SQL select filters Note.content != "", so this note was never processed.
    assert note.due_at is None


@pytest.mark.asyncio
async def test_backfill_extracts_priority_and_recurring(monkeypatch, db_session):
    email = f"combined_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash="x", display_name="Combined")
    db_session.add(user)
    await db_session.flush()
    note = Note(
        user_id=user.id,
        content="Pay rent by tomorrow #high #monthly",
        category="Ideas",
    )
    db_session.add(note)
    await db_session.flush()

    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))

    rc = await script.backfill(email, dry_run=False, tz="UTC")

    assert rc == 0
    await db_session.refresh(note)
    assert note.due_at is not None
    assert note.priority == 1
    assert note.recurring == "monthly"
