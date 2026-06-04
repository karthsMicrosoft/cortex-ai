from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.note import Note
from app.models.user import User
from scripts import backfill_titles as script


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _mock_openai(title: str = "Generated Title"):
    mock_openai = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = title
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_openai


def test_dry_run_returns_zero_no_db_writes(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session_local = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    email = f"dry_titles_{uuid.uuid4().hex[:8]}@example.com"

    async def seed():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with test_session_local() as db:
            user = User(email=email, password_hash="x", display_name="Dry Titles")
            db.add(user)
            await db.flush()
            db.add(Note(user_id=user.id, content="needs a title", category="Ideas"))
            await db.commit()

    async def fetch_titles():
        async with test_session_local() as db:
            return list((await db.execute(select(Note.title))).scalars().all())

    import app.database as database

    asyncio.run(seed())
    monkeypatch.setattr(database, "SessionLocal", test_session_local)
    mock_openai = _mock_openai()
    monkeypatch.setattr(script, "get_openai_client", lambda: mock_openai)
    try:
        rc = script.main(["--email", email, "--dry-run"])
        titles = asyncio.run(fetch_titles())
    finally:
        asyncio.run(engine.dispose())

    assert rc == 0
    assert titles == [None]
    mock_openai.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_titles_existing_notes(monkeypatch, db_session):
    email = f"titles_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash="x", display_name="Title User")
    db_session.add(user)
    await db_session.flush()
    notes = [
        Note(user_id=user.id, content=f"untitled note {idx}", category="Ideas")
        for idx in range(3)
    ]
    db_session.add_all(notes)
    await db_session.flush()

    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))
    monkeypatch.setattr(script, "get_openai_client", lambda: _mock_openai("Generated Title"))

    rc = await script.backfill(email)

    assert rc == 0
    assert [note.title for note in notes] == ["Generated Title"] * 3


@pytest.mark.asyncio
async def test_backfill_skips_notes_with_existing_title(monkeypatch, db_session):
    email = f"manual_title_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash="x", display_name="Manual Title")
    db_session.add(user)
    await db_session.flush()
    manual = Note(user_id=user.id, content="already titled", category="Ideas", title="Manual")
    untitled = Note(user_id=user.id, content="needs title", category="Ideas")
    db_session.add_all([manual, untitled])
    await db_session.flush()

    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))
    monkeypatch.setattr(script, "get_openai_client", lambda: _mock_openai("Generated Title"))

    rc = await script.backfill(email)

    assert rc == 0
    assert manual.title == "Manual"
    assert untitled.title == "Generated Title"


@pytest.mark.asyncio
async def test_unknown_email_exits_1(monkeypatch, db_session):
    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))

    rc = await script.backfill("missing@example.com")

    assert rc == 1


@pytest.mark.asyncio
async def test_skips_empty_content_notes(monkeypatch, db_session):
    email = f"empty_content_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash="x", display_name="Empty Content")
    db_session.add(user)
    await db_session.flush()
    note = Note(user_id=user.id, content="", category="Ideas")
    db_session.add(note)
    await db_session.flush()

    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))
    mock_openai = _mock_openai("Generated Title")
    monkeypatch.setattr(script, "get_openai_client", lambda: mock_openai)

    rc = await script.backfill(email)

    assert rc == 0
    assert note.title is None
    mock_openai.chat.completions.create.assert_not_called()
