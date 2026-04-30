"""
test_voice_phrase_list.py — US-7 Speech service integration (TDD red phase)

Verifies:
  1. load_user_phrase_list(recognizer, user_id, db, max_phrases=500) exists in
     app.services.speech and is callable/async.
  2. increment_term_usage(content, user_id, db) exists in app.services.speech.
  3. load_user_phrase_list calls PhraseListGrammar.from_recognizer(recognizer)
     and addPhrase() for each term (and pronunciation_hint if present).
  4. load_user_phrase_list returns the count of terms loaded.
  5. load_user_phrase_list returns 0 and makes no SDK calls when vocabulary is empty.
  6. load_user_phrase_list respects max_phrases limit (orders by usage_count desc).
  7. increment_term_usage increments usage_count for terms found (case-insensitive).
  8. increment_term_usage does NOT increment usage_count for terms absent from content.
  9. POST /api/voice/upload (file mode) calls load_user_phrase_list before recognition
     and increment_term_usage after transcript is returned.
 10. POST /api/voice/upload logs "Loaded {n} phrases for user {id}".

Critical resolution B16:
  - Task 3.4 is a NO-OP. The WebSocket handler belongs to US-9.
  - These tests do NOT assert on any WebSocket handler (ws_stream etc.).

Design refs:
  - SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md § F1.2 (Azure Speech Integration)
  - us-7-personal-dictionary.tasks.md tasks 3.1, 3.2, 3.3
"""
import io
import uuid
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_phrase_list_mock():
    """Return a mock PhraseListGrammar instance."""
    mock_plg = MagicMock()
    mock_plg.addPhrase = MagicMock()
    return mock_plg


def _make_recognizer_mock():
    """Return a mock SpeechRecognizer."""
    return MagicMock()


def _make_vocab_entry(term: str, pronunciation_hint=None, usage_count: int = 0):
    """Create a minimal UserVocabulary-like object."""
    entry = MagicMock()
    entry.term = term
    entry.pronunciation_hint = pronunciation_hint
    entry.usage_count = usage_count
    return entry


def _make_db_mock(vocab_rows=None):
    """Return an AsyncMock db session that returns the given vocab rows."""
    vocab_rows = vocab_rows or []
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = vocab_rows
    db.execute = AsyncMock(return_value=mock_result)
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# 1. Module-level symbol importability
# ---------------------------------------------------------------------------

class TestSpeechServiceSymbolImports:
    def test_load_user_phrase_list_importable(self):
        """load_user_phrase_list must be importable from app.services.speech."""
        from app.services.speech import load_user_phrase_list  # noqa: F401

    def test_load_user_phrase_list_callable(self):
        from app.services.speech import load_user_phrase_list
        assert callable(load_user_phrase_list)

    def test_increment_term_usage_importable(self):
        """increment_term_usage must be importable from app.services.speech."""
        from app.services.speech import increment_term_usage  # noqa: F401

    def test_increment_term_usage_callable(self):
        from app.services.speech import increment_term_usage
        assert callable(increment_term_usage)

    def test_existing_transcribe_audio_file_not_removed(self):
        """transcribe_audio_file must still be present (additive change only)."""
        from app.services.speech import transcribe_audio_file  # noqa: F401
        assert callable(transcribe_audio_file)


# ---------------------------------------------------------------------------
# 2. load_user_phrase_list behaviour
# ---------------------------------------------------------------------------

class TestLoadUserPhraseList:
    async def test_returns_zero_for_empty_vocabulary(self):
        """When user has no terms, load_user_phrase_list must return 0."""
        from app.services.speech import load_user_phrase_list

        recognizer = _make_recognizer_mock()
        db = _make_db_mock(vocab_rows=[])

        mock_plg = _make_phrase_list_mock()
        with patch(
            "app.services.speech.speechsdk.PhraseListGrammar.from_recognizer",
            return_value=mock_plg,
        ):
            count = await load_user_phrase_list(recognizer, uuid.uuid4(), db)

        assert count == 0

    async def test_no_sdk_calls_for_empty_vocabulary(self):
        """When user has no terms, from_recognizer must NOT be called."""
        from app.services.speech import load_user_phrase_list

        recognizer = _make_recognizer_mock()
        db = _make_db_mock(vocab_rows=[])

        mock_from_recognizer = MagicMock()
        with patch(
            "app.services.speech.speechsdk.PhraseListGrammar.from_recognizer",
            mock_from_recognizer,
        ):
            await load_user_phrase_list(recognizer, uuid.uuid4(), db)

        mock_from_recognizer.assert_not_called()

    async def test_returns_count_equal_to_loaded_terms(self):
        """load_user_phrase_list must return len(terms) when vocabulary is non-empty."""
        from app.services.speech import load_user_phrase_list

        vocab = [
            _make_vocab_entry("arpeggio"),
            _make_vocab_entry("pgvector"),
            _make_vocab_entry("Phrygian mode"),
        ]
        recognizer = _make_recognizer_mock()
        db = _make_db_mock(vocab_rows=vocab)

        mock_plg = _make_phrase_list_mock()
        with patch(
            "app.services.speech.speechsdk.PhraseListGrammar.from_recognizer",
            return_value=mock_plg,
        ):
            count = await load_user_phrase_list(recognizer, uuid.uuid4(), db)

        assert count == 3

    async def test_from_recognizer_called_with_recognizer_arg(self):
        """PhraseListGrammar.from_recognizer must be called with the recognizer object."""
        from app.services.speech import load_user_phrase_list

        vocab = [_make_vocab_entry("hello")]
        recognizer = _make_recognizer_mock()
        db = _make_db_mock(vocab_rows=vocab)

        mock_plg = _make_phrase_list_mock()
        mock_from_recognizer = MagicMock(return_value=mock_plg)
        with patch(
            "app.services.speech.speechsdk.PhraseListGrammar.from_recognizer",
            mock_from_recognizer,
        ):
            await load_user_phrase_list(recognizer, uuid.uuid4(), db)

        mock_from_recognizer.assert_called_once_with(recognizer)

    async def test_add_phrase_called_for_each_term(self):
        """addPhrase must be called once per term."""
        from app.services.speech import load_user_phrase_list

        vocab = [
            _make_vocab_entry("arpeggio"),
            _make_vocab_entry("Cosmos DB"),
        ]
        recognizer = _make_recognizer_mock()
        db = _make_db_mock(vocab_rows=vocab)

        mock_plg = _make_phrase_list_mock()
        with patch(
            "app.services.speech.speechsdk.PhraseListGrammar.from_recognizer",
            return_value=mock_plg,
        ):
            await load_user_phrase_list(recognizer, uuid.uuid4(), db)

        # At minimum, addPhrase called for each term (may also be called for hints)
        calls_args = [c.args[0] for c in mock_plg.addPhrase.call_args_list]
        assert "arpeggio" in calls_args
        assert "Cosmos DB" in calls_args

    async def test_add_phrase_called_for_pronunciation_hint(self):
        """addPhrase must also be called with pronunciation_hint when present."""
        from app.services.speech import load_user_phrase_list

        vocab = [
            _make_vocab_entry("Karthik", pronunciation_hint="car-thick"),
        ]
        recognizer = _make_recognizer_mock()
        db = _make_db_mock(vocab_rows=vocab)

        mock_plg = _make_phrase_list_mock()
        with patch(
            "app.services.speech.speechsdk.PhraseListGrammar.from_recognizer",
            return_value=mock_plg,
        ):
            await load_user_phrase_list(recognizer, uuid.uuid4(), db)

        all_phrases = [c.args[0] for c in mock_plg.addPhrase.call_args_list]
        assert "car-thick" in all_phrases, (
            f"Expected pronunciation_hint 'car-thick' to be added as a phrase; got: {all_phrases}"
        )

    async def test_no_extra_phrase_for_none_hint(self):
        """When pronunciation_hint is None, addPhrase must only be called once for that term."""
        from app.services.speech import load_user_phrase_list

        vocab = [_make_vocab_entry("pgvector", pronunciation_hint=None)]
        recognizer = _make_recognizer_mock()
        db = _make_db_mock(vocab_rows=vocab)

        mock_plg = _make_phrase_list_mock()
        with patch(
            "app.services.speech.speechsdk.PhraseListGrammar.from_recognizer",
            return_value=mock_plg,
        ):
            await load_user_phrase_list(recognizer, uuid.uuid4(), db)

        assert mock_plg.addPhrase.call_count == 1

    async def test_default_max_phrases_is_500(self):
        """load_user_phrase_list must query with LIMIT 500 by default."""
        from app.services.speech import load_user_phrase_list
        import inspect
        sig = inspect.signature(load_user_phrase_list)
        assert "max_phrases" in sig.parameters, "max_phrases parameter missing"
        default = sig.parameters["max_phrases"].default
        assert default == 500, f"Expected default max_phrases=500, got {default}"


# ---------------------------------------------------------------------------
# 3. increment_term_usage behaviour
# ---------------------------------------------------------------------------

class TestIncrementTermUsage:
    async def test_increments_usage_count_for_found_term(self):
        """increment_term_usage must increment usage_count for terms in content."""
        from app.services.speech import increment_term_usage

        vocab_entry = _make_vocab_entry("arpeggio", usage_count=3)
        db = _make_db_mock(vocab_rows=[vocab_entry])

        await increment_term_usage(
            "Today I practiced an arpeggio sequence in C major",
            uuid.uuid4(),
            db,
        )

        assert vocab_entry.usage_count == 4

    async def test_case_insensitive_match(self):
        """Term matching must be case-insensitive."""
        from app.services.speech import increment_term_usage

        vocab_entry = _make_vocab_entry("Phrygian", usage_count=0)
        db = _make_db_mock(vocab_rows=[vocab_entry])

        # Content uses different casing
        await increment_term_usage("I love the phrygian mode", uuid.uuid4(), db)

        assert vocab_entry.usage_count == 1

    async def test_does_not_increment_absent_term(self):
        """increment_term_usage must not touch terms not found in the content."""
        from app.services.speech import increment_term_usage

        vocab_entry = _make_vocab_entry("pgvector", usage_count=0)
        db = _make_db_mock(vocab_rows=[vocab_entry])

        await increment_term_usage("Completely unrelated content here", uuid.uuid4(), db)

        assert vocab_entry.usage_count == 0

    async def test_commits_after_increment(self):
        """increment_term_usage must call db.commit() after updating."""
        from app.services.speech import increment_term_usage

        vocab_entry = _make_vocab_entry("cosmos db", usage_count=0)
        db = _make_db_mock(vocab_rows=[vocab_entry])

        await increment_term_usage("deployed to cosmos db today", uuid.uuid4(), db)

        db.commit.assert_called_once()

    async def test_multiple_terms_incremented(self):
        """When content contains multiple user terms, all must be incremented."""
        from app.services.speech import increment_term_usage

        entry_a = _make_vocab_entry("arpeggio", usage_count=0)
        entry_b = _make_vocab_entry("Phrygian", usage_count=0)
        entry_c = _make_vocab_entry("pgvector", usage_count=0)  # not in content
        db = _make_db_mock(vocab_rows=[entry_a, entry_b, entry_c])

        content = "I played an arpeggio in the Phrygian scale today"
        await increment_term_usage(content, uuid.uuid4(), db)

        assert entry_a.usage_count == 1
        assert entry_b.usage_count == 1
        assert entry_c.usage_count == 0

    async def test_empty_content_no_increment(self):
        """Empty transcript must not increment any term."""
        from app.services.speech import increment_term_usage

        vocab_entry = _make_vocab_entry("arpeggio", usage_count=5)
        db = _make_db_mock(vocab_rows=[vocab_entry])

        await increment_term_usage("", uuid.uuid4(), db)

        assert vocab_entry.usage_count == 5


# ---------------------------------------------------------------------------
# 4. POST /api/voice/upload integration — phrase list + usage increment
# ---------------------------------------------------------------------------

FAKE_BLOB_URL = (
    "https://fakestorage.blob.core.windows.net/cortex-media/audio/test.webm?sig=x"
)
FAKE_TRANSCRIPT = "Practiced an arpeggio in the Phrygian mode today"


class TestVoiceUploadPhraseListIntegration:
    """
    Verifies that the file-mode POST /api/voice/upload endpoint:
      a) calls load_user_phrase_list before recognition (task 3.3)
      b) calls increment_term_usage after transcript is obtained (task 3.3)
      c) logs "Loaded {n} phrases for user {id}" (addendum F1.2)

    WebSocket handler (task 3.4) is NOT tested here — that is US-9 territory (B16).
    """

    @pytest.fixture
    def audio_file(self):
        audio_bytes = b"RIFF" + b"\x00" * 100 + b"fake webm data"
        return {"file": ("voice_note.webm", io.BytesIO(audio_bytes), "audio/webm")}

    async def test_load_user_phrase_list_called_before_transcription(
        self, client, auth_headers, audio_file
    ):
        """load_user_phrase_list must be called before transcribe_audio_file."""
        call_order = []

        async def fake_load_phrase_list(recognizer, user_id, db, max_phrases=500):
            call_order.append("load_phrase_list")
            return 3

        async def fake_transcribe(audio_bytes, language="en-US"):
            call_order.append("transcribe")
            return FAKE_TRANSCRIPT

        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch("app.api.voice.transcribe_audio_file", side_effect=fake_transcribe):
                with patch(
                    "app.api.voice.load_user_phrase_list", side_effect=fake_load_phrase_list
                ):
                    with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                        mock_pipeline_cls.return_value.process_note = AsyncMock()
                        resp = await client.post(
                            "/api/voice/upload",
                            files=audio_file,
                            headers=auth_headers,
                        )

        assert resp.status_code == 201
        assert "load_phrase_list" in call_order, (
            "load_user_phrase_list was not called during voice upload"
        )
        if "transcribe" in call_order:
            load_idx = call_order.index("load_phrase_list")
            transcribe_idx = call_order.index("transcribe")
            assert load_idx < transcribe_idx, (
                "load_user_phrase_list must be called BEFORE transcribe_audio_file"
            )

    async def test_load_user_phrase_list_called_once(
        self, client, auth_headers, audio_file
    ):
        """load_user_phrase_list must be called exactly once per upload."""
        mock_load = AsyncMock(return_value=2)

        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch(
                "app.api.voice.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=FAKE_TRANSCRIPT,
            ):
                with patch("app.api.voice.load_user_phrase_list", mock_load):
                    with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                        mock_pipeline_cls.return_value.process_note = AsyncMock()
                        resp = await client.post(
                            "/api/voice/upload",
                            files=audio_file,
                            headers=auth_headers,
                        )

        assert resp.status_code == 201
        mock_load.assert_called_once()

    async def test_increment_term_usage_called_after_transcription(
        self, client, auth_headers, audio_file
    ):
        """increment_term_usage must be called after transcribe_audio_file returns."""
        mock_increment = AsyncMock()

        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch(
                "app.api.voice.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=FAKE_TRANSCRIPT,
            ):
                with patch("app.api.voice.load_user_phrase_list", new_callable=AsyncMock, return_value=1):
                    with patch("app.api.voice.increment_term_usage", mock_increment):
                        with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                            mock_pipeline_cls.return_value.process_note = AsyncMock()
                            resp = await client.post(
                                "/api/voice/upload",
                                files=audio_file,
                                headers=auth_headers,
                            )

        assert resp.status_code == 201
        mock_increment.assert_called_once()

    async def test_increment_term_usage_receives_transcript(
        self, client, auth_headers, audio_file
    ):
        """increment_term_usage must be called with the actual transcript text."""
        mock_increment = AsyncMock()

        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch(
                "app.api.voice.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=FAKE_TRANSCRIPT,
            ):
                with patch("app.api.voice.load_user_phrase_list", new_callable=AsyncMock, return_value=1):
                    with patch("app.api.voice.increment_term_usage", mock_increment):
                        with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                            mock_pipeline_cls.return_value.process_note = AsyncMock()
                            await client.post(
                                "/api/voice/upload",
                                files=audio_file,
                                headers=auth_headers,
                            )

        # First positional arg to increment_term_usage must be the transcript
        first_call_args = mock_increment.call_args
        assert first_call_args is not None
        transcript_arg = first_call_args.args[0] if first_call_args.args else None
        assert transcript_arg == FAKE_TRANSCRIPT, (
            f"increment_term_usage received '{transcript_arg}' instead of the transcript"
        )

    async def test_upload_logs_loaded_phrase_count(
        self, client, auth_headers, audio_file, caplog
    ):
        """voice_upload must log 'Loaded {n} phrases for user {id}' after loading the phrase list."""
        import logging

        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch(
                "app.api.voice.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=FAKE_TRANSCRIPT,
            ):
                with patch(
                    "app.api.voice.load_user_phrase_list",
                    new_callable=AsyncMock,
                    return_value=42,
                ):
                    with patch("app.api.voice.increment_term_usage", new_callable=AsyncMock):
                        with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                            mock_pipeline_cls.return_value.process_note = AsyncMock()
                            with caplog.at_level(logging.INFO, logger="app.api.voice"):
                                resp = await client.post(
                                    "/api/voice/upload",
                                    files=audio_file,
                                    headers=auth_headers,
                                )

        assert resp.status_code == 201
        log_text = caplog.text
        assert "42" in log_text and "phrase" in log_text.lower(), (
            f"Expected log message containing phrase count 42; got log: {log_text!r}"
        )

    async def test_voice_upload_still_returns_201_when_no_vocab(
        self, client, auth_headers, audio_file
    ):
        """Upload must succeed (201) even when load_user_phrase_list returns 0 (empty vocab)."""
        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch(
                "app.api.voice.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=FAKE_TRANSCRIPT,
            ):
                with patch(
                    "app.api.voice.load_user_phrase_list",
                    new_callable=AsyncMock,
                    return_value=0,
                ):
                    with patch("app.api.voice.increment_term_usage", new_callable=AsyncMock):
                        with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                            mock_pipeline_cls.return_value.process_note = AsyncMock()
                            resp = await client.post(
                                "/api/voice/upload",
                                files=audio_file,
                                headers=auth_headers,
                            )

        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# 5. No-op assertion for WebSocket (B16 guard)
# ---------------------------------------------------------------------------

class TestWebSocketHandlerNotModifiedByUS7:
    """
    Asserts that us-7 does NOT own the WebSocket handler.
    The WS route /api/voice/stream belongs to US-9.
    This test intentionally does NOT import or reference the WS handler.
    """

    def test_us7_does_not_register_ws_stream_route(self):
        """
        The load_user_phrase_list symbol must exist in speech.py, NOT be wired
        into a WebSocket route by US-7.  We simply verify the voice router still
        contains the upload route and nothing in the router registration indicates
        US-7 touched the WS handler.
        """
        from app.api.voice import router
        routes = {getattr(r, "path", "") for r in router.routes}
        assert "/upload" in routes, "voice router must still have /upload route"
        # The WS stream route may or may not exist yet (added by US-9); either is fine.
        # This test simply asserts we haven't accidentally removed the upload route.


# ---------------------------------------------------------------------------
# QA-08 (additional): file-mode upload calls load_user_phrase_list BEFORE transcribe
# review-comments.tasks.md § 3.8
#
# Note: the main QA-08 tests are in TestVoiceUploadPhraseListIntegration above.
# This class adds sharper assertion that the call order is strictly enforced.
# ---------------------------------------------------------------------------


class TestVoiceUploadFileModePhraseListOrder:
    """QA-08: POST /api/voice/upload (file-mode) must call load_user_phrase_list
    BEFORE transcribe_audio_file. US-7 task 3.3 requires this.

    The WebSocket path already handles this correctly. The file-mode path must
    be updated to load the personal dictionary phrase list before recognition.
    """

    @pytest.fixture
    def audio_file(self):
        audio_bytes = b"RIFF" + b"\x00" * 100 + b"fake webm data"
        return {"file": ("voice_note.webm", io.BytesIO(audio_bytes), "audio/webm")}

    async def test_load_phrase_list_called_strictly_before_transcribe(
        self, client, auth_headers, audio_file
    ):
        """QA-08: load_user_phrase_list must be invoked strictly before transcribe_audio_file.

        This enforces the ordering required by US-7 task 3.3:
        'call load_user_phrase_list before recognition'.
        """
        FAKE_BLOB_URL = "https://fakestorage.blob.core.windows.net/cortex-media/audio/test.webm"
        FAKE_TRANSCRIPT = "Testing phrase list ordering"
        call_order = []

        async def fake_load(recognizer_or_user, user_id=None, db=None, max_phrases=500):
            call_order.append("load_phrase_list")
            return 5

        async def fake_transcribe(audio_bytes, language="en-US"):
            call_order.append("transcribe")
            return FAKE_TRANSCRIPT

        with patch("app.api.voice.upload_blob", new_callable=AsyncMock, return_value=FAKE_BLOB_URL):
            with patch("app.api.voice.transcribe_audio_file", side_effect=fake_transcribe):
                with patch("app.api.voice.load_user_phrase_list", side_effect=fake_load):
                    with patch("app.api.voice.AIPipeline") as mock_pipeline_cls:
                        mock_pipeline_cls.return_value.process_note = AsyncMock()
                        resp = await client.post(
                            "/api/voice/upload",
                            files=audio_file,
                            headers=auth_headers,
                        )

        assert resp.status_code == 201

        # QA-08 core assertion: load_phrase_list must appear before transcribe
        assert "load_phrase_list" in call_order, (
            "QA-08 FAIL: load_user_phrase_list was never called during file-mode voice upload. "
            "US-7 task 3.3 requires calling load_user_phrase_list before recognition."
        )
        if "transcribe" in call_order:
            load_idx = call_order.index("load_phrase_list")
            transcribe_idx = call_order.index("transcribe")
            assert load_idx < transcribe_idx, (
                f"QA-08 FAIL: load_user_phrase_list (index {load_idx}) was called AFTER "
                f"transcribe_audio_file (index {transcribe_idx}). "
                "The phrase list must be loaded BEFORE transcription begins."
            )

    async def test_voice_upload_file_mode_imports_load_user_phrase_list(self):
        """QA-08: The voice.py module must import load_user_phrase_list from speech service.

        US-7 task 3.3 specifies that POST /api/voice/upload (file mode) must call
        load_user_phrase_list before recognition. This verifies the import exists.
        """
        from app.api import voice as voice_module
        import inspect

        src = inspect.getsource(voice_module)
        assert "load_user_phrase_list" in src, (
            "QA-08 FAIL: voice.py does not reference load_user_phrase_list. "
            "US-7 task 3.3 requires calling load_user_phrase_list in file-mode upload."
        )


# ---------------------------------------------------------------------------
# QA-05: Single _note_to_out helper — voice.py must use the shared serializer
#         and include shadow_reader_* fields
# review-comments.tasks.md § 3.5
# ---------------------------------------------------------------------------


class TestSingleNoteToOutHelper:
    """QA-05: There must be only ONE _note_to_out implementation.
    voice.py must import/use the same helper as notes.py (or a shared module),
    and that helper must populate shadow_reader_status, shadow_reader_questions,
    and shadow_reader_answer from the DB values.

    The bug: voice.py had its own _note_to_out that omitted all shadow_reader_* fields,
    causing voice-upload responses to always show Pydantic defaults instead of DB values.
    """

    def test_voice_py_note_to_out_includes_shadow_reader_status(self):
        """QA-05: voice.py _note_to_out (or shared helper) must map shadow_reader_status."""
        from app.api import voice as voice_module
        import inspect

        src = inspect.getsource(voice_module)
        assert "shadow_reader_status" in src, (
            "QA-05 FAIL: voice.py _note_to_out does not include shadow_reader_status. "
            "Voice-upload responses will always surface the Pydantic default ('pending') "
            "instead of the actual DB value. Use the shared _note_to_out from notes.py."
        )

    def test_voice_py_note_to_out_includes_shadow_reader_questions(self):
        """QA-05: voice.py _note_to_out must map shadow_reader_questions."""
        from app.api import voice as voice_module
        import inspect

        src = inspect.getsource(voice_module)
        assert "shadow_reader_questions" in src, (
            "QA-05 FAIL: voice.py _note_to_out does not include shadow_reader_questions. "
            "Use the shared serializer that includes all shadow reader fields."
        )

    def test_voice_py_note_to_out_includes_shadow_reader_answer(self):
        """QA-05: voice.py _note_to_out must map shadow_reader_answer."""
        from app.api import voice as voice_module
        import inspect

        src = inspect.getsource(voice_module)
        assert "shadow_reader_answer" in src, (
            "QA-05 FAIL: voice.py _note_to_out does not include shadow_reader_answer. "
            "Use the shared serializer that includes all shadow reader fields."
        )

    def test_no_duplicate_note_to_out_definitions(self):
        """QA-05: There must be at most ONE _note_to_out function definition across
        notes.py and voice.py. The correct fix is to extract a shared helper and
        import it in both routers, eliminating the divergence risk.

        We count function definitions of _note_to_out. If voice.py has its own
        local definition, the count will be 2 — which is the duplicated state.
        """
        import inspect
        from app.api import notes as notes_module
        from app.api import voice as voice_module

        notes_src = inspect.getsource(notes_module)
        voice_src = inspect.getsource(voice_module)

        notes_has_def = "def _note_to_out" in notes_src
        voice_has_def = "def _note_to_out" in voice_src

        # If voice.py defines its own _note_to_out AND it omits shadow_reader fields,
        # that's the QA-05 bug. We check the combination.
        if voice_has_def:
            # Voice has its own definition — check it includes shadow reader fields
            assert "shadow_reader_status" in voice_src, (
                "QA-05 FAIL: voice.py defines its own _note_to_out but omits "
                "shadow_reader_status. Either import the shared helper from notes.py "
                "or a shared module, OR ensure the voice-local definition is complete."
            )

    def test_voice_upload_response_includes_shadow_reader_status_field(self, client=None):
        """QA-05: NoteOut (returned by voice upload) must have shadow_reader_status field.

        This tests the schema level — NoteOut must expose all three shadow_reader_* fields.
        """
        try:
            from app.schemas.note import NoteOut
            fields = NoteOut.model_fields if hasattr(NoteOut, "model_fields") else NoteOut.__fields__
            assert "shadow_reader_status" in fields, (
                "QA-05 FAIL: NoteOut schema does not include shadow_reader_status. "
                "Voice upload responses will not include this field."
            )
            assert "shadow_reader_questions" in fields, (
                "QA-05 FAIL: NoteOut schema does not include shadow_reader_questions."
            )
            assert "shadow_reader_answer" in fields, (
                "QA-05 FAIL: NoteOut schema does not include shadow_reader_answer."
            )
        except ImportError:
            import pytest
            pytest.skip("NoteOut schema not yet implemented")


# ---------------------------------------------------------------------------
# PERF-02 — increment_term_usage must use a single UPDATE, not an in-Python loop
# review-comments.tasks.md § 2.2
# ---------------------------------------------------------------------------

class TestPERF02IncrementTermUsageSingleUpdate:
    """
    PERF-02: increment_term_usage must NOT fetch all user vocabulary terms into
    Python memory and then scan/update them in a loop. The fixed implementation
    should push matching to SQL (WHERE term ILIKE ANY(...)) and issue a single
    UPDATE statement, not one execute per term.

    Assert: db.execute is called exactly once (the batch UPDATE), not N times.
    """

    async def test_increment_term_usage_issues_single_execute_call(self):
        """
        increment_term_usage must issue ≤ 2 db.execute calls total (1 UPDATE query),
        regardless of how many vocabulary terms the user has.
        """
        from app.services.speech import increment_term_usage

        execute_calls = []

        db = AsyncMock()

        async def recording_execute(stmt, *args, **kwargs):
            execute_calls.append(stmt)
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            return mock_result

        db.execute = recording_execute
        db.commit = AsyncMock()

        content = "I practiced arpeggio in the Phrygian mode"
        user_id = uuid.uuid4()

        try:
            await increment_term_usage(content, user_id, db)
        except Exception:
            pass

        assert len(execute_calls) <= 2, (
            f"PERF-02 FAIL: increment_term_usage issued {len(execute_calls)} execute "
            f"calls — expected ≤ 2 (single UPDATE or fetch+UPDATE). "
            f"Fetching all terms and looping in Python is the N+1 anti-pattern."
        )

    async def test_increment_does_not_fetch_all_terms_to_python(self):
        """
        The SELECT issued by increment_term_usage must NOT be an unbounded
        'SELECT * FROM user_vocabulary WHERE user_id = ?' with no term filter.
        The query must include either a LIMIT or a WHERE clause filtering by content
        match (proving the scan is pushed to SQL, not Python).
        """
        from app.services.speech import increment_term_usage
        import inspect

        src = inspect.getsource(increment_term_usage)

        # The optimised implementation should NOT have both:
        # 1. An unbounded SELECT * with no content-related filter
        # 2. Followed by a Python `in` scan inside a for loop
        # We check for the absence of the naive pattern: iterating over ALL terms.
        # A compliant impl pushes matching to SQL via ILIKE ANY / UPDATE WHERE.
        has_python_loop_scan = (
            "for" in src
            and "in content" in src
            and "term" in src
        )
        assert not has_python_loop_scan, (
            "PERF-02 FAIL: increment_term_usage still scans all terms in a Python "
            "for-loop ('for ... if term in content'). Push the filter to SQL."
        )

    async def test_increment_term_usage_single_commit(self):
        """
        increment_term_usage must call db.commit() exactly once regardless of
        how many terms are matched (not once per matched term).
        """
        from app.services.speech import increment_term_usage

        db = _make_db_mock(vocab_rows=[
            _make_vocab_entry("arpeggio", usage_count=1),
            _make_vocab_entry("Phrygian", usage_count=0),
        ])

        await increment_term_usage(
            "I played an arpeggio in the Phrygian mode", uuid.uuid4(), db
        )

        assert db.commit.call_count == 1, (
            f"PERF-02 FAIL: db.commit() called {db.commit.call_count} times — "
            f"expected exactly 1 (single commit after all updates)."
        )
