"""
test_insights_graph_filters.py — PR 6.2 Brain View polish (Round 18)

Extends GET /api/insights/graph with:
  - ?category=<Category>  filter to a single category
  - ?since=<ISO date>     only notes created on/after that date
  - ?limit=<int>          cap (default 200, max 1000)
  - response: each link now includes link_type
  - response: each node now includes title (fallback summary or content[:60])

TDD red-phase tests.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_note(db_session, *, user_id, category="Ideas", title=None,
                       summary=None, content="hello", created_at=None):
    from app.models.note import Note
    note = Note(
        user_id=user_id,
        content=content,
        source_type="text",
        category=category,
        processing_status="enriched",
        title=title,
        summary=summary,
    )
    db_session.add(note)
    await db_session.flush()
    if created_at is not None:
        note.created_at = created_at
        await db_session.flush()
    return note


async def _me_id(client, headers):
    me = await client.get("/api/auth/me", headers=headers)
    if me.status_code != 200:
        pytest.skip("auth/me unavailable")
    return _uuid.UUID(me.json()["id"])


class TestGraphCategoryFilter:
    async def test_graph_accepts_category_filter(
        self, client: AsyncClient, auth_headers: dict, db_session
    ):
        user_id = await _me_id(client, auth_headers)
        await _create_note(db_session, user_id=user_id, category="Learning",
                           content="learning a")
        await _create_note(db_session, user_id=user_id, category="Music",
                           content="music a")
        await _create_note(db_session, user_id=user_id, category="Music",
                           content="music b")

        resp = await client.get(
            "/api/insights/graph?category=Learning", headers=auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert all(n["category"] == "Learning" for n in body["nodes"])
        assert len(body["nodes"]) >= 1


class TestGraphSinceFilter:
    async def test_graph_accepts_since_filter(
        self, client: AsyncClient, auth_headers: dict, db_session
    ):
        user_id = await _me_id(client, auth_headers)
        old = datetime.now(timezone.utc) - timedelta(days=400)
        recent = datetime.now(timezone.utc) - timedelta(days=2)
        old_note = await _create_note(
            db_session, user_id=user_id, category="Ideas",
            content="old note", created_at=old,
        )
        recent_note = await _create_note(
            db_session, user_id=user_id, category="Ideas",
            content="recent note", created_at=recent,
        )

        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
        resp = await client.get(
            f"/api/insights/graph?since={cutoff}", headers=auth_headers
        )
        assert resp.status_code == 200
        ids = [n["id"] for n in resp.json()["nodes"]]
        assert str(recent_note.id) in ids
        assert str(old_note.id) not in ids


class TestGraphLimitParam:
    async def test_graph_accepts_limit_param(
        self, client: AsyncClient, auth_headers: dict, db_session
    ):
        user_id = await _me_id(client, auth_headers)
        for i in range(15):
            await _create_note(
                db_session, user_id=user_id, category="Ideas",
                content=f"note {i}",
            )
        resp = await client.get(
            "/api/insights/graph?limit=10", headers=auth_headers
        )
        assert resp.status_code == 200
        assert len(resp.json()["nodes"]) <= 10

    async def test_graph_limit_capped_at_1000(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get(
            "/api/insights/graph?limit=99999", headers=auth_headers
        )
        assert resp.status_code == 200
        assert len(resp.json()["nodes"]) <= 1000


class TestGraphLinkTypeInResponse:
    async def test_graph_includes_link_type_in_edges(
        self, client: AsyncClient, auth_headers: dict, db_session
    ):
        from app.models.note_link import NoteLink

        user_id = await _me_id(client, auth_headers)
        a = await _create_note(db_session, user_id=user_id, content="A")
        b = await _create_note(db_session, user_id=user_id, content="B")
        link = NoteLink(
            source_note_id=a.id,
            target_note_id=b.id,
            similarity_score=0.9,
            link_type="manual",
        )
        db_session.add(link)
        await db_session.flush()

        resp = await client.get("/api/insights/graph", headers=auth_headers)
        assert resp.status_code == 200
        edges = resp.json()["links"]
        assert len(edges) >= 1
        for e in edges:
            assert "link_type" in e


class TestGraphTitleInNodes:
    async def test_graph_includes_title_in_nodes(
        self, client: AsyncClient, auth_headers: dict, db_session
    ):
        user_id = await _me_id(client, auth_headers)
        await _create_note(
            db_session, user_id=user_id, category="Ideas",
            content="long form content body", title="My Cool Title",
        )
        resp = await client.get("/api/insights/graph", headers=auth_headers)
        assert resp.status_code == 200
        nodes = resp.json()["nodes"]
        assert len(nodes) >= 1
        for n in nodes:
            assert "title" in n
        titled = [n for n in nodes if n["title"] == "My Cool Title"]
        assert len(titled) == 1

    async def test_graph_title_falls_back_to_summary_or_content(
        self, client: AsyncClient, auth_headers: dict, db_session
    ):
        user_id = await _me_id(client, auth_headers)
        await _create_note(
            db_session, user_id=user_id, category="Ideas",
            content="A" * 200, title=None, summary="A nice summary",
        )
        await _create_note(
            db_session, user_id=user_id, category="Ideas",
            content="B" * 200, title=None, summary=None,
        )
        resp = await client.get("/api/insights/graph", headers=auth_headers)
        assert resp.status_code == 200
        nodes = resp.json()["nodes"]
        # Every node has non-null title (fallback applied).
        assert all(n["title"] for n in nodes)
        # Summary fallback present somewhere.
        assert any(n["title"] == "A nice summary" for n in nodes)
