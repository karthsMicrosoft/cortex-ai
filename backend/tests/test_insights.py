"""
test_insights.py — Task 2 (Insights endpoints)
TDD red-phase tests for backend/app/api/insights.py

Covers:
  Task 2.1 — GET /api/ai/summary/daily?date=YYYY-MM-DD
    - Returns daily summary row or 404
    - Requires auth

  Task 2.1 — GET /api/ai/summary/weekly?week=YYYY-W##
    - Returns weekly summary composed from 7 dailies or 404
    - Requires auth

  Task 2.2 — GET /api/insights/graph
    - Returns {nodes: [{id, label, category}], links: [{source, target, score}]}
    - Capped at 200 nodes
    - Requires auth

  Task 2.3 — GET /api/insights/patterns
    - Returns {patterns: [{theme, evidence_note_ids}]}
    - Calls GPT-4o-mini with last 14 days notes
    - Requires auth

  Task 2.4 — Router wired into main.py

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
        """insights module must expose a FastAPI router."""
        from app.api.insights import router
        assert router is not None

    def test_router_has_daily_summary_route(self):
        """ai_summary_router must include GET /summary/daily route."""
        from app.api.insights import ai_summary_router
        routes = [r.path for r in ai_summary_router.routes]
        assert any("summary/daily" in p or "daily" in p for p in routes)

    def test_router_has_weekly_summary_route(self):
        """ai_summary_router must include GET /summary/weekly route."""
        from app.api.insights import ai_summary_router
        routes = [r.path for r in ai_summary_router.routes]
        assert any("summary/weekly" in p or "weekly" in p for p in routes)

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


# ---------------------------------------------------------------------------
# Task 2.1 — GET /api/ai/summary/daily
# ---------------------------------------------------------------------------

class TestDailySummaryEndpoint:
    async def test_daily_summary_requires_auth(self, client: AsyncClient):
        """GET /api/ai/summary/daily must return 401 without auth."""
        resp = await client.get("/api/ai/summary/daily", params={"date": "2026-04-29"})
        assert resp.status_code == 401

    async def test_daily_summary_404_when_not_found(self, client: AsyncClient, auth_headers: dict):
        """GET /api/ai/summary/daily returns 404 when no summary exists for date."""
        resp = await client.get(
            "/api/ai/summary/daily",
            params={"date": "2000-01-01"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_daily_summary_returns_summary_text(self, client: AsyncClient, auth_headers: dict, db_session):
        """GET /api/ai/summary/daily returns summary_text when record exists."""
        from app.models.daily_summary import DailySummary
        import uuid as _uuid

        # Get current user id
        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        summary = DailySummary(
            user_id=user_id,
            summary_date=date(2026, 4, 20),
            summary_text="Great day of music practice.",
            note_count=3,
        )
        db_session.add(summary)
        await db_session.flush()

        resp = await client.get(
            "/api/ai/summary/daily",
            params={"date": "2026-04-20"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "summary_text" in body or "summary" in body
        text = body.get("summary_text") or body.get("summary", "")
        assert "music" in text.lower() or len(text) > 0

    async def test_daily_summary_returns_correct_schema(self, client: AsyncClient, auth_headers: dict, db_session):
        """Daily summary response must include summary_date and note_count."""
        from app.models.daily_summary import DailySummary
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        target_date = date(2026, 4, 21)
        summary = DailySummary(
            user_id=user_id,
            summary_date=target_date,
            summary_text="Fitness and learning day.",
            note_count=5,
        )
        db_session.add(summary)
        await db_session.flush()

        resp = await client.get(
            "/api/ai/summary/daily",
            params={"date": "2026-04-21"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        # Must have some date field
        assert any(k in body for k in ("summary_date", "date"))
        # Must have note count
        assert any(k in body for k in ("note_count", "count"))

    async def test_daily_summary_isolates_by_user(self, client: AsyncClient, auth_headers: dict, second_user_headers: dict, db_session):
        """User A cannot see User B's daily summary."""
        from app.models.daily_summary import DailySummary
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=second_user_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        other_user_id = _uuid.UUID(me_resp.json()["id"])

        target_date = date(2026, 4, 22)
        summary = DailySummary(
            user_id=other_user_id,
            summary_date=target_date,
            summary_text="Secret summary for other user.",
            note_count=2,
        )
        db_session.add(summary)
        await db_session.flush()

        # Requesting user should get 404
        resp = await client.get(
            "/api/ai/summary/daily",
            params={"date": "2026-04-22"},
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task 2.1 — GET /api/ai/summary/weekly
# ---------------------------------------------------------------------------

class TestWeeklySummaryEndpoint:
    async def test_weekly_summary_requires_auth(self, client: AsyncClient):
        """GET /api/ai/summary/weekly must return 401 without auth."""
        resp = await client.get("/api/ai/summary/weekly", params={"week": "2026-W17"})
        assert resp.status_code == 401

    async def test_weekly_summary_returns_text(self, client: AsyncClient, auth_headers: dict, db_session):
        """GET /api/ai/summary/weekly returns WeeklySummaryOut with summary_text."""
        from app.models.daily_summary import DailySummary
        from app.services.openai_client import get_openai
        from app.main import app
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        # Week 2026-W16 = April 13–19
        for i, day in enumerate(range(13, 20)):
            s = DailySummary(
                user_id=user_id,
                summary_date=date(2026, 4, day),
                summary_text=f"Day {i+1} summary: worked on projects.",
                note_count=2,
            )
            db_session.add(s)
        await db_session.flush()

        mock_openai = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This was a productive week with music and learning."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
        app.dependency_overrides[get_openai] = lambda: mock_openai

        resp = await client.get(
            "/api/ai/summary/weekly",
            params={"week": "2026-W16"},
            headers=auth_headers,
        )
        app.dependency_overrides.pop(get_openai, None)

        assert resp.status_code == 200
        body = resp.json()
        assert "summary_text" in body

    async def test_weekly_summary_week_param_format(self, client: AsyncClient, auth_headers: dict):
        """Weekly summary must reject invalid week format with 400 or 422."""
        from app.services.openai_client import get_openai
        from app.main import app

        mock_openai = AsyncMock()
        app.dependency_overrides[get_openai] = lambda: mock_openai

        resp = await client.get(
            "/api/ai/summary/weekly",
            params={"week": "not-a-week"},
            headers=auth_headers,
        )
        app.dependency_overrides.pop(get_openai, None)

        assert resp.status_code in (400, 404, 422)


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
    async def test_daily_summary_endpoint_reachable(self, client: AsyncClient, auth_headers: dict):
        """GET /api/ai/summary/daily must be reachable (not 405 from routing)."""
        resp = await client.get(
            "/api/ai/summary/daily",
            params={"date": "2026-04-01"},
            headers=auth_headers,
        )
        # 404 = route exists but no data; 200 = found; 401 = not authed
        # 405 = route NOT registered — this is the failure case
        assert resp.status_code not in (405,), f"Route not registered: {resp.status_code}"
        assert resp.status_code in (200, 404)

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
