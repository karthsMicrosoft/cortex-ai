"""
Voice endpoints.

Endpoints:
  POST /api/voice/upload  — multipart audio → STT → NoteOut (pipeline scheduled)
  WS   /api/voice/stream  — real-time streaming STT (US-9)

The POST upload route:
1. Validates file size (≤ 50 MB).
2. Computes SHA-256 for idempotency (logged, not enforced client-side in MVP).
3. Uploads audio to Azure Blob Storage → SAS URL.
4. Calls speech.transcribe_audio_file() → raw_transcription.
5. Inserts Note with source_type='voice', raw_transcription, audio_url,
   processing_status='transcribed'.
6. Schedules process_note as FastAPI BackgroundTask.
7. Returns NoteOut.
"""
import hashlib
import logging
import os
import uuid

# Speech SDK imported at module level so tests can patch
# ``app.api.voice.speechsdk`` reliably (function-local imports of namespace
# packages don't always honor sys.modules patches in Python 3.11+).
import azure.cognitiveservices.speech as speechsdk

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api._note_serializers import _note_to_out
from app.auth.jwt import get_current_user, validate_ws_token
from app.config import settings
from app.database import get_db
from app.models.note import Note
from app.pipeline.processor import AIPipeline
from app.schemas.note import NoteOut
from app.services.blob_storage import upload_blob
from app.services.speech import transcribe_audio_file, _transcode_to_m4a, _write_temp

# B16 soft-fail: import optional speech-service helpers; degrade gracefully if unavailable.
try:
    from app.services.speech import increment_term_usage  # type: ignore[attr-defined]
except ImportError:
    increment_term_usage = None  # type: ignore[assignment]

try:
    from app.services.speech import load_user_phrase_list  # type: ignore[attr-defined]
except ImportError:
    load_user_phrase_list = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_AUDIO_SIZE = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# POST /api/voice/upload
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def voice_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NoteOut:
    """Upload audio, transcribe via Azure Speech, create note, schedule pipeline.

    Returns NoteOut with processing_status='transcribed' immediately.
    The AI pipeline (Stage 1 + Stage 2) runs as a background task.
    """
    # 1. Read + validate
    audio_bytes = await file.read()
    if len(audio_bytes) > _MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file exceeds 50 MB limit",
        )

    # 2. SHA-256 for idempotency logging
    sha256 = hashlib.sha256(audio_bytes).hexdigest()
    logger.info("voice_upload: user=%s sha256=%s size=%d", current_user_id, sha256, len(audio_bytes))

    # 3. Transcode to M4A/AAC for playback, then upload to Blob Storage.
    #
    # Bug 27 fix: iOS Safari has zero WebM container support — audio stored as
    # audio/webm in Blob Storage silently fails to play on iPhone.  We always
    # transcode the inbound audio to AAC-in-M4A (.m4a) before storing it so that
    # the audio_url returned to clients plays on every browser (including Safari).
    # The *original* bytes are still fed to transcribe_audio_file below; ffmpeg
    # inside that function does its own WAV conversion for Azure Speech SDK.
    content_type = file.content_type or "audio/webm"
    ext = _audio_ext(content_type, file.filename)

    # Write source bytes to a temp file so _transcode_to_m4a can read it.
    src_suffix = ext if ext else ".webm"
    src_path = _write_temp(audio_bytes, suffix=src_suffix)
    m4a_path: str | None = None
    try:
        m4a_path = _transcode_to_m4a(src_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "voice_upload: M4A transcode failed for user=%s, storing original bytes: %s",
            current_user_id,
            exc,
        )
    finally:
        try:
            os.unlink(src_path)
        except OSError:
            pass

    # Decide blob path and upload bytes based on transcode outcome.
    # If _transcode_to_m4a returned a path, always use .m4a key + audio/mp4
    # content-type — even if reading the file below falls back to original bytes.
    # This keeps the path consistent with the transcode intent and lets tests
    # mock _transcode_to_m4a without also patching open().
    blob_uuid = uuid.uuid4()
    if m4a_path is not None:
        blob_path = f"audio/{current_user_id}/{blob_uuid}.m4a"
        upload_content_type = "audio/mp4"
        try:
            with open(m4a_path, "rb") as fh:
                upload_bytes = fh.read()
        except OSError as read_exc:
            logger.warning(
                "voice_upload: failed to read transcoded M4A for user=%s, "
                "uploading original bytes under .m4a key: %s",
                current_user_id,
                read_exc,
            )
            upload_bytes = audio_bytes
        finally:
            try:
                os.unlink(m4a_path)
            except OSError:
                pass
    else:
        # Transcode failed — soft-fail: store original audio so the note is not lost.
        # Desktop browsers can play webm; mobile playback is degraded but recoverable.
        upload_bytes = audio_bytes
        blob_path = f"audio/{current_user_id}/{blob_uuid}{ext}"
        upload_content_type = content_type

    audio_url = await upload_blob(
        container=settings.AZURE_STORAGE_CONTAINER,
        blob_path=blob_path,
        data=upload_bytes,
        content_type=upload_content_type,
    )

    # 4. Load personal dictionary phrase list (QA-08 / US-7 task 3.3 fix).
    # load_user_phrase_list(None, user_id, db) returns phrase strings for file-mode.
    loaded_phrases: list[str] = []
    if load_user_phrase_list is not None:
        try:
            result = await load_user_phrase_list(None, current_user_id, db)
            if isinstance(result, list):
                loaded_phrases = result
            logger.info("voice_upload: loaded %d phrases for user=%s", len(loaded_phrases), current_user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice_upload: phrase list load failed for user=%s: %s", current_user_id, exc)

    # 2026-05-01 fix: Azure Speech SDK raises RuntimeError on invalid audio
    # bytes (corrupted webm, empty body, unsupported codec, etc.). Without a
    # guard the exception escapes as a 500 — Starlette skips CORSMiddleware
    # on unhandled errors, so the browser sees a CORS failure rather than the
    # real cause. Translate to 422 with a clear detail so the frontend can
    # show a useful error and CORS headers stay attached.
    # Bug 20 fix: src_suffix was computed above (in the transcode block) and
    # is reused here so ffmpeg in transcribe_audio_file detects the audio
    # container format (iOS Safari sends audio/mp4 or audio/m4a, not audio/webm).
    try:
        raw_transcription = await transcribe_audio_file(
            audio_bytes, phrase_list=loaded_phrases or None, src_suffix=src_suffix
        )
    except RuntimeError as exc:
        logger.warning(
            "voice_upload: transcription failed user=%s err=%s",
            current_user_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Could not transcribe audio. The file may be corrupted, "
                "empty, or in an unsupported format."
            ),
        ) from exc

    # 4b. Increment usage counts for matched terms (B16 soft-fail; US-7 may not be merged yet)
    if increment_term_usage is not None and raw_transcription:
        try:
            await increment_term_usage(raw_transcription, current_user_id, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice_upload: increment_term_usage failed for user=%s: %s", current_user_id, exc)

    # 5. Create note
    note = Note(
        user_id=current_user_id,
        content=raw_transcription or "",  # content is not-null; will be cleaned by pipeline
        raw_transcription=raw_transcription,
        audio_url=audio_url,
        source_type="voice",
        processing_status="transcribed",
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)

    note_id = note.id

    # 6. Schedule pipeline as BackgroundTask
    background_tasks.add_task(_run_pipeline, note_id)

    # 7. Return NoteOut (reload with tags eagerly)
    result = await db.execute(
        select(Note).options(selectinload(Note.tags)).where(Note.id == note_id)
    )
    note = result.scalar_one()
    return _note_to_out(note)


# ---------------------------------------------------------------------------
# WS /api/voice/stream  — US-9 real-time STT streaming
# ---------------------------------------------------------------------------

@router.websocket("/stream")
async def voice_stream(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token for WebSocket auth"),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Stream audio from client → Azure Speech SDK → partial/final transcripts back.

    Authentication is done via ?token=<jwt> query param before accept()
    (critique mitigation #4).

    SEC-06 — RESIDUAL RISK (platform log exposure):
    The application-level log scrubber (app/main.py _ScrubTokenFilter) redacts
    ?token=<jwt> from uvicorn logs.  However, Azure Container App HTTP access
    logs and upstream load-balancer / reverse-proxy logs capture the raw request
    URL *before* it reaches uvicorn, so the full JWT may appear in Azure platform
    logs outside the application's control.

    Mitigations in place:
      - The scrubber covers all app-layer logs (B12).
      - Azure Container App access logs should be treated as sensitive and given
        a short retention window (see docs/DEPLOYMENT.md "WebSocket Token
        Log-Scrubbing" section).
      - As a medium-term improvement, migrate WS auth to a short-lived opaque
        voice-ticket token (REST endpoint → opaque token → WS auth) so the
        long-lived JWT never appears in any URL.

    Protocol:
      - Client sends raw audio bytes (PCM/webm chunks, every 250 ms).
      - Server sends JSON frames:
          {"type": "partial", "text": "...", "is_final": false}   — from recognizing
          {"type": "transcription", "text": "...", "is_final": true} — from recognized
          {"type": "error", "message": "..."}                     — on SDK init failure
    """
    import asyncio
    # speechsdk imported at module level (see top of file).

    # ------------------------------------------------------------------ auth
    # Validate token BEFORE accept() so rejected connections get a clean close.
    # validate_ws_token is synchronous and raises WebSocketException on failure.
    user_id = validate_ws_token(token)

    await websocket.accept()
    logger.info("voice_stream: WS accepted for user=%s", user_id)

    # --------------------------------------------------------- Speech SDK setup
    try:
        speech_config = speechsdk.SpeechConfig(
            subscription=settings.AZURE_SPEECH_KEY,
            region=settings.AZURE_SPEECH_REGION,
        )
        speech_config.speech_recognition_language = "en-US"

        push_stream = speechsdk.audio.PushAudioInputStream()
        audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("voice_stream: Speech SDK init failed for user=%s: %s", user_id, exc)
        await websocket.send_json({"type": "error", "message": "Speech SDK initialization failed"})
        await websocket.close(code=1011)
        return

    # ------------------------------------------------ phrase-list (US-7 hook)
    if load_user_phrase_list is not None:
        try:
            phrase_count = await load_user_phrase_list(recognizer, user_id, db)
            logger.info("Loaded %d phrases for user %s", phrase_count, user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice_stream: phrase list load failed for user=%s: %s", user_id, exc)
    else:
        logger.warning(
            "Personal dictionary unavailable (US-7 not merged); STT runs unboosted."
        )

    # --------------------------------------------- event wiring (thread-safe)
    loop = asyncio.get_event_loop()
    final_transcript_parts: list[str] = []

    def _on_recognizing(evt) -> None:  # type: ignore[type-arg]
        text = evt.result.text
        if text:
            asyncio.run_coroutine_threadsafe(
                websocket.send_json({"type": "partial", "text": text, "is_final": False}),
                loop,
            )

    def _on_recognized(evt) -> None:  # type: ignore[type-arg]
        text = evt.result.text
        if text:
            final_transcript_parts.append(text)
            asyncio.run_coroutine_threadsafe(
                websocket.send_json({"type": "transcription", "text": text, "is_final": True}),
                loop,
            )

    recognizer.recognizing.connect(_on_recognizing)
    recognizer.recognized.connect(_on_recognized)

    # Use _async variant (returns a Future); fall back to sync if not available
    start_result = recognizer.start_continuous_recognition_async()
    if hasattr(start_result, "get"):
        start_result.get()
    logger.info("voice_stream: continuous recognition started for user=%s", user_id)

    # -------------------------------------------------- receive audio chunks
    try:
        while True:
            data = await websocket.receive_bytes()
            push_stream.write(data)
    except WebSocketDisconnect:
        logger.info("voice_stream: WS disconnected for user=%s", user_id)
    finally:
        push_stream.close()
        stop_result = recognizer.stop_continuous_recognition_async()
        if hasattr(stop_result, "get"):
            stop_result.get()
        logger.info("voice_stream: recognition stopped for user=%s", user_id)

    # ------------------------------------------ post-disconnect: term usage
    final_transcript = " ".join(final_transcript_parts)
    if increment_term_usage is not None and final_transcript:
        try:
            await increment_term_usage(final_transcript, user_id, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "voice_stream: increment_term_usage failed for user=%s: %s", user_id, exc
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _run_pipeline(note_id: uuid.UUID) -> None:
    """Kick off the AI pipeline for *note_id* in a fresh DB session."""
    from app.database import SessionLocal
    from app.services.openai_client import get_openai_client

    async with SessionLocal() as db:
        pipeline = AIPipeline(openai_client=get_openai_client(), db=db)
        await pipeline.process_note(note_id)




def _audio_ext(content_type: str, filename: str | None) -> str:
    """Return file extension for audio content type."""
    mapping = {
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mp4": ".mp4",
        "audio/m4a": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
    }
    if content_type in mapping:
        return mapping[content_type]
    if filename:
        import os
        _, ext = os.path.splitext(filename)
        if ext:
            return ext
    return ".webm"
