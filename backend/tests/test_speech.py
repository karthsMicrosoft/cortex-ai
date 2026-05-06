"""
test_speech.py — Task 1.4
Tests for backend/app/services/speech.py

Covers:
  - transcribe_audio_file(audio_bytes, language='en-US') returns a string
  - Uses Azure Speech SDK continuous recognition (Bug 25 fix — replaced
    recognize_once_async() with start_continuous_recognition_async() to handle
    multi-pause recordings)
  - Wrapped with tenacity retry decorator
  - Returns the transcript text on success
  - Raises on recognition failure after retries exhausted

Mock strategy (B15): unittest.mock.patch — Speech SDK uses gRPC/native transport;
respx cannot intercept it. Patch ``azure.cognitiveservices.speech.SpeechRecognizer``.
2026-05-06 fix: also patch _ffmpeg_to_wav so tests don't require the ffmpeg
binary to be on PATH (which it isn't in CI / dev shells).
"""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers / Fake SDK objects
# ---------------------------------------------------------------------------

class FakeSpeechRecognitionResult:
    """Minimal stub for azure.cognitiveservices.speech.SpeechRecognitionResult."""

    def __init__(self, text: str, reason_value: int = 3):  # 3 = RecognizedSpeech
        self.text = text
        self._reason_value = reason_value

    @property
    def reason(self):
        import azure.cognitiveservices.speech as speechsdk
        for member in speechsdk.ResultReason:
            if member.value == self._reason_value:
                return member
        return self._reason_value


def _make_continuous_recognizer(text: str = "", *, raises=None):
    """
    Build a MagicMock standing in for speechsdk.SpeechRecognizer, configured
    for the Bug-25 continuous-recognition flow:

      recognizer.recognized.connect(cb)        # captured for later firing
      recognizer.session_stopped.connect(cb)
      recognizer.canceled.connect(cb)
      recognizer.start_continuous_recognition_async().get()  # drives callbacks
      recognizer.stop_continuous_recognition_async().get()

    When start_continuous_recognition_async().get() is called, this fake fires
    the captured ``recognized`` callback once with ``text`` and then the
    ``session_stopped`` callback, mirroring how the live SDK behaves with a
    short audio file. If ``raises`` is set, .get() raises that exception
    instead — used to exercise the tenacity retry decorator.
    """
    import azure.cognitiveservices.speech as speechsdk

    recognizer = MagicMock()
    state = {"recognized_cb": None, "session_stopped_cb": None, "canceled_cb": None}

    recognizer.recognized.connect.side_effect = lambda cb: state.update(recognized_cb=cb)
    recognizer.session_stopped.connect.side_effect = lambda cb: state.update(session_stopped_cb=cb)
    recognizer.canceled.connect.side_effect = lambda cb: state.update(canceled_cb=cb)

    def start_async():
        future = MagicMock()

        def _get():
            if raises is not None:
                raise raises
            if state["recognized_cb"] is not None:
                evt = MagicMock()
                evt.result.reason = speechsdk.ResultReason.RecognizedSpeech
                evt.result.text = text
                state["recognized_cb"](evt)
            if state["session_stopped_cb"] is not None:
                state["session_stopped_cb"](MagicMock())

        future.get.side_effect = _get
        return future

    recognizer.start_continuous_recognition_async.side_effect = start_async
    stop_future = MagicMock()
    stop_future.get.return_value = None
    recognizer.stop_continuous_recognition_async.return_value = stop_future
    return recognizer


@pytest.fixture(autouse=True)
def _patch_ffmpeg_and_unlink():
    """Stub out _ffmpeg_to_wav + os.unlink so these tests don't need the
    ffmpeg binary on PATH and don't error trying to delete fake temp files."""
    with patch("app.services.speech._ffmpeg_to_wav", return_value="/tmp/fake.wav"), \
         patch("app.services.speech.os.unlink"):
        yield


# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------

class TestSpeechModuleImport:
    def test_module_importable(self):
        from app.services import speech  # noqa: F401

    def test_transcribe_callable(self):
        from app.services.speech import transcribe_audio_file
        assert callable(transcribe_audio_file)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestTranscribeAudioFile:
    @pytest.mark.asyncio
    async def test_returns_transcript_string(self):
        """transcribe_audio_file must return the recognised text as a string."""
        from app.services.speech import transcribe_audio_file

        expected_text = "Hello world this is a test voice note"
        recognizer = _make_continuous_recognizer(text=expected_text)

        with patch("app.services.speech.settings") as mock_settings:
            mock_settings.AZURE_SPEECH_KEY = "fake-key"
            mock_settings.AZURE_SPEECH_REGION = "westus2"
            with patch("app.services.speech.speechsdk.SpeechConfig", MagicMock()), \
                 patch("app.services.speech.speechsdk.audio.AudioConfig", MagicMock()), \
                 patch("app.services.speech.speechsdk.SpeechRecognizer", return_value=recognizer):
                result = await transcribe_audio_file(b"fake audio bytes")

        assert isinstance(result, str)
        assert result == expected_text

    @pytest.mark.asyncio
    async def test_default_language_en_us(self):
        """The default language passed to SpeechConfig must be 'en-US'."""
        from app.services.speech import transcribe_audio_file

        speech_config_instance = MagicMock()

        recognizer = _make_continuous_recognizer(text="ok")

        with patch("app.services.speech.settings") as mock_settings:
            mock_settings.AZURE_SPEECH_KEY = "fake-key"
            mock_settings.AZURE_SPEECH_REGION = "westus2"
            with patch(
                "app.services.speech.speechsdk.SpeechConfig",
                return_value=speech_config_instance,
            ), patch("app.services.speech.speechsdk.audio.AudioConfig", MagicMock()), \
               patch("app.services.speech.speechsdk.SpeechRecognizer", return_value=recognizer):
                await transcribe_audio_file(b"audio")

        # Production sets ``speech_config.speech_recognition_language = language``
        # post-construction. Verify the assignment happened with default 'en-US'.
        assert speech_config_instance.speech_recognition_language == "en-US"

    @pytest.mark.asyncio
    async def test_explicit_language_passed_through(self):
        """A non-default language must be forwarded to the Speech SDK config."""
        from app.services.speech import transcribe_audio_file

        speech_config_instance = MagicMock()
        recognizer = _make_continuous_recognizer(text="Hola")

        with patch("app.services.speech.settings") as mock_settings:
            mock_settings.AZURE_SPEECH_KEY = "fake-key"
            mock_settings.AZURE_SPEECH_REGION = "westus2"
            with patch(
                "app.services.speech.speechsdk.SpeechConfig",
                return_value=speech_config_instance,
            ), patch("app.services.speech.speechsdk.audio.AudioConfig", MagicMock()), \
               patch("app.services.speech.speechsdk.SpeechRecognizer", return_value=recognizer):
                result = await transcribe_audio_file(b"audio", language="es-ES")

        assert speech_config_instance.speech_recognition_language == "es-ES"
        assert result == "Hola"

    @pytest.mark.asyncio
    async def test_continuous_recognition_used(self):
        """
        Bug 25 fix: production must use start_continuous_recognition_async()
        (which accumulates segments across pauses), not the old
        recognize_once_async() which truncated at the first silence.
        """
        from app.services.speech import transcribe_audio_file

        recognizer = _make_continuous_recognizer(text="test")

        with patch("app.services.speech.settings") as mock_settings:
            mock_settings.AZURE_SPEECH_KEY = "fake-key"
            mock_settings.AZURE_SPEECH_REGION = "westus2"
            with patch("app.services.speech.speechsdk.SpeechConfig", MagicMock()), \
                 patch("app.services.speech.speechsdk.audio.AudioConfig", MagicMock()), \
                 patch("app.services.speech.speechsdk.SpeechRecognizer", return_value=recognizer):
                await transcribe_audio_file(b"audio data")

        recognizer.start_continuous_recognition_async.assert_called_once()
        recognizer.stop_continuous_recognition_async.assert_called_once()
        # The deprecated single-shot API must NOT be called.
        assert not recognizer.recognize_once_async.called


# ---------------------------------------------------------------------------
# Error / retry behaviour
# ---------------------------------------------------------------------------

class TestTranscribeSpeechRetry:
    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self):
        """
        transcribe_audio_file must be wrapped with the tenacity retry decorator.
        If the underlying SDK call raises a transient error twice and succeeds
        on the third attempt, the function must return the result without
        propagating the error.
        """
        from app.services.speech import transcribe_audio_file

        call_count = {"n": 0}

        # Each attempt builds a fresh recognizer; the first two raise on
        # start_continuous_recognition_async().get(), the third succeeds.
        def make_recognizer(*_args, **_kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                return _make_continuous_recognizer(raises=ConnectionError("Transient STT error"))
            return _make_continuous_recognizer(text="retry success")

        with patch("app.services.speech.settings") as mock_settings:
            mock_settings.AZURE_SPEECH_KEY = "fake-key"
            mock_settings.AZURE_SPEECH_REGION = "westus2"
            with patch("app.services.speech.speechsdk.SpeechConfig", MagicMock()), \
                 patch("app.services.speech.speechsdk.audio.AudioConfig", MagicMock()), \
                 patch("app.services.speech.speechsdk.SpeechRecognizer", side_effect=make_recognizer):
                result = await transcribe_audio_file(b"audio")

        assert result == "retry success"
        assert call_count["n"] == 3
