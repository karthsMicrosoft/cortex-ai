"""
Task 5 — Notes CRUD tests (TDD red phase).

Covers:
  - POST /api/notes (201 with auth; 401 without auth)
  - GET /api/notes (paginated list, filtered by category/tag/date_from/date_to)
  - GET /api/notes/{id} (200 owner; 404 other user; 404 non-existent)
  - PUT /api/notes/{id} (partial update; content change resets processing_status; 404 other user)
  - DELETE /api/notes/{id} (204; 404 other user)
  - Ownership isolation: cross-user access returns 404
  - Pagination: limit/offset parameters
  - NoteOut schema validation
  - processing_status logic (raw for text, raw/transcribed for audio)

Design references:
  - design.md § Notes CRUD (spec section 2.4)
  - us-1-foundation.tasks.md Task 5.1–5.5
"""
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_note(
    client: AsyncClient,
    headers: dict,
    content: str = "This is a test note content.",
    source_type: str = "text",
    category: str = "Ideas",
    tags: list | None = None,
    **kwargs,
) -> dict:
    payload = {
        "content": content,
        "source_type": source_type,
        "category": category,
    }
    if tags is not None:
        payload["tags"] = tags
    payload.update(kwargs)
    resp = await client.post("/api/notes", json=payload, headers=headers)
    return resp


# ---------------------------------------------------------------------------
# POST /api/notes
# ---------------------------------------------------------------------------

class TestCreateNote:

    @pytest.mark.asyncio
    async def test_create_note_201(self, client: AsyncClient, auth_headers: dict):
        """POST /api/notes must return 201 on valid payload."""
        resp = await _create_note(client, auth_headers)
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_create_note_returns_note_out(self, client: AsyncClient, auth_headers: dict):
        """POST /api/notes must return NoteOut with required fields."""
        resp = await _create_note(client, auth_headers, content="My first note.")
        body = resp.json()
        assert "id" in body, f"'id' missing from note: {body}"
        assert "content" in body
        assert body["content"] == "My first note."
        assert "source_type" in body
        assert "category" in body
        assert "processing_status" in body
        assert "created_at" in body
        assert "updated_at" in body

    @pytest.mark.asyncio
    async def test_create_note_no_auth_401(self, client: AsyncClient):
        """POST /api/notes without auth must return 401."""
        resp = await client.post(
            "/api/notes",
            json={"content": "Test", "source_type": "text"},
        )
        assert resp.status_code == 401, (
            f"Expected 401 without auth, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_create_note_text_processing_status_raw(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Text notes must have processing_status='raw' on creation."""
        resp = await _create_note(client, auth_headers, source_type="text")
        body = resp.json()
        assert body.get("processing_status") == "raw", (
            f"Text note must have processing_status='raw', got: {body.get('processing_status')}"
        )

    @pytest.mark.asyncio
    async def test_create_note_audio_processing_status(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Notes with audio_url must have processing_status='transcribed' or 'raw'."""
        resp = await _create_note(
            client, auth_headers,
            source_type="voice",
            audio_url="https://example.com/audio.webm",
        )
        body = resp.json()
        assert body.get("processing_status") in ("transcribed", "raw"), (
            f"Audio note status must be 'transcribed' or 'raw', got: {body.get('processing_status')}"
        )

    @pytest.mark.asyncio
    async def test_create_note_missing_content_422(
        self, client: AsyncClient, auth_headers: dict
    ):
        """POST /api/notes without content must return 422."""
        resp = await client.post(
            "/api/notes",
            json={"source_type": "text"},
            headers=auth_headers,
        )
        assert resp.status_code == 422, (
            f"Expected 422 for missing content, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_create_note_with_tags(self, client: AsyncClient, auth_headers: dict):
        """POST /api/notes with tags must return those tags in NoteOut."""
        resp = await _create_note(
            client, auth_headers,
            content="Note with tags",
            tags=["python", "testing"],
        )
        body = resp.json()
        assert resp.status_code == 201
        # Tags might be in body["tags"] as list of strings
        returned_tags = body.get("tags", [])
        tag_names = [t if isinstance(t, str) else t.get("name", "") for t in returned_tags]
        for expected in ["python", "testing"]:
            assert expected in tag_names, (
                f"Tag '{expected}' not found in returned tags: {returned_tags}"
            )

    @pytest.mark.asyncio
    async def test_create_note_invalid_category_422(
        self, client: AsyncClient, auth_headers: dict
    ):
        """POST /api/notes with invalid category must return 422."""
        resp = await client.post(
            "/api/notes",
            json={"content": "Test", "source_type": "text", "category": "InvalidCat"},
            headers=auth_headers,
        )
        assert resp.status_code == 422, (
            f"Expected 422 for invalid category, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_create_note_embedding_not_exposed(
        self, client: AsyncClient, auth_headers: dict
    ):
        """NoteOut must NOT expose the embedding bytes/vector."""
        resp = await _create_note(client, auth_headers)
        body = resp.json()
        assert "embedding" not in body, (
            "embedding must not be exposed in NoteOut (too large + privacy)"
        )


# ---------------------------------------------------------------------------
# GET /api/notes (list)
# ---------------------------------------------------------------------------

class TestListNotes:

    @pytest.mark.asyncio
    async def test_list_notes_200(self, client: AsyncClient, auth_headers: dict):
        """GET /api/notes must return 200."""
        resp = await client.get("/api/notes", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_list_notes_returns_items_and_total(
        self, client: AsyncClient, auth_headers: dict
    ):
        """GET /api/notes response must have 'items' list and 'total' count."""
        resp = await client.get("/api/notes", headers=auth_headers)
        body = resp.json()
        assert "items" in body, f"'items' missing from list response: {body}"
        assert "total" in body, f"'total' missing from list response: {body}"
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)

    @pytest.mark.asyncio
    async def test_list_notes_no_auth_401(self, client: AsyncClient):
        """GET /api/notes without auth must return 401."""
        resp = await client.get("/api/notes")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_notes_returns_only_own_notes(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """GET /api/notes must return only the authenticated user's notes."""
        # User A creates a note
        await _create_note(client, auth_headers, content="User A note")
        # User B creates a note
        await _create_note(client, second_user_headers, content="User B note")

        # User A should NOT see user B's note
        resp_a = await client.get("/api/notes", headers=auth_headers)
        items_a = resp_a.json()["items"]
        contents_a = [n["content"] for n in items_a]
        assert "User B note" not in contents_a, (
            "User A must not see User B's notes in list"
        )

    @pytest.mark.asyncio
    async def test_list_notes_pagination_limit(
        self, client: AsyncClient, auth_headers: dict
    ):
        """GET /api/notes?limit=2 must return at most 2 items."""
        # Create 3 notes
        for i in range(3):
            await _create_note(client, auth_headers, content=f"Pagination note {i}")

        resp = await client.get("/api/notes?limit=2", headers=auth_headers)
        body = resp.json()
        assert len(body["items"]) <= 2, (
            f"Expected at most 2 items with limit=2, got {len(body['items'])}"
        )

    @pytest.mark.asyncio
    async def test_list_notes_pagination_offset(
        self, client: AsyncClient, auth_headers: dict
    ):
        """GET /api/notes?offset=N must skip N items."""
        # Create notes
        for i in range(4):
            await _create_note(client, auth_headers, content=f"Offset note {i}")

        resp_all = await client.get("/api/notes?limit=100&offset=0", headers=auth_headers)
        resp_offset = await client.get("/api/notes?limit=100&offset=2", headers=auth_headers)

        total_all = resp_all.json()["total"]
        total_offset = resp_offset.json()["total"]
        items_offset = resp_offset.json()["items"]

        # total should be same (it's the full count), items shifted
        assert total_all == total_offset, "total must reflect full count, not sliced count"
        assert len(items_offset) <= total_all - 2, (
            "offset=2 should skip 2 items"
        )

    @pytest.mark.asyncio
    async def test_list_notes_filter_by_category(
        self, client: AsyncClient, auth_headers: dict
    ):
        """GET /api/notes?category=Music must return only Music notes."""
        await _create_note(client, auth_headers, content="A music note", category="Music")
        await _create_note(client, auth_headers, content="A fitness note", category="Fitness")

        resp = await client.get("/api/notes?category=Music", headers=auth_headers)
        body = resp.json()
        for note in body["items"]:
            assert note["category"] == "Music", (
                f"Expected only Music notes, got category: {note['category']}"
            )

    @pytest.mark.asyncio
    async def test_list_notes_filter_by_tag(
        self, client: AsyncClient, auth_headers: dict
    ):
        """GET /api/notes?tag=jazz must return only notes tagged with 'jazz'."""
        await _create_note(client, auth_headers, content="Jazz note", tags=["jazz"])
        await _create_note(client, auth_headers, content="Rock note", tags=["rock"])

        resp = await client.get("/api/notes?tag=jazz", headers=auth_headers)
        body = resp.json()
        for note in body["items"]:
            note_tags = note.get("tags", [])
            tag_names = [t if isinstance(t, str) else t.get("name", "") for t in note_tags]
            assert "jazz" in tag_names, (
                f"Note {note['id']} should have tag 'jazz', got tags: {note_tags}"
            )

    @pytest.mark.asyncio
    async def test_list_notes_filter_by_date_from(
        self, client: AsyncClient, auth_headers: dict
    ):
        """GET /api/notes?date_from=YYYY-MM-DD must return notes on/after that date."""
        today = date.today()
        future_date = (today + timedelta(days=365)).isoformat()
        resp = await client.get(
            f"/api/notes?date_from={future_date}", headers=auth_headers
        )
        body = resp.json()
        # No existing notes should be from the future
        assert body["total"] == 0 or len(body["items"]) == 0, (
            "date_from filter with a future date should return 0 items"
        )

    @pytest.mark.asyncio
    async def test_list_notes_default_limit_50(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Default limit must be 50 per design spec."""
        resp = await client.get("/api/notes", headers=auth_headers)
        body = resp.json()
        assert len(body["items"]) <= 50, (
            f"Default limit must be ≤ 50, got {len(body['items'])}"
        )


# ---------------------------------------------------------------------------
# GET /api/notes/{id}
# ---------------------------------------------------------------------------

class TestGetNote:

    @pytest.mark.asyncio
    async def test_get_note_200(self, client: AsyncClient, auth_headers: dict):
        """GET /api/notes/{id} for own note must return 200."""
        create_resp = await _create_note(client, auth_headers, content="Fetch this note")
        note_id = create_resp.json()["id"]

        resp = await client.get(f"/api/notes/{note_id}", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_get_note_returns_note_out(self, client: AsyncClient, auth_headers: dict):
        """GET /api/notes/{id} must return NoteOut with id, content, etc."""
        create_resp = await _create_note(client, auth_headers, content="Detail view note")
        note_id = create_resp.json()["id"]

        resp = await client.get(f"/api/notes/{note_id}", headers=auth_headers)
        body = resp.json()
        assert body["id"] == note_id
        assert body["content"] == "Detail view note"

    @pytest.mark.asyncio
    async def test_get_note_404_nonexistent(self, client: AsyncClient, auth_headers: dict):
        """GET /api/notes/{id} for nonexistent ID must return 404."""
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/notes/{fake_id}", headers=auth_headers)
        assert resp.status_code == 404, (
            f"Expected 404 for nonexistent note, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_get_note_404_other_user(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """GET /api/notes/{id} for another user's note must return 404 (not 403)."""
        # User B creates a note
        create_resp = await _create_note(client, second_user_headers, content="User B private")
        note_id = create_resp.json()["id"]

        # User A tries to access it — must get 404, NOT 403 (ownership isolation)
        resp = await client.get(f"/api/notes/{note_id}", headers=auth_headers)
        assert resp.status_code == 404, (
            f"Cross-user access must return 404 (not 403 or 200), got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_get_note_no_auth_401(self, client: AsyncClient, auth_headers: dict):
        """GET /api/notes/{id} without auth must return 401."""
        create_resp = await _create_note(client, auth_headers)
        note_id = create_resp.json()["id"]

        resp = await client.get(f"/api/notes/{note_id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/notes/{id}
# ---------------------------------------------------------------------------

class TestUpdateNote:

    @pytest.mark.asyncio
    async def test_update_note_200(self, client: AsyncClient, auth_headers: dict):
        """PUT /api/notes/{id} with valid data must return 200."""
        create_resp = await _create_note(client, auth_headers, content="Original content")
        note_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/notes/{note_id}",
            json={"content": "Updated content"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_update_note_content_changes(self, client: AsyncClient, auth_headers: dict):
        """PUT /api/notes/{id} must reflect the new content in the response."""
        create_resp = await _create_note(client, auth_headers, content="Before update")
        note_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/notes/{note_id}",
            json={"content": "After update"},
            headers=auth_headers,
        )
        body = resp.json()
        assert body["content"] == "After update", (
            f"Content not updated: {body['content']}"
        )

    @pytest.mark.asyncio
    async def test_update_note_content_resets_processing_status(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Changing content must reset processing_status to 'raw' (re-pipeline trigger)."""
        create_resp = await _create_note(client, auth_headers, content="Original")
        note_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/notes/{note_id}",
            json={"content": "Completely new content requiring re-analysis"},
            headers=auth_headers,
        )
        body = resp.json()
        assert body.get("processing_status") == "raw", (
            f"Content change must reset processing_status to 'raw', got: {body.get('processing_status')}"
        )

    @pytest.mark.asyncio
    async def test_update_note_category_does_not_reset_status(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Changing only category must NOT reset processing_status (mitigation #6)."""
        create_resp = await _create_note(client, auth_headers, content="Stable content")
        note_id = create_resp.json()["id"]
        original_status = create_resp.json().get("processing_status")

        resp = await client.put(
            f"/api/notes/{note_id}",
            json={"category": "Music"},
            headers=auth_headers,
        )
        body = resp.json()
        assert body.get("processing_status") == original_status, (
            f"Changing only category must NOT reset processing_status. "
            f"Expected {original_status}, got {body.get('processing_status')}"
        )

    @pytest.mark.asyncio
    async def test_update_note_partial_update(self, client: AsyncClient, auth_headers: dict):
        """PUT accepts partial update — fields not sent must remain unchanged."""
        create_resp = await _create_note(
            client, auth_headers,
            content="Partial test", category="Ideas",
        )
        note_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/notes/{note_id}",
            json={"category": "Fitness"},  # Only update category
            headers=auth_headers,
        )
        body = resp.json()
        assert body["category"] == "Fitness"
        assert body["content"] == "Partial test", (
            "Content must remain unchanged in partial update"
        )

    @pytest.mark.asyncio
    async def test_update_note_404_other_user(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """PUT /api/notes/{id} on another user's note must return 404."""
        create_resp = await _create_note(client, second_user_headers, content="User B note")
        note_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/notes/{note_id}",
            json={"content": "Hijacked!"},
            headers=auth_headers,
        )
        assert resp.status_code == 404, (
            f"Cross-user PUT must return 404, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_update_note_404_nonexistent(self, client: AsyncClient, auth_headers: dict):
        """PUT /api/notes/{fake-id} must return 404."""
        fake_id = str(uuid.uuid4())
        resp = await client.put(
            f"/api/notes/{fake_id}",
            json={"content": "Update ghost"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_note_invalid_category_422(
        self, client: AsyncClient, auth_headers: dict
    ):
        """PUT with invalid category value must return 422."""
        create_resp = await _create_note(client, auth_headers)
        note_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/notes/{note_id}",
            json={"category": "Nonexistent"},
            headers=auth_headers,
        )
        assert resp.status_code == 422, (
            f"Expected 422 for invalid category, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_update_note_no_auth_401(self, client: AsyncClient, auth_headers: dict):
        """PUT /api/notes/{id} without auth must return 401."""
        create_resp = await _create_note(client, auth_headers)
        note_id = create_resp.json()["id"]

        resp = await client.put(f"/api/notes/{note_id}", json={"content": "x"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/notes/{id}
# ---------------------------------------------------------------------------

class TestDeleteNote:

    @pytest.mark.asyncio
    async def test_delete_note_204(self, client: AsyncClient, auth_headers: dict):
        """DELETE /api/notes/{id} for own note must return 204."""
        create_resp = await _create_note(client, auth_headers, content="Delete me")
        note_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/notes/{note_id}", headers=auth_headers)
        assert resp.status_code == 204, f"Expected 204, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_delete_note_gone_after_delete(
        self, client: AsyncClient, auth_headers: dict
    ):
        """After DELETE, GET /api/notes/{id} must return 404."""
        create_resp = await _create_note(client, auth_headers, content="Ephemeral note")
        note_id = create_resp.json()["id"]

        await client.delete(f"/api/notes/{note_id}", headers=auth_headers)

        get_resp = await client.get(f"/api/notes/{note_id}", headers=auth_headers)
        assert get_resp.status_code == 404, (
            f"Deleted note must return 404 on subsequent GET, got {get_resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_delete_note_404_other_user(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """DELETE on another user's note must return 404."""
        create_resp = await _create_note(client, second_user_headers, content="User B note")
        note_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/notes/{note_id}", headers=auth_headers)
        assert resp.status_code == 404, (
            f"Cross-user DELETE must return 404, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_delete_note_404_nonexistent(self, client: AsyncClient, auth_headers: dict):
        """DELETE /api/notes/{fake-id} must return 404."""
        fake_id = str(uuid.uuid4())
        resp = await client.delete(f"/api/notes/{fake_id}", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_note_no_auth_401(self, client: AsyncClient, auth_headers: dict):
        """DELETE /api/notes/{id} without auth must return 401."""
        create_resp = await _create_note(client, auth_headers)
        note_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/notes/{note_id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Ownership isolation (Task 5.5 — comprehensive)
# ---------------------------------------------------------------------------

class TestOwnershipIsolation:
    """User A must not be able to read, modify, or delete User B's notes.
    Cross-user access must return 404 (not 403) to avoid leaking existence."""

    @pytest.mark.asyncio
    async def test_cannot_read_other_user_note(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """User A cannot GET User B's note — must get 404."""
        resp_b = await _create_note(client, second_user_headers, content="B's private note")
        note_id = resp_b.json()["id"]
        resp = await client.get(f"/api/notes/{note_id}", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_update_other_user_note(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """User A cannot PUT User B's note — must get 404."""
        resp_b = await _create_note(client, second_user_headers, content="B original")
        note_id = resp_b.json()["id"]
        resp = await client.put(
            f"/api/notes/{note_id}", json={"content": "A hijack"}, headers=auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_delete_other_user_note(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """User A cannot DELETE User B's note — must get 404."""
        resp_b = await _create_note(client, second_user_headers, content="B's note")
        note_id = resp_b.json()["id"]
        resp = await client.delete(f"/api/notes/{note_id}", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_user_returns_404_not_403(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """
        Cross-user access MUST return 404 — not 403 — to avoid leaking that
        the note exists (as specified in design Task 5.5).
        """
        resp_b = await _create_note(client, second_user_headers, content="Secret note")
        note_id = resp_b.json()["id"]

        for method, path, kwargs in [
            ("get", f"/api/notes/{note_id}", {}),
            ("put", f"/api/notes/{note_id}", {"json": {"content": "x"}}),
            ("delete", f"/api/notes/{note_id}", {}),
        ]:
            resp = await getattr(client, method)(path, headers=auth_headers, **kwargs)
            assert resp.status_code == 404, (
                f"{method.upper()} cross-user note must return 404, "
                f"got {resp.status_code} (must not be 403 — avoids existence leak)"
            )
