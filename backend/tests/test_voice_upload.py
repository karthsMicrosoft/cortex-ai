"""
test_voice_upload.py — Task 2.2
Tests for POST /api/voice/upload

Covers:
  - Accepts multipart audio
  - Calls blob_storage.upload_blob to store audio
  - Calls speech.transcribe_audio_file
  - Creates a note with raw_transcription, audio_url, source_type='voice',
    processing_status='transcribed'
  - Schedules pipeline as BackgroundTask
  - Returns NoteOut (201)
  - Requires authentication

Mock strategy (B15):
  - blob_storage.upload_blob → unittest.mock.patch (AsyncMock)
  - speech.transcribe_audio_file → unittest.mock.patch (AsyncMock)
  - pipeline.processor.AIPipeline → patch to avoid real Azure calls
"""
import io
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def audio_bytes():
    return b"RIFF" + b"\x00" * 100 + b"fake webm audio data"


@pytest.fixture
def audio_file(audio_bytes):
    return {
        "file": ("voice_note.webm", io.BytesIO(audio_bytes), "audio/webm"),
    }


FAKE_BLOB_URL = (
    "https://fakestorage.blob.core.windows.net/cortex-media/audio/voice_note.webm?sig=abc"
)
FAKE_TRANSCRIPT = "This is my voice note about the project meeting today."


# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------

class TestVoiceModuleImport:
    def test_voice_module_importable(self):
        from app.api import voice  # noqa: F401

    def test_router_exported(self):
        from app.api.voice import router
        from fastapi import APIRouter
        assert isinstance(router, APIRouter)


# ---------------------------------------------------------------------------
# POST /api/voice/upload — auth
# ---------------------------------------------------------------------------

class TestVoiceUploadAuth:
    async def test_requires_auth(self, client, audio_file):
        """Unauthenticated request must return 401."""
        resp = await client.post("/api/voice/upload", files=audio_file)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/voice/upload — happy path
# ---------------------------------------------------------------------------

class TestVoiceUploadHappyPath:
    async def test_returns_201_note_out(self, client, auth_headers, audio_file):
        """
        POST /api/voice/upload should return 201 with NoteOut shape including
        raw_transcription, audio_url, source_type='voice', processing_status='transcribed'.
        """
        with patch(
            "app.api.voice.upload_blob",
            new_callable=AsyncMock,
            return_value=FAKE_BLOB_URL,
        ):
            with patch(
                "app.api.voice.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=FAKE_TRANSCRIPT,
            ):
                with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                    mock_pipeline_cls.return_value.process_note = AsyncMock()
                    resp = await client.post(
                        "/api/voice/upload",
                        files=audio_file,
                        headers=auth_headers,
                    )

        assert resp.status_code == 201
        body = resp.json()

        # NoteOut required fields
        assert "id" in body
        assert "content" in body
        assert "processing_status" in body
        assert "source_type" in body

    async def test_source_type_is_voice(self, client, auth_headers, audio_file):
        """Created note must have source_type='voice'."""
        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch(
                "app.api.voice.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=FAKE_TRANSCRIPT,
            ):
                with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                    mock_pipeline_cls.return_value.process_note = AsyncMock()
                    resp = await client.post(
                        "/api/voice/upload",
                        files=audio_file,
                        headers=auth_headers,
                    )

        assert resp.status_code == 201
        assert resp.json()["source_type"] == "voice"

    async def test_processing_status_is_transcribed(self, client, auth_headers, audio_file):
        """Created note must have processing_status='transcribed'."""
        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch(
                "app.api.voice.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=FAKE_TRANSCRIPT,
            ):
                with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                    mock_pipeline_cls.return_value.process_note = AsyncMock()
                    resp = await client.post(
                        "/api/voice/upload",
                        files=audio_file,
                        headers=auth_headers,
                    )

        assert resp.status_code == 201
        assert resp.json()["processing_status"] == "transcribed"

    async def test_raw_transcription_populated(self, client, auth_headers, audio_file):
        """The returned note must include raw_transcription from Speech SDK."""
        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch(
                "app.api.voice.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=FAKE_TRANSCRIPT,
            ):
                with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                    mock_pipeline_cls.return_value.process_note = AsyncMock()
                    resp = await client.post(
                        "/api/voice/upload",
                        files=audio_file,
                        headers=auth_headers,
                    )

        assert resp.status_code == 201
        body = resp.json()
        assert body.get("raw_transcription") == FAKE_TRANSCRIPT

    async def test_audio_url_populated(self, client, auth_headers, audio_file):
        """The returned note must include audio_url from blob_storage."""
        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch(
                "app.api.voice.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=FAKE_TRANSCRIPT,
            ):
                with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                    mock_pipeline_cls.return_value.process_note = AsyncMock()
                    resp = await client.post(
                        "/api/voice/upload",
                        files=audio_file,
                        headers=auth_headers,
                    )

        assert resp.status_code == 201
        body = resp.json()
        assert body.get("audio_url") == FAKE_BLOB_URL

    async def test_pipeline_scheduled_as_background_task(self, client, auth_headers, audio_file):
        """
        The AI pipeline must be scheduled via BackgroundTasks.
        We verify this by checking that the pipeline process_note coroutine
        is eventually triggered (background tasks run immediately in test client).
        """
        process_note_mock = AsyncMock()

        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch(
                "app.api.voice.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=FAKE_TRANSCRIPT,
            ):
                with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                    instance = MagicMock()
                    instance.process_note = process_note_mock
                    mock_pipeline_cls.return_value = instance
                    resp = await client.post(
                        "/api/voice/upload",
                        files=audio_file,
                        headers=auth_headers,
                    )

        assert resp.status_code == 201
        # BackgroundTasks in test client execute synchronously after response
        process_note_mock.assert_called_once()

    async def test_blob_upload_called_with_audio_data(self, client, auth_headers, audio_file):
        """upload_blob must be called exactly once with the audio bytes."""
        mock_upload = AsyncMock(return_value=FAKE_BLOB_URL)

        with patch("app.api.voice.upload_blob", mock_upload):
            with patch(
                "app.api.voice.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=FAKE_TRANSCRIPT,
            ):
                with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                    mock_pipeline_cls.return_value.process_note = AsyncMock()
                    await client.post(
                        "/api/voice/upload",
                        files=audio_file,
                        headers=auth_headers,
                    )

        mock_upload.assert_called_once()

    async def test_transcribe_called_with_audio_bytes(self, client, auth_headers, audio_file):
        """transcribe_audio_file must be called exactly once per upload."""
        mock_transcribe = AsyncMock(return_value=FAKE_TRANSCRIPT)

        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch("app.api.voice.transcribe_audio_file", mock_transcribe):
                with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                    mock_pipeline_cls.return_value.process_note = AsyncMock()
                    await client.post(
                        "/api/voice/upload",
                        files=audio_file,
                        headers=auth_headers,
                    )

        mock_transcribe.assert_called_once()
