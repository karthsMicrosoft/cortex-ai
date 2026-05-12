"""
Tests for persistent JWT revocation (Round 19 / SEC-07 follow-up).

Covers ``app.auth.jwt`` helpers:
  - revoke_jti        — DB INSERT + in-memory cache write, idempotent
  - is_jti_revoked    — cache hit + DB fallback, cache promotion
  - prune_expired_revoked_jtis — GC for past-`exp` rows
  - access/refresh token verification rejects revoked JTIs

These are unit-level tests using the shared SQLite fixture; integration
behaviour through the HTTP layer is covered by ``test_auth_logout``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import jwt as jwt_mod
from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    is_jti_revoked,
    prune_expired_revoked_jtis,
    revoke_jti,
)
from app.models.revoked_jti import RevokedJTI


@pytest.fixture(autouse=True)
def _clear_in_memory_cache():
    """Each test starts with an empty process-local denylist so the cache
    behaviour we're testing isn't poisoned by a previous test."""
    jwt_mod._revoked_jtis.clear()
    yield
    jwt_mod._revoked_jtis.clear()


def _future(seconds: int = 3600) -> datetime:
    return datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)


def _past(seconds: int = 3600) -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# revoke_jti
# ---------------------------------------------------------------------------

class TestRevokeJti:
    @pytest.mark.asyncio
    async def test_persists_to_db_and_cache(self, db_session):
        jti = f"jti-{uuid.uuid4()}"
        await revoke_jti(db_session, jti, _future())
        await db_session.commit()

        # Cache populated
        assert jti in jwt_mod._revoked_jtis

        # DB row present
        row = await db_session.get(RevokedJTI, jti)
        assert row is not None
        assert row.expires_at is not None

    @pytest.mark.asyncio
    async def test_idempotent_does_not_raise(self, db_session):
        jti = f"jti-{uuid.uuid4()}"
        exp = _future()
        await revoke_jti(db_session, jti, exp)
        # Calling twice must not raise; second call is a no-op.
        await revoke_jti(db_session, jti, exp)
        await db_session.commit()

        # Still exactly one row.
        row = await db_session.get(RevokedJTI, jti)
        assert row is not None


# ---------------------------------------------------------------------------
# is_jti_revoked
# ---------------------------------------------------------------------------

class TestIsJtiRevoked:
    @pytest.mark.asyncio
    async def test_returns_true_after_revoke(self, db_session):
        jti = f"jti-{uuid.uuid4()}"
        await revoke_jti(db_session, jti, _future())
        assert await is_jti_revoked(db_session, jti) is True

    @pytest.mark.asyncio
    async def test_returns_false_for_unknown_jti(self, db_session):
        assert await is_jti_revoked(db_session, f"never-{uuid.uuid4()}") is False

    @pytest.mark.asyncio
    async def test_in_memory_cache_hit_avoids_db(self, db_session):
        """Round 19: the in-memory cache must short-circuit BEFORE issuing a DB
        query so the hot path stays cheap. Verified by patching the DB
        execute call and asserting it's never invoked when the cache hit
        already resolves the question."""
        jti = f"jti-{uuid.uuid4()}"
        # Prime ONLY the cache (no DB row).
        jwt_mod._revoked_jtis.add(jti)

        original_execute = db_session.execute
        with patch.object(db_session, "execute", wraps=original_execute) as spy:
            assert await is_jti_revoked(db_session, jti) is True
            assert spy.call_count == 0, (
                "is_jti_revoked must consult the in-memory cache first; the "
                "DB execute should not be called on a cache hit."
            )

    @pytest.mark.asyncio
    async def test_db_hit_promotes_to_cache(self, db_session):
        """A positive DB lookup should promote the JTI into the cache so the
        next request in this process avoids the round trip."""
        jti = f"jti-{uuid.uuid4()}"
        # Insert directly so the cache is NOT primed.
        db_session.add(RevokedJTI(jti=jti, expires_at=_future()))
        await db_session.flush()

        assert jti not in jwt_mod._revoked_jtis
        assert await is_jti_revoked(db_session, jti) is True
        assert jti in jwt_mod._revoked_jtis  # promoted


# ---------------------------------------------------------------------------
# Token verification rejects revoked JTIs
# ---------------------------------------------------------------------------

class TestRevokedTokenRejection:
    @pytest.mark.asyncio
    async def test_revoked_access_token_returns_401(self, db_session):
        """An access token whose JTI has been revoked must be rejected by
        ``_resolve_user_from_credentials`` (i.e. ``get_current_user``)."""
        # Need a real user so the post-revocation user lookup wouldn't muddy
        # the failure mode.
        from app.models.user import User
        u = User(
            id=uuid.uuid4(),
            email=f"revtok_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="x",
        )
        db_session.add(u)
        await db_session.flush()

        token = create_access_token(u.id)
        # Decode locally to grab the JTI then revoke.
        payload = jwt_mod.decode_token(token)
        await revoke_jti(db_session, payload["jti"], _future())

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with pytest.raises(HTTPException) as ei:
            await jwt_mod._resolve_user_from_credentials(
                creds, db_session, allowed_scopes=None
            )
        assert ei.value.status_code == 401
        assert "revoked" in ei.value.detail.lower()

    @pytest.mark.asyncio
    async def test_revoked_refresh_token_blocks_rotation(self, client, db_session):
        """Round 19: a revoked refresh-token JTI must cause /api/auth/refresh
        to return 401, not silently rotate."""
        import uuid as _uuid
        email = f"rev_refresh_{_uuid.uuid4().hex[:6]}@example.com"
        reg = await client.post(
            "/api/auth/register",
            json={"email": email, "password": "Pa$$word123", "display_name": "R"},
        )
        assert reg.status_code == 201
        refresh = reg.json()["refresh_token"]

        payload = jwt_mod.decode_token(refresh)
        # Revoke through the SAME session the request handler will use (the
        # test fixture overrides get_db so it's the same `db_session`).
        await revoke_jti(db_session, payload["jti"], _future())
        await db_session.commit()

        resp = await client.post(
            "/api/auth/refresh", json={"refresh_token": refresh}
        )
        assert resp.status_code == 401
        assert "revoked" in resp.text.lower()


# ---------------------------------------------------------------------------
# prune_expired_revoked_jtis
# ---------------------------------------------------------------------------

class TestPruneExpired:
    @pytest.mark.asyncio
    async def test_deletes_only_past_expiry(self, db_session):
        live_jti = f"live-{uuid.uuid4()}"
        dead_jti = f"dead-{uuid.uuid4()}"
        await revoke_jti(db_session, live_jti, _future())
        await revoke_jti(db_session, dead_jti, _past())
        await db_session.flush()

        deleted = await prune_expired_revoked_jtis(db_session)
        assert deleted == 1

        assert await db_session.get(RevokedJTI, live_jti) is not None
        assert await db_session.get(RevokedJTI, dead_jti) is None

    @pytest.mark.asyncio
    async def test_returns_zero_when_nothing_to_prune(self, db_session):
        await revoke_jti(db_session, f"future-{uuid.uuid4()}", _future())
        await db_session.flush()
        assert await prune_expired_revoked_jtis(db_session) == 0
