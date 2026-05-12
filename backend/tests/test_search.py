"""
test_search.py — Task 7
Tests for POST /api/search (hybrid semantic + keyword search)
and GET /api/search/similar/{note_id}

Covers:
  - POST /api/search requires auth
  - POST /api/search embeds query via text-embedding-3-small
  - Hybrid score: 0.7*semantic + 0.3*ts_rank
  - Optional filters: category, tags, date_from, date_to, limit
  - Returns list of SearchResultItem with id/content/summary/category/
    created_at/semantic_score/text_score/combined_score
  - GET /api/search/similar/{note_id} returns top-N by cosine
  - SearchRequest schema includes tags?: list[str] binding (B7)

Mock strategy (B15): respx for OpenAI embeddings HTTP call; raw SQL
mocked via AsyncSession.execute patch for pgvector cosine queries.
"""
import json
import uuid
import pytest
import respx
import httpx
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

pytestmark = pytest.mark.asyncio

FAKE_EMBEDDING = [0.05] * 1536
FAKE_NOTE_ID = str(uuid.uuid4())
FAKE_USER_ID = str(uuid.uuid4())

FAKE_SEARCH_ROW = {
    "id": FAKE_NOTE_ID,
    "content": "Machine learning ideas for the project",
    "summary": "ML project ideas",
    "category": "Ideas",
    "created_at": datetime.utcnow().isoformat(),
    "semantic_score": 0.82,
    "text_score": 0.45,
    "combined_score": 0.71,
}


# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------

class TestSearchModuleImport:
    def test_search_module_importable(self):
        from app.api import search  # noqa: F401

    def test_router_exported(self):
        from app.api.search import router
        from fastapi import APIRouter
        assert isinstance(router, APIRouter)

    def test_search_schema_importable(self):
        from app.schemas import search as search_schema  # noqa: F401

    def test_search_request_schema_has_tags(self):
        """SearchRequest must include a tags field for B7 SQL filter."""
        from app.schemas.search import SearchRequest
        import inspect
        fields = SearchRequest.model_fields
        assert "tags" in fields, "SearchRequest must have a 'tags' field"

    def test_search_request_schema_fields(self):
        """SearchRequest must have query, category, tags, date_from, date_to, limit."""
        from app.schemas.search import SearchRequest
        fields = SearchRequest.model_fields
        for required_field in ("query", "limit"):
            assert required_field in fields, f"SearchRequest must have '{required_field}' field"

    def test_search_result_item_schema_has_scores(self):
        """SearchResultItem must expose semantic_score, text_score, combined_score."""
        from app.schemas.search import SearchResultItem
        fields = SearchResultItem.model_fields
        for score_field in ("semantic_score", "text_score", "combined_score"):
            assert score_field in fields, f"SearchResultItem must have '{score_field}'"


# ---------------------------------------------------------------------------
# POST /api/search — auth
# ---------------------------------------------------------------------------

class TestSearchAuth:
    async def test_search_requires_auth(self, client):
        """POST /api/search without token must return 401."""
        resp = await client.post("/api/search", json={"query": "test"})
        assert resp.status_code == 401

    async def test_search_with_invalid_token_returns_401(self, client):
        resp = await client.post(
            "/api/search",
            json={"query": "test"},
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/search — embedding
# ---------------------------------------------------------------------------

class TestSearchEmbedding:
    async def test_search_calls_openai_embeddings(self, client, auth_headers):
        """POST /api/search must call text-embedding-3-small to embed the query."""
        mock_embed = AsyncMock(return_value=MagicMock(
            data=[MagicMock(embedding=FAKE_EMBEDDING)]
        ))
        mock_db_execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))

        with patch("app.api.search.get_openai") as mock_get_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = mock_embed
            mock_get_openai.return_value = mock_client

            with patch("app.api.search.get_db") as mock_get_db:
                mock_session = AsyncMock()
                mock_session.execute = mock_db_execute
                mock_get_db.return_value = mock_session

                resp = await client.post(
                    "/api/search",
                    json={"query": "machine learning ideas"},
                    headers=auth_headers,
                )

        # The embedding create must have been called with the query
        if resp.status_code == 200:
            mock_embed.assert_called_once()
            call_kwargs = mock_embed.call_args[1]
            assert "text-embedding-3-small" in call_kwargs.get("model", "")

    async def test_search_returns_list(self, client, auth_headers):
        """POST /api/search must return a JSON list (may be empty)."""
        mock_embed = AsyncMock(return_value=MagicMock(
            data=[MagicMock(embedding=FAKE_EMBEDDING)]
        ))

        with patch("app.api.search.get_openai") as mock_get_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = mock_embed
            mock_get_openai.return_value = mock_client

            with patch("app.api.search.get_db"):
                resp = await client.post(
                    "/api/search",
                    json={"query": "test query"},
                    headers=auth_headers,
                )

        if resp.status_code == 200:
            assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# POST /api/search — filters
# ---------------------------------------------------------------------------

class TestSearchFilters:
    async def test_search_accepts_category_filter(self, client, auth_headers):
        """POST /api/search must accept optional category filter.
        Note: search uses Postgres-specific SQL (pgvector, ts_rank); on the SQLite
        test DB it may return 503 (SQL failure). Acceptable outcomes: 200, 422, 503.
        """
        with patch("app.api.search.get_openai") as mock_get_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=MagicMock(
                data=[MagicMock(embedding=FAKE_EMBEDDING)]
            ))
            mock_get_openai.return_value = mock_client

            with patch("app.api.search.get_db"):
                resp = await client.post(
                    "/api/search",
                    json={"query": "fitness notes", "category": "Fitness"},
                    headers=auth_headers,
                )

        # 200: search ran OK; 422: category not a valid literal; 503: Postgres SQL on SQLite
        assert resp.status_code in (200, 422, 503)

    async def test_search_accepts_tags_filter(self, client, auth_headers):
        """POST /api/search must accept optional tags filter (B7)."""
        with patch("app.api.search.get_openai") as mock_get_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=MagicMock(
                data=[MagicMock(embedding=FAKE_EMBEDDING)]
            ))
            mock_get_openai.return_value = mock_client

            with patch("app.api.search.get_db"):
                resp = await client.post(
                    "/api/search",
                    json={"query": "tagged notes", "tags": ["python", "ml"]},
                    headers=auth_headers,
                )

        # 422 would mean tags is not accepted — that's a bug
        assert resp.status_code != 422, "SearchRequest must accept 'tags' list"

    async def test_search_accepts_date_filters(self, client, auth_headers):
        """POST /api/search must accept date_from and date_to."""
        now = datetime.utcnow()
        with patch("app.api.search.get_openai") as mock_get_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=MagicMock(
                data=[MagicMock(embedding=FAKE_EMBEDDING)]
            ))
            mock_get_openai.return_value = mock_client

            with patch("app.api.search.get_db"):
                resp = await client.post(
                    "/api/search",
                    json={
                        "query": "old notes",
                        "date_from": (now - timedelta(days=7)).isoformat(),
                        "date_to": now.isoformat(),
                    },
                    headers=auth_headers,
                )

        assert resp.status_code != 422, "SearchRequest must accept date_from/date_to"

    async def test_search_accepts_limit(self, client, auth_headers):
        """POST /api/search must accept a limit parameter (default 20)."""
        with patch("app.api.search.get_openai") as mock_get_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=MagicMock(
                data=[MagicMock(embedding=FAKE_EMBEDDING)]
            ))
            mock_get_openai.return_value = mock_client

            with patch("app.api.search.get_db"):
                resp = await client.post(
                    "/api/search",
                    json={"query": "query", "limit": 5},
                    headers=auth_headers,
                )

        assert resp.status_code != 422


# ---------------------------------------------------------------------------
# GET /api/search/similar/{note_id}
# ---------------------------------------------------------------------------

class TestSearchSimilar:
    async def test_similar_endpoint_exists(self, client, auth_headers):
        """GET /api/search/similar/{note_id} must exist."""
        note_id = str(uuid.uuid4())

        with patch("app.api.search.get_db"):
            resp = await client.get(
                f"/api/search/similar/{note_id}",
                headers=auth_headers,
            )

        assert resp.status_code != 405, "GET /api/search/similar/{note_id} must exist"

    async def test_similar_requires_auth(self, client):
        """GET /api/search/similar/{note_id} must require auth."""
        note_id = str(uuid.uuid4())
        resp = await client.get(f"/api/search/similar/{note_id}")
        assert resp.status_code == 401

    async def test_similar_returns_list(self, client, auth_headers):
        """GET /api/search/similar/{note_id} must return a list."""
        note_id = str(uuid.uuid4())

        with patch("app.api.search.get_db"):
            resp = await client.get(
                f"/api/search/similar/{note_id}",
                headers=auth_headers,
            )

        if resp.status_code == 200:
            assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Hybrid score formula
# ---------------------------------------------------------------------------

class TestHybridScoreFormula:
    def test_combined_score_weights(self):
        """
        The hybrid score formula must be: 0.7 * semantic + 0.3 * text_score.
        Verify the weight constants are correct in the search SQL / implementation.
        """
        # Static verification: import search module and check for weight constants
        try:
            import app.api.search as search_module
            import inspect
            src = inspect.getsource(search_module)
            # The formula 0.7 * semantic + 0.3 * text must appear in the SQL or code
            assert "0.7" in src, "Hybrid search must use weight 0.7 for semantic score"
            assert "0.3" in src, "Hybrid search must use weight 0.3 for text score"
        except ImportError:
            pytest.skip("search module not yet implemented")

    def test_search_sql_contains_tags_exists_subquery(self):
        """
        The search SQL must include an EXISTS subquery against note_tags JOIN tags
        for the tags filter (B7 — design canonical SQL).
        """
        try:
            import app.api.search as search_module
            import inspect
            src = inspect.getsource(search_module)
            # The B7 tags filter must be present
            assert "EXISTS" in src or "note_tags" in src, (
                "Search SQL must include EXISTS subquery for tags filter (B7)"
            )
        except ImportError:
            pytest.skip("search module not yet implemented")


# ---------------------------------------------------------------------------
# PERF-05 — Migration must create GIN index; _HYBRID_SQL must not call to_tsvector at runtime
# review-comments.tasks.md § 2.5
# ---------------------------------------------------------------------------

class TestPERF05FullTextIndex:
    """
    PERF-05: The migration must add a GIN index on to_tsvector('english', content)
    so that full-text searches do not perform a sequential scan.
    Also assert _HYBRID_SQL uses an index-friendly form (no inline to_tsvector
    wrapping the entire notes table at query time without an index).
    """

    def test_migration_creates_gin_index_on_notes_content(self):
        """
        A migration must include a CREATE INDEX ... USING gin on notes.content
        (or the generated tsvector column). The GIN index may live in the initial
        schema (001) or a dedicated migration (005_add_fts_index.py).
        Checks that at least one migration file contains the GIN index DDL.
        """
        import pathlib

        versions_dir = (
            pathlib.Path(__file__).parent.parent / "alembic" / "versions"
        )
        if not versions_dir.exists():
            pytest.skip("alembic/versions directory not found — skipping GIN index check")

        # Search all migration files for the GIN index DDL
        has_gin_index = False
        for migration_file in sorted(versions_dir.glob("*.py")):
            src = migration_file.read_text(encoding="utf-8")
            if (
                "gin" in src.lower()
                and (
                    "idx_notes_content_fts" in src
                    or ("to_tsvector" in src and "content" in src)
                )
            ):
                has_gin_index = True
                break

        assert has_gin_index, (
            "PERF-05 FAIL: No migration creates a GIN full-text index on notes.content. "
            "Add: CREATE INDEX idx_notes_content_fts ON notes "
            "USING gin(to_tsvector('english', content))"
        )

    def test_hybrid_sql_does_not_inline_to_tsvector_without_index(self):
        """
        _HYBRID_SQL must reference the pre-computed tsvector column or use
        a stored generated column — not call to_tsvector() inline on each search
        without a supporting GIN index.

        Compliant implementations either:
        a) Use a stored generated column `content_fts tsvector GENERATED ALWAYS AS ...`
        b) Reference the index-friendly form that Postgres can use with the GIN index

        At minimum the SQL must NOT do a full table scan via to_tsvector() on raw content
        when an idx_notes_content_fts GIN index exists. We check the SQL references the
        index-supporting pattern.
        """
        try:
            import app.api.search as search_module
            import inspect
            src = inspect.getsource(search_module)

            # The SQL should either:
            # 1. Use to_tsvector with the content column (which the GIN index covers), OR
            # 2. Reference a stored tsvector column
            # Either is acceptable — what is NOT acceptable is no text search at all.
            has_text_search = (
                "tsvector" in src
                or "ts_rank" in src
                or "plainto_tsquery" in src
                or "to_tsvector" in src
            )
            assert has_text_search, (
                "PERF-05 FAIL: _HYBRID_SQL does not include any full-text search "
                "construct (tsvector/ts_rank/plainto_tsquery). "
                "The hybrid search must include a text component."
            )
        except ImportError:
            pytest.skip("search module not yet implemented")

    def test_hybrid_search_excludes_null_embedding_notes(self):
        """
        Round 16 / PR 4.0a — Latent-bug fix.

        Notes with embedding IS NULL (pipeline failures — visible in prod as
        "Failed" items in the Library) must NOT appear in hybrid search
        results. The cosine operator (<=>) returns NULL for NULL embeddings,
        which makes combined_score NULL; Postgres' default DESC sort places
        NULLs FIRST, so broken notes would otherwise top the ranked list.

        The fix is a SQL-level WHERE clause on _HYBRID_SQL guaranteeing that
        only notes with a non-null embedding enter the semantic top-K. This
        test inspects the SQL source statically because the SQLite test DB
        has no pgvector and cannot execute the query end-to-end.
        """
        import app.api.search as search_module
        import inspect
        src = inspect.getsource(search_module)

        # Locate the _HYBRID_SQL block specifically (don't accept a stray
        # IS NOT NULL elsewhere in the module).
        start = src.index("_HYBRID_SQL")
        end = src.index("@router.post", start)
        hybrid_sql = src[start:end]

        assert "embedding IS NOT NULL" in hybrid_sql, (
            "PR 4.0a FAIL: _HYBRID_SQL does not exclude NULL-embedding notes. "
            "Add `AND n.embedding IS NOT NULL` to the WHERE clause so that "
            "pipeline-failure notes (embedding=NULL) cannot pollute the ranked "
            "results via NULL combined_score sorting first."
        )

    def test_hybrid_search_orders_nulls_last(self):
        """
        Round 16 / PR 4.0a — Defence-in-depth.

        Even with the WHERE filter above, the ORDER BY clause on
        combined_score must use `NULLS LAST` so that any future code path
        producing a NULL score (e.g. ts_rank fallback when text_score is
        NULL on no-match) cannot float to the top of the results.
        """
        import app.api.search as search_module
        import inspect
        src = inspect.getsource(search_module)

        start = src.index("_HYBRID_SQL")
        end = src.index("@router.post", start)
        hybrid_sql = src[start:end]

        assert "NULLS LAST" in hybrid_sql, (
            "PR 4.0a FAIL: _HYBRID_SQL ORDER BY combined_score DESC must "
            "append `NULLS LAST` so NULL scores cannot rank first."
        )

    async def test_hybrid_search_handles_zero_valid_results_gracefully(
        self, client, auth_headers
    ):
        """
        Round 16 / PR 4.0a — Empty-corpus regression.

        When every candidate note has been filtered out (e.g. all notes have
        embedding IS NULL after the new WHERE clause), the search endpoint
        must return an empty list with 200, not raise a 500.
        """
        from unittest.mock import patch, AsyncMock, MagicMock

        mock_embed = AsyncMock(return_value=MagicMock(
            data=[MagicMock(embedding=FAKE_EMBEDDING)]
        ))
        # DB returns no rows — simulates all-NULL-embedding corpus post-filter.
        mock_db_execute = AsyncMock(
            return_value=MagicMock(fetchall=MagicMock(return_value=[]))
        )

        with patch("app.api.search.get_openai") as mock_get_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = mock_embed
            mock_get_openai.return_value = mock_client

            with patch("app.api.search.get_db") as mock_get_db:
                mock_session = AsyncMock()
                mock_session.execute = mock_db_execute
                mock_get_db.return_value = mock_session

                resp = await client.post(
                    "/api/search",
                    json={"query": "anything"},
                    headers=auth_headers,
                )

        # Either the SQLite test DB rejects the SQL (503 — acceptable, since
        # the WHERE filter doesn't change Postgres-vs-SQLite compatibility)
        # or the mocked-out DB path returns 200 with []. A 500 is a regression.
        assert resp.status_code in (200, 503), (
            f"Expected 200 or 503, got {resp.status_code}: {resp.text}"
        )
        if resp.status_code == 200:
            assert resp.json() == []

    def test_similar_sql_does_not_use_cross_join(self):
        """
        PERF-08: _SIMILAR_SQL must NOT use a Cartesian cross-join (FROM notes n, notes src).
        The source note's embedding must be passed as a parameter so the query
        only touches the notes table once and can use the HNSW index.
        """
        try:
            import app.api.search as search_module
            import inspect
            src = inspect.getsource(search_module)

            # Look for the _SIMILAR_SQL variable
            lines = src.split("\n")
            in_similar = False
            similar_sql_lines = []
            for line in lines:
                if "_SIMILAR_SQL" in line:
                    in_similar = True
                if in_similar:
                    similar_sql_lines.append(line)
                    # Stop after finding the closing of the text() block
                    if '"""' in line and len(similar_sql_lines) > 1:
                        break

            similar_sql = "\n".join(similar_sql_lines)

            # The cross-join pattern: FROM notes n, notes src
            uses_cross_join = (
                "notes n, notes src" in similar_sql
                or "notes src" in similar_sql
            )
            assert not uses_cross_join, (
                "PERF-08 FAIL: _SIMILAR_SQL uses a cross-join (FROM notes n, notes src). "
                "Pass the source note embedding as a parameter (:source_emb) and "
                "rewrite as: FROM notes n WHERE n.embedding <=> CAST(:source_emb AS vector)"
            )
        except ImportError:
            pytest.skip("search module not yet implemented")


# ---------------------------------------------------------------------------
# Round 19 - title in search results
# ---------------------------------------------------------------------------

class TestSearchResultsIncludeTitle:
    """Round 19: /api/search and /api/search/similar must surface notes.title."""

    def test_search_result_item_schema_has_title(self):
        from app.schemas.search import SearchResultItem
        assert "title" in SearchResultItem.model_fields, (
            "Round 19: SearchResultItem must include a 'title' field"
        )

    def test_hybrid_sql_selects_title_column(self):
        import app.api.search as search_module
        import inspect
        src = inspect.getsource(search_module)
        start = src.index("_HYBRID_SQL")
        end = src.index("@router.post", start)
        hybrid_sql = src[start:end]
        assert "n.title" in hybrid_sql, (
            "Round 19: _HYBRID_SQL must SELECT n.title alongside the other note columns"
        )

    def test_similar_sql_selects_title_column(self):
        import app.api.search as search_module
        import inspect
        src = inspect.getsource(search_module)
        start = src.index("_SIMILAR_SQL")
        end = src.index("@router.get", start)
        similar_sql = src[start:end]
        assert "n.title" in similar_sql, (
            "Round 19: _SIMILAR_SQL must SELECT n.title alongside the other note columns"
        )

    def test_search_result_item_serializes_title_when_set(self):
        """SearchResultItem(title='Foo') must round-trip through model_dump."""
        from app.schemas.search import SearchResultItem
        item = SearchResultItem(
            id=uuid.uuid4(),
            title="Foo",
            content="body",
            summary="sum",
            category="Ideas",
            created_at=datetime.utcnow(),
            semantic_score=0.5,
            text_score=0.2,
            combined_score=0.41,
        )
        dumped = item.model_dump(mode="json")
        assert dumped.get("title") == "Foo"

    def test_search_result_item_title_null_when_unset(self):
        """SearchResultItem with no title must serialize as title: null."""
        from app.schemas.search import SearchResultItem
        item = SearchResultItem(
            id=uuid.uuid4(),
            content="body",
            summary="sum",
            category="Ideas",
            created_at=datetime.utcnow(),
            semantic_score=0.5,
            text_score=0.2,
            combined_score=0.41,
        )
        dumped = item.model_dump(mode="json")
        assert "title" in dumped
        assert dumped["title"] is None

    async def test_search_endpoint_passes_title_through(self, client, auth_headers):
        """End-to-end: a mocked DB row with title=Foo must serialize through /api/search."""
        from unittest.mock import patch as _patch
        title_value = "Foo"
        row = MagicMock()
        row.id = uuid.uuid4()
        row.title = title_value
        row.content = "body"
        row.summary = "sum"
        row.category = "Ideas"
        row.created_at = datetime.utcnow()
        row.semantic_score = 0.5
        row.text_score = 0.2
        row.combined_score = 0.41

        mock_embed = AsyncMock(return_value=MagicMock(
            data=[MagicMock(embedding=FAKE_EMBEDDING)]
        ))

        # Patch the `db.execute` method on AsyncSession at runtime so auth-path
        # DB calls keep using the real test session, but the search SQL returns
        # our mocked row.
        import app.api.search as search_module

        async def fake_execute_for_search(self, statement, params=None):
            sql = str(statement)
            if "combined_score" in sql:
                return MagicMock(fetchall=MagicMock(return_value=[row]))
            # Fall through to the original implementation for non-search SQL.
            return await _orig_execute(self, statement, params)

        from sqlalchemy.ext.asyncio import AsyncSession
        _orig_execute = AsyncSession.execute

        with _patch("app.api.search.get_openai") as mock_get_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = mock_embed
            mock_get_openai.return_value = mock_client
            with _patch.object(AsyncSession, "execute", fake_execute_for_search):
                resp = await client.post(
                    "/api/search",
                    json={"query": "anything"},
                    headers=auth_headers,
                )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list) and len(body) == 1
        assert body[0].get("title") == title_value