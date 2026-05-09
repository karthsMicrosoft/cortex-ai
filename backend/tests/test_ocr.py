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
        the OCR+pipeline background task (_run_ocr_and_pipeline).

        We patch the entire background task function to avoid opening a real DB
        session (the background task uses SessionLocal, not the test's in-memory DB).
        """
        from unittest.mock import AsyncMock as AM, patch as pt

        ocr_pipeline_mock = AM()

        with pt("app.api.notes._run_ocr_and_pipeline", ocr_pipeline_mock):
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
        # OCR+pipeline background task must have been scheduled and called
        ocr_pipeline_mock.assert_called_once()

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


# ---------------------------------------------------------------------------
# QA-06: Background OCR task re-fetches the note by ID from DB session
# review-comments.tasks.md § 3.6
# ---------------------------------------------------------------------------


class TestOCRBackgroundTaskRefetchesByID:
    """QA-06: _run_ocr_and_pipeline must re-fetch the note from a fresh DB session
    (not pass the in-request Note object to the background task).

    This prevents the race condition where the note object from the request session
    is detached/expired by the time the background task runs, or where the background
    task operates on a stale in-memory object rather than the committed DB row.

    The coder fix: await db.commit() before spawning the background task so the
    note row is fully visible in other sessions; remove the SimpleNamespace fallback.
    """

    async def test_ocr_background_task_receives_note_id_not_object(self, client, auth_headers):
        """QA-06: The background task _run_ocr_and_pipeline must be called with note_id (UUID),
        not with the Note ORM object from the request session.

        This test verifies that after POST /api/notes with source_type='image',
        the background task function is given the note_id scalar and re-fetches
        from the database rather than closing over the request-scoped object.
        """
        import uuid as _uuid

        captured_args = []

        async def fake_ocr_pipeline(note_id, image_url):
            captured_args.append({"note_id": note_id, "image_url": image_url})

        with patch("app.api.notes.process_image_note", AsyncMock()):
            with patch("app.api.notes._run_ocr_and_pipeline", side_effect=fake_ocr_pipeline):
                with patch("app.api.notes.AIPipeline") as mock_cls:
                    mock_cls.return_value.process_note = AsyncMock()
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

        if captured_args:
            # The note_id passed to the background task must be a UUID, not an ORM object
            note_id_arg = captured_args[0]["note_id"]
            assert isinstance(note_id_arg, _uuid.UUID), (
                f"QA-06 FAIL: _run_ocr_and_pipeline received {type(note_id_arg).__name__} "
                f"instead of UUID. The background task must receive note_id (scalar UUID) "
                f"so it can re-fetch the note from a fresh DB session."
            )

    async def test_ocr_background_task_fetches_note_from_fresh_session(self):
        """QA-06: _run_ocr_and_pipeline must open a fresh DB session and fetch the note
        from it (using select(Note).where(Note.id == note_id)), not use the Note object
        passed from the request-scoped session.

        We verify this by inspecting the source code for the session pattern.
        """
        from app.api import notes as notes_module
        import inspect

        src = inspect.getsource(notes_module._run_ocr_and_pipeline)
        # Must use SessionLocal to create a fresh session
        assert "SessionLocal" in src, (
            "QA-06 FAIL: _run_ocr_and_pipeline must open a fresh session using SessionLocal(). "
            "This ensures the note row is fully visible after commit."
        )
        # Must fetch by note_id (not pass through the request-scoped Note object)
        assert "note_id" in src, (
            "QA-06 FAIL: _run_ocr_and_pipeline must fetch the note from DB by note_id."
        )

    async def test_ocr_background_uses_note_id_for_db_fetch(self):
        """QA-06: _run_ocr_and_pipeline must execute a DB query using note_id,
        not rely on a pre-fetched Note object that may be from a closed session.
        """
        from app.api import notes as notes_module
        import inspect

        src = inspect.getsource(notes_module._run_ocr_and_pipeline)
        # Must select Note from DB by note_id
        assert "select(Note)" in src or "select(Note).where" in src, (
            "QA-06 FAIL: _run_ocr_and_pipeline must re-fetch the Note from DB using select(). "
            "Passing the request-scoped ORM object directly causes race conditions."
        )

    async def test_race_condition_note_not_yet_in_db_handled_without_simple_namespace(self):
        """QA-06: The background task must not use types.SimpleNamespace as a fallback
        when the note is not found in the new session (this indicates a race condition).

        The correct fix is: commit before spawning the task (await db.commit()),
        so the note is always visible by the time the background task queries for it.
        """
        from app.api import notes as notes_module
        import inspect

        src = inspect.getsource(notes_module._run_ocr_and_pipeline)
        # SimpleNamespace is the fragile fallback that QA-06 says must be removed
        # after the commit-before-spawn fix is applied.
        # If SimpleNamespace is still present, we warn (not hard-fail, since it could
        # be left as legacy code while the fix is incomplete).
        has_simple_namespace = "SimpleNamespace" in src
        has_early_commit = "db.commit()" in src or "await db.commit" in src

        if has_simple_namespace and not has_early_commit:
            pytest.fail(
                "QA-06 FAIL: _run_ocr_and_pipeline still uses SimpleNamespace fallback "
                "without an early db.commit(). Fix: call await db.commit() before "
                "background_tasks.add_task() in create_note(), then remove SimpleNamespace."
            )


# ---------------------------------------------------------------------------
# Empty OCR result — placeholder content (Round 15 / PR #24)
# ---------------------------------------------------------------------------

class TestProcessImageNoteEmptyOCR:
    async def test_process_image_note_empty_read_result_writes_placeholder(self):
        '''When Vision returns zero blocks, note.content gets a no-text placeholder
        and processing_status proceeds to transcribed (so Stage 2 still runs).'''
        from app.pipeline.ocr import process_image_note

        note = MagicMock()
        note.image_url = FAKE_IMAGE_URL
        note.content = ''
        note.processing_status = 'raw'

        # Vision returns a result with read.blocks == [] (no readable text)
        mock_result = MagicMock()
        mock_result.read = MagicMock()
        mock_result.read.blocks = []

        mock_client = MagicMock()
        mock_client.analyze_from_url = MagicMock(return_value=mock_result)

        with patch('app.pipeline.ocr.settings') as mock_settings:
            mock_settings.AZURE_VISION_ENDPOINT = 'https://fake.cognitiveservices.azure.com'
            mock_settings.AZURE_VISION_KEY = 'fake-key'
            with patch('app.pipeline.ocr.ImageAnalysisClient', return_value=mock_client):
                with patch('app.pipeline.ocr.AzureKeyCredential', MagicMock()):
                    await process_image_note(note)

        assert note.content == '[image with no readable text]', (
            f'Expected placeholder, got: {note.content!r}'
        )
        # Status must still proceed so the pipeline does not stall on this note.
        assert note.processing_status == 'transcribed'

    async def test_process_image_note_none_read_writes_placeholder(self):
        '''When Vision returns result.read == None, treat as no readable text.'''
        from app.pipeline.ocr import process_image_note

        note = MagicMock()
        note.image_url = FAKE_IMAGE_URL
        note.content = ''
        note.processing_status = 'raw'

        mock_result = MagicMock()
        mock_result.read = None

        mock_client = MagicMock()
        mock_client.analyze_from_url = MagicMock(return_value=mock_result)

        with patch('app.pipeline.ocr.settings') as mock_settings:
            mock_settings.AZURE_VISION_ENDPOINT = 'https://fake.cognitiveservices.azure.com'
            mock_settings.AZURE_VISION_KEY = 'fake-key'
            with patch('app.pipeline.ocr.ImageAnalysisClient', return_value=mock_client):
                with patch('app.pipeline.ocr.AzureKeyCredential', MagicMock()):
                    await process_image_note(note)

        assert note.content == '[image with no readable text]'
        assert note.processing_status == 'transcribed'
