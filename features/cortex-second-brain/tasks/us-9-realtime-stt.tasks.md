# User Story: US-9 — Real-time STT (WebSocket Streaming)

> Feature: cortex-second-brain
> Requirements: `/features/cortex-second-brain/requirements/requirements.md`
> Design: `/features/cortex-second-brain/designs/design.md` (Voice-First UX)
> Spec: `SECOND_BRAIN_BUILD_SPEC.md` Phase 2 items 33–34 (section 4.2 + addendum), § 2.6

## Acceptance Criteria

- WebSocket endpoint `/api/voice/stream` accepts JWT via `?token=<jwt>` query parameter (critique mitigation #4) and rejects unauthenticated connections.
- Client streams 250ms audio chunks via `MediaRecorder` ondataavailable; backend pipes them into Azure Speech `PushAudioInputStream`.
- Server emits real-time JSON over WS: `{type:'partial', text, is_final:false}` from `recognizing` events, and `{type:'transcription', text, is_final:true}` from `recognized` events.
- On WebSocket connect, the user's Personal Dictionary phrase list is loaded into the recognizer (US-7 hook); a log line records the count.
- After WS close, audio is uploaded to Blob, a note is created with `processing_status='transcribed'` and the pipeline runs.
- Frontend `<VoiceCapture />` shows partial text during recording (live transcription) and the final cleaned note within 2 seconds of stop (NFR-1).
- Total budget impact remains negligible; no new Azure resources.

## Status
**Status**: Not Started
**Started**: TBD
**Completed**: TBD

## Relevant Documentation
- `/features/cortex-second-brain/designs/design.md` — Voice-First UX
- `SECOND_BRAIN_BUILD_SPEC.md` § 2.6 (WebSocket STT impl + frontend VoiceCapture)
- `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md` § F1.2 (phrase list integration into voice handler)

## TDD Hook
Tester writes failing tests in `backend/tests/test_voice_ws.py` (auth via query token, mocked Speech recognizer, partial/final message round-trip, phrase-list-loaded log assertion) and `frontend/src/__tests__/VoiceCapture.realtime.test.tsx` (WS connection, partial-text display, audio chunk send). Coder waits for failing-tests signal before each task.

---

## Tasks

- [ ] 1 WebSocket endpoint
  - [ ] 1.1 In `backend/app/auth/jwt.py`, add `validate_ws_token(token: str) -> UUID` that decodes the access token and raises a clean WebSocket-friendly error if invalid (used by the WS endpoint to reject before accept)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.2 In `backend/app/api/voice.py`, implement `@router.websocket('/api/voice/stream')` per spec § 2.6 — accept query `token`, call `validate_ws_token`, then `await websocket.accept()`. Build `SpeechConfig` from `settings.AZURE_SPEECH_KEY/REGION`, `language='en-US'`. Create `PushAudioInputStream` + `AudioConfig` + `SpeechRecognizer`.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.3 Before `start_continuous_recognition()`, call the phrase-list loader from US-7 and log the count. Per work-sequence § Phase 5 (B16 convention): US-7 ships `load_user_phrase_list` in `services/speech.py` first; US-9 imports it. To make this story resilient to merge order, gate the import with `try / except ImportError` and degrade gracefully when the helper hasn't been merged yet:
    ```python
    try:
        from app.services.speech import load_user_phrase_list, increment_term_usage
        phrase_count = await load_user_phrase_list(recognizer, user_id, db)
        logger.info("Loaded %d phrases for user %s", phrase_count, user_id)
    except ImportError:
        # US-7 not merged yet — operate without phrase boost; do not fail the WS handshake.
        logger.warning("Personal dictionary unavailable (US-7 not merged); STT runs unboosted.")
        phrase_count = 0
    ```
    The Lead/Coder pair MUST merge US-7 before US-9 to avoid the warning path in production; this is the soft-fail safety net.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.4 Wire `recognizing` → `await websocket.send_json({'type':'partial','text':evt.result.text,'is_final':False})` and `recognized` → `{'type':'transcription','text':evt.result.text,'is_final':True}` per spec § 2.6
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.5 In the receive loop `while True: data = await websocket.receive_bytes(); push_stream.write(data)`. On `WebSocketDisconnect`, close push_stream and `stop_continuous_recognition`. After disconnect, if `increment_term_usage` was successfully imported in task 1.3, call `await increment_term_usage(final_transcript, user_id, db)`; otherwise skip silently (B16 — soft-fail when US-7 not yet merged).
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 2 Frontend real-time integration
  - [ ] 2.1 Update `frontend/src/hooks/useVoiceRecorder.ts` to also expose a `wsRef` and emit accumulated chunks into the WS as `ArrayBuffer`s every 250ms (alongside existing chunk accumulation for the offline-first fallback)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.2 Update `frontend/src/components/VoiceCapture.tsx` to open `new WebSocket(`${WS_BASE_URL}/api/voice/stream?token=${accessToken}`)` on `startRecording`. On `message`, parse JSON; for `partial`/`transcription`, set `partialText`. Close WS on `stopRecording`.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.3 In `VoiceCapture.tsx`, prefer WS-derived final transcription over polling once available; on stop, save LocalNote with `rawTranscription = partialText`, then upload audio blob and POST to `/api/notes` (online path) — same offline-first persistence regardless
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.4 Add a small live-transcription display element above the FAB during recording — shows `partialText` (truncates after 200 chars with ellipsis) so the user sees feedback in real time
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 3 Reconnection and error handling
  - [ ] 3.1 In `VoiceCapture.tsx`, handle `ws.onerror` and `ws.onclose` by falling back to file-mode `POST /api/voice/upload` after recording stops (so a network blip doesn't lose the capture). Surface a small toast on degraded mode.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.2 In `backend/app/api/voice.py` WS handler, wrap recognizer setup with try/except and `await websocket.send_json({type:'error', message})` + close on Speech SDK init failure
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
