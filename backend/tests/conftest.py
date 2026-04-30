"""
Shared pytest fixtures for cortex-second-brain backend tests.

Uses an in-memory SQLite database via aiosqlite for speed.
Because pgvector is PostgreSQL-only, the Vector column is mocked as Text
in the test models — production migrations run against a real Postgres DB.

For full integration tests (Alembic migration tests), a real Postgres
connection can be used by setting TEST_DATABASE_URL env var.
"""
import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Test database URL — default is SQLite in-memory; override with Postgres
# for migration tests by setting TEST_DATABASE_URL env var.
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "sqlite+aiosqlite:///:memory:",
)

USE_SQLITE = TEST_DATABASE_URL.startswith("sqlite")

# ---------------------------------------------------------------------------
# Engine + session factory
# ---------------------------------------------------------------------------
if USE_SQLITE:
    test_engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
else:
    test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# App import — deferred so tests can still be *collected* even when the app
# package does not yet exist (TDD red phase).
# ---------------------------------------------------------------------------
def _import_app():
    """Import FastAPI app; raise ImportError if not yet implemented."""
    from app.main import app  # noqa: PLC0415
    return app


def _import_base():
    """Import SQLAlchemy declarative Base; raise ImportError if not yet implemented."""
    from app.database import Base  # noqa: PLC0415
    return Base


def _import_get_db():
    """Import get_db dependency."""
    from app.database import get_db  # noqa: PLC0415
    return get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Create all tables once per test session, drop at teardown."""
    try:
        Base = _import_base()
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield test_engine
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    except ImportError:
        # App not yet implemented — yield raw engine so db-agnostic tests still run
        yield test_engine
    finally:
        await test_engine.dispose()


@pytest_asyncio.fixture()
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional session that rolls back after each test."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture()
async def client(db_session: AsyncSession):
    """
    AsyncClient wired to the FastAPI app with the test DB session injected.
    Skips if the app is not yet implemented.
    """
    try:
        app = _import_app()
        get_db = _import_get_db()
    except ImportError as exc:
        pytest.skip(f"App not yet implemented: {exc}")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def registered_user(client: AsyncClient) -> dict:
    """Register a test user and return the response JSON."""
    payload = {
        "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
        "password": "TestPass123!",
        "display_name": "Test User",
    }
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return {"user": resp.json(), "password": payload["password"], "email": payload["email"]}


@pytest_asyncio.fixture()
async def auth_headers(client: AsyncClient, registered_user: dict) -> dict:
    """Register + login a test user; return Bearer auth headers."""
    login_payload = {
        "email": registered_user["email"],
        "password": registered_user["password"],
    }
    resp = await client.post("/api/auth/login", json=login_payload)
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    access_token = data["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture()
async def second_user_headers(client: AsyncClient) -> dict:
    """Register + login a *second* test user; used for ownership tests."""
    email = f"other_{uuid.uuid4().hex[:8]}@example.com"
    reg = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "OtherPass456!", "display_name": "Other User"},
    )
    assert reg.status_code == 201

    login = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "OtherPass456!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
