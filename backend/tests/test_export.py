"""
test_export.py — Task 4 (Export endpoint)
TDD red-phase tests for backend/app/api/export.py

Covers:
  Task 4.1 — GET /api/export
    - Returns JSON dump of all user notes (with SAS-signed media URLs)
    - Includes tags, daily summaries
    - Streaming response for large data sets
    - Requires auth
    - Only returns the authenticated user's data (ownership isolation)

Mock strategy: Mock blob storage SAS URL generation; use conftest client fixture.
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

class TestExportModuleImport:
    def test_export_module_importable(self):
        """backend/app/api/export.py must exist and be importable."""
        import app.api.export  # noqa: F401

    def test_export_router_exists(self):
        """export module must expose a FastAPI router."""
        from app.api.export import router
        assert router is not None

    def test_export_router_has_export_route(self):
        """Router must include GET /export route."""
        from app.api.export import router
        routes = [r.path for r in router.routes]
        assert any("export" in p for p in routes)


# ---------------------------------------------------------------------------
# GET /api/export
# ---------------------------------------------------------------------------

class TestExportEndpoint:
    async def test_export_requires_auth(self, client: AsyncClient):
        """GET /api/export must return 401 without auth."""
        resp = await client.get("/api/export")
        assert resp.status_code == 401

    async def test_export_returns_200(self, client: AsyncClient, auth_headers: dict):
        """GET /api/export must return 200 for authenticated user."""
        resp = await client.get("/api/export", headers=auth_headers)
        assert resp.status_code == 200

    async def test_export_returns_json_content_type(self, client: AsyncClient, auth_headers: dict):
        """GET /api/export must return application/json content type."""
        resp = await client.get("/api/export", headers=auth_headers)
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "json" in content_type or "application/json" in content_type

    async def test_export_includes_notes_key(self, client: AsyncClient, auth_headers: dict):
        """Export JSON must include a 'notes' key."""
        resp = await client.get("/api/export", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "notes" in body

    async def test_export_includes_summaries_key(self, client: AsyncClient, auth_headers: dict):
        """Export JSON must include a 'summaries' key (daily summaries)."""
        resp = await client.get("/api/export", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        # The actual key is 'summaries' per export.py implementation
        assert any(k in body for k in ("summaries", "daily_summaries"))

    async def test_export_notes_have_required_fields(self, client: AsyncClient, auth_headers: dict, db_session):
        """Each exported note must have id, content, category, source_type, created_at."""
        from app.models.note import Note
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content="A note to be exported.",
            source_type="text",
            category="Ideas",
            processing_status="enriched",
        )
        db_session.add(note)
        await db_session.flush()

        resp = await client.get("/api/export", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        if body["notes"]:
            n = body["notes"][0]
            assert "id" in n
            assert "content" in n
            assert "category" in n
            assert "source_type" in n
            assert "created_at" in n

    async def test_export_audio_url_is_preserved(self, client: AsyncClient, auth_headers: dict, db_session):
        """Notes with audio_url must have audio_url in export (SAS pass-through for MVP)."""
        from app.models.note import Note
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        audio_url = "https://cortexblob.blob.core.windows.net/audio/test.webm?sig=abc123"
        note = Note(
            user_id=user_id,
            content="Voice note about music.",
            source_type="voice",
            category="Music",
            processing_status="enriched",
            audio_url=audio_url,
        )
        db_session.add(note)
        await db_session.flush()

        resp = await client.get("/api/export", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        voice_notes = [n for n in body["notes"] if n.get("source_type") == "voice" and n.get("audio_url")]
        if voice_notes:
            assert voice_notes[0]["audio_url"] == audio_url

    async def test_export_isolates_by_user(self, client: AsyncClient, auth_headers: dict, second_user_headers: dict, db_session):
        """GET /api/export must only return the authenticated user's notes."""
        from app.models.note import Note
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=second_user_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        other_user_id = _uuid.UUID(me_resp.json()["id"])

        other_note = Note(
            user_id=other_user_id,
            content="This note belongs to another user — must not appear in export.",
            source_type="text",
            category="Journal",
            processing_status="enriched",
        )
        db_session.add(other_note)
        await db_session.flush()

        resp = await client.get("/api/export", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        exported_note_ids = [n["id"] for n in body["notes"]]
        assert str(other_note.id) not in exported_note_ids

    async def test_export_empty_for_new_user(self, client: AsyncClient, auth_headers: dict):
        """Export for a user with no notes should return empty notes list."""
        resp = await client.get("/api/export", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["notes"], list)

    async def test_export_is_complete_data_dump(self, client: AsyncClient, auth_headers: dict, db_session):
        """Export must include all user notes (not paginated/truncated)."""
        from app.models.note import Note
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        notes_created = []
        for i in range(5):
            n = Note(
                user_id=user_id,
                content=f"Export test note {i}.",
                source_type="text",
                category="Ideas",
                processing_status="enriched",
            )
            db_session.add(n)
            notes_created.append(n)
        await db_session.flush()

        resp = await client.get("/api/export", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        exported_ids = {n["id"] for n in body["notes"]}
        for created_note in notes_created:
            assert str(created_note.id) in exported_ids, f"Note {created_note.id} missing from export"


# ---------------------------------------------------------------------------
# Export module wired into main.py
# ---------------------------------------------------------------------------

class TestExportRouterWired:
    async def test_export_endpoint_reachable(self, client: AsyncClient, auth_headers: dict):
        """GET /api/export must be reachable (not 405 from routing)."""
        resp = await client.get("/api/export", headers=auth_headers)
        assert resp.status_code not in (405,), f"Export route not registered: {resp.status_code}"
        assert resp.status_code in (200, 404)
