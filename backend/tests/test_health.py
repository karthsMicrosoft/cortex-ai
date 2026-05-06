"""
Task 2 — Health endpoint tests (TDD red phase).

Tests the GET /api/health endpoint as defined in:
  - design.md § API/Interfaces
  - us-1-foundation.tasks.md Task 2.5

Expected behaviour:
  - Returns HTTP 200
  - Body is {"status": "ok"}
  - No auth required
"""
import pytest
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Helpers — import app without the conftest client fixture so we can
# test the unauthenticated path independently.
# ---------------------------------------------------------------------------

def _get_app():
    try:
        from app.main import app
        return app
    except ImportError as exc:
        pytest.skip(f"app.main not yet implemented: {exc}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Tests for GET /api/health."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self):
        """Health endpoint must return HTTP 200."""
        app = _get_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_health_returns_status_ok(self):
        """Health endpoint body must be {\"status\": \"ok\"}."""
        app = _get_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/health")
        body = resp.json()
        assert "status" in body, f"'status' key missing from response: {body}"
        assert body["status"] == "ok", f"Expected 'ok', got '{body['status']}'"

    @pytest.mark.asyncio
    async def test_health_no_auth_required(self):
        """Health endpoint must be publicly accessible (no Authorization header)."""
        app = _get_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Deliberately send NO Authorization header
            resp = await ac.get("/api/health")
        assert resp.status_code == 200, (
            f"Health endpoint returned {resp.status_code}; must not require auth"
        )

    @pytest.mark.asyncio
    async def test_health_content_type_json(self):
        """Health endpoint must return JSON content-type."""
        app = _get_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/health")
        content_type = resp.headers.get("content-type", "")
        assert "application/json" in content_type, (
            f"Expected application/json, got: {content_type}"
        )

    @pytest.mark.asyncio
    async def test_health_method_not_allowed(self):
        """POST /api/health should return 405 (method not allowed)."""
        app = _get_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/health")
        assert resp.status_code == 405, (
            f"Expected 405 Method Not Allowed, got {resp.status_code}"
        )
