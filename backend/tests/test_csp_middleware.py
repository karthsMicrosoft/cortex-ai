"""Round 20 / PR delta — Strict Content-Security-Policy middleware tests.

Verifies that every backend response carries the locked-down CSP header
``default-src 'none'; frame-ancestors 'none'`` plus the supporting
``X-Content-Type-Options`` and ``Referrer-Policy`` hardening headers.
The CSP must be present on:

* the root path,
* normal API routes (``/api/health``),
* error responses produced by validation/exception handlers.

DECISIONS § 22v references this middleware as the mitigation that
closes the XSS surface created by storing the refresh token in
``localStorage``.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient


def _get_app():
    try:
        from app.main import app
        return app
    except ImportError as exc:  # pragma: no cover - environment skip
        pytest.skip(f"app.main not yet importable: {exc}")


def _get_csp_value():
    try:
        from app.middleware.csp import CSP_VALUE
        return CSP_VALUE
    except ImportError as exc:  # pragma: no cover - environment skip
        pytest.skip(f"csp middleware not yet importable: {exc}")


@pytest.mark.asyncio
async def test_csp_header_present_on_root():
    app = _get_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/")
    assert "content-security-policy" in {k.lower() for k in resp.headers.keys()}
    assert resp.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"


@pytest.mark.asyncio
async def test_csp_header_present_on_api_route():
    app = _get_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health")
    assert resp.status_code == 200
    assert resp.headers.get("content-security-policy") == "default-src 'none'; frame-ancestors 'none'"


@pytest.mark.asyncio
async def test_csp_header_present_on_error_response():
    """Error responses (e.g. 422 from path validation) must also carry the CSP."""
    app = _get_app()
    transport = ASGITransport(app=app)
    bad = "not-a-uuid"
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/api/notes/{bad}")
    # Could be 401 (auth) or 422 (validation) depending on middleware order.
    # Either way the response must have the CSP header attached.
    assert resp.status_code >= 400
    assert resp.headers.get("content-security-policy") == "default-src 'none'; frame-ancestors 'none'"


def test_csp_value_blocks_default_src():
    csp = _get_csp_value()
    assert "default-src 'none'" in csp


def test_csp_value_blocks_frame_ancestors():
    csp = _get_csp_value()
    assert "frame-ancestors 'none'" in csp


@pytest.mark.asyncio
async def test_x_content_type_options_nosniff():
    app = _get_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.asyncio
async def test_referrer_policy_no_referrer():
    app = _get_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health")
    assert resp.headers.get("referrer-policy") == "no-referrer"
