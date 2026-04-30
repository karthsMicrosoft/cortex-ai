"""
Azure Speech SDK adapter — file-mode transcription.

Exposes:
- transcribe_audio_file(audio_bytes, language) → str
- load_user_phrase_list(recognizer, user_id, db, max_phrases) → int   [US-7]
- increment_term_usage(content, user_id, db)                          [US-7]

WebSocket streaming STT is added in US-9; this module handles only file-mode
recognition using SpeechRecognizer.recognize_once_async().

Environment:
- AZURE_SPEECH_KEY
- AZURE_SPEECH_REGION  (default: westus2)
"""
import logging
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
) -> str:
    """Transcribe *audio_bytes* using Azure Speech file-mode recognition.

    Args:
        audio_bytes:  Raw audio content (WAV, MP3, OGG, WEBM, etc.).
        language:     BCP-47 language tag (default: "en-US").
        phrase_list:  Optional list of phrase strings to boost via PhraseListGrammar
                      before recognition (QA-08 / US-7 task 3.3 personal dictionary).

    Returns:
        Transcribed text string (may be empty if no speech detected).

    Raises:
        RuntimeError: If the Speech SDK returns an error or cancellation.
    """
    speech_config = speechsdk.SpeechConfig(
        subscription=settings.AZURE_SPEECH_KEY,
        region=settings.AZURE_SPEECH_REGION,
    )
    speech_config.speech_recognition_language = language

    # Write audio bytes to a temporary file — Azure Speech SDK requires a path
    # for file-mode recognition (PushAudioInputStream is for streaming).
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        tmp_path = tmp_file.name
        tmp_file.write(audio_bytes)

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

        # recognize_once_async() is a one-shot file recognition call.
        result = await _recognize_once(recognizer)

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            logger.info("Speech transcription complete, text_len=%d", len(result.text))
            return result.text
        elif result.reason == speechsdk.ResultReason.NoMatch:
            logger.warning("Speech no match: %s", result.no_match_details)
            return ""
        else:
            # Cancelled — extract error details
            cancellation = speechsdk.CancellationDetails.from_result(result)
            logger.error(
                "Speech cancellation: reason=%s error_code=%s error_details=%s",
                cancellation.reason,
                cancellation.error_code,
                cancellation.error_details,
            )
            raise RuntimeError(
                f"Speech recognition cancelled: {cancellation.reason} — {cancellation.error_details}"
            )
    finally:
        os.unlink(tmp_path)


async def _recognize_once(recognizer: speechsdk.SpeechRecognizer):
    """Await the SDK's recognize_once_async() future and return the result."""
    import asyncio

    loop = asyncio.get_event_loop()
    future = recognizer.recognize_once_async()
    # The SDK returns a concurrent.futures-style Future; run it in executor.
    result = await loop.run_in_executor(None, future.get)
    return result


# ---------------------------------------------------------------------------
# US-7 — Personal Dictionary helpers
# ---------------------------------------------------------------------------

async def load_user_phrase_list(
    recognizer: speechsdk.SpeechRecognizer,
    user_id,
    db,
    max_phrases: int = 500,
) -> int:
    """Load the user's personal dictionary into the STT recognizer via PhraseListGrammar.

    Selects up to *max_phrases* terms ordered by usage_count DESC and adds each
    term (plus pronunciation_hint when present) to the grammar.

    Args:
        recognizer:   Azure SpeechRecognizer instance (before recognition starts).
        user_id:      UUID of the authenticated user.
        db:           Async SQLAlchemy session.
        max_phrases:  Cap on phrases loaded (Azure limit ~500 per session).

    Returns:
        Number of UserVocabulary rows loaded (not total phrase strings added,
        since each row may add 1 or 2 phrases).
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
        return 0

    phrase_list = speechsdk.PhraseListGrammar.from_recognizer(recognizer)
    for term in terms:
        phrase_list.addPhrase(term.term)
        if term.pronunciation_hint:
            phrase_list.addPhrase(term.pronunciation_hint)

    return len(terms)


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
