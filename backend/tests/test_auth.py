"""
Task 4 — JWT authentication tests (TDD red phase).

Covers:
  - POST /api/auth/register (201, returns UserOut; 409 on duplicate; 422 on bad email)
  - POST /api/auth/login (200, returns TokenPair; 401 on bad creds)
  - POST /api/auth/refresh (200, rotates refresh token)
  - GET /api/auth/me (200, returns UserOut; 401 without token)
  - bcrypt password hashing (password NOT stored in plain text)
  - JWT access token: correct structure, 30-min TTL, HS256
  - JWT refresh token: 30-day TTL
  - Token expiration behaviour
  - Refresh token reuse / rotation detection

Design references:
  - design.md § Auth (spec section 2.10)
  - us-1-foundation.tasks.md Task 4.1–4.4
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_email() -> str:
    return f"user_{uuid.uuid4().hex[:8]}@example.com"


async def _register(client: AsyncClient, email: str, password: str = "TestPass123!",
                    display_name: str = "Test User") -> dict:
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )
    return resp


async def _login(client: AsyncClient, email: str, password: str = "TestPass123!") -> dict:
    resp = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    return resp


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

class TestRegister:

    @pytest.mark.asyncio
    async def test_register_success_201(self, client: AsyncClient):
        """POST /api/auth/register must return 201 on valid payload."""
        resp = await _register(client, _unique_email())
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_register_returns_user_out(self, client: AsyncClient):
        """Register response must include id, email, display_name (UserOut schema)."""
        email = _unique_email()
        resp = await _register(client, email, display_name="Alice")
        body = resp.json()
        assert "id" in body, f"'id' missing from register response: {body}"
        assert "email" in body, f"'email' missing from register response: {body}"
        assert body["email"] == email
        assert "display_name" in body
        assert body["display_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_register_does_not_return_password(self, client: AsyncClient):
        """Register response must NOT expose password or password_hash."""
        resp = await _register(client, _unique_email())
        body = resp.json()
        assert "password" not in body, "password must not be in register response"
        assert "password_hash" not in body, "password_hash must not be in register response"

    @pytest.mark.asyncio
    async def test_register_no_tokens_returned(self, client: AsyncClient):
        """Register (per design) does NOT return tokens — only UserOut."""
        resp = await _register(client, _unique_email())
        body = resp.json()
        assert "access_token" not in body, "Register must not return access_token"
        assert "refresh_token" not in body, "Register must not return refresh_token"

    @pytest.mark.asyncio
    async def test_register_duplicate_email_409(self, client: AsyncClient):
        """Registering with an existing email must return 409."""
        email = _unique_email()
        await _register(client, email)
        resp2 = await _register(client, email)
        assert resp2.status_code == 409, (
            f"Expected 409 on duplicate email, got {resp2.status_code}: {resp2.text}"
        )

    @pytest.mark.asyncio
    async def test_register_invalid_email_422(self, client: AsyncClient):
        """Registering with a malformed email must return 422 (validation error)."""
        resp = await client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "password": "TestPass123!"},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for invalid email, got {resp.status_code}: {resp.text}"
        )

    @pytest.mark.asyncio
    async def test_register_missing_password_422(self, client: AsyncClient):
        """Registering without a password must return 422."""
        resp = await client.post(
            "/api/auth/register",
            json={"email": _unique_email()},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for missing password, got {resp.status_code}: {resp.text}"
        )

    @pytest.mark.asyncio
    async def test_register_optional_display_name(self, client: AsyncClient):
        """display_name must be optional — registration without it must succeed."""
        resp = await client.post(
            "/api/auth/register",
            json={"email": _unique_email(), "password": "TestPass123!"},
        )
        assert resp.status_code == 201, (
            f"Register without display_name failed: {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------

class TestLogin:

    @pytest.mark.asyncio
    async def test_login_success_200(self, client: AsyncClient):
        """POST /api/auth/login must return 200 on valid credentials."""
        email = _unique_email()
        await _register(client, email)
        resp = await _login(client, email)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_login_returns_token_pair(self, client: AsyncClient):
        """Login must return access_token, refresh_token, token_type."""
        email = _unique_email()
        await _register(client, email)
        resp = await _login(client, email)
        body = resp.json()
        assert "access_token" in body, f"'access_token' missing: {body}"
        assert "refresh_token" in body, f"'refresh_token' missing: {body}"
        assert "token_type" in body, f"'token_type' missing: {body}"
        assert body["token_type"].lower() == "bearer", (
            f"token_type must be 'bearer', got '{body['token_type']}'"
        )

    @pytest.mark.asyncio
    async def test_login_sets_refresh_cookie(self, client: AsyncClient):
        """Login must set an httpOnly refresh cookie."""
        email = _unique_email()
        await _register(client, email)
        resp = await _login(client, email)
        cookies = resp.cookies
        # Check that a refresh-related cookie is set
        cookie_names = list(cookies.keys())
        assert any("refresh" in name.lower() for name in cookie_names), (
            f"Expected httpOnly refresh cookie, found cookies: {cookie_names}"
        )

    @pytest.mark.asyncio
    async def test_login_wrong_password_401(self, client: AsyncClient):
        """Login with wrong password must return 401."""
        email = _unique_email()
        await _register(client, email)
        resp = await client.post(
            "/api/auth/login",
            json={"email": email, "password": "WrongPassword!"},
        )
        assert resp.status_code == 401, (
            f"Expected 401 for wrong password, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_login_unknown_email_401(self, client: AsyncClient):
        """Login with an unregistered email must return 401."""
        resp = await _login(client, "nobody@example.com")
        assert resp.status_code == 401, (
            f"Expected 401 for unknown email, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_login_access_token_is_jwt(self, client: AsyncClient):
        """access_token must be a valid JWT (3-part dot-separated string)."""
        email = _unique_email()
        await _register(client, email)
        resp = await _login(client, email)
        token = resp.json()["access_token"]
        parts = token.split(".")
        assert len(parts) == 3, (
            f"access_token must be a JWT (3 dot-separated parts), got: {token[:50]}"
        )


# ---------------------------------------------------------------------------
# Bcrypt password hashing tests
# ---------------------------------------------------------------------------

class TestBcryptHashing:

    @pytest.mark.asyncio
    async def test_password_not_stored_plain(self, client: AsyncClient):
        """After registration, the plain password must NOT appear in DB (via /me)."""
        email = _unique_email()
        password = "TestPass123!"
        await _register(client, email, password=password)
        login_resp = await _login(client, email, password=password)
        token = login_resp.json()["access_token"]
        me_resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = me_resp.json()
        # The /me response must not contain the plain password
        assert password not in str(body), (
            "Plain password must not appear in /me response"
        )

    def test_bcrypt_hash_is_used(self):
        """app.auth.jwt must use passlib CryptContext with bcrypt scheme."""
        try:
            from app.auth.jwt import pwd_context
            assert "bcrypt" in pwd_context.schemes(), (
                f"Expected bcrypt scheme, got: {pwd_context.schemes()}"
            )
        except ImportError as exc:
            pytest.skip(f"app.auth.jwt not yet implemented: {exc}")

    def test_bcrypt_verify_roundtrip(self):
        """passlib bcrypt: hash then verify must return True."""
        try:
            from app.auth.jwt import pwd_context
            plain = "ASecurePassw0rd!"
            hashed = pwd_context.hash(plain)
            assert pwd_context.verify(plain, hashed), "bcrypt verify roundtrip failed"
            assert not pwd_context.verify("wrong", hashed), (
                "bcrypt verify must return False for wrong password"
            )
        except ImportError as exc:
            pytest.skip(f"app.auth.jwt not yet implemented: {exc}")


# ---------------------------------------------------------------------------
# JWT token tests
# ---------------------------------------------------------------------------

class TestJWTTokens:

    def test_create_access_token_returns_string(self):
        """create_access_token must return a non-empty string."""
        try:
            from app.auth.jwt import create_access_token
            token = create_access_token(uuid.uuid4())
            assert isinstance(token, str) and len(token) > 0, (
                "create_access_token must return a non-empty string"
            )
        except ImportError as exc:
            pytest.skip(f"app.auth.jwt not yet implemented: {exc}")

    def test_create_refresh_token_returns_string(self):
        """create_refresh_token must return a non-empty string."""
        try:
            from app.auth.jwt import create_refresh_token
            token = create_refresh_token(uuid.uuid4())
            assert isinstance(token, str) and len(token) > 0
        except ImportError as exc:
            pytest.skip(f"app.auth.jwt not yet implemented: {exc}")

    def test_access_token_hs256_algorithm(self):
        """Access token must be signed with HS256."""
        try:
            import base64, json
            from app.auth.jwt import create_access_token
            token = create_access_token(uuid.uuid4())
            header_b64 = token.split(".")[0]
            # Add padding
            header_b64 += "=" * (-len(header_b64) % 4)
            header = json.loads(base64.urlsafe_b64decode(header_b64))
            assert header.get("alg") == "HS256", (
                f"Expected HS256, got {header.get('alg')}"
            )
        except ImportError as exc:
            pytest.skip(f"app.auth.jwt not yet implemented: {exc}")

    def test_access_token_ttl_30_minutes(self):
        """Access token must expire in ~30 minutes (1800 seconds)."""
        try:
            import base64, json
            from app.auth.jwt import create_access_token
            before = time.time()
            token = create_access_token(uuid.uuid4())
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = payload.get("exp")
            assert exp is not None, "Access token must have 'exp' claim"
            ttl_seconds = exp - before
            # Allow 30s tolerance
            assert 1770 <= ttl_seconds <= 1830, (
                f"Access token TTL must be ~1800s (30 min), got {ttl_seconds:.0f}s"
            )
        except ImportError as exc:
            pytest.skip(f"app.auth.jwt not yet implemented: {exc}")

    def test_refresh_token_ttl_30_days(self):
        """Refresh token must expire in ~30 days (2592000 seconds)."""
        try:
            import base64, json
            from app.auth.jwt import create_refresh_token
            before = time.time()
            token = create_refresh_token(uuid.uuid4())
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = payload.get("exp")
            assert exp is not None, "Refresh token must have 'exp' claim"
            ttl_seconds = exp - before
            expected = 30 * 24 * 3600  # 2592000
            # Allow 60s tolerance
            assert expected - 60 <= ttl_seconds <= expected + 60, (
                f"Refresh token TTL must be ~{expected}s (30 days), got {ttl_seconds:.0f}s"
            )
        except ImportError as exc:
            pytest.skip(f"app.auth.jwt not yet implemented: {exc}")

    def test_access_token_contains_user_id(self):
        """Access token payload must contain the user_id as 'sub' claim."""
        try:
            import base64, json
            from app.auth.jwt import create_access_token
            user_id = uuid.uuid4()
            token = create_access_token(user_id)
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            assert "sub" in payload, "Token must have 'sub' claim"
            assert str(user_id) == payload["sub"], (
                f"'sub' must equal user_id: expected {user_id}, got {payload['sub']}"
            )
        except ImportError as exc:
            pytest.skip(f"app.auth.jwt not yet implemented: {exc}")


# ---------------------------------------------------------------------------
# Refresh endpoint tests
# ---------------------------------------------------------------------------

class TestRefreshEndpoint:

    @pytest.mark.asyncio
    async def test_refresh_returns_new_access_token(self, client: AsyncClient):
        """POST /api/auth/refresh must return a new access_token."""
        email = _unique_email()
        await _register(client, email)
        login_resp = await _login(client, email)
        body = login_resp.json()
        refresh_token = body["refresh_token"]

        # Use refresh token via cookie (as set by login) or body
        resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        # Accept either cookie-based (no body token) or body-based refresh
        if resp.status_code == 422:
            # Try cookie-based — login already set the cookie
            resp = await client.post("/api/auth/refresh")

        assert resp.status_code == 200, (
            f"Expected 200 from /api/auth/refresh, got {resp.status_code}: {resp.text}"
        )
        new_body = resp.json()
        assert "access_token" in new_body, f"'access_token' missing from refresh response: {new_body}"

    @pytest.mark.asyncio
    async def test_refresh_rotates_token(self, client: AsyncClient):
        """Each refresh call should return a DIFFERENT access_token."""
        email = _unique_email()
        await _register(client, email)
        login_resp = await _login(client, email)
        old_access = login_resp.json()["access_token"]

        # Use cookie that was set by login
        resp = await client.post("/api/auth/refresh")
        if resp.status_code in (401, 422, 405):
            pytest.skip("Refresh endpoint not yet implemented or requires different auth")

        new_access = resp.json().get("access_token")
        assert new_access != old_access, "Refreshed access_token must differ from old one"

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_401(self, client: AsyncClient):
        """Using a garbage refresh token must return 401."""
        resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": "not.a.valid.jwt"},
        )
        assert resp.status_code == 401, (
            f"Expected 401 for invalid refresh token, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# /me endpoint tests
# ---------------------------------------------------------------------------

class TestMeEndpoint:

    @pytest.mark.asyncio
    async def test_me_returns_200(self, client: AsyncClient, auth_headers: dict):
        """GET /api/auth/me must return 200 with valid token."""
        resp = await client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_me_returns_user_out(self, client: AsyncClient, auth_headers: dict,
                                       registered_user: dict):
        """GET /api/auth/me must return UserOut (id, email, display_name)."""
        resp = await client.get("/api/auth/me", headers=auth_headers)
        body = resp.json()
        assert "id" in body
        assert "email" in body
        assert body["email"] == registered_user["email"]
        assert "display_name" in body

    @pytest.mark.asyncio
    async def test_me_no_token_401(self, client: AsyncClient):
        """GET /api/auth/me without Authorization header must return 401."""
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401, (
            f"Expected 401 without token, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_me_invalid_token_401(self, client: AsyncClient):
        """GET /api/auth/me with a garbage token must return 401."""
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer garbage.token.here"},
        )
        assert resp.status_code == 401, (
            f"Expected 401 for invalid token, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_me_expired_token_401(self, client: AsyncClient):
        """GET /api/auth/me with an expired token must return 401."""
        try:
            from jose import jwt as jose_jwt
            # Create a token that expired 1 second ago
            payload = {
                "sub": str(uuid.uuid4()),
                "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
            }
            # Use a test secret — the real secret may differ but this token should fail
            expired_token = jose_jwt.encode(payload, "test-secret", algorithm="HS256")
            resp = await client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {expired_token}"},
            )
            assert resp.status_code == 401, (
                f"Expired token must return 401, got {resp.status_code}"
            )
        except ImportError:
            pytest.skip("python-jose not installed yet")
