from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.note import Note
from app.models.user import User
from app.services.semantic_links import RelinkResult
from scripts import backfill_semantic_links as script


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class _FakeDb:
    def __init__(self, results):
        self._results = list(results)
        self.committed = False

    async def execute(self, _stmt):
        return _ScalarResult(self._results.pop(0))

    async def commit(self):
        self.committed = True


def test_main_exits_0_on_dry_run(monkeypatch, capsys):
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
    email = "dryrun@example.com"

    async def seed_user():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with test_session_local() as db:
            user = User(email=email, password_hash="x", display_name="Dry Run")
            db.add(user)
            await db.flush()
            db.add_all([
                Note(user_id=user.id, content="embedded 1", category="Ideas", embedding="[0.1]"),
                Note(user_id=user.id, content="embedded 2", category="Ideas", embedding="[0.2]"),
                Note(user_id=user.id, content="not embedded", category="Ideas"),
            ])
            await db.commit()

    import app.database as database

    asyncio.run(seed_user())
    monkeypatch.setattr(database, "SessionLocal", test_session_local)

    async def fail_rebuild(*_args, **_kwargs):
        raise AssertionError("dry-run must not rebuild semantic links")

    monkeypatch.setattr(script, "rebuild_user_links", fail_rebuild)
    try:
        rc = script.main(["--email", email, "--dry-run"])
    finally:
        asyncio.run(engine.dispose())

    assert rc == 0
    assert "notes_with_embeddings=2" in capsys.readouterr().out


def test_main_exits_1_on_unknown_email(monkeypatch, capsys):
    fake_db = _FakeDb([None])

    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(fake_db))

    rc = script.main(["--email", "missing@example.com"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "User missing@example.com not found" in captured.err


@pytest.mark.asyncio
async def test_backfill_calls_rebuild_user_links_with_operator_args(
    monkeypatch,
    db_session,
    capsys,
):
    email = f"semantic_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash="x", display_name="Semantic User")
    db_session.add(user)
    await db_session.flush()

    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))

    calls = {}

    async def spy_rebuild_user_links(db, user_id, **kwargs):
        calls["db"] = db
        calls["user_id"] = user_id
        calls["kwargs"] = kwargs
        return RelinkResult(created=3, updated=2, duration_ms=42)

    monkeypatch.setattr(script, "rebuild_user_links", spy_rebuild_user_links)

    rc = await script.backfill(email, limit_notes=7)

    assert rc == 0
    assert calls == {
        "db": db_session,
        "user_id": user.id,
        "kwargs": {"last_relink_window": 0, "limit_notes": 7},
    }
    assert "created=3 updated=2 duration_ms=42" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_backfill_exits_1_when_user_not_found(monkeypatch, db_session, capsys):
    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))

    rc = await script.backfill("absent@example.com")

    captured = capsys.readouterr()
    assert rc == 1
    assert "User absent@example.com not found" in captured.err


@pytest.mark.asyncio
async def test_backfill_dry_run_counts_notes_with_embeddings(
    monkeypatch,
    db_session,
    capsys,
):
    email = f"dry_count_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash="x", display_name="Dry Count")
    db_session.add(user)
    await db_session.flush()
    db_session.add_all([
        Note(user_id=user.id, content="has embedding", category="Ideas", embedding="[0.1]"),
        Note(user_id=user.id, content="missing embedding", category="Ideas"),
    ])
    await db_session.flush()

    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: _SessionContext(db_session))

    async def fail_rebuild(*_args, **_kwargs):
        raise AssertionError("dry-run must not rebuild semantic links")

    monkeypatch.setattr(script, "rebuild_user_links", fail_rebuild)

    rc = await script.backfill(email, dry_run=True)

    assert rc == 0
    assert "notes_with_embeddings=1" in capsys.readouterr().out
