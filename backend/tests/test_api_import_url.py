"""
Endpoint integration tests for POST /api/import/url — Phase 5 / PR 5.2.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.note import Note
from app.services import url_ingest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_extract_ok(
    *,
    final_url: str = "https://example.com/article",
    title: str = "An Article",
    content: str = "Body text " * 100,
):
    """Patch fetch_and_extract to succeed with a fixed payload."""
    return patch(
        "app.api.import_url.fetch_and_extract",
        new=AsyncMock(
            return_value={
                "title": title,
                "content": content,
                "final_url": final_url,
            }
        ),
    )


# ---------------------------------------------------------------------------
# Auth + URL validation
# ---------------------------------------------------------------------------

class TestAuthAndValidation:
    async def test_import_url_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/import/url",
            json={"url": "https://example.com/x"},
        )
        assert resp.status_code in (401, 403), resp.text

    async def test_import_url_validates_url_400(
        self, client: AsyncClient, auth_headers: dict
    ):
        for bad in ["file:///etc/passwd", "ftp://x.com", "not-a-url", ""]:
            resp = await client.post(
                "/api/import/url",
                json={"url": bad},
                headers=auth_headers,
            )
            assert resp.status_code in (400, 422), (
                f"{bad!r} should be 400/422, got {resp.status_code}: {resp.text}"
            )


# ---------------------------------------------------------------------------
# SSRF — blocked IPs
# ---------------------------------------------------------------------------

class TestSSRFBlocks:
    async def test_import_url_blocks_private_ip_403(
        self, client: AsyncClient, auth_headers: dict
    ):
        with patch(
            "app.api.import_url.fetch_and_extract",
            new=AsyncMock(side_effect=url_ingest.PrivateIPError("private")),
        ):
            resp = await client.post(
                "/api/import/url",
                json={"url": "http://10.0.0.1/x"},
                headers=auth_headers,
            )
            assert resp.status_code == 403, resp.text

    async def test_import_url_blocks_imds_403(
        self, client: AsyncClient, auth_headers: dict
    ):
        # Azure IMDS — most important block. We don't need to mock here because
        # 169.254.169.254 is parsed as an IP literal and rejected pre-fetch.
        resp = await client.post(
            "/api/import/url",
            json={"url": "http://169.254.169.254/metadata"},
            headers=auth_headers,
        )
        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    async def test_import_url_happy_path_creates_note(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session,
    ):
        body = "This is the article body. " * 20
        with _mock_extract_ok(
            title="Hello World",
            content=body,
            final_url="https://example.com/final",
        ):
            resp = await client.post(
                "/api/import/url",
                json={"url": "https://example.com/article"},
                headers=auth_headers,
            )

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["source_url"] == "https://example.com/final"
        assert data["source_title"] == "Hello World"
        assert data["char_count"] == len(body)
        assert "note_id" in data

        # Verify a row landed in the notes table.
        row = (
            await db_session.execute(
                select(Note).where(Note.id == __import__("uuid").UUID(data["note_id"]))
            )
        ).scalar_one()
        assert row.source_url == "https://example.com/final"
        assert row.source_title == "Hello World"
        assert row.source_type == "text"
        assert row.processing_status == "raw"
        assert body[:200] in row.content


# ---------------------------------------------------------------------------
# Error contracts (per upstream exception)
# ---------------------------------------------------------------------------

class TestErrorContracts:
    async def test_import_url_too_large_413(
        self, client: AsyncClient, auth_headers: dict
    ):
        with patch(
            "app.api.import_url.fetch_and_extract",
            new=AsyncMock(side_effect=url_ingest.ContentTooLargeError("too big")),
        ):
            resp = await client.post(
                "/api/import/url",
                json={"url": "https://example.com/big"},
                headers=auth_headers,
            )
            assert resp.status_code == 413, resp.text

    async def test_import_url_unsupported_type_415(
        self, client: AsyncClient, auth_headers: dict
    ):
        with patch(
            "app.api.import_url.fetch_and_extract",
            new=AsyncMock(
                side_effect=url_ingest.UnsupportedContentTypeError("application/json")
            ),
        ):
            resp = await client.post(
                "/api/import/url",
                json={"url": "https://example.com/api.json"},
                headers=auth_headers,
            )
            assert resp.status_code == 415, resp.text

    async def test_import_url_extraction_empty_422(
        self, client: AsyncClient, auth_headers: dict
    ):
        with patch(
            "app.api.import_url.fetch_and_extract",
            new=AsyncMock(side_effect=url_ingest.ExtractionEmptyError("nothing")),
        ):
            resp = await client.post(
                "/api/import/url",
                json={"url": "https://example.com/empty"},
                headers=auth_headers,
            )
            assert resp.status_code == 422, resp.text

    async def test_import_url_upstream_error_502(
        self, client: AsyncClient, auth_headers: dict
    ):
        with patch(
            "app.api.import_url.fetch_and_extract",
            new=AsyncMock(side_effect=url_ingest.UpstreamError("500 from origin")),
        ):
            resp = await client.post(
                "/api/import/url",
                json={"url": "https://example.com/fail"},
                headers=auth_headers,
            )
            assert resp.status_code == 502, resp.text

    async def test_import_url_timeout_504(
        self, client: AsyncClient, auth_headers: dict
    ):
        with patch(
            "app.api.import_url.fetch_and_extract",
            new=AsyncMock(side_effect=url_ingest.UpstreamTimeoutError("timeout")),
        ):
            resp = await client.post(
                "/api/import/url",
                json={"url": "https://example.com/slow"},
                headers=auth_headers,
            )
            assert resp.status_code == 504, resp.text


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------

class TestRateLimit:
    async def test_import_url_rate_limit_30_per_hour(
        self, client: AsyncClient, auth_headers: dict
    ):
        with _mock_extract_ok():
            for i in range(30):
                resp = await client.post(
                    "/api/import/url",
                    json={"url": f"https://example.com/n{i}"},
                    headers=auth_headers,
                )
                assert resp.status_code == 201, (
                    f"call #{i+1} should succeed, got {resp.status_code}: {resp.text}"
                )

            resp = await client.post(
                "/api/import/url",
                json={"url": "https://example.com/last"},
                headers=auth_headers,
            )
            assert resp.status_code == 429, resp.text
            assert "retry-after" in {k.lower() for k in resp.headers.keys()}
