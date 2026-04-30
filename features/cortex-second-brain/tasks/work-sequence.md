# Work Sequence: cortex-second-brain

> Each name maps to `features/cortex-second-brain/tasks/{name}.tasks.md`.

## Build Topology
- Ecosystem: Multi-language (Python backend + JavaScript/TypeScript frontend)
- Source units: `backend/` (Python package — FastAPI app), `frontend/` (Vite + React + TS package), `infra/` (Bicep + scripts)
- Test units: `backend/tests/` (pytest), `frontend/tests/` and `frontend/src/__tests__/` (Vitest)
- Topology: multi-project monorepo

> Note on User Story count: workforce.json `design.whatYouDoExtensions[2]` mandates exactly 9 User Stories grouped per the spec's MVP item ranges (Phase 1 items 1–6, 7–11, 12–14, 15–19, 20–21; Phase 2 items 22–28, 29–30, 31–32, 33–34). The default 3-story guideline is overridden by this explicit configuration. The phasing below sequences these 9 stories by their dependency order.

## Phase 0
<!-- Foundation must come first: every other story depends on the database schema, JWT auth, base SQLAlchemy models, FastAPI app skeleton, and the monorepo folder layout. -->
- us-1-foundation
  source: backend/ | test: backend/tests/

## Phase 1
<!-- AI pipeline depends on Foundation: needs the User/Note/Tag SQLAlchemy models, JWT auth dependency, notes router, env-var settings, alembic migration runner, and Docker image. -->
- us-2-ai-pipeline
  source: backend/ | test: backend/tests/

## Phase 2
<!-- Frontend setup depends on backend API surface (auth + notes) being live so the API client and login flow can be wired against real contracts. Single-story phase: the frontend setup is one source unit (frontend/) and one test unit (frontend/src/__tests__/). -->
- us-3-frontend-setup
  source: frontend/ | test: frontend/src/__tests__/

## Phase 3
<!-- Voice UX + Offline depends on the Vite/Tailwind/Dexie/PWA setup and the auth pages from Phase 2. Same frontend source unit, so this is sequential to Phase 2 (cannot parallelize with Phase 2). -->
- us-4-voice-ux-offline
  source: frontend/ | test: frontend/src/__tests__/

## Phase 4
<!-- Deployment depends on a working backend image and a working frontend build — i.e., both source units in a deployable state. Single story; touches the infra/ source unit (and a tiny middleware tweak in backend/app/main.py for slowapi). -->
- us-5-deployment
  source: infra/ | test: backend/tests/

## Phase 5
<!--
Three Phase 2 features can run in parallel:
- us-6-insights touches NEW backend modules (pipeline/distill.py, api/insights.py, api/export.py) and NEW frontend pages/components (InsightsPage, BrainViewPage, MusicPlayer, CreatePage). Test files live under backend/tests/test_distill.py, test_insights.py, and frontend/src/__tests__/Insights*, BrainView*, MusicPlayer*.
- us-7-personal-dictionary touches NEW backend modules (models/vocabulary.py, schemas/dictionary.py, api/dictionary.py, alembic/versions/002_add_user_vocabulary.py) plus a small additive call site inside services/speech.py and a small additive line inside api/voice.py file-mode upload. Frontend adds NEW components (PersonalDictionary.tsx, SettingsPage.tsx) and a NEW api/dictionary.ts.
- us-9-realtime-stt extends api/voice.py with a NEW @router.websocket route plus a small auth helper in auth/jwt.py; on the frontend it extends hooks/useVoiceRecorder.ts and components/VoiceCapture.tsx.

Source-exclusivity caveat (B16 — this convention is canonical and is now also reflected in the corresponding us-7 / us-9 task wording):
  - us-7 ships:
      * NEW symbols `load_user_phrase_list`, `increment_term_usage` in `backend/app/services/speech.py`.
      * MODIFIES `POST /api/voice/upload` in `backend/app/api/voice.py` (file-mode integration ONLY).
      * us-7 does NOT touch any WebSocket handler. Task 3.4 in us-7-personal-dictionary.tasks.md is explicitly a NO-OP.
  - us-9 ships:
      * NEW `@router.websocket('/api/voice/stream')` route in `backend/app/api/voice.py` — a new symbol, NOT a modification of an existing function in voice.py.
      * CONSUMES `load_user_phrase_list` / `increment_term_usage` from us-7 via a `try / except ImportError` guard so us-9 stays mergeable even when us-7 has not landed yet (degrades gracefully — STT runs unboosted with a WARN log).
  - That keeps each story's edits to non-overlapping symbols within voice.py and speech.py.
  - Merge-order rule: us-7 SHOULD merge first. If they merge in reverse, us-9's soft-fail import-guard means STT still works — just without phrase boost — until us-7 lands and the next deploy picks up the helpers.

Frontend exclusivity:
  - us-6 NEW pages/components only.
  - us-7 NEW SettingsPage + PersonalDictionary; touches App.tsx routing additively.
  - us-9 modifies VoiceCapture.tsx and useVoiceRecorder.ts that were authored in US-4 — no overlap with us-6 or us-7.

Test exclusivity:
  - us-6 → backend/tests/test_distill.py, test_insights.py + frontend/src/__tests__/Insights*, BrainView*, MusicPlayer*
  - us-7 → backend/tests/test_dictionary.py, test_voice_phrase_list.py + frontend/src/__tests__/PersonalDictionary*
  - us-9 → backend/tests/test_voice_ws.py + frontend/src/__tests__/VoiceCapture.realtime*

All three are deemed parallel-safe under the explicit merge-order rule above. If the Lead prefers strict no-shared-file enforcement, fall back to running us-7 and us-9 sequentially in two sub-phases — see below.
-->
- us-6-insights
  source: backend/ + frontend/ | test: backend/tests/ + frontend/src/__tests__/
- us-7-personal-dictionary
  source: backend/ + frontend/ | test: backend/tests/ + frontend/src/__tests__/
- us-9-realtime-stt
  source: backend/ + frontend/ | test: backend/tests/ + frontend/src/__tests__/

## Phase 6
<!-- Shadow Reader inserts Stage 1.5 into pipeline/processor.py (modifying the orchestration written in US-2) and adds the bottom-sheet to pages/NoteDetailPage.tsx (written in US-4). It also updates SettingsPage.tsx (written in US-7) to host ShadowReaderSettings. Because of these multiple shared-file edits, Shadow Reader is sequenced AFTER Phase 5 — particularly after us-7 so SettingsPage exists. -->
- us-8-shadow-reader
  source: backend/ + frontend/ | test: backend/tests/ + frontend/src/__tests__/
