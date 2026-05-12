"""
Unit tests for JWT scope claim handling — Phase 5 / PR 5.5.

These tests exercise the pure helpers in ``app.auth.jwt``; no FastAPI app or
DB is required.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from jose import jwt as jose_jwt

from app.auth.jwt import (
    ALGORITHM,
    create_access_token,
    verify_scope,
)
from app.config import settings


def _decode(token: str) -> dict:
    return jose_jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])


class TestCreateAccessTokenScope:
    def test_create_access_token_with_scope_includes_claim(self):
        uid = uuid.uuid4()
        token = create_access_token(uid, scope="clip")
        payload = _decode(token)
        assert payload.get("scope") == "clip"
        assert payload.get("sub") == str(uid)
        assert payload.get("type") == "access"

    def test_create_access_token_without_scope_omits_claim(self):
        uid = uuid.uuid4()
        token = create_access_token(uid)
        payload = _decode(token)
        assert "scope" not in payload, (
            "Default token must not include a scope claim "
            f"(got payload keys: {sorted(payload.keys())})"
        )

    def test_create_access_token_explicit_none_omits_claim(self):
        uid = uuid.uuid4()
        token = create_access_token(uid, scope=None)
        payload = _decode(token)
        assert "scope" not in payload


class TestVerifyScope:
    def test_verify_scope_rejects_mismatched(self):
        payload = {"scope": "clip"}
        with pytest.raises(HTTPException) as exc:
            verify_scope(payload, required_scope="other")
        assert exc.value.status_code == 403

    def test_verify_scope_accepts_matching(self):
        payload = {"scope": "clip"}
        # Should not raise
        verify_scope(payload, required_scope="clip")

    def test_verify_scope_accepts_no_scope_for_any_check(self):
        # No scope claim = full session = always allowed for any required_scope
        payload = {}  # no 'scope' key
        verify_scope(payload, required_scope="clip")
        verify_scope(payload, required_scope="anything")

    def test_verify_scope_no_required_accepts_anything(self):
        # required_scope=None means "no scope required" → any token passes
        verify_scope({"scope": "clip"}, required_scope=None)
        verify_scope({}, required_scope=None)
