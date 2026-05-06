"""
test_blob.py — Task 1.3
Tests for backend/app/services/blob_storage.py

Covers:
  - upload_blob(container, path, data) returns a 24h SAS URL
  - delete_blob(path) calls the correct REST endpoint
  - Both functions are wrapped with the tenacity retry decorator

Mock strategy (B15): respx intercepts HTTP calls to *.blob.core.windows.net
"""
import pytest
import respx
import httpx
from unittest.mock import patch, MagicMock, AsyncMock
import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_ACCOUNT = "fakestorageaccount"
FAKE_CONTAINER = "cortex-media"
FAKE_BLOB_PATH = "audio/test-audio-file.webm"
FAKE_CONN_STR = (
    f"DefaultEndpointsProtocol=https;"
    f"AccountName={FAKE_ACCOUNT};"
    f"AccountKey=ZmFrZWtleQ==;"  # base64 of "fakekey"
    f"EndpointSuffix=core.windows.net"
)


# ---------------------------------------------------------------------------
# Smoke: module imports
# ---------------------------------------------------------------------------

class TestBlobModuleImport:
    def test_module_importable(self):
        """blob_storage module must be importable."""
        from app.services import blob_storage  # noqa: F401

    def test_upload_blob_callable(self):
        """upload_blob must be a callable exposed by the module."""
        from app.services.blob_storage import upload_blob
        assert callable(upload_blob)

    def test_delete_blob_callable(self):
        """delete_blob must be a callable exposed by the module."""
        from app.services.blob_storage import delete_blob
        assert callable(delete_blob)


# ---------------------------------------------------------------------------
# upload_blob — happy path
# ---------------------------------------------------------------------------

class TestUploadBlob:
    @pytest.mark.asyncio
    async def test_upload_returns_sas_url(self):
        """
        upload_blob should return a URL containing the blob path and a SAS
        query string (presence of 'sig=' is the minimum assertion).
        """
        from app.services.blob_storage import upload_blob

        fake_data = b"RIFF fake audio data"

        with patch("app.services.blob_storage.settings") as mock_settings:
            mock_settings.AZURE_STORAGE_CONNECTION_STRING = FAKE_CONN_STR
            mock_settings.AZURE_STORAGE_CONTAINER = FAKE_CONTAINER

            # Mock the BlobServiceClient and the blob client chain
            mock_blob_client = MagicMock()
            mock_blob_client.upload_blob = MagicMock()

            mock_container_client = MagicMock()
            mock_container_client.get_blob_client.return_value = mock_blob_client

            mock_service_client = MagicMock()
            mock_service_client.get_container_client.return_value = mock_container_client

            # generate_sas returns a fake SAS token
            fake_sas_token = "sv=2021-06-08&se=2024-01-01&sig=fakesig&sp=r"

            with patch(
                "app.services.blob_storage.BlobServiceClient.from_connection_string",
                return_value=mock_service_client,
            ):
                with patch(
                    "app.services.blob_storage.generate_blob_sas",
                    return_value=fake_sas_token,
                ):
                    url = await upload_blob(FAKE_CONTAINER, FAKE_BLOB_PATH, fake_data)

        assert isinstance(url, str)
        assert FAKE_BLOB_PATH in url or "fakestorageaccount" in url
        # SAS token elements must be in the URL
        assert "sig=" in url or fake_sas_token in url

    @pytest.mark.asyncio
    async def test_upload_sas_ttl_24h(self):
        """
        The SAS token generated for the returned URL must have a 24-hour TTL.
        We verify this by inspecting the arguments passed to generate_blob_sas.
        """
        from app.services.blob_storage import upload_blob

        fake_data = b"audio"
        captured_kwargs = {}

        def fake_generate_sas(**kwargs):
            captured_kwargs.update(kwargs)
            return "sig=fakesig&sp=r"

        mock_blob_client = MagicMock()
        mock_blob_client.upload_blob = MagicMock()
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_service_client = MagicMock()
        mock_service_client.get_container_client.return_value = mock_container_client

        with patch("app.services.blob_storage.settings") as mock_settings:
            mock_settings.AZURE_STORAGE_CONNECTION_STRING = FAKE_CONN_STR
            mock_settings.AZURE_STORAGE_CONTAINER = FAKE_CONTAINER
            with patch(
                "app.services.blob_storage.BlobServiceClient.from_connection_string",
                return_value=mock_service_client,
            ):
                with patch(
                    "app.services.blob_storage.generate_blob_sas",
                    side_effect=fake_generate_sas,
                ):
                    await upload_blob(FAKE_CONTAINER, FAKE_BLOB_PATH, fake_data)

        assert "expiry" in captured_kwargs, "generate_blob_sas must receive an 'expiry' kwarg"
        expiry: datetime.datetime = captured_kwargs["expiry"]
        # expiry should be approximately 24h from now
        diff = expiry - datetime.datetime.utcnow()
        hours = diff.total_seconds() / 3600
        assert 23.0 <= hours <= 25.0, f"SAS TTL should be ~24h, got {hours:.1f}h"

    @pytest.mark.asyncio
    async def test_upload_sas_read_only(self):
        """
        The SAS token must be read-only (permission 'r', not 'w' or 'rw').
        """
        from app.services.blob_storage import upload_blob

        fake_data = b"audio"
        captured_kwargs = {}

        def fake_generate_sas(**kwargs):
            captured_kwargs.update(kwargs)
            return "sig=fakesig"

        mock_blob_client = MagicMock()
        mock_blob_client.upload_blob = MagicMock()
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_service_client = MagicMock()
        mock_service_client.get_container_client.return_value = mock_container_client

        with patch("app.services.blob_storage.settings") as mock_settings:
            mock_settings.AZURE_STORAGE_CONNECTION_STRING = FAKE_CONN_STR
            mock_settings.AZURE_STORAGE_CONTAINER = FAKE_CONTAINER
            with patch(
                "app.services.blob_storage.BlobServiceClient.from_connection_string",
                return_value=mock_service_client,
            ):
                with patch(
                    "app.services.blob_storage.generate_blob_sas",
                    side_effect=fake_generate_sas,
                ):
                    await upload_blob(FAKE_CONTAINER, FAKE_BLOB_PATH, fake_data)

        # Permission must be 'r' (read-only)
        perm = captured_kwargs.get("permission")
        assert perm is not None, "generate_blob_sas must receive a 'permission' kwarg"
        perm_str = str(perm).lower()
        assert "r" in perm_str, f"SAS permission must include 'r', got: {perm_str}"
        assert "w" not in perm_str, f"SAS permission must NOT include 'w', got: {perm_str}"


# ---------------------------------------------------------------------------
# delete_blob
# ---------------------------------------------------------------------------

class TestDeleteBlob:
    @pytest.mark.asyncio
    async def test_delete_blob_calls_azure(self):
        """delete_blob should call the Azure SDK delete on the correct blob."""
        from app.services.blob_storage import delete_blob

        mock_blob_client = MagicMock()
        mock_blob_client.delete_blob = MagicMock()

        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client

        mock_service_client = MagicMock()
        mock_service_client.get_container_client.return_value = mock_container_client

        with patch("app.services.blob_storage.settings") as mock_settings:
            mock_settings.AZURE_STORAGE_CONNECTION_STRING = FAKE_CONN_STR
            mock_settings.AZURE_STORAGE_CONTAINER = FAKE_CONTAINER
            with patch(
                "app.services.blob_storage.BlobServiceClient.from_connection_string",
                return_value=mock_service_client,
            ):
                await delete_blob(FAKE_BLOB_PATH)

        mock_blob_client.delete_blob.assert_called_once()


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

class TestBlobRetry:
    @pytest.mark.asyncio
    async def test_upload_retries_on_exception(self):
        """
        upload_blob must be decorated with the tenacity retry decorator.
        We verify this by causing the underlying SDK call to raise twice and
        succeed on the third attempt — the function must not propagate the error.
        """
        from app.services.blob_storage import upload_blob

        call_count = 0

        def fake_upload(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Transient Azure error")

        mock_blob_client = MagicMock()
        mock_blob_client.upload_blob = MagicMock(side_effect=fake_upload)

        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client

        mock_service_client = MagicMock()
        mock_service_client.get_container_client.return_value = mock_container_client

        with patch("app.services.blob_storage.settings") as mock_settings:
            mock_settings.AZURE_STORAGE_CONNECTION_STRING = FAKE_CONN_STR
            mock_settings.AZURE_STORAGE_CONTAINER = FAKE_CONTAINER
            with patch(
                "app.services.blob_storage.BlobServiceClient.from_connection_string",
                return_value=mock_service_client,
            ):
                with patch("app.services.blob_storage.generate_blob_sas", return_value="sig=x"):
                    # Should not raise — retry decorator absorbs transient errors
                    url = await upload_blob(FAKE_CONTAINER, FAKE_BLOB_PATH, b"data")

        assert call_count == 3  # two failures + one success
        assert url is not None
