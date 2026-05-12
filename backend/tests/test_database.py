"""
Task 2 + Task 3 — Database engine, session, and Alembic migration tests.

Covers:
  - app.database exposes engine, SessionLocal, Base, get_db()  (Task 2.4)
  - Alembic migration 001_initial_schema runs forward (upgrade head) and
    backward (downgrade base) cleanly  (Task 3.6)
  - pgvector extension uses CREATE EXTENSION IF NOT EXISTS vector (lowercase) — B3 resolution
  - uuid-ossp extension present in migration

NOTE: Migration tests require a real Postgres database.  They are skipped when
TEST_DATABASE_URL is not set or points to SQLite.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Task 2.4 — database module interface tests
# ---------------------------------------------------------------------------

class TestDatabaseModule:
    """app.database must expose the expected symbols."""

    def test_database_module_importable(self):
        """app.database must be importable."""
        try:
            import app.database  # noqa: F401
        except ImportError as exc:
            pytest.fail(f"app.database is not importable: {exc}")

    def test_engine_exported(self):
        """app.database must export 'engine'."""
        try:
            from app.database import engine  # noqa: F401
        except ImportError as exc:
            pytest.fail(f"app.database.engine not found: {exc}")

    def test_session_local_exported(self):
        """app.database must export 'SessionLocal'."""
        try:
            from app.database import SessionLocal  # noqa: F401
        except ImportError as exc:
            pytest.fail(f"app.database.SessionLocal not found: {exc}")

    def test_base_exported(self):
        """app.database must export 'Base' (declarative base)."""
        try:
            from app.database import Base  # noqa: F401
        except ImportError as exc:
            pytest.fail(f"app.database.Base not found: {exc}")

    def test_get_db_exported(self):
        """app.database must export 'get_db' FastAPI dependency."""
        try:
            from app.database import get_db  # noqa: F401
        except ImportError as exc:
            pytest.fail(f"app.database.get_db not found: {exc}")

    def test_engine_is_async(self):
        """engine must be an async engine (AsyncEngine)."""
        try:
            from app.database import engine
            from sqlalchemy.ext.asyncio import AsyncEngine
            assert isinstance(engine, AsyncEngine), (
                f"engine must be AsyncEngine, got {type(engine)}"
            )
        except ImportError as exc:
            pytest.skip(f"app.database not yet implemented: {exc}")

    def test_session_local_produces_async_session(self):
        """SessionLocal() must return an AsyncSession (or async_sessionmaker)."""
        try:
            from app.database import SessionLocal
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
            # async_sessionmaker is callable; check it's the right type
            assert callable(SessionLocal), "SessionLocal must be callable"
        except ImportError as exc:
            pytest.skip(f"app.database not yet implemented: {exc}")

    @pytest.mark.asyncio
    async def test_get_db_is_async_generator(self):
        """get_db must be an async generator yielding AsyncSession."""
        try:
            from app.database import get_db, SessionLocal
            import inspect
            assert inspect.isasyncgenfunction(get_db), (
                "get_db must be an async generator function"
            )
        except ImportError as exc:
            pytest.skip(f"app.database not yet implemented: {exc}")

    def test_engine_uses_asyncpg_dialect(self):
        """engine.url must use postgresql+asyncpg driver (production config)."""
        try:
            from app.database import engine
            dialect = engine.url.drivername
            # In test env the URL may be overridden — only check production default
            database_url = os.getenv("DATABASE_URL", "")
            if database_url:
                assert "asyncpg" in dialect, (
                    f"Production engine must use asyncpg driver, got: {dialect}"
                )
        except ImportError as exc:
            pytest.skip(f"app.database not yet implemented: {exc}")


# ---------------------------------------------------------------------------
# Task 3 — Alembic migration tests
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).parent.parent
MIGRATION_FILE = BACKEND_DIR / "alembic" / "versions" / "001_initial_schema.py"
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "")
SKIP_MIGRATION = not TEST_DB_URL or TEST_DB_URL.startswith("sqlite")


class TestAlembicMigrationFile:
    """Static analysis of the migration file — runs without a DB."""

    def test_migration_file_exists(self):
        """001_initial_schema.py must exist."""
        assert MIGRATION_FILE.exists(), (
            f"Migration file not found: {MIGRATION_FILE}"
        )

    def test_migration_has_upgrade_function(self):
        """Migration must define an upgrade() function."""
        if not MIGRATION_FILE.exists():
            pytest.skip("Migration file not yet created")
        content = MIGRATION_FILE.read_text(encoding="utf-8")
        assert "def upgrade()" in content, (
            "upgrade() function missing from migration"
        )

    def test_migration_has_downgrade_function(self):
        """Migration must define a downgrade() function."""
        if not MIGRATION_FILE.exists():
            pytest.skip("Migration file not yet created")
        content = MIGRATION_FILE.read_text(encoding="utf-8")
        assert "def downgrade()" in content, (
            "downgrade() function missing from migration"
        )

    def test_vector_extension_lowercase(self):
        """
        pgvector extension must be created as 'vector' (lowercase, no quotes).
        B3 resolution: Azure uses 'vector', NOT 'pgvector'.
        """
        if not MIGRATION_FILE.exists():
            pytest.skip("Migration file not yet created")
        content = MIGRATION_FILE.read_text(encoding="utf-8")
        # Must contain: CREATE EXTENSION IF NOT EXISTS vector
        pattern = r"CREATE EXTENSION IF NOT EXISTS vector"
        assert re.search(pattern, content, re.IGNORECASE), (
            "Migration must contain 'CREATE EXTENSION IF NOT EXISTS vector' (lowercase, no quotes). "
            "Azure Database for PostgreSQL uses 'vector', not 'pgvector' — OQ-9 / B3 resolution."
        )

    def test_uuid_ossp_extension_present(self):
        """uuid-ossp extension must be created in migration."""
        if not MIGRATION_FILE.exists():
            pytest.skip("Migration file not yet created")
        content = MIGRATION_FILE.read_text(encoding="utf-8")
        assert "uuid-ossp" in content, (
            "Migration must create the 'uuid-ossp' extension"
        )

    def test_hnsw_index_present(self):
        """HNSW index on notes.embedding must be defined in migration."""
        if not MIGRATION_FILE.exists():
            pytest.skip("Migration file not yet created")
        content = MIGRATION_FILE.read_text(encoding="utf-8")
        assert "hnsw" in content.lower(), (
            "Migration must define an HNSW index on notes.embedding"
        )
        assert "vector_cosine_ops" in content, (
            "HNSW index must use vector_cosine_ops operator class"
        )

    def test_all_required_tables_in_migration(self):
        """All required tables must be mentioned in the migration."""
        if not MIGRATION_FILE.exists():
            pytest.skip("Migration file not yet created")
        content = MIGRATION_FILE.read_text(encoding="utf-8")
        required_tables = [
            "users", "notes", "tags", "note_tags",
            "note_links", "daily_summaries",
        ]
        for table in required_tables:
            assert table in content, (
                f"Table '{table}' not found in migration 001_initial_schema"
            )

    def test_downgrade_drops_tables(self):
        """downgrade() must contain drop statements for created tables."""
        if not MIGRATION_FILE.exists():
            pytest.skip("Migration file not yet created")
        content = MIGRATION_FILE.read_text(encoding="utf-8")
        assert "drop_table" in content or "DROP TABLE" in content, (
            "downgrade() must drop tables"
        )

    def test_no_embedding_placeholder_dance_in_001(self):
        """SA-M1 cleanup (Round 14): migration 001 must NOT use the
        placeholder-then-drop+re-add pattern for notes.embedding. It must
        declare the vector column directly via
        op.execute('ALTER TABLE notes ADD COLUMN embedding vector(1536)')
        without a preceding DROP and without a sa.Column("embedding") placeholder.
        """
        if not MIGRATION_FILE.exists():
            pytest.skip("Migration file not yet created")
        content = MIGRATION_FILE.read_text(encoding="utf-8")
        assert 'sa.Column("embedding"' not in content, (
            "SA-M1: notes.embedding placeholder column still present in op.create_table. "
            "Remove the sa.Text() placeholder and rely on the raw ALTER TABLE ADD COLUMN."
        )
        assert "DROP COLUMN embedding" not in content, (
            "SA-M1: ALTER TABLE notes DROP COLUMN embedding still present. "
            "Removing the placeholder makes the DROP unnecessary."
        )
        add_count = len(re.findall(r"ADD COLUMN embedding vector\(1536\)", content))
        assert add_count == 1, (
            f"SA-M1: expected exactly 1 ADD COLUMN embedding vector(1536); got {add_count}."
        )

    def test_hnsw_index_still_present_after_001(self):
        """SA-M1 regression guard: cleanup must not remove the HNSW index
        on notes.embedding."""
        if not MIGRATION_FILE.exists():
            pytest.skip("Migration file not yet created")
        content = MIGRATION_FILE.read_text(encoding="utf-8")
        assert "idx_notes_embedding" in content, (
            "SA-M1 regression: HNSW index name idx_notes_embedding missing"
        )
        assert "hnsw" in content.lower(), (
            "SA-M1 regression: HNSW index DDL missing"
        )
        assert "vector_cosine_ops" in content, (
            "SA-M1 regression: vector_cosine_ops operator class missing from HNSW index"
        )

    # ------------------------------------------------------------------
    # Migration 008 — source provenance schema (Phase 5 / PR 5.0)
    # ------------------------------------------------------------------
    def test_migration_008_source_provenance_exists(self):
        """008_source_provenance.py must exist and add the 3 provenance cols."""
        path = BACKEND_DIR / "alembic" / "versions" / "008_source_provenance.py"
        assert path.exists(), f"Migration file not found: {path}"
        body = path.read_text(encoding="utf-8")
        for col in ("source_url", "source_title", "source_parent_id"):
            assert col in body, f"Migration 008 missing column reference: {col}"
        assert "def upgrade()" in body
        assert "def downgrade()" in body

    def test_migration_008_creates_index(self):
        """008 must create idx_notes_source_parent via op.create_index."""
        path = BACKEND_DIR / "alembic" / "versions" / "008_source_provenance.py"
        if not path.exists():
            pytest.skip("Migration 008 not yet created")
        body = path.read_text(encoding="utf-8")
        assert "idx_notes_source_parent" in body, (
            "Migration 008 must create idx_notes_source_parent"
        )
        assert "create_index" in body, (
            "Migration 008 must use op.create_index for idx_notes_source_parent"
        )

    def test_migration_008_downgrade_drops_columns(self):
        """008 downgrade() must drop all 3 provenance columns + the index."""
        path = BACKEND_DIR / "alembic" / "versions" / "008_source_provenance.py"
        if not path.exists():
            pytest.skip("Migration 008 not yet created")
        body = path.read_text(encoding="utf-8")
        # Slice from 'def downgrade' to end of file
        idx = body.find("def downgrade()")
        assert idx >= 0, "downgrade() not defined"
        downgrade_body = body[idx:]
        for col in ("source_url", "source_title", "source_parent_id"):
            assert col in downgrade_body, (
                f"downgrade() must reference column: {col}"
            )
        assert "drop_column" in downgrade_body, (
            "downgrade() must use op.drop_column"
        )

    # ------------------------------------------------------------------
    # Migration 009 — note_links uniqueness on (source, target, link_type)
    # ------------------------------------------------------------------
    def test_migration_009_exists_and_drops_old_uq(self):
        """009 must drop uq_note_links_pair and create the triple-uniqueness."""
        path = BACKEND_DIR / "alembic" / "versions" / "009_note_links_link_type_uniqueness.py"
        assert path.exists(), f"Migration 009 not found: {path}"
        body = path.read_text(encoding="utf-8")
        assert "def upgrade()" in body
        assert "def downgrade()" in body
        assert 'down_revision = "008_source_provenance"' in body
        assert "uq_note_links_pair" in body, (
            "Migration 009 must reference the existing uq_note_links_pair constraint"
        )
        assert "drop_constraint" in body, (
            "Migration 009 upgrade() must drop the old uniqueness constraint"
        )
        assert "link_type" in body
        assert "create_unique_constraint" in body, (
            "Migration 009 upgrade() must create the new unique constraint"
        )

    # ------------------------------------------------------------------
    # Migration 010 — notes.title + notes.aliases
    # ------------------------------------------------------------------
    def test_migration_010_exists_and_adds_title_aliases(self):
        """010 must add title (VARCHAR(120)) + aliases (ARRAY(Text)) and backfill title."""
        path = BACKEND_DIR / "alembic" / "versions" / "010_notes_title_aliases.py"
        assert path.exists(), f"Migration 010 not found: {path}"
        body = path.read_text(encoding="utf-8")
        assert "def upgrade()" in body
        assert "def downgrade()" in body
        assert 'down_revision = "009_note_links_link_type_uniqueness"' in body
        assert "title" in body and "aliases" in body
        assert "ARRAY" in body
        assert "UPDATE notes SET title" in body
        assert "idx_notes_title_lower" in body


@pytest.mark.skipif(
    SKIP_MIGRATION,
    reason="Requires real Postgres; set TEST_DATABASE_URL to a non-SQLite DB URL",
)
class TestAlembicMigrationRuns:
    """Run alembic upgrade/downgrade against a real Postgres DB."""

    def _run_alembic(self, *args) -> subprocess.CompletedProcess:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            capture_output=True,
            text=True,
            cwd=str(BACKEND_DIR),
            env={**os.environ, "DATABASE_URL": TEST_DB_URL},
        )
        return result

    def test_alembic_upgrade_head(self):
        """alembic upgrade head must complete without errors."""
        result = self._run_alembic("upgrade", "head")
        assert result.returncode == 0, (
            f"alembic upgrade head failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

    def test_alembic_downgrade_base(self):
        """alembic downgrade base must complete without errors."""
        result = self._run_alembic("downgrade", "base")
        assert result.returncode == 0, (
            f"alembic downgrade base failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

    def test_alembic_upgrade_idempotent(self):
        """Running upgrade head twice must not error (idempotent)."""
        self._run_alembic("upgrade", "head")  # first run (may already be done)
        result = self._run_alembic("upgrade", "head")  # second run
        assert result.returncode == 0, (
            f"Second alembic upgrade head failed:\n{result.stderr}"
        )
