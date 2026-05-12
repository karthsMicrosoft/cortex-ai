"""
Endpoint integration tests for POST /api/auth/clip-token and the scope guard
on protected routes — Phase 5 / PR 5.5.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from jose import jwt as jose_jwt

from app.auth.jwt import ALGORITHM
from app.config import settings

pytestmark = pytest.mark.asyncio


def _decode(token: str) -> dict:
    return jose_jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])


# ---------------------------------------------------------------------------
# Fixture: mint a clip token from a registered user
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def clip_headers(client: AsyncClient, auth_headers: dict) -> dict:
    resp = await client.post("/api/auth/clip-token", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    token = resp.json()["clip_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# /api/auth/clip-token endpoint
# ---------------------------------------------------------------------------

class TestClipTokenEndpoint:
    async def test_clip_token_endpoint_requires_auth(self, client: AsyncClient):
        resp = await client.post("/api/auth/clip-token")
        assert resp.status_code in (401, 403), resp.text

    async def test_clip_token_returns_scoped_jwt(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post("/api/auth/clip-token", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["scope"] == "clip"
        assert body["expires_in"] == 30 * 24 * 3600
        assert "clip_token" in body and body["clip_token"]

        payload = _decode(body["clip_token"])
        assert payload["scope"] == "clip"
        assert payload["type"] == "access"
        # Expiry roughly 30 days from issue
        assert payload["exp"] - payload["iat"] == 30 * 24 * 3600

    async def test_clip_token_rate_limit_5_per_hour(
        self, client: AsyncClient, auth_headers: dict
    ):
        for i in range(5):
            resp = await client.post("/api/auth/clip-token", headers=auth_headers)
            assert resp.status_code == 200, (
                f"call #{i+1} should succeed, got {resp.status_code}: {resp.text}"
            )
        resp = await client.post("/api/auth/clip-token", headers=auth_headers)
        assert resp.status_code == 429, resp.text


# ---------------------------------------------------------------------------
# Scope enforcement: clip token can only call import/url + create note
# ---------------------------------------------------------------------------

def _mock_extract_ok():
    return patch(
        "app.api.import_url.fetch_and_extract",
        new=AsyncMock(
            return_value={
                "title": "Hello",
                "content": "Body " * 50,
                "final_url": "https://example.com/x",
            }
        ),
    )


class TestClipTokenAllowedRoutes:
    async def test_clip_token_can_call_import_url(
        self, client: AsyncClient, clip_headers: dict
    ):
        with _mock_extract_ok():
            resp = await client.post(
                "/api/import/url",
                json={"url": "https://example.com/x"},
                headers=clip_headers,
            )
        assert resp.status_code == 201, resp.text

    async def test_clip_token_can_create_note(
        self, client: AsyncClient, clip_headers: dict
    ):
        resp = await client.post(
            "/api/notes",
            json={"content": "From extension"},
            headers=clip_headers,
        )
        assert resp.status_code == 201, resp.text


class TestClipTokenForbiddenRoutes:
    async def test_clip_token_cannot_call_delete_note(
        self,
        client: AsyncClient,
        auth_headers: dict,
        clip_headers: dict,
    ):
        # Create a note via the full session token first
        create = await client.post(
            "/api/notes",
            json={"content": "delete-me"},
            headers=auth_headers,
        )
        assert create.status_code == 201, create.text
        note_id = create.json()["id"]

        # Attempt delete with the clip token → 403
        resp = await client.delete(f"/api/notes/{note_id}", headers=clip_headers)
        assert resp.status_code == 403, resp.text

    async def test_clip_token_cannot_call_export(
        self, client: AsyncClient, clip_headers: dict
    ):
        resp = await client.get("/api/export", headers=clip_headers)
        assert resp.status_code == 403, resp.text

    async def test_clip_token_cannot_call_change_password(
        self, client: AsyncClient, clip_headers: dict
    ):
        resp = await client.post(
            "/api/auth/password",
            json={"current_password": "TestPass123!", "new_password": "NewPass987!"},
            headers=clip_headers,
        )
        assert resp.status_code == 403, resp.text

    async def test_clip_token_cannot_call_get_me(
        self, client: AsyncClient, clip_headers: dict
    ):
        # /api/auth/me uses get_current_user — clip-scoped tokens must be rejected.
        resp = await client.get("/api/auth/me", headers=clip_headers)
        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Regression: non-scoped (full session) tokens still work everywhere
# ---------------------------------------------------------------------------

class TestFullSessionTokenUnchanged:
    async def test_full_session_token_can_call_everything_unchanged(
        self, client: AsyncClient, auth_headers: dict
    ):
        # /api/auth/me
        me = await client.get("/api/auth/me", headers=auth_headers)
        assert me.status_code == 200, me.text

        # /api/notes (POST)
        create = await client.post(
            "/api/notes",
            json={"content": "regression"},
            headers=auth_headers,
        )
        assert create.status_code == 201, create.text
        note_id = create.json()["id"]

        # /api/notes/{id} (DELETE)
        delete = await client.delete(f"/api/notes/{note_id}", headers=auth_headers)
        assert delete.status_code == 204, delete.text

        # /api/export
        exp = await client.get("/api/export", headers=auth_headers)
        assert exp.status_code == 200, exp.text

        # /api/import/url
        with _mock_extract_ok():
            imp = await client.post(
                "/api/import/url",
                json={"url": "https://example.com/y"},
                headers=auth_headers,
            )
        assert imp.status_code == 201, imp.text
