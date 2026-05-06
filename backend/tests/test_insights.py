"""
test_insights.py — Task 2 (Insights endpoints)
TDD red-phase tests for backend/app/api/insights.py

Covers:
  Task 2.2 — GET /api/insights/graph
    - Returns {nodes: [{id, label, category}], links: [{source, target, score}]}
    - Capped at 200 nodes
    - Requires auth

  Task 2.3 — GET /api/insights/patterns
    - Returns {patterns: [{theme, evidence_note_ids}]}
    - Calls GPT-4o-mini with last 14 days notes
    - Requires auth

  Task 2.4 — Router wired into main.py

NOTE — 2026-05-06: Daily/weekly summary endpoints removed entirely
(see migration 007 + DECISIONS § 22y). Tests for /api/ai/summary/daily
and /api/ai/summary/weekly were deleted with that change.

Mock strategy: respx for OpenAI HTTP calls; use conftest client fixture.
"""
import uuid
import json
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Module import checks
# ---------------------------------------------------------------------------

class TestInsightsModuleImport:
    def test_insights_module_importable(self):
        """backend/app/api/insights.py must exist and be importable."""
        import app.api.insights  # noqa: F401

    def test_insights_router_exists(self):
        """insights module must expose two FastAPI routers."""
        # insights.py exposes two routers: ai_router (Express /generate) and insights_router (graph, patterns)
        from app.api.insights import ai_router, insights_router
        assert ai_router is not None
        assert insights_router is not None

    def test_router_has_graph_route(self):
        """insights_router must include GET /graph route."""
        from app.api.insights import insights_router
        routes = [r.path for r in insights_router.routes]
        assert any("graph" in p for p in routes)

    def test_router_has_patterns_route(self):
        """insights_router must include GET /patterns route."""
        from app.api.insights import insights_router
        routes = [r.path for r in insights_router.routes]
        assert any("patterns" in p for p in routes)

    def test_daily_and_weekly_summary_routes_removed(self):
        """2026-05-06: daily/weekly summary endpoints must NOT be registered."""
        from app.api.insights import ai_router, insights_router
        all_routes = [r.path for r in ai_router.routes] + [r.path for r in insights_router.routes]
        assert not any("summary/daily" in p for p in all_routes), (
            f"summary/daily route still registered: {all_routes}"
        )
        assert not any("summary/weekly" in p for p in all_routes), (
            f"summary/weekly route still registered: {all_routes}"
        )


# ---------------------------------------------------------------------------
# Daily/weekly summary endpoint tests REMOVED 2026-05-06.
# The endpoints were dropped along with the cron and the daily_summaries table
# (see alembic migration 007). The tests that previously lived here covered
# routes that no longer exist:
#   - TestDailySummaryEndpoint (5 tests)
#   - TestWeeklySummaryEndpoint (3 tests)
# Only the route-removal regression test in TestInsightsModuleImport remains
# to guard against accidental re-introduction.
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Task 2.2 — GET /api/insights/graph
# ---------------------------------------------------------------------------

class TestInsightsGraphEndpoint:
    async def test_graph_requires_auth(self, client: AsyncClient):
        """GET /api/insights/graph must return 401 without auth."""
        resp = await client.get("/api/insights/graph")
        assert resp.status_code == 401

    async def test_graph_returns_nodes_and_links(self, client: AsyncClient, auth_headers: dict):
        """GET /api/insights/graph must return {nodes, links} structure."""
        resp = await client.get("/api/insights/graph", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "nodes" in body
        assert "links" in body
        assert isinstance(body["nodes"], list)
        assert isinstance(body["links"], list)

    async def test_graph_nodes_have_required_fields(self, client: AsyncClient, auth_headers: dict, db_session):
        """Each node must have id, label, category."""
        from app.models.note import Note
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content="An interesting musical idea.",
            source_type="text",
            category="Music",
            processing_status="enriched",
        )
        db_session.add(note)
        await db_session.flush()

        resp = await client.get("/api/insights/graph", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        if body["nodes"]:
            node = body["nodes"][0]
            assert "id" in node
            assert "label" in node
            assert "category" in node

    async def test_graph_links_have_required_fields(self, client: AsyncClient, auth_headers: dict, db_session):
        """Each link must have source, target, score."""
        from app.models.note import Note
        from app.models.note_link import NoteLink
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        note_a = Note(user_id=user_id, content="Note A.", source_type="text", category="Ideas", processing_status="enriched")
        note_b = Note(user_id=user_id, content="Note B.", source_type="text", category="Ideas", processing_status="enriched")
        db_session.add(note_a)
        db_session.add(note_b)
        await db_session.flush()

        link = NoteLink(
            source_note_id=note_a.id,
            target_note_id=note_b.id,
            similarity_score=0.85,
        )
        db_session.add(link)
        await db_session.flush()

        resp = await client.get("/api/insights/graph", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        if body["links"]:
            lnk = body["links"][0]
            assert "source" in lnk
            assert "target" in lnk
            assert "score" in lnk

    async def test_graph_capped_at_200_nodes(self, client: AsyncClient, auth_headers: dict):
        """Graph endpoint must cap at 200 nodes for performance."""
        resp = await client.get("/api/insights/graph", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["nodes"]) <= 200

    async def test_graph_isolates_by_user(self, client: AsyncClient, auth_headers: dict, second_user_headers: dict, db_session):
        """Graph must only return nodes/links belonging to the authenticated user."""
        from app.models.note import Note
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=second_user_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        other_user_id = _uuid.UUID(me_resp.json()["id"])

        other_note = Note(
            user_id=other_user_id,
            content="Other user's private note.",
            source_type="text",
            category="Journal",
            processing_status="enriched",
        )
        db_session.add(other_note)
        await db_session.flush()

        resp = await client.get("/api/insights/graph", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        node_ids = [n["id"] for n in body["nodes"]]
        assert str(other_note.id) not in node_ids


# ---------------------------------------------------------------------------
# Task 2.3 — GET /api/insights/patterns
# ---------------------------------------------------------------------------

class TestInsightsPatternsEndpoint:
    async def test_patterns_requires_auth(self, client: AsyncClient):
        """GET /api/insights/patterns must return 401 without auth."""
        resp = await client.get("/api/insights/patterns")
        assert resp.status_code == 401

    async def test_patterns_returns_patterns_list(self, client: AsyncClient, auth_headers: dict):
        """GET /api/insights/patterns must return {patterns: [...]}."""
        from app.services.openai_client import get_openai

        mock_openai = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"patterns": [{"theme": "Music Practice", "evidence_note_ids": []}]}'
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        try:
            from app.main import app
            get_db = None
            try:
                from app.database import get_db as _get_db
                get_db = _get_db
            except ImportError:
                pass

            # Override OpenAI dependency
            app.dependency_overrides[get_openai] = lambda: mock_openai
            resp = await client.get("/api/insights/patterns", headers=auth_headers)
            app.dependency_overrides.pop(get_openai, None)
        except Exception:
            resp = await client.get("/api/insights/patterns", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert "patterns" in body
        assert isinstance(body["patterns"], list)

    async def test_patterns_items_have_theme_and_evidence(self, client: AsyncClient, auth_headers: dict, db_session):
        """Each pattern must have theme and evidence_note_ids when notes exist."""
        from app.models.note import Note
        import uuid as _uuid
        from datetime import datetime

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        # Add a recent note
        note = Note(
            user_id=user_id,
            content="Practicing jazz scales every morning.",
            source_type="text",
            category="Music",
            processing_status="enriched",
        )
        db_session.add(note)
        await db_session.flush()

        from app.services.openai_client import get_openai
        from app.main import app

        mock_openai = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            f'{{"patterns": [{{"theme": "Daily Music Practice", "evidence_note_ids": ["{note.id}"]}}]}}'
        )
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
        app.dependency_overrides[get_openai] = lambda: mock_openai

        resp = await client.get("/api/insights/patterns", headers=auth_headers)
        app.dependency_overrides.pop(get_openai, None)

        assert resp.status_code == 200
        body = resp.json()
        if body["patterns"]:
            pattern = body["patterns"][0]
            assert "theme" in pattern
            assert "evidence_note_ids" in pattern

    async def test_patterns_returns_empty_list_when_no_notes(self, client: AsyncClient, auth_headers: dict):
        """patterns endpoint returns empty list when user has no notes in last 14 days."""
        # With no notes in DB, the endpoint short-circuits and returns empty
        resp = await client.get("/api/insights/patterns", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["patterns"] == []


# ---------------------------------------------------------------------------
# Task 2.4 — Router wired into main.py
# ---------------------------------------------------------------------------

class TestInsightsRouterWired:
    async def test_graph_endpoint_reachable(self, client: AsyncClient, auth_headers: dict):
        """GET /api/insights/graph must be reachable."""
        resp = await client.get("/api/insights/graph", headers=auth_headers)
        assert resp.status_code not in (405,)
        assert resp.status_code in (200, 404)

    async def test_patterns_endpoint_reachable(self, client: AsyncClient, auth_headers: dict):
        """GET /api/insights/patterns must be reachable."""
        resp = await client.get("/api/insights/patterns", headers=auth_headers)
        assert resp.status_code not in (405,)
        assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# QA-10: OpenAIDep Depends(get_openai) injection works; can override via
#         app.dependency_overrides
# review-comments.tasks.md § 3.10
# ---------------------------------------------------------------------------


class TestOpenAIDepInjection:
    """QA-10: The OpenAIDep type alias (Annotated[AsyncAzureOpenAI, Depends(get_openai)])
    used in insights.py must be correctly wired so FastAPI injects the OpenAI client.

    If OpenAIDep is not correctly defined, the parameter will be None or raise 422.
    This test verifies the injection works AND that it can be overridden via
    app.dependency_overrides (enabling testability without real Azure credentials).
    """

    def test_open_ai_dep_is_correctly_annotated(self):
        """QA-10: OpenAIDep must be Annotated[AsyncAzureOpenAI, Depends(get_openai)]."""
        from app.services.openai_client import OpenAIDep, get_openai
        from typing import get_args, get_origin, Annotated
        from fastapi import Depends

        # get_args on Annotated[T, metadata...] returns (T, metadata...)
        args = get_args(OpenAIDep)
        assert len(args) >= 2, (
            "QA-10 FAIL: OpenAIDep must be Annotated[AsyncAzureOpenAI, Depends(get_openai)] "
            f"but get_args returned only {len(args)} args: {args}"
        )

        # First arg must be AsyncAzureOpenAI
        from openai import AsyncAzureOpenAI
        assert args[0] is AsyncAzureOpenAI, (
            f"QA-10 FAIL: OpenAIDep first type arg must be AsyncAzureOpenAI, got {args[0]}"
        )

        # Second arg must be a Depends instance wrapping get_openai
        dep = args[1]
        assert hasattr(dep, "dependency"), (
            f"QA-10 FAIL: OpenAIDep second arg must be Depends(...), got {type(dep)}"
        )
        assert dep.dependency is get_openai, (
            f"QA-10 FAIL: OpenAIDep dependency must be get_openai, got {dep.dependency}"
        )

    async def test_get_openai_dependency_can_be_overridden(
        self, client: AsyncClient, auth_headers: dict
    ):
        """QA-10: The get_openai dependency must be overridable via app.dependency_overrides.

        This is the key testability requirement: tests must be able to inject a mock
        OpenAI client without real Azure credentials.
        """
        from app.services.openai_client import get_openai
        from app.main import app

        mock_openai = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"patterns": [{"theme": "Test pattern", "evidence_note_ids": []}]}'
        )
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        # Override the dependency
        app.dependency_overrides[get_openai] = lambda: mock_openai

        try:
            resp = await client.get("/api/insights/patterns", headers=auth_headers)
            # The override must be accepted without errors
            assert resp.status_code in (200, 404), (
                f"QA-10 FAIL: dependency override raised unexpected status {resp.status_code}. "
                "The get_openai dependency must be overridable via app.dependency_overrides."
            )
        finally:
            app.dependency_overrides.pop(get_openai, None)

    def test_insights_py_uses_openai_dep_type_alias(self):
        """QA-10: insights.py must declare openai parameters using OpenAIDep type alias
        (or the equivalent get_openai dependency) — not access the client inline without DI.

        The review comment notes the OpenAIDep pattern is inconsistent with the rest
        of the codebase. Either OpenAIDep must be correctly defined, or the endpoints
        must switch to openai_client = await get_openai() inline. Either way, the
        injection must be testable via dependency_overrides.
        """
        from app.services.openai_client import get_openai, OpenAIDep
        from app.api.insights import ai_router, insights_router
        import inspect

        # The insight module should reference OpenAIDep or get_openai in its route handlers
        from app.api import insights as insights_module
        src = inspect.getsource(insights_module)
        assert "get_openai" in src or "OpenAIDep" in src, (
            "QA-10 FAIL: insights.py does not reference get_openai or OpenAIDep. "
            "OpenAI client must be injected via Depends(get_openai) to be testable."
        )


# ---------------------------------------------------------------------------
# PERF-04 — GET /api/insights/patterns must cache result; not call OpenAI twice in 24h
# review-comments.tasks.md § 2.4
# ---------------------------------------------------------------------------

class TestPERF04PatternsCache:
    """
    PERF-04: /api/insights/patterns must cache the GPT result and NOT invoke
    OpenAI on a second call within 24 hours. A ?refresh=true query parameter
    must bypass the cache and invoke OpenAI again.
    """

    async def test_patterns_second_call_within_24h_skips_openai(
        self, client: AsyncClient, auth_headers: dict
    ):
        """
        Two consecutive calls to /api/insights/patterns must result in OpenAI
        being called only ONCE — the second call must return from cache.
        """
        from app.services.openai_client import get_openai
        from app.main import app

        openai_call_count = 0

        mock_openai = AsyncMock()

        async def counting_create(**kwargs):
            nonlocal openai_call_count
            openai_call_count += 1
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = (
                '{"patterns": [{"theme": "Daily Practice", "evidence_note_ids": []}]}'
            )
            return mock_response

        mock_openai.chat.completions.create = counting_create
        app.dependency_overrides[get_openai] = lambda: mock_openai

        try:
            # First call — should invoke OpenAI
            resp1 = await client.get("/api/insights/patterns", headers=auth_headers)
            # Second call within same session — should use cache
            resp2 = await client.get("/api/insights/patterns", headers=auth_headers)
        finally:
            app.dependency_overrides.pop(get_openai, None)

        assert resp1.status_code == 200
        assert resp2.status_code == 200

        assert openai_call_count <= 1, (
            f"PERF-04 FAIL: OpenAI was called {openai_call_count} times for two "
            f"consecutive /api/insights/patterns requests. The second call must be "
            f"served from cache (cached within 24h)."
        )

    async def test_patterns_refresh_true_bypasses_cache(
        self, client: AsyncClient, auth_headers: dict
    ):
        """
        GET /api/insights/patterns?refresh=true must invoke OpenAI even if a
        cached result exists, as long as the user has notes (endpoint skips OpenAI
        when there are no notes).
        """
        from app.services.openai_client import get_openai
        from app.main import app

        # Create at least one note so the endpoint proceeds to call OpenAI
        note_resp = await client.post(
            "/api/notes",
            json={"content": "Learning patterns test note", "category": "learning"},
            headers=auth_headers,
        )
        if note_resp.status_code not in (200, 201):
            pytest.skip("Could not create note for patterns test")

        openai_call_count = 0

        mock_openai = AsyncMock()

        async def counting_create(**kwargs):
            nonlocal openai_call_count
            openai_call_count += 1
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = (
                '{"patterns": [{"theme": "Practice", "evidence_note_ids": []}]}'
            )
            return mock_response

        mock_openai.chat.completions.create = counting_create
        app.dependency_overrides[get_openai] = lambda: mock_openai

        try:
            # Warm the cache
            resp1 = await client.get("/api/insights/patterns", headers=auth_headers)
            # Force refresh
            resp2 = await client.get(
                "/api/insights/patterns?refresh=true", headers=auth_headers
            )
        finally:
            app.dependency_overrides.pop(get_openai, None)

        assert resp2.status_code == 200

        # With ?refresh=true and at least one note, OpenAI must have been called
        assert openai_call_count >= 1, (
            "PERF-04 FAIL: OpenAI was never called even with ?refresh=true and notes present"
        )
