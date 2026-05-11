"""
test_ai_answer.py — Phase 4 / PR 4.1
TDD tests for the RAG endpoint POST /api/ai/answer.

Endpoint contract (see PR description):
- POST /api/ai/answer with {query, max_results?, filters?, prior_messages?}.
- Embeds the query, runs hybrid retrieval (re-using search.py SQL semantics),
  builds a strict GPT-4o-mini prompt with numbered notes, parses citations,
  and returns {answer, citations, model, retrieval_count, elapsed_ms}.
- Per-user 30/hour rate limit. 401 / 400 / 429 / 502 / 503 error contracts.
- prior_messages is accepted but unused in this PR (PR 4.5 will consume it).

Mock strategy:
- Patch `app.api.ai_answer._retrieve_notes` to bypass the pgvector SQL
  (SQLite test DB cannot run hybrid pgvector + ts_rank queries).
- Override the `get_openai` dependency with an AsyncMock chat client.
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_retrieval_row(
    note_id: str | None = None,
    content: str = "Sample note content",
    summary: str | None = None,
    category: str = "Learning",
    combined_score: float = 0.75,
    semantic_score: float = 0.80,
    text_score: float = 0.30,
) -> dict[str, Any]:
    return {
        "note_id": note_id or str(uuid.uuid4()),
        "content": content,
        "summary": summary,
        "category": category,
        "semantic_score": semantic_score,
        "text_score": text_score,
        "combined_score": combined_score,
    }


def _make_openai_mock(content: str) -> AsyncMock:
    """Build an AsyncMock that mimics openai.chat.completions.create."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    mock_openai = AsyncMock()
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_openai


def _override_openai(mock_openai: AsyncMock) -> None:
    """Install the OpenAI dependency override on the FastAPI app."""
    from app.main import app
    from app.services.openai_client import get_openai
    app.dependency_overrides[get_openai] = lambda: mock_openai


def _clear_openai_override() -> None:
    from app.main import app
    from app.services.openai_client import get_openai
    app.dependency_overrides.pop(get_openai, None)


# ---------------------------------------------------------------------------
# Module import / wiring
# ---------------------------------------------------------------------------

class TestAiAnswerModuleWiring:
    @staticmethod
    def test_module_importable():
        import app.api.ai_answer  # noqa: F401

    @staticmethod
    def test_router_registers_answer_route():
        """POST /api/ai/answer must be registered on the FastAPI app."""
        from app.main import app
        paths = {getattr(r, "path", "") for r in app.router.routes}
        assert "/api/ai/answer" in paths, (
            f"/api/ai/answer not registered. Registered paths sample: "
            f"{sorted(p for p in paths if '/ai' in p)}"
        )

    @staticmethod
    def test_schema_module_importable():
        from app.schemas import ai_answer as schema_mod
        assert hasattr(schema_mod, "AnswerRequest")
        assert hasattr(schema_mod, "AnswerResponse")
        assert hasattr(schema_mod, "AnswerCitation")


# ---------------------------------------------------------------------------
# 1. Auth
# ---------------------------------------------------------------------------

class TestAnswerAuth:
    async def test_answer_requires_auth(self, client: AsyncClient):
        """POST /api/ai/answer without Bearer token must return 401."""
        resp = await client.post("/api/ai/answer", json={"query": "anything"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2. No retrieval matches → friendly answer
# ---------------------------------------------------------------------------

class TestAnswerNoMatches:
    async def test_answer_returns_no_match_message_when_zero_notes(
        self, client: AsyncClient, auth_headers: dict
    ):
        """When retrieval returns 0 notes, return 200 + canned friendly answer."""
        mock_openai = _make_openai_mock("(should not be called)")
        _override_openai(mock_openai)
        try:
            with patch(
                "app.api.ai_answer._retrieve_notes",
                new=AsyncMock(return_value=[]),
            ):
                resp = await client.post(
                    "/api/ai/answer",
                    json={"query": "Nothing in my notes matches this"},
                    headers=auth_headers,
                )
        finally:
            _clear_openai_override()

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["answer"] == "I don't have any notes that match this question."
        assert body["citations"] == []
        assert body["retrieval_count"] == 0
        assert "elapsed_ms" in body
        # OpenAI must NOT be called for zero-retrieval case.
        mock_openai.chat.completions.create.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. Happy path
# ---------------------------------------------------------------------------

class TestAnswerHappyPath:
    async def test_happy_path_returns_answer_and_citations(
        self, client: AsyncClient, auth_headers: dict
    ):
        note_id_1 = str(uuid.uuid4())
        note_id_2 = str(uuid.uuid4())
        rows = [
            _make_retrieval_row(
                note_id=note_id_1,
                content="Leadership requires listening intently.",
                category="Learning",
                combined_score=0.91,
            ),
            _make_retrieval_row(
                note_id=note_id_2,
                content="Leading by example matters more than words.",
                category="Learning",
                combined_score=0.83,
            ),
        ]
        answer_text = "Per your notes, leadership is X [1] and Y [2]."
        mock_openai = _make_openai_mock(answer_text)
        _override_openai(mock_openai)

        try:
            with patch(
                "app.api.ai_answer._retrieve_notes",
                new=AsyncMock(return_value=rows),
            ):
                resp = await client.post(
                    "/api/ai/answer",
                    json={"query": "How do I think about leadership?"},
                    headers=auth_headers,
                )
        finally:
            _clear_openai_override()

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["answer"] == answer_text
        assert body["model"] == "gpt-4o-mini"
        assert body["retrieval_count"] == 2
        assert isinstance(body["citations"], list)
        assert len(body["citations"]) == 2
        cit_ids = {c["note_id"] for c in body["citations"]}
        assert cit_ids == {note_id_1, note_id_2}
        for c in body["citations"]:
            assert "title" in c
            assert "snippet" in c
            assert "relevance" in c
            assert isinstance(c["snippet"], str)
            assert len(c["snippet"]) <= 240
        assert "elapsed_ms" in body and body["elapsed_ms"] >= 0


# ---------------------------------------------------------------------------
# 4. Rate limiting — 30/hour per user
# ---------------------------------------------------------------------------

class TestAnswerRateLimit:
    async def test_rate_limit_30_per_hour(
        self, client: AsyncClient, auth_headers: dict
    ):
        """30 successful calls must succeed; the 31st must return 429 with Retry-After."""
        # Use empty retrieval to short-circuit OpenAI and keep the test fast.
        with patch(
            "app.api.ai_answer._retrieve_notes",
            new=AsyncMock(return_value=[]),
        ):
            for i in range(30):
                resp = await client.post(
                    "/api/ai/answer",
                    json={"query": f"call {i}"},
                    headers=auth_headers,
                )
                assert resp.status_code == 200, (
                    f"call #{i + 1} should have succeeded, got {resp.status_code}: {resp.text}"
                )

            resp = await client.post(
                "/api/ai/answer",
                json={"query": "one too many"},
                headers=auth_headers,
            )
            assert resp.status_code == 429, (
                f"31st call should be rate-limited, got {resp.status_code}: {resp.text}"
            )
            # SlowAPI's default rate-limit-exceeded handler adds Retry-After.
            assert "retry-after" in {k.lower() for k in resp.headers.keys()}, (
                f"429 must include Retry-After header, got headers: {dict(resp.headers)}"
            )


# ---------------------------------------------------------------------------
# 5/6/7. Input validation
# ---------------------------------------------------------------------------

class TestAnswerInputValidation:
    async def test_empty_query_is_rejected(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/ai/answer",
            json={"query": ""},
            headers=auth_headers,
        )
        # Either pydantic 422 or our explicit 400 — spec asks for 400.
        assert resp.status_code in (400, 422), resp.text

    async def test_query_over_1000_chars_is_rejected(
        self, client: AsyncClient, auth_headers: dict
    ):
        long_query = "x" * 1001
        resp = await client.post(
            "/api/ai/answer",
            json={"query": long_query},
            headers=auth_headers,
        )
        assert resp.status_code in (400, 422), resp.text

    async def test_max_results_capped_or_rejected(
        self, client: AsyncClient, auth_headers: dict
    ):
        """max_results=100 must either be 422 or silently capped to <=20."""
        captured_max: list[int] = []

        async def fake_retrieve(
            db, openai_client, user_id, query, max_results, filters
        ):  # noqa: ANN001
            captured_max.append(max_results)
            return []

        with patch("app.api.ai_answer._retrieve_notes", new=fake_retrieve):
            resp = await client.post(
                "/api/ai/answer",
                json={"query": "test", "max_results": 100},
                headers=auth_headers,
            )

        if resp.status_code == 422:
            return  # acceptable: rejected outright
        assert resp.status_code == 200, resp.text
        assert captured_max, "retrieval helper should have been called"
        assert captured_max[0] <= 20, (
            f"max_results must be silently capped to <= 20, got {captured_max[0]}"
        )


# ---------------------------------------------------------------------------
# 8. Filters passed through to retrieval helper
# ---------------------------------------------------------------------------

class TestAnswerFiltersForwarded:
    async def test_filters_forwarded_to_retrieval_helper(
        self, client: AsyncClient, auth_headers: dict
    ):
        captured: dict[str, Any] = {}

        async def fake_retrieve(
            db, openai_client, user_id, query, max_results, filters
        ):  # noqa: ANN001
            captured["filters"] = filters
            captured["query"] = query
            captured["max_results"] = max_results
            return []

        with patch("app.api.ai_answer._retrieve_notes", new=fake_retrieve):
            resp = await client.post(
                "/api/ai/answer",
                json={
                    "query": "leadership reflections",
                    "max_results": 5,
                    "filters": {
                        "category": "Learning",
                        "tags": ["leadership"],
                        "since": "2026-01-01",
                        "until": "2026-05-08",
                    },
                },
                headers=auth_headers,
            )

        assert resp.status_code == 200, resp.text
        assert captured["filters"] is not None
        # filters object should expose category attribute (pydantic) or key (dict)
        flt = captured["filters"]
        cat = getattr(flt, "category", None) if not isinstance(flt, dict) else flt.get("category")
        tags = getattr(flt, "tags", None) if not isinstance(flt, dict) else flt.get("tags")
        assert cat == "Learning"
        assert tags == ["leadership"]


# ---------------------------------------------------------------------------
# 9. OpenAI failure → 502 after one retry
# ---------------------------------------------------------------------------

class TestAnswerOpenAIFailure:
    async def test_openai_failure_propagates_as_502(
        self, client: AsyncClient, auth_headers: dict
    ):
        rows = [_make_retrieval_row(content="some content")]
        call_counter = {"n": 0}

        async def boom(*args, **kwargs):  # noqa: ANN001
            call_counter["n"] += 1
            raise RuntimeError("OpenAI is down")

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = boom
        _override_openai(mock_openai)

        try:
            with patch(
                "app.api.ai_answer._retrieve_notes",
                new=AsyncMock(return_value=rows),
            ):
                resp = await client.post(
                    "/api/ai/answer",
                    json={"query": "what does my journal say?"},
                    headers=auth_headers,
                )
        finally:
            _clear_openai_override()

        assert resp.status_code == 502, resp.text
        # Retried at least once → at least 2 invocations.
        assert call_counter["n"] >= 2, (
            f"OpenAI should be retried once after failure; got {call_counter['n']} calls"
        )


# ---------------------------------------------------------------------------
# 10. Null embedding notes never appear in citations
# ---------------------------------------------------------------------------

class TestAnswerExcludesNullEmbeddings:
    @staticmethod
    def test_hybrid_sql_filters_null_embedding():
        """Static contract: the retrieval SQL must include an
        `embedding IS NOT NULL` predicate so notes without embeddings can
        never be returned as citations (matches PR 4.0a guarantee)."""
        from app.api.ai_answer import _HYBRID_SQL_AI
        sql_text = str(_HYBRID_SQL_AI).lower()
        assert "embedding is not null" in sql_text, (
            "Hybrid retrieval SQL must filter notes whose embedding is NULL"
        )


# ---------------------------------------------------------------------------
# 11. Citation relevance == hybrid combined_score
# ---------------------------------------------------------------------------

class TestAnswerCitationRelevance:
    async def test_citation_relevance_uses_combined_score(
        self, client: AsyncClient, auth_headers: dict
    ):
        nid_a = str(uuid.uuid4())
        nid_b = str(uuid.uuid4())
        rows = [
            _make_retrieval_row(note_id=nid_a, combined_score=0.87),
            _make_retrieval_row(note_id=nid_b, combined_score=0.42),
        ]
        mock_openai = _make_openai_mock("Answer body [1][2]")
        _override_openai(mock_openai)

        try:
            with patch(
                "app.api.ai_answer._retrieve_notes",
                new=AsyncMock(return_value=rows),
            ):
                resp = await client.post(
                    "/api/ai/answer",
                    json={"query": "tell me about X"},
                    headers=auth_headers,
                )
        finally:
            _clear_openai_override()

        assert resp.status_code == 200, resp.text
        cits = {c["note_id"]: c["relevance"] for c in resp.json()["citations"]}
        assert cits[nid_a] == pytest.approx(0.87)
        assert cits[nid_b] == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# 12. prior_messages accepted but unused in this PR
# ---------------------------------------------------------------------------

class TestAnswerPriorMessagesUnused:
    async def test_prior_messages_accepted_but_not_passed_to_openai(
        self, client: AsyncClient, auth_headers: dict
    ):
        rows = [_make_retrieval_row(content="some note about x")]
        captured_kwargs: list[dict[str, Any]] = []

        async def fake_create(**kwargs):  # noqa: ANN003
            captured_kwargs.append(kwargs)
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "An answer [1]"
            return mock_response

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = fake_create
        _override_openai(mock_openai)

        try:
            with patch(
                "app.api.ai_answer._retrieve_notes",
                new=AsyncMock(return_value=rows),
            ):
                resp = await client.post(
                    "/api/ai/answer",
                    json={
                        "query": "what did I say about x?",
                        "prior_messages": [
                            {"role": "user", "content": "earlier user message"},
                            {"role": "assistant", "content": "earlier assistant reply"},
                        ],
                    },
                    headers=auth_headers,
                )
        finally:
            _clear_openai_override()

        assert resp.status_code == 200, resp.text
        assert captured_kwargs, "OpenAI should have been called once"
        msgs = captured_kwargs[0]["messages"]
        msg_blob = " ".join(str(m.get("content", "")) for m in msgs)
        assert "earlier user message" not in msg_blob, (
            "prior_messages must NOT be forwarded to OpenAI in this PR"
        )
        assert "earlier assistant reply" not in msg_blob, (
            "prior_messages must NOT be forwarded to OpenAI in this PR"
        )
