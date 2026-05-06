"""
Azure Speech SDK adapter — file-mode transcription.

Exposes:
- transcribe_audio_file(audio_bytes, language) → str
- load_user_phrase_list(recognizer, user_id, db, max_phrases) → int   [US-7]
- increment_term_usage(content, user_id, db)                          [US-7]

WebSocket streaming STT is added in US-9; this module handles only file-mode
recognition using start_continuous_recognition_async() (Bug 25 fix — the
previous recognize_once_async() truncated at the first pause).

Environment:
- AZURE_SPEECH_KEY
- AZURE_SPEECH_REGION  (default: westus2)
"""
import asyncio
import logging
import subprocess
import tempfile
import os

import azure.cognitiveservices.speech as speechsdk

from app.config import settings
from app.utils.retry import azure_retry

logger = logging.getLogger(__name__)


@azure_retry
async def transcribe_audio_file(
    audio_bytes: bytes,
    language: str = "en-US",
    phrase_list: list[str] | None = None,
    src_suffix: str = ".webm",
) -> str:
    """Transcribe *audio_bytes* using Azure Speech continuous recognition.

    Args:
        audio_bytes:  Raw audio content (WAV, MP3, OGG, WEBM, MP4/M4A, etc.).
        language:     BCP-47 language tag (default: "en-US").
        phrase_list:  Optional list of phrase strings to boost via PhraseListGrammar
                      before recognition (QA-08 / US-7 task 3.3 personal dictionary).
        src_suffix:   File extension for the temp source file; helps ffmpeg detect
                      the container format. Defaults to ".webm"; pass ".mp4" or
                      ".m4a" for iOS Safari recordings.

    Returns:
        Transcribed text string (may be empty if no speech detected).

    Raises:
        RuntimeError: If the Speech SDK returns an error or cancellation.

    Bug 25 fix: replaced recognize_once_async() (stops at first silence) with
    start_continuous_recognition_async() + session_stopped event so multi-pause
    recordings are fully transcribed instead of truncated at the first pause.
    """
    speech_config = speechsdk.SpeechConfig(
        subscription=settings.AZURE_SPEECH_KEY,
        region=settings.AZURE_SPEECH_REGION,
    )
    speech_config.speech_recognition_language = language

    # Bug 13 fix (2026-05-01): MediaRecorder's audio/webm output is OPUS-in-WebM.
    # Azure Speech SDK file-mode expects WAV/PCM by default — feeding it WebM
    # bytes inside a .wav-suffixed temp file caused NoMatch on every audible
    # recording. Convert WebM (or any input) to 16 kHz mono PCM WAV via ffmpeg
    # (already in our Docker image) before handing the path to Speech.
    # Bug 20 fix (2026-05-01): iOS Safari records audio/mp4 — use the correct
    # suffix so ffmpeg can detect the container format.
    src_path = _write_temp(audio_bytes, suffix=src_suffix)
    try:
        wav_path = _ffmpeg_to_wav(src_path)
    except Exception as exc:  # noqa: BLE001
        os.unlink(src_path)
        logger.error("Speech transcribe: ffmpeg failed err=%s", exc)
        raise RuntimeError(f"Audio conversion failed: {exc}") from exc
    os.unlink(src_path)
    tmp_path = wav_path

    try:
        audio_config = speechsdk.AudioConfig(filename=tmp_path)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )

        # Apply personal dictionary phrase list before recognition (QA-08 fix).
        if phrase_list:
            grammar = speechsdk.PhraseListGrammar.from_recognizer(recognizer)
            for phrase in phrase_list:
                grammar.addPhrase(phrase)

        # Bug 25 fix: continuous recognition accumulates all segments across
        # natural pauses. recognize_once_async() stopped at the first silence,
        # so a 20s recording with 3 pauses returned only the first segment.
        # The SDK callbacks fire on a worker thread; all asyncio interaction
        # must go through loop.call_soon_threadsafe to avoid cross-thread issues.
        loop = asyncio.get_event_loop()
        done = asyncio.Event()
        segments: list[str] = []
        cancellation_error: list[str] = []

        def on_recognized(evt) -> None:  # type: ignore[type-arg]
            if (
                evt.result.reason == speechsdk.ResultReason.RecognizedSpeech
                and evt.result.text
            ):
                segments.append(evt.result.text)

        def on_session_stopped(evt) -> None:  # type: ignore[type-arg]
            loop.call_soon_threadsafe(done.set)

        def on_canceled(evt) -> None:  # type: ignore[type-arg]
            details = speechsdk.CancellationDetails(evt.result)
            if details.reason == speechsdk.CancellationReason.Error:
                cancellation_error.append(
                    f"{details.reason} — {details.error_details}"
                )
                logger.error(
                    "Speech cancellation: reason=%s error_code=%s error_details=%s",
                    details.reason,
                    details.error_code,
                    details.error_details,
                )
            loop.call_soon_threadsafe(done.set)

        recognizer.recognized.connect(on_recognized)
        recognizer.session_stopped.connect(on_session_stopped)
        recognizer.canceled.connect(on_canceled)

        recognizer.start_continuous_recognition_async().get()
        await done.wait()
        recognizer.stop_continuous_recognition_async().get()

        if cancellation_error:
            raise RuntimeError(f"Speech recognition cancelled: {cancellation_error[0]}")

        text = " ".join(segments)
        logger.info("Speech transcription complete, segments=%d text_len=%d", len(segments), len(text))
        return text
    finally:
        os.unlink(tmp_path)


def _write_temp(data: bytes, suffix: str) -> str:
    """Write *data* to a NamedTemporaryFile with *suffix* and return its path.

    Caller is responsible for unlinking the returned path.
    """
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except Exception:
        os.unlink(path)
        raise
    return path


def _transcode_to_m4a(src_path: str) -> str:
    """Transcode *src_path* (any container/codec ffmpeg supports) to AAC-in-M4A.

    Purpose: **playback compatibility**.  iOS Safari has zero WebM container
    support, so audio/webm blobs stored in Blob Storage silently fail to play on
    iPhone.  MP4/AAC (audio/mp4, .m4a) plays on every browser including Safari.

    This helper is intentionally separate from ``_ffmpeg_to_wav`` which converts
    audio for **transcription** (16 kHz mono PCM WAV for Azure Speech SDK).
    Keeping the two helpers distinct lets callers clean up each temp file
    independently and avoids coupling the transcription pipeline to playback needs.

    Args:
        src_path: Path to the source audio file (any ffmpeg-readable container).

    Returns:
        Path to the transcoded .m4a file. Caller must unlink it.

    Raises:
        RuntimeError: if ffmpeg is not installed, times out, or returns non-zero.
    """
    out_path = src_path + ".m4a"
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", src_path,
                "-c:a", "aac",
                "-b:a", "128k",
                "-ar", "44100",
                out_path,
            ],
            capture_output=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg binary not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffmpeg M4A transcode timed out after 60s") from exc

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"ffmpeg M4A transcode exited {result.returncode}: {stderr}")
    return out_path


def _ffmpeg_to_wav(src_path: str) -> str:
    """Convert *src_path* (any container/codec ffmpeg supports) to 16 kHz mono PCM WAV.

    Returns the path to the new .wav file. Caller must unlink it.
    Raises RuntimeError if ffmpeg fails or is not installed.
    """
    out_path = src_path + ".wav"
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", src_path,
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                out_path,
            ],
            capture_output=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg binary not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffmpeg conversion timed out after 60s") from exc

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"ffmpeg exited {result.returncode}: {stderr}")
    return out_path


# ---------------------------------------------------------------------------
# US-7 — Personal Dictionary helpers
# ---------------------------------------------------------------------------

async def load_user_phrase_list(
    recognizer,
    user_id,
    db,
    max_phrases: int = 500,
) -> int | list[str]:
    """Load the user's personal dictionary.

    Two modes based on *recognizer*:
    - recognizer is a SpeechRecognizer: adds phrases to grammar via PhraseListGrammar;
      returns count (int) of rows loaded. Used by the WebSocket streaming path.
    - recognizer is None: returns a list of phrase strings for caller to pass to
      transcribe_audio_file(phrase_list=...). Used by the file-mode upload path.

    Args:
        recognizer:   Azure SpeechRecognizer instance, or None for file-mode uploads.
        user_id:      UUID of the authenticated user.
        db:           Async SQLAlchemy session.
        max_phrases:  Cap on phrases loaded (Azure limit ~500 per session).

    Returns:
        int (count) when recognizer is provided; list[str] when recognizer is None.
    """
    from sqlalchemy import select
    from app.models.vocabulary import UserVocabulary

    result = await db.execute(
        select(UserVocabulary)
        .where(UserVocabulary.user_id == user_id)
        .order_by(UserVocabulary.usage_count.desc())
        .limit(max_phrases)
    )
    terms = result.scalars().all()
    if not terms:
        return 0 if recognizer is not None else []

    if recognizer is not None:
        grammar = speechsdk.PhraseListGrammar.from_recognizer(recognizer)
        for term in terms:
            grammar.addPhrase(term.term)
            if term.pronunciation_hint:
                grammar.addPhrase(term.pronunciation_hint)
        return len(terms)
    else:
        # File-mode: return phrase strings for transcribe_audio_file(phrase_list=...)
        phrases: list[str] = []
        for term in terms:
            phrases.append(term.term)
            if term.pronunciation_hint:
                phrases.append(term.pronunciation_hint)
        return phrases


async def increment_term_usage(content: str, user_id, db) -> None:
    """After STT, increment usage_count for each user vocabulary term found in *content*.

    PERF-02 fix: pushes the substring scan to Postgres with a single UPDATE
    statement instead of fetching all terms into Python and scanning in a loop.
    The SQL uses ILIKE for case-insensitive containment check, which lets
    Postgres avoid the O(N) memory load of the old SELECT * approach.

    Args:
        content:  The transcribed text returned by STT.
        user_id:  UUID of the authenticated user.
        db:       Async SQLAlchemy session.
    """
    from sqlalchemy import text

    if not content:
        return

    await db.execute(
        text(
            """
            UPDATE user_vocabulary
               SET usage_count = usage_count + 1
             WHERE user_id = :uid
               AND :content ILIKE '%' || term || '%'
            """
        ),
        {"uid": str(user_id), "content": content},
    )
    await db.commit()
