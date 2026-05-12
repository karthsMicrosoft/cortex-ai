"""
test_note_update.py — PR 6.4 (Phase 6 / Round 18)

Verifies that the partial-update endpoint (PUT /api/notes/{id}, partial-update
semantics) accepts and validates the new `title` and `aliases` fields added
in PR 6.0.

Validation rules:
  - title: Optional[str], max 120 chars (matches DB column)
  - aliases: Optional[list[str]], max 20 entries, each entry max 120 chars,
    deduplicated case-insensitively, empty entries stripped.
"""
import uuid

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_note(client: AsyncClient, headers: dict, content: str = "x") -> dict:
    resp = await client.post(
        "/api/notes",
        json={"content": content, "source_type": "text", "category": "Ideas"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Title persistence + validation
# ---------------------------------------------------------------------------

class TestUpdateNoteTitle:

    @pytest.mark.asyncio
    async def test_patch_note_title_persists(
        self, client: AsyncClient, auth_headers: dict
    ):
        note = await _create_note(client, auth_headers)
        resp = await client.put(
            f"/api/notes/{note['id']}",
            json={"title": "Hello World"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["title"] == "Hello World"

        # Re-fetch and verify persistence
        get_resp = await client.get(
            f"/api/notes/{note['id']}", headers=auth_headers
        )
        assert get_resp.json()["title"] == "Hello World"

    @pytest.mark.asyncio
    async def test_patch_note_title_can_be_cleared(
        self, client: AsyncClient, auth_headers: dict
    ):
        note = await _create_note(client, auth_headers)
        await client.put(
            f"/api/notes/{note['id']}",
            json={"title": "Set"},
            headers=auth_headers,
        )
        resp = await client.put(
            f"/api/notes/{note['id']}",
            json={"title": None},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["title"] is None

    @pytest.mark.asyncio
    async def test_patch_note_title_max_120_chars(
        self, client: AsyncClient, auth_headers: dict
    ):
        note = await _create_note(client, auth_headers)
        too_long = "a" * 121
        resp = await client.put(
            f"/api/notes/{note['id']}",
            json={"title": too_long},
            headers=auth_headers,
        )
        assert resp.status_code == 422, (
            f"Title >120 chars must 422, got {resp.status_code}: {resp.text}"
        )

    @pytest.mark.asyncio
    async def test_patch_note_title_exactly_120_chars_ok(
        self, client: AsyncClient, auth_headers: dict
    ):
        note = await _create_note(client, auth_headers)
        ok_title = "a" * 120
        resp = await client.put(
            f"/api/notes/{note['id']}",
            json={"title": ok_title},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["title"] == ok_title


# ---------------------------------------------------------------------------
# Aliases persistence + validation
# ---------------------------------------------------------------------------

class TestUpdateNoteAliases:

    @pytest.mark.asyncio
    async def test_patch_note_aliases_persists_and_deduplicates(
        self, client: AsyncClient, auth_headers: dict
    ):
        note = await _create_note(client, auth_headers)
        resp = await client.put(
            f"/api/notes/{note['id']}",
            json={"aliases": ["Foo", "  ", "bar", "FOO", "", "baz"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        # Empty entries stripped, "FOO" is a case-insensitive duplicate of "Foo"
        assert resp.json()["aliases"] == ["Foo", "bar", "baz"]

        get_resp = await client.get(
            f"/api/notes/{note['id']}", headers=auth_headers
        )
        assert get_resp.json()["aliases"] == ["Foo", "bar", "baz"]

    @pytest.mark.asyncio
    async def test_patch_note_aliases_max_20_entries(
        self, client: AsyncClient, auth_headers: dict
    ):
        note = await _create_note(client, auth_headers)
        too_many = [f"alias-{i}" for i in range(21)]
        resp = await client.put(
            f"/api/notes/{note['id']}",
            json={"aliases": too_many},
            headers=auth_headers,
        )
        assert resp.status_code == 422, (
            f"21 aliases must 422, got {resp.status_code}: {resp.text}"
        )

    @pytest.mark.asyncio
    async def test_patch_note_aliases_max_120_each(
        self, client: AsyncClient, auth_headers: dict
    ):
        note = await _create_note(client, auth_headers)
        resp = await client.put(
            f"/api/notes/{note['id']}",
            json={"aliases": ["ok", "x" * 121]},
            headers=auth_headers,
        )
        assert resp.status_code == 422, (
            f"alias >120 chars must 422, got {resp.status_code}: {resp.text}"
        )

    @pytest.mark.asyncio
    async def test_patch_note_aliases_empty_list_clears(
        self, client: AsyncClient, auth_headers: dict
    ):
        note = await _create_note(client, auth_headers)
        await client.put(
            f"/api/notes/{note['id']}",
            json={"aliases": ["foo", "bar"]},
            headers=auth_headers,
        )
        resp = await client.put(
            f"/api/notes/{note['id']}",
            json={"aliases": []},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["aliases"] == []


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_note_other_user_404(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    """PATCH-style update of another user's note must 404 (no info leak)."""
    note = await _create_note(client, second_user_headers)
    resp = await client.put(
        f"/api/notes/{note['id']}",
        json={"title": "Hijack"},
        headers=auth_headers,
    )
    assert resp.status_code == 404, (
        f"Cross-user title update must 404, got {resp.status_code}"
    )
