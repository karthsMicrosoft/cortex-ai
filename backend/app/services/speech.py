"""
Azure Speech SDK adapter — file-mode transcription.

Exposes:
- transcribe_audio_file(audio_bytes, language) → str

WebSocket streaming STT is added in US-9; this module handles only file-mode
recognition using SpeechRecognizer.recognize_once_async().

Environment:
- AZURE_SPEECH_KEY
- AZURE_SPEECH_REGION  (default: westus2)
"""
import io
import logging
import tempfile
import os
from typing import Optional

import azure.cognitiveservices.speech as speechsdk

from app.config import settings
from app.utils.retry import azure_retry

logger = logging.getLogger(__name__)


@azure_retry
async def transcribe_audio_file(
    audio_bytes: bytes,
    language: str = "en-US",
) -> str:
    """Transcribe *audio_bytes* using Azure Speech file-mode recognition.

    Args:
        audio_bytes: Raw audio content (WAV, MP3, OGG, WEBM, etc.).
        language:    BCP-47 language tag (default: "en-US").

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
