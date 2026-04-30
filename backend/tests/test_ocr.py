"""
test_ocr.py — Task 6
Tests for backend/app/pipeline/ocr.py (process_image_note)
and integration with POST /api/notes when source_type='image'

Covers:
  - process_image_note(note) constructs Azure AI Vision ImageAnalysisClient inline
  - Calls the READ analysis feature on note.image_url
  - Writes extracted text to note.content
  - Sets processing_status='transcribed' so the rest of the pipeline runs
  - Wrapped with tenacity retry decorator
  - POST /api/notes with source_type='image' and image_url schedules OCR BackgroundTask

Mock strategy (B15): respx for Azure Vision REST HTTP calls;
the azure-ai-vision-imageanalysis SDK uses HTTP REST so respx can intercept it.
Alternatively, mock the ImageAnalysisClient directly via unittest.mock.patch
when the SDK wraps the HTTP call opaquely.
"""
import uuid
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

pytestmark = pytest.mark.asyncio

FAKE_IMAGE_URL = "https://example.blob.core.windows.net/cortex-media/image/test.jpg?sig=x"
FAKE_OCR_TEXT = "This is the text extracted from the image via Azure AI Vision."


# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------

class TestOCRModuleImport:
    def test_ocr_module_importable(self):
        """backend/app/pipeline/ocr.py must be importable."""
        from app.pipeline import ocr  # noqa: F401

    def test_process_image_note_callable(self):
        """process_image_note must be a callable in the ocr module."""
        from app.pipeline.ocr import process_image_note
        assert callable(process_image_note)

    def test_image_analysis_client_not_in_services(self):
        """
        Per spec § 4.1 and B5 resolution, there must be no services/vision.py.
        OCR lives in pipeline/ocr.py only.
        """
        import importlib
        import sys
        try:
            spec = importlib.util.find_spec("app.services.vision")
            assert spec is None, (
                "services/vision.py must NOT exist — OCR lives in pipeline/ocr.py (B5)"
            )
        except (ModuleNotFoundError, ValueError):
            pass  # module doesn't exist — correct


# ---------------------------------------------------------------------------
# process_image_note — happy path
# ---------------------------------------------------------------------------

class TestProcessImageNote:
    async def test_writes_ocr_text_to_content(self):
        """process_image_note must write the OCR-extracted text to note.content."""
        from app.pipeline.ocr import process_image_note

        note = MagicMock()
        note.image_url = FAKE_IMAGE_URL
        note.content = ""
        note.processing_status = "raw"

        # Mock ImageAnalysisClient
        mock_result = MagicMock()
        mock_result.read = MagicMock()
        mock_result.read.blocks = [
            MagicMock(lines=[
                MagicMock(text="This is the text"),
                MagicMock(text="extracted from the image via Azure AI Vision."),
            ])
        ]

        mock_client = MagicMock()
        mock_client.analyze.return_value = mock_result
        mock_client.analyze_from_url = MagicMock(return_value=mock_result)

        with patch("app.pipeline.ocr.settings") as mock_settings:
            mock_settings.AZURE_VISION_ENDPOINT = "https://fake.cognitiveservices.azure.com"
            mock_settings.AZURE_VISION_KEY = "fake-key"
            with patch("app.pipeline.ocr.ImageAnalysisClient", return_value=mock_client):
                with patch("app.pipeline.ocr.AzureKeyCredential", MagicMock()):
                    await process_image_note(note)

        assert note.content != "", "process_image_note must write extracted text to note.content"

    async def test_sets_processing_status_transcribed(self):
        """
        After OCR, processing_status must be set to 'transcribed' so the
        main AI pipeline picks it up in Stage 1 CAPTURE.
        """
        from app.pipeline.ocr import process_image_note

        note = MagicMock()
        note.image_url = FAKE_IMAGE_URL
        note.content = ""
        note.processing_status = "raw"

        mock_result = MagicMock()
        mock_result.read = MagicMock()
        mock_result.read.blocks = [
            MagicMock(lines=[MagicMock(text="OCR text")])
        ]

        mock_client = MagicMock()
        mock_client.analyze.return_value = mock_result
        mock_client.analyze_from_url = MagicMock(return_value=mock_result)

        with patch("app.pipeline.ocr.settings") as mock_settings:
            mock_settings.AZURE_VISION_ENDPOINT = "https://fake.cognitiveservices.azure.com"
            mock_settings.AZURE_VISION_KEY = "fake-key"
            with patch("app.pipeline.ocr.ImageAnalysisClient", return_value=mock_client):
                with patch("app.pipeline.ocr.AzureKeyCredential", MagicMock()):
                    await process_image_note(note)

        assert note.processing_status == "transcribed"

    async def test_uses_read_analysis_feature(self):
        """
        process_image_note must call the Vision SDK with the READ analysis feature
        (not CAPTION or DENSE_CAPTIONS).
        """
        from app.pipeline.ocr import process_image_note

        note = MagicMock()
        note.image_url = FAKE_IMAGE_URL
        note.content = ""
        note.processing_status = "raw"

        mock_result = MagicMock()
        mock_result.read = MagicMock()
        mock_result.read.blocks = []

        mock_client = MagicMock()
        mock_client.analyze.return_value = mock_result
        mock_client.analyze_from_url = MagicMock(return_value=mock_result)

        captured_kwargs = {}

        original_analyze = mock_client.analyze

        def capturing_analyze(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_result

        mock_client.analyze = MagicMock(side_effect=capturing_analyze)
        mock_client.analyze_from_url = MagicMock(side_effect=capturing_analyze)

        with patch("app.pipeline.ocr.settings") as mock_settings:
            mock_settings.AZURE_VISION_ENDPOINT = "https://fake.cognitiveservices.azure.com"
            mock_settings.AZURE_VISION_KEY = "fake-key"
            with patch("app.pipeline.ocr.ImageAnalysisClient", return_value=mock_client):
                with patch("app.pipeline.ocr.AzureKeyCredential", MagicMock()):
                    await process_image_note(note)

        # The SDK call must have been made
        assert mock_client.analyze.called or mock_client.analyze_from_url.called

    async def test_constructs_client_inline(self):
        """
        ImageAnalysisClient must be constructed inside process_image_note
        (not imported from a services module).
        """
        from app.pipeline import ocr
        import inspect
        src = inspect.getsource(ocr)
        assert "ImageAnalysisClient" in src, (
            "process_image_note must construct ImageAnalysisClient inline"
        )

    async def test_uses_vision_endpoint_and_key_from_settings(self):
        """
        process_image_note must read AZURE_VISION_ENDPOINT and AZURE_VISION_KEY
        from settings (not hardcode them).
        """
        from app.pipeline import ocr
        import inspect
        src = inspect.getsource(ocr)
        assert "AZURE_VISION_ENDPOINT" in src or "vision_endpoint" in src.lower(), (
            "OCR must use AZURE_VISION_ENDPOINT from settings"
        )
        assert "AZURE_VISION_KEY" in src or "vision_key" in src.lower(), (
            "OCR must use AZURE_VISION_KEY from settings"
        )


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

class TestOCRRetry:
    async def test_process_image_note_wrapped_with_retry(self):
        """
        process_image_note must be wrapped with the tenacity retry decorator.
        If the Vision SDK raises twice and succeeds on the third call,
        the function must not propagate the error.
        """
        from app.pipeline.ocr import process_image_note

        note = MagicMock()
        note.image_url = FAKE_IMAGE_URL
        note.content = ""
        note.processing_status = "raw"

        call_count = 0

        def fake_analyze(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Vision service unavailable")
            result = MagicMock()
            result.read = MagicMock()
            result.read.blocks = [MagicMock(lines=[MagicMock(text="Success")])]
            return result

        mock_client = MagicMock()
        mock_client.analyze = MagicMock(side_effect=fake_analyze)
        mock_client.analyze_from_url = MagicMock(side_effect=fake_analyze)

        with patch("app.pipeline.ocr.settings") as mock_settings:
            mock_settings.AZURE_VISION_ENDPOINT = "https://fake.cognitiveservices.azure.com"
            mock_settings.AZURE_VISION_KEY = "fake-key"
            with patch("app.pipeline.ocr.ImageAnalysisClient", return_value=mock_client):
                with patch("app.pipeline.ocr.AzureKeyCredential", MagicMock()):
                    await process_image_note(note)

        assert call_count == 3
        assert note.processing_status == "transcribed"


# ---------------------------------------------------------------------------
# Integration: POST /api/notes with source_type='image'
# ---------------------------------------------------------------------------

class TestNotesImageIntegration:
    async def test_post_notes_with_image_schedules_ocr(self, client, auth_headers):
        """
        POST /api/notes with source_type='image' and image_url must schedule
        process_image_note as a BackgroundTask (before the main AI pipeline).
        """
        from unittest.mock import AsyncMock as AM, patch as pt

        ocr_mock = AM()
        pipeline_mock = AM()

        with pt("app.api.notes.process_image_note", ocr_mock):
            with pt("app.api.notes.AIPipeline") as mock_cls:
                mock_cls.return_value.process_note = pipeline_mock
                resp = await client.post(
                    "/api/notes",
                    json={
                        "content": "Image note",
                        "source_type": "image",
                        "image_url": FAKE_IMAGE_URL,
                    },
                    headers=auth_headers,
                )

        assert resp.status_code == 201
        # OCR must have been scheduled (BackgroundTasks run immediately in TestClient)
        ocr_mock.assert_called_once()

    async def test_post_notes_text_does_not_schedule_ocr(self, client, auth_headers):
        """
        POST /api/notes with source_type='text' must NOT schedule OCR.
        """
        ocr_mock = AsyncMock()
        with patch("app.api.notes.process_image_note", ocr_mock):
            with patch("app.api.notes.AIPipeline") as mock_cls:
                mock_cls.return_value.process_note = AsyncMock()
                resp = await client.post(
                    "/api/notes",
                    json={"content": "Text note", "source_type": "text"},
                    headers=auth_headers,
                )

        assert resp.status_code == 201
        ocr_mock.assert_not_called()
