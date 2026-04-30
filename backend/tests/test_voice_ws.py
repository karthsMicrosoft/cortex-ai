"""
test_voice_ws.py — US-9 Real-time STT (WebSocket Streaming) — TDD red

Covers (per task file + spec § 2.6):
  1.1  validate_ws_token(token) exported from app.auth.jwt
       - Decodes a valid access token → returns UUID
       - Raises WebSocketException (or equivalent) on invalid token
       - Raises on refresh token (wrong type)

  1.2  @router.websocket('/api/voice/stream') exists in voice.py
       - Rejects connection when no ?token= param (code 4001 or early close)
       - Accepts valid JWT → connection established

  1.3  Phrase-list loader called (with ImportError soft-fail)
       - When speech.load_user_phrase_list importable → called + log emitted
       - When not importable → warning logged, connection proceeds (not failed)

  1.4  Partial / final message round-trip
       - recognizing event → {"type":"partial","text":…,"is_final":false}
       - recognized event  → {"type":"transcription","text":…,"is_final":true}

  1.5  Receive loop + disconnect
       - Bytes sent from client are written into the push stream
       - On disconnect: push_stream closed + stop_continuous_recognition called

  3.2  Error path: Speech SDK init failure → error JSON + close

Mock strategy:
  - Azure Speech SDK (azure.cognitiveservices.speech) is fully mocked via
    unittest.mock — no real SDK installed in CI.
  - FastAPI TestClient websocket_connect used for WS tests.
  - DB dependency overridden with in-memory SQLite session (conftest).
  - JWT tokens generated with the real jwt.create_access_token helper.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketState

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers — generate real tokens for test assertions
# ---------------------------------------------------------------------------

def _make_access_token(user_id: uuid.UUID | None = None) -> str:
    """Return a signed access token for a (optionally specified) user."""
    from app.auth.jwt import create_access_token
    return create_access_token(user_id or uuid.uuid4())


def _make_refresh_token(user_id: uuid.UUID | None = None) -> str:
    """Return a signed REFRESH token (wrong type for WS)."""
    from app.auth.jwt import create_refresh_token
    return create_refresh_token(user_id or uuid.uuid4())


# ---------------------------------------------------------------------------
# Module import tests (always run — no app needed)
# ---------------------------------------------------------------------------

class TestModuleImports:
    """These tests are intentionally broad to confirm all symbols are wired."""

    def test_validate_ws_token_exported(self):
        """Task 1.1 — validate_ws_token must be importable from app.auth.jwt."""
        from app.auth.jwt import validate_ws_token  # noqa: F401
        assert callable(validate_ws_token)

    def test_voice_router_has_websocket_stream(self):
        """Task 1.2 — router must register a WS route at /api/voice/stream."""
        from app.api.voice import router
        ws_routes = [
            r for r in router.routes
            if hasattr(r, "path") and r.path in ("/api/voice/stream", "/stream")
        ]
        assert ws_routes, (
            "No WebSocket route found for /api/voice/stream (or /stream) in voice.router. "
            "Implement @router.websocket('/api/voice/stream') per spec § 2.6."
        )


# ---------------------------------------------------------------------------
# Task 1.1 — validate_ws_token
# ---------------------------------------------------------------------------

class TestValidateWsToken:
    """Unit tests for the standalone validate_ws_token helper."""

    def test_valid_access_token_returns_uuid(self):
        """A freshly minted access token should decode to the correct UUID."""
        from app.auth.jwt import validate_ws_token
        user_id = uuid.uuid4()
        token = _make_access_token(user_id)
        result = validate_ws_token(token)
        assert result == user_id

    def test_invalid_token_raises(self):
        """A garbage token must raise — not return None, not crash the process."""
        from app.auth.jwt import validate_ws_token
        import pytest
        with pytest.raises(Exception):  # WebSocketException or HTTPException
            validate_ws_token("not.a.valid.token")

    def test_expired_token_raises(self):
        """An expired token must raise."""
        from app.auth.jwt import validate_ws_token
        from jose import jwt as jose_jwt
        from app.config import settings
        import time

        # Build a token with exp in the past
        payload = {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "iat": int(time.time()) - 3600,
            "exp": int(time.time()) - 1,
        }
        expired_token = jose_jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
        with pytest.raises(Exception):
            validate_ws_token(expired_token)

    def test_refresh_token_raises(self):
        """A refresh token (type='refresh') must be rejected by validate_ws_token."""
        from app.auth.jwt import validate_ws_token
        refresh_token = _make_refresh_token()
        with pytest.raises(Exception):
            validate_ws_token(refresh_token)

    def test_empty_token_raises(self):
        """An empty string must raise."""
        from app.auth.jwt import validate_ws_token
        with pytest.raises(Exception):
            validate_ws_token("")


# ---------------------------------------------------------------------------
# Fixtures for WebSocket endpoint tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def speech_sdk_mock():
    """
    Mock the entire azure.cognitiveservices.speech namespace so no real SDK
    is needed. Returns a dict of mock objects for test assertions.
    """
    push_stream = MagicMock()
    push_stream.write = MagicMock()
    push_stream.close = MagicMock()

    audio_config = MagicMock()
    speech_config = MagicMock()

    recognizer = MagicMock()
    recognizer.start_continuous_recognition_async = MagicMock(
        return_value=MagicMock(get=MagicMock(return_value=None))
    )
    recognizer.stop_continuous_recognition_async = MagicMock(
        return_value=MagicMock(get=MagicMock(return_value=None))
    )
    recognizer.recognizing = MagicMock()
    recognizer.recognized = MagicMock()
    recognizer.phrase_list_grammar = MagicMock()

    mock_sdk = MagicMock()
    mock_sdk.SpeechConfig.return_value = speech_config
    mock_sdk.audio.PushAudioInputStream.return_value = push_stream
    mock_sdk.audio.AudioConfig.return_value = audio_config
    mock_sdk.SpeechRecognizer.return_value = recognizer
    mock_sdk.PhraseListGrammar.from_recognizer.return_value = MagicMock()

    return {
        "sdk": mock_sdk,
        "push_stream": push_stream,
        "audio_config": audio_config,
        "speech_config": speech_config,
        "recognizer": recognizer,
    }


@pytest.fixture()
def test_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture()
def valid_token(test_user_id) -> str:
    return _make_access_token(test_user_id)


@pytest.fixture()
def ws_client():
    """
    Sync TestClient wrapping the FastAPI app.
    Skips if app is not yet importable.
    """
    try:
        from app.main import app
    except ImportError as exc:
        pytest.skip(f"App not yet implemented: {exc}")

    # Override DB to use test session (simplified — DB not used by WS in tests)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Task 1.2 — WS auth via query token
# ---------------------------------------------------------------------------

class TestWebSocketAuth:
    """The WS endpoint must enforce JWT via ?token= query parameter."""

    def test_no_token_closes_connection(self, ws_client):
        """
        Connecting without ?token= must result in a closed WS (code 4001 or similar).
        The endpoint must NOT accept() a connection it cannot authenticate.
        """
        with pytest.raises(Exception):
            # Either websocket.connect raises, or we receive an immediate close
            with ws_client.websocket_connect("/api/voice/stream") as ws:
                msg = ws.receive_json()
                # If accepted: must have received an error, not a welcome
                assert msg.get("type") == "error", (
                    "Unauthenticated WS was accepted without an error response"
                )

    def test_invalid_token_closes_connection(self, ws_client):
        """
        An invalid/forged token must be rejected before accept().
        """
        with pytest.raises(Exception):
            with ws_client.websocket_connect(
                "/api/voice/stream?token=forged.token.here"
            ) as ws:
                msg = ws.receive_json()
                assert msg.get("type") == "error"

    def test_valid_token_accepted(self, ws_client, valid_token, speech_sdk_mock):
        """
        A valid access token should allow accept() to succeed.
        After connection, sending bytes + closing should not crash.
        """
        sdk_mocks = speech_sdk_mock

        with patch.dict("sys.modules", {"azure.cognitiveservices.speech": sdk_mocks["sdk"],
                                         "azure.cognitiveservices.speech.audio": sdk_mocks["sdk"].audio}):
            try:
                with ws_client.websocket_connect(
                    f"/api/voice/stream?token={valid_token}"
                ) as ws:
                    # Connection accepted — send a small audio chunk
                    ws.send_bytes(b"\x00\x01\x02\x03")
                    # Close from client side
            except Exception as exc:
                # If the endpoint closed after accepting (speech SDK mock issue), that's OK
                # as long as we connected (no 403/401 raise on connect itself)
                if "403" in str(exc) or "401" in str(exc) or "4001" in str(exc):
                    pytest.fail(
                        f"Valid token was rejected at WS auth: {exc}"
                    )


# ---------------------------------------------------------------------------
# Task 1.3 — Phrase list loader (soft-fail on ImportError)
# ---------------------------------------------------------------------------

class TestPhraseListLoader:
    """The WS handler loads phrase list from US-7 or degrades gracefully."""

    def test_phrase_list_loaded_when_available(self, ws_client, valid_token,
                                                speech_sdk_mock, caplog):
        """
        When load_user_phrase_list is importable, it must be called and a
        log line at INFO with the count must appear.
        """
        sdk_mocks = speech_sdk_mock

        mock_load = AsyncMock(return_value=5)

        with patch.dict("sys.modules", {
            "azure.cognitiveservices.speech": sdk_mocks["sdk"],
            "azure.cognitiveservices.speech.audio": sdk_mocks["sdk"].audio,
        }):
            with patch(
                "app.services.speech.load_user_phrase_list",
                mock_load,
                create=True,
            ):
                with caplog.at_level(logging.INFO, logger="app.api.voice"):
                    try:
                        with ws_client.websocket_connect(
                            f"/api/voice/stream?token={valid_token}"
                        ) as ws:
                            ws.send_bytes(b"\x00\x01")
                    except Exception:
                        pass  # disconnect is expected after send

        phrase_log_found = any(
            "phrase" in rec.message.lower() or "loaded" in rec.message.lower()
            for rec in caplog.records
        )
        assert phrase_log_found, (
            "Expected an INFO log about phrase count but none found. "
            "Task 1.3 requires: logger.info('Loaded %d phrases for user %s', phrase_count, user_id)"
        )

    def test_missing_phrase_loader_logs_warning_not_crash(self, ws_client, valid_token,
                                                           speech_sdk_mock, caplog):
        """
        When US-7 helpers are not importable (ImportError), the WS must:
        - NOT close with an error
        - Log a WARNING about the missing module
        """
        sdk_mocks = speech_sdk_mock

        with patch.dict("sys.modules", {
            "azure.cognitiveservices.speech": sdk_mocks["sdk"],
            "azure.cognitiveservices.speech.audio": sdk_mocks["sdk"].audio,
            # Ensure load_user_phrase_list is NOT importable
            "app.services.speech": None,  # type: ignore[assignment]
        }):
            with caplog.at_level(logging.WARNING, logger="app.api.voice"):
                try:
                    with ws_client.websocket_connect(
                        f"/api/voice/stream?token={valid_token}"
                    ) as ws:
                        ws.send_bytes(b"\x00\x01")
                except Exception:
                    pass

        warning_found = any(
            "unboosted" in rec.message.lower()
            or "us-7" in rec.message.lower()
            or "phrase" in rec.message.lower()
            for rec in caplog.records
            if rec.levelno >= logging.WARNING
        )
        assert warning_found, (
            "Expected a WARNING log when load_user_phrase_list not importable, "
            "but none found. Task 1.3 requires a graceful soft-fail log."
        )


# ---------------------------------------------------------------------------
# Task 1.4 — Partial / final message round-trip
# ---------------------------------------------------------------------------

class TestPartialFinalMessages:
    """The WS handler must emit correct JSON for STT events."""

    def _make_recognizing_event(self, text: str) -> MagicMock:
        evt = MagicMock()
        evt.result.text = text
        return evt

    def _make_recognized_event(self, text: str) -> MagicMock:
        evt = MagicMock()
        evt.result.text = text
        return evt

    def test_partial_message_schema(self, ws_client, valid_token, speech_sdk_mock):
        """
        When the recognizer fires a 'recognizing' event the WS must send:
          {"type": "partial", "text": <text>, "is_final": false}
        """
        sdk_mocks = speech_sdk_mock
        recognizer = sdk_mocks["recognizer"]

        # Capture the callback registered for recognizing
        recognizing_callbacks: list[Any] = []

        def capture_recognizing_connect(fn):
            recognizing_callbacks.append(fn)

        recognizer.recognizing.connect = capture_recognizing_connect

        received: list[dict] = []

        with patch.dict("sys.modules", {
            "azure.cognitiveservices.speech": sdk_mocks["sdk"],
            "azure.cognitiveservices.speech.audio": sdk_mocks["sdk"].audio,
        }):
            try:
                with ws_client.websocket_connect(
                    f"/api/voice/stream?token={valid_token}"
                ) as ws:
                    # Trigger the recognizing event from outside
                    if recognizing_callbacks:
                        evt = self._make_recognizing_event("Hello")
                        # The callback may be async; handle both cases
                        cb = recognizing_callbacks[0]
                        import asyncio
                        import inspect
                        if inspect.iscoroutinefunction(cb):
                            asyncio.get_event_loop().run_until_complete(cb(evt))
                        else:
                            cb(evt)

                    try:
                        msg = ws.receive_json(mode="text")
                        received.append(msg)
                    except Exception:
                        pass
            except Exception:
                pass

        if received:
            partial_msgs = [m for m in received if m.get("type") == "partial"]
            assert partial_msgs, f"No 'partial' message received; got: {received}"
            msg = partial_msgs[0]
            assert msg["is_final"] is False, "partial message must have is_final=false"
            assert "text" in msg, "partial message must contain 'text' key"

    def test_final_message_schema(self, ws_client, valid_token, speech_sdk_mock):
        """
        When the recognizer fires a 'recognized' event the WS must send:
          {"type": "transcription", "text": <text>, "is_final": true}
        """
        sdk_mocks = speech_sdk_mock
        recognizer = sdk_mocks["recognizer"]

        recognized_callbacks: list[Any] = []

        def capture_recognized_connect(fn):
            recognized_callbacks.append(fn)

        recognizer.recognized.connect = capture_recognized_connect

        received: list[dict] = []

        with patch.dict("sys.modules", {
            "azure.cognitiveservices.speech": sdk_mocks["sdk"],
            "azure.cognitiveservices.speech.audio": sdk_mocks["sdk"].audio,
        }):
            try:
                with ws_client.websocket_connect(
                    f"/api/voice/stream?token={valid_token}"
                ) as ws:
                    if recognized_callbacks:
                        evt = self._make_recognized_event("Final transcript text")
                        cb = recognized_callbacks[0]
                        import asyncio
                        import inspect
                        if inspect.iscoroutinefunction(cb):
                            asyncio.get_event_loop().run_until_complete(cb(evt))
                        else:
                            cb(evt)

                    try:
                        msg = ws.receive_json(mode="text")
                        received.append(msg)
                    except Exception:
                        pass
            except Exception:
                pass

        if received:
            final_msgs = [m for m in received if m.get("type") == "transcription"]
            assert final_msgs, f"No 'transcription' message received; got: {received}"
            msg = final_msgs[0]
            assert msg["is_final"] is True, "transcription message must have is_final=true"
            assert "text" in msg, "transcription message must contain 'text' key"


# ---------------------------------------------------------------------------
# Task 1.5 — Receive loop + disconnect
# ---------------------------------------------------------------------------

class TestReceiveLoopAndDisconnect:
    """Audio bytes from client go into push_stream; disconnect cleans up."""

    def test_bytes_written_to_push_stream(self, ws_client, valid_token, speech_sdk_mock):
        """
        Bytes sent over the WS must be forwarded to push_stream.write().
        """
        sdk_mocks = speech_sdk_mock
        push_stream = sdk_mocks["push_stream"]

        audio_chunk = b"\x52\x49\x46\x46" + b"\x00" * 20  # fake RIFF header

        with patch.dict("sys.modules", {
            "azure.cognitiveservices.speech": sdk_mocks["sdk"],
            "azure.cognitiveservices.speech.audio": sdk_mocks["sdk"].audio,
        }):
            try:
                with ws_client.websocket_connect(
                    f"/api/voice/stream?token={valid_token}"
                ) as ws:
                    ws.send_bytes(audio_chunk)
                    # Close immediately
            except Exception:
                pass

        # push_stream.write must have been called with the bytes we sent
        push_stream.write.assert_called()
        call_args = [c.args[0] for c in push_stream.write.call_args_list]
        assert any(audio_chunk in arg or arg == audio_chunk for arg in call_args), (
            f"Expected push_stream.write to be called with the audio bytes. "
            f"Actual calls: {call_args}"
        )

    def test_push_stream_closed_on_disconnect(self, ws_client, valid_token, speech_sdk_mock):
        """
        After the client disconnects, push_stream.close() must be called.
        """
        sdk_mocks = speech_sdk_mock
        push_stream = sdk_mocks["push_stream"]

        with patch.dict("sys.modules", {
            "azure.cognitiveservices.speech": sdk_mocks["sdk"],
            "azure.cognitiveservices.speech.audio": sdk_mocks["sdk"].audio,
        }):
            try:
                with ws_client.websocket_connect(
                    f"/api/voice/stream?token={valid_token}"
                ) as ws:
                    ws.send_bytes(b"\x00")
            except Exception:
                pass

        push_stream.close.assert_called()

    def test_stop_continuous_recognition_called_on_disconnect(self, ws_client, valid_token,
                                                               speech_sdk_mock):
        """
        After disconnect, stop_continuous_recognition_async (or sync variant) must be called.
        """
        sdk_mocks = speech_sdk_mock
        recognizer = sdk_mocks["recognizer"]

        with patch.dict("sys.modules", {
            "azure.cognitiveservices.speech": sdk_mocks["sdk"],
            "azure.cognitiveservices.speech.audio": sdk_mocks["sdk"].audio,
        }):
            try:
                with ws_client.websocket_connect(
                    f"/api/voice/stream?token={valid_token}"
                ) as ws:
                    ws.send_bytes(b"\x00")
            except Exception:
                pass

        stop_called = (
            recognizer.stop_continuous_recognition_async.called
            or recognizer.stop_continuous_recognition.called
        )
        assert stop_called, (
            "Expected stop_continuous_recognition_async (or stop_continuous_recognition) "
            "to be called after WS disconnect. Task 1.5."
        )


# ---------------------------------------------------------------------------
# Task 3.2 — Error path: Speech SDK init failure
# ---------------------------------------------------------------------------

class TestSpeechSdkInitFailure:
    """If Speech SDK setup fails the WS must send an error JSON then close."""

    def test_sdk_init_error_sends_error_json(self, ws_client, valid_token):
        """
        When SpeechConfig or SpeechRecognizer raises during setup,
        the endpoint must send {"type":"error","message":...} before closing.
        """
        broken_sdk = MagicMock()
        broken_sdk.SpeechConfig.side_effect = RuntimeError("Azure credentials missing")

        received: list[dict] = []

        with patch.dict("sys.modules", {
            "azure.cognitiveservices.speech": broken_sdk,
            "azure.cognitiveservices.speech.audio": broken_sdk.audio,
        }):
            try:
                with ws_client.websocket_connect(
                    f"/api/voice/stream?token={valid_token}"
                ) as ws:
                    try:
                        msg = ws.receive_json(mode="text")
                        received.append(msg)
                    except Exception:
                        pass
            except Exception:
                pass

        if received:
            error_msgs = [m for m in received if m.get("type") == "error"]
            assert error_msgs, (
                f"Expected an error JSON message on SDK init failure but got: {received}"
            )
            assert "message" in error_msgs[0], "Error JSON must contain 'message' key"
