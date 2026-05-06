"""
test_upload.py — Task 2.1
Tests for POST /api/upload (generic media upload endpoint)

Covers:
  - POST /api/upload with multipart file returns {url}
  - Requires authentication (401 without token)
  - Calls blob_storage.upload_blob internally
  - Router registered at /api/upload (NOT in __init__.py — B6)
  - Module lives at backend/app/api/upload.py

Mock strategy (B15): mock blob_storage.upload_blob via unittest.mock.patch
"""
import io
import uuid
import pytest
from unittest.mock import patch, AsyncMock

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def audio_file():
    """Fake multipart audio file payload."""
    return {
        "file": ("test_audio.webm", io.BytesIO(b"RIFF fake audio content"), "audio/webm"),
    }


@pytest.fixture
def image_file():
    """Fake multipart image file payload."""
    return {
        "file": ("test_image.jpg", io.BytesIO(b"\xff\xd8\xff fake jpeg"), "image/jpeg"),
    }


# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------

class TestUploadModuleImport:
    def test_upload_module_importable(self):
        """backend/app/api/upload.py must be importable."""
        from app.api import upload  # noqa: F401

    def test_router_exported(self):
        """upload module must expose a FastAPI APIRouter named `router`."""
        from app.api.upload import router
        from fastapi import APIRouter
        assert isinstance(router, APIRouter)


# ---------------------------------------------------------------------------
# POST /api/upload — auth
# ---------------------------------------------------------------------------

class TestUploadAuth:
    async def test_upload_without_token_returns_401(self, client, audio_file):
        """Unauthenticated request must be rejected with 401."""
        resp = await client.post("/api/upload", files=audio_file)
        assert resp.status_code == 401

    async def test_upload_with_invalid_token_returns_401(self, client, audio_file):
        """Invalid Bearer token must be rejected with 401."""
        resp = await client.post(
            "/api/upload",
            files=audio_file,
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/upload — happy path
# ---------------------------------------------------------------------------

class TestUploadHappyPath:
    async def test_upload_audio_returns_url(self, client, auth_headers, audio_file):
        """
        POST /api/upload with a valid audio file should return 200 with {url}.
        blob_storage.upload_blob is mocked to avoid real Azure calls.
        """
        fake_url = "https://fakestorageaccount.blob.core.windows.net/cortex-media/audio/test.webm?sig=x"

        with patch(
            "app.api.upload.upload_blob",
            new_callable=AsyncMock,
            return_value=fake_url,
        ):
            resp = await client.post(
                "/api/upload",
                files=audio_file,
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "url" in body
        assert body["url"] == fake_url

    async def test_upload_image_returns_url(self, client, auth_headers, image_file):
        """POST /api/upload with an image file should also return 200 with {url}."""
        fake_url = "https://fakestorageaccount.blob.core.windows.net/cortex-media/image/test.jpg?sig=y"

        with patch(
            "app.api.upload.upload_blob",
            new_callable=AsyncMock,
            return_value=fake_url,
        ):
            resp = await client.post(
                "/api/upload",
                files=image_file,
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "url" in body

    async def test_upload_calls_blob_storage(self, client, auth_headers, audio_file):
        """upload_blob must be invoked exactly once when a file is uploaded."""
        fake_url = "https://example.blob.core.windows.net/cortex-media/x?sig=z"
        mock_upload = AsyncMock(return_value=fake_url)

        with patch("app.api.upload.upload_blob", mock_upload):
            await client.post(
                "/api/upload",
                files=audio_file,
                headers=auth_headers,
            )

        mock_upload.assert_called_once()

    async def test_upload_url_is_string(self, client, auth_headers, audio_file):
        """The returned url must be a non-empty string."""
        fake_url = "https://fake.blob.core.windows.net/c/p?sig=a"
        with patch("app.api.upload.upload_blob", new_callable=AsyncMock, return_value=fake_url):
            resp = await client.post(
                "/api/upload",
                files=audio_file,
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert isinstance(resp.json()["url"], str)
        assert len(resp.json()["url"]) > 0
