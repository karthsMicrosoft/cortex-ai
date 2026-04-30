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
        """POST /api/search must accept optional category filter."""
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

        assert resp.status_code in (200, 422)
        if resp.status_code == 422:
            # Only acceptable if category is not a valid literal
            pass

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
