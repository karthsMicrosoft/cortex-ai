"""
Regression tests for the 2026-05-01 live-deploy fixes.

Bugs covered:
  S1. /api/auth/refresh cookie was SameSite=Lax — blocked on cross-origin
      fetch from SWA (gentle-river-*) to Container App (cortexks-*). Fix:
      SameSite=None + Secure on every Set-Cookie of the refresh token.
  S2. Profile editing was missing — added PUT /api/auth/me (display_name)
      and POST /api/auth/password (verify current + change new).
  S3. Logout was missing — added POST /api/auth/logout that revokes the
      refresh JTI and clears the cookie.
  S4. SEC-04 password strength rule must apply to changePassword as well.
"""

import inspect

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# S1 — refresh cookie SameSite=None
# ---------------------------------------------------------------------------


class TestRefreshCookieSameSiteNone:
    """SameSite=Lax blocks browsers from sending the refresh cookie on
    cross-origin XHR/fetch — which is exactly the SWA→Container App
    topology of the live deploy. Must be SameSite=None + Secure."""

    def test_auth_module_does_not_use_samesite_lax(self):
        from app.api import auth

        src = inspect.getsource(auth)
        assert 'samesite="lax"' not in src and "samesite='lax'" not in src, (
            "refresh-token cookie must NOT be SameSite=Lax — browsers refuse "
            "to send it on cross-origin fetch from the SWA frontend, breaking "
            "session restore on page refresh."
        )

    def test_auth_module_uses_samesite_none(self):
        from app.api import auth

        src = inspect.getsource(auth)
        assert 'samesite="none"' in src or "samesite='none'" in src, (
            "refresh-token cookie must be SameSite=None for cross-origin SWA→backend"
        )

    def test_login_sets_secure_cookie(self):
        from app.api import auth

        src = inspect.getsource(auth)
        # Both /login and /refresh must set secure=True (required when SameSite=None)
        assert src.count("secure=True") >= 2


# ---------------------------------------------------------------------------
# S2 — PUT /api/auth/me + POST /api/auth/password
# ---------------------------------------------------------------------------


class TestProfileEditingEndpoints:
    """ProfilePage edits display_name via PUT /api/auth/me and changes
    password via POST /api/auth/password."""

    def test_put_me_endpoint_registered(self):
        from app.main import app

        routes = [
            (getattr(r, "path", ""), getattr(r, "methods", set()) or set())
            for r in app.routes
        ]
        put_me = [
            (path, methods) for path, methods in routes
            if path == "/api/auth/me" and "PUT" in methods
        ]
        assert put_me, "PUT /api/auth/me must be registered (S2 — profile edit)"

    def test_post_password_endpoint_registered(self):
        from app.main import app

        routes = [
            (getattr(r, "path", ""), getattr(r, "methods", set()) or set())
            for r in app.routes
        ]
        post_pw = [
            (path, methods) for path, methods in routes
            if path == "/api/auth/password" and "POST" in methods
        ]
        assert post_pw, "POST /api/auth/password must be registered (S2 — change password)"

    def test_profile_update_request_schema_caps_display_name_length(self):
        from app.schemas.auth import ProfileUpdateRequest

        schema = ProfileUpdateRequest.model_json_schema()
        prop = schema["properties"]["display_name"]
        # Pydantic v2 reports max_length under "anyOf" entries; the constraint
        # must be present somewhere.
        json_text = str(schema)
        assert "100" in json_text and "maxLength" in json_text, (
            f"ProfileUpdateRequest.display_name must have max_length=100. Schema: {schema}"
        )

    def test_password_change_request_enforces_min_length_8(self):
        from app.schemas.auth import PasswordChangeRequest

        schema = PasswordChangeRequest.model_json_schema()
        new_pw = schema["properties"]["new_password"]
        assert new_pw.get("minLength") == 8, (
            f"new_password must have minLength=8 (matches SEC-04 register rule). Got: {new_pw}"
        )
        assert new_pw.get("maxLength") == 128


# ---------------------------------------------------------------------------
# S3 — logout endpoint + JTI revocation
# ---------------------------------------------------------------------------


class TestLogoutEndpoint:
    """POST /api/auth/logout revokes the refresh JTI and deletes the cookie.
    Idempotent so a double-click is safe."""

    def test_post_logout_endpoint_registered(self):
        from app.main import app

        routes = [
            (getattr(r, "path", ""), getattr(r, "methods", set()) or set())
            for r in app.routes
        ]
        logout_routes = [
            (p, m) for p, m in routes if p == "/api/auth/logout" and "POST" in m
        ]
        assert logout_routes

    def test_logout_handler_revokes_jti(self):
        from app.api import auth

        src = inspect.getsource(auth.logout)
        assert "revoke_jti" in src

    def test_logout_handler_deletes_cookie(self):
        from app.api import auth

        src = inspect.getsource(auth.logout)
        assert "delete_cookie" in src

    def test_logout_is_idempotent_on_missing_cookie(self):
        from app.api import auth

        src = inspect.getsource(auth.logout)
        # The handler must tolerate a None cookie (else clicking sign-out
        # twice would 500 the second click).
        assert "if refresh_cookie" in src or "Cookie(default=None" in src


# ---------------------------------------------------------------------------
# S4 — End-to-end smoke: register → update profile → change password
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_me_updates_display_name(client: AsyncClient, auth_headers: dict):
    resp = await client.put("/api/auth/me", json={"display_name": "Renamed"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["display_name"] == "Renamed"


@pytest.mark.asyncio
async def test_post_password_changes_with_correct_current_password(
    client: AsyncClient, registered_user: dict, auth_headers: dict
):
    resp = await client.post(
        "/api/auth/password",
        json={
            "current_password": registered_user["password"],
            "new_password": "brand-new-password-1",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 204, resp.text

    # Confirm: new password authenticates the user
    login = await client.post(
        "/api/auth/login",
        json={"email": registered_user["email"], "password": "brand-new-password-1"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_post_password_rejects_wrong_current_password(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/auth/password",
        json={"current_password": "wrongguess", "new_password": "brand-new-password-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_post_password_rejects_short_new_password(
    client: AsyncClient, registered_user: dict, auth_headers: dict
):
    resp = await client.post(
        "/api/auth/password",
        json={
            "current_password": registered_user["password"],
            "new_password": "short",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422  # Pydantic min_length=8 violation


@pytest.mark.asyncio
async def test_logout_clears_cookie_idempotently(client: AsyncClient):
    """Logout must require a valid access token (Round 19 / SEC-07 hardening)
    but, given a valid token, must succeed even when no refresh cookie is
    present (idempotent — defends against double-click + already-expired
    refresh tokens)."""
    # Without auth: 401 (Round 19 — was 204 before persistent revocation).
    resp_no_auth = await client.post("/api/auth/logout")
    assert resp_no_auth.status_code == 401

    # With a fresh access token but no refresh cookie/body: 204 (idempotent).
    import uuid as _uuid
    email = f"logout_idem_{_uuid.uuid4().hex[:8]}@example.com"
    reg = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "Pa$$word123", "display_name": "L"},
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp1 = await client.post("/api/auth/logout", headers=headers)
    assert resp1.status_code == 204
    # Second call with the SAME token must now 401 (the JTI was revoked on
    # the first call); that's the new contract.
    resp2 = await client.post("/api/auth/logout", headers=headers)
    assert resp2.status_code == 401
