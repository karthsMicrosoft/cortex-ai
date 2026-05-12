"""
Integration tests for POST /api/auth/logout (Round 19 / SEC-07 follow-up).
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.auth import jwt as jwt_mod


@pytest.fixture(autouse=True)
def _clear_in_memory_cache():
    jwt_mod._revoked_jtis.clear()
    yield
    jwt_mod._revoked_jtis.clear()


async def _register(client: AsyncClient) -> dict:
    email = f"logout_{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "Pa$$word123", "display_name": "L"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Auth requirement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_requires_auth(client: AsyncClient):
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_with_invalid_access_token_returns_401(client: AsyncClient):
    resp = await client.post(
        "/api/auth/logout",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Access JTI revocation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_returns_204_with_valid_token(client: AsyncClient):
    body = await _register(client)
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    resp = await client.post(
        "/api/auth/logout",
        headers=headers,
        json={"refresh_token": body["refresh_token"]},
    )
    assert resp.status_code == 204
    assert resp.content == b""


@pytest.mark.asyncio
async def test_logout_revokes_access_jti(client: AsyncClient):
    """After logout, the same access token must no longer be accepted by
    any authenticated endpoint (we sample /api/auth/me)."""
    body = await _register(client)
    token = body["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Pre-logout: /me works.
    pre = await client.get("/api/auth/me", headers=headers)
    assert pre.status_code == 200

    logout = await client.post("/api/auth/logout", headers=headers)
    assert logout.status_code == 204

    # Post-logout: /me must reject the now-revoked access token.
    post = await client.get("/api/auth/me", headers=headers)
    assert post.status_code == 401


# ---------------------------------------------------------------------------
# Refresh JTI revocation (body vs cookie)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_revokes_refresh_jti_from_body(client: AsyncClient):
    body = await _register(client)
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    refresh = body["refresh_token"]

    logout = await client.post(
        "/api/auth/logout", headers=headers, json={"refresh_token": refresh}
    )
    assert logout.status_code == 204

    # The revoked refresh token must be rejected by /refresh.
    rotate = await client.post(
        "/api/auth/refresh", json={"refresh_token": refresh}
    )
    assert rotate.status_code == 401


@pytest.mark.asyncio
async def test_logout_succeeds_without_refresh_token(client: AsyncClient):
    """No refresh token in body or cookie ⇒ still 204 (idempotent path).
    Only the access JTI is revoked."""
    body = await _register(client)
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    # Strip cookies the registration may have set.
    client.cookies.clear()

    resp = await client.post("/api/auth/logout", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_logout_tolerates_malformed_refresh_token(client: AsyncClient):
    """Malformed refresh token must not crash the handler — logout must
    always succeed from the user's perspective."""
    body = await _register(client)
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    resp = await client.post(
        "/api/auth/logout",
        headers=headers,
        json={"refresh_token": "this-is-not-a-jwt"},
    )
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Cookie clearing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_emits_delete_cookie_header(client: AsyncClient):
    body = await _register(client)
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    resp = await client.post("/api/auth/logout", headers=headers)
    assert resp.status_code == 204
    set_cookie = resp.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    # FastAPI/Starlette uses Max-Age=0 to clear cookies.
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()
