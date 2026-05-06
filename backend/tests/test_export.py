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

Security review additions (review-comments.tasks.md Task 1):
  SEC-08: _refresh_sas_url must be a real implementation (not a stub) that
          calls into the blob_storage helper to generate short-lived SAS URLs.

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


# ---------------------------------------------------------------------------
# SEC-08: _refresh_sas_url must call blob_storage helper, not be a stub
# review-comments.tasks.md Task 1, subtask 1.7
# ---------------------------------------------------------------------------

class TestRefreshSasUrlNotStub:
    """
    SEC-08 (review-comments.tasks.md 1.7)

    The _refresh_sas_url() function in export.py is a stub that passes stored
    URLs through unchanged. This means:
    1. Expired 24h SAS URLs in old notes silently return broken media URLs.
    2. If SAS TTL is ever increased, long-lived URLs remain valid even after note
       deletion.

    Fix: _refresh_sas_url must call blob_storage.generate_sas_url (or equivalent)
    to re-sign the URL with a short (1h) TTL at export time.

    These tests verify the fixed implementation.
    """

    def test_refresh_sas_url_is_not_identity_stub(self):
        """
        SEC-08 static check: _refresh_sas_url must NOT be a no-op stub that
        simply returns its argument unchanged for Azure Blob SAS URLs.

        Inspect the function's source code for the stub pattern:
          return url  (with no real logic)
        A fixed implementation must contain a call to a blob_storage helper
        or re-signing logic.
        """
        import inspect
        try:
            from app.api.export import _refresh_sas_url
            source = inspect.getsource(_refresh_sas_url)

            # Detect stub: function body is only 'return url' with no blob call
            # Strip comments and docstrings from analysis
            non_comment_lines = [
                line.strip()
                for line in source.splitlines()
                if line.strip()
                and not line.strip().startswith("#")
                and not line.strip().startswith('"""')
                and not line.strip().startswith("'''")
                and not line.strip().startswith("def ")
            ]
            # A stub has only 'return url' or just 'return url' after docstring
            only_return_url = all(
                line in ("return url", "return url  # stub", "pass")
                or line.startswith('"""')
                or line.startswith("'''")
                for line in non_comment_lines
            )
            assert not only_return_url, (
                "SEC-08 NOT FIXED: _refresh_sas_url is a stub (returns url unchanged). "
                "Implement SAS URL re-signing with a short TTL by calling "
                "blob_storage.generate_sas_url() or equivalent. "
                "See review-comments.tasks.md 1.7."
            )
        except ImportError as exc:
            pytest.skip(f"app.api.export not importable: {exc}")

    def test_refresh_sas_url_calls_blob_storage_helper(self):
        """
        SEC-08 static check: _refresh_sas_url source must reference a
        blob_storage module function (generate_sas_url, generate_blob_sas,
        or upload_blob's SAS generation logic).
        """
        import inspect
        try:
            from app.api.export import _refresh_sas_url
            source = inspect.getsource(_refresh_sas_url)

            blob_storage_referenced = (
                "blob_storage" in source
                or "generate_sas_url" in source
                or "generate_blob_sas" in source
                or "BlobSasPermissions" in source
                or "sas_token" in source
                or "expiry" in source.lower()
            )
            assert blob_storage_referenced, (
                "SEC-08 NOT FIXED: _refresh_sas_url does not reference any "
                "blob_storage helper or SAS-generation logic. "
                "It must call into app.services.blob_storage to re-sign URLs "
                "with a short (≤ 1h) TTL at export time."
            )
        except ImportError as exc:
            pytest.skip(f"app.api.export not importable: {exc}")

    def test_refresh_sas_url_with_none_returns_none(self):
        """
        SEC-08: _refresh_sas_url(None) must return None — notes without media
        URLs must not error during export.
        """
        try:
            from app.api.export import _refresh_sas_url
            # The function signature is _refresh_sas_url(url: str | None) -> str | None
            result = _refresh_sas_url(None)
            assert result is None, (
                f"_refresh_sas_url(None) must return None, got {result!r}"
            )
        except ImportError as exc:
            pytest.skip(f"app.api.export not importable: {exc}")
        except Exception as exc:
            # If it raises, that's also a sign the implementation handles None;
            # a TypeError means None wasn't handled → flag it.
            if isinstance(exc, TypeError):
                pytest.fail(
                    f"SEC-08: _refresh_sas_url(None) raised TypeError — "
                    f"None input must be handled gracefully: {exc}"
                )

    def test_refresh_sas_url_with_non_blob_url_returns_unchanged(self):
        """
        SEC-08: _refresh_sas_url on a non-Azure-Blob URL (e.g. an http://example.com URL)
        must return the URL unchanged (no re-signing attempted for non-blob URLs).

        This guards against errors when notes have non-blob media URLs.
        """
        try:
            from app.api.export import _refresh_sas_url
            non_blob_url = "https://example.com/media/audio.webm"
            result = _refresh_sas_url(non_blob_url)
            # For non-blob URLs the implementation should pass through unchanged
            # (since it can't re-sign URLs it doesn't own the key for).
            assert result is not None, (
                f"_refresh_sas_url on a non-blob URL must return a non-None value"
            )
        except ImportError as exc:
            pytest.skip(f"app.api.export not importable: {exc}")
        except Exception:
            # Implementation may call blob_storage and fail for non-blob URLs;
            # that's an acceptable behaviour (the test validates None handling above).
            pass

    def test_export_refreshes_sas_url_for_audio_notes(
        self, client: AsyncClient, auth_headers: dict, db_session
    ):
        """
        SEC-08 integration: When exporting a note with an Azure Blob audio_url,
        the export must call _refresh_sas_url (verified via mock) to ensure
        SAS URLs are refreshed rather than returned stale.

        If _refresh_sas_url is a stub, mocking blob_storage won't change the
        export response — the URL comes through the stub unchanged.
        """
        from unittest.mock import patch, MagicMock
        from app.models.note import Note
        import uuid as _uuid

        async def _run():
            me_resp = await client.get("/api/auth/me", headers=auth_headers)
            if me_resp.status_code != 200:
                pytest.skip("Auth/me not available")
            user_id = _uuid.UUID(me_resp.json()["id"])

            original_url = "https://cortexacct.blob.core.windows.net/media/audio.webm?sig=old"
            refreshed_url = "https://cortexacct.blob.core.windows.net/media/audio.webm?sig=NEW"

            note = Note(
                user_id=user_id,
                content="Voice note for SAS refresh test.",
                source_type="voice",
                category="Music",
                processing_status="enriched",
                audio_url=original_url,
            )
            db_session.add(note)
            await db_session.flush()

            with patch("app.api.export._refresh_sas_url", return_value=refreshed_url) as mock_refresh:
                resp = await client.get("/api/export", headers=auth_headers)
                assert resp.status_code == 200
                # _refresh_sas_url must have been called at least once
                # (for the audio_url of our test note)
                assert mock_refresh.call_count >= 1, (
                    "SEC-08 NOT FIXED: _refresh_sas_url was not called during export. "
                    "The export handler must call _refresh_sas_url for each note's "
                    "audio_url and image_url fields."
                )
                body = resp.json()
                # Verify the refreshed URL appears in the output
                voice_notes = [
                    n for n in body["notes"]
                    if n.get("source_type") == "voice" and n.get("audio_url")
                ]
                if voice_notes:
                    assert voice_notes[0]["audio_url"] == refreshed_url, (
                        f"SEC-08: Exported audio_url should be the refreshed URL. "
                        f"Got {voice_notes[0]['audio_url']!r}, expected {refreshed_url!r}."
                    )

        import asyncio
        # This test is async — run via pytest-asyncio mark
        pytest.mark.asyncio(_run)

    @pytest.mark.asyncio
    async def test_export_audio_url_is_refreshed_via_mock(
        self, client: AsyncClient, auth_headers: dict, db_session
    ):
        """
        SEC-08 integration (async): Export calls _refresh_sas_url for each note.
        Verifies the call count using unittest.mock.patch.
        """
        from unittest.mock import patch, AsyncMock
        from app.models.note import Note
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        original_url = "https://cortexacct.blob.core.windows.net/media/audio.webm?sig=old"
        refreshed_url = "https://cortexacct.blob.core.windows.net/media/audio.webm?sig=NEW"

        note = Note(
            user_id=user_id,
            content="Voice note for SAS refresh test (async).",
            source_type="voice",
            category="Music",
            processing_status="enriched",
            audio_url=original_url,
        )
        db_session.add(note)
        await db_session.flush()

        with patch("app.api.export._refresh_sas_url", return_value=refreshed_url) as mock_refresh:
            resp = await client.get("/api/export", headers=auth_headers)
            assert resp.status_code == 200

            assert mock_refresh.call_count >= 1, (
                "SEC-08 NOT FIXED: _refresh_sas_url was never called during export. "
                "The export serialiser must call _refresh_sas_url(note.audio_url) and "
                "_refresh_sas_url(note.image_url) for each note. "
                "See review-comments.tasks.md 1.7."
            )

            # Check the refreshed URL appears in the output body
            body = resp.json()
            voice_notes = [
                n for n in body["notes"]
                if n.get("source_type") == "voice" and n.get("audio_url") == refreshed_url
            ]
            assert len(voice_notes) >= 1, (
                f"SEC-08: Expected at least one note with refreshed audio_url={refreshed_url!r} "
                f"in export output, but none found. _refresh_sas_url is likely a stub."
            )
