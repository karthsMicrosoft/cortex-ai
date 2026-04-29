# User Story: US-8 — Shadow Reader (Reflect Stage)

> Feature: cortex-second-brain
> Requirements: `/features/cortex-second-brain/requirements/requirements.md` (Stories 21–23, FR-8)
> Design: `/features/cortex-second-brain/designs/design.md` (Shadow Reader section, AI Pipeline Stage 1.5)
> Spec: `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md` § F2.2, F2.4

## Acceptance Criteria

- Migration `003_add_shadow_reader.py` adds `shadow_reader_enabled`, `shadow_reader_disabled_categories` to `users` and `shadow_reader_questions`, `shadow_reader_answer`, `shadow_reader_status` (with CHECK) to `notes`.
- Pipeline Stage 1.5 (Reflect) runs between Capture (Stage 1) and Organize (Stage 2). Trigger conditions: `users.shadow_reader_enabled` AND `note.category not in users.shadow_reader_disabled_categories` AND `len(note.content.split()) >= 50`.
- When triggered, Stage 1.5 generates ≤ 2 questions ≤ 15 words via GPT-4o-mini using category-specific prompts; persists `shadow_reader_questions`, sets status `asked`. When not triggered, status `skipped`.
- `GET /api/notes/{id}/shadow-reader`, `POST /api/notes/{id}/shadow-reader/answer`, `POST /api/notes/{id}/shadow-reader/dismiss`, `PUT /api/users/me/shadow-reader/settings` all work.
- On answer, content gets `\n\n--- Reflection ---\n{answer}` appended; embedding is regenerated asynchronously.
- Frontend `<ShadowReaderPrompt />` polls 5× at 1s after note creation and renders bottom-sheet on `asked`; dismiss/answer/skip transitions work; component never blocks the UI.
- Settings page hosts `<ShadowReaderSettings />` (global toggle + per-category opt-out chips).
- All six categories produce contextually appropriate prompts on a manual review (acceptance from F2.5 + requirements doc Phase 2).

## Status
**Status**: Not Started
**Started**: TBD
**Completed**: TBD

## Relevant Documentation
- `/features/cortex-second-brain/designs/design.md` — Shadow Reader section, AI Pipeline (Reflect stage), API/Interfaces (Shadow Reader)
- `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md` § F2.2 (verbatim implementation reference), § F2.4 (file modifications), § F2.5 (acceptance)

## TDD Hook
Tester writes failing tests in `backend/tests/test_shadow_reader.py` (trigger conditions, question generation cap, state transitions, answer-merge + embedding regen, settings endpoint), and `frontend/src/__tests__/ShadowReaderPrompt.test.tsx`, `ShadowReaderSettings.test.tsx`. Coder waits for failing-tests signal before each task.

---

## Tasks

- [ ] 1 Database migration and model updates
  - [ ] 1.1 Create `backend/alembic/versions/003_add_shadow_reader.py` — ALTER `users` ADD `shadow_reader_enabled BOOLEAN DEFAULT TRUE`, `shadow_reader_disabled_categories JSONB DEFAULT '[]'::jsonb`. ALTER `notes` ADD `shadow_reader_questions JSONB DEFAULT NULL`, `shadow_reader_answer TEXT DEFAULT NULL`, `shadow_reader_status VARCHAR(20) DEFAULT 'pending'` with CHECK on `(pending, asked, answered, dismissed, skipped)`. Include working `downgrade()`.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.2 Update `backend/app/models/user.py` to add the two columns; update `backend/app/models/note.py` to add the three columns. Confirm Pydantic `NoteOut` exposes `shadow_reader_status`, `shadow_reader_questions`, `shadow_reader_answer`.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 2 Reflect pipeline stage
  - [ ] 2.1 Create `backend/app/pipeline/shadow_reader.py` per addendum F2.2 — define `CATEGORY_PROMPTS` dict (Music / Journal / Ideas / Fitness / Spiritual / Learning) verbatim, constant `MIN_WORDS_FOR_TRIGGER = 50`, and async functions `should_trigger_shadow_reader(note, user)`, `generate_questions(note, openai_client)`, `run_shadow_reader_stage(note, user, openai_client, db)`, `merge_answer_into_note(note, answer, openai_client, db)`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.2 In `generate_questions`, call GPT-4o-mini with `max_tokens=200`, `temperature=0.7`, `response_format={'type':'json_object'}`. Parse `result.get('questions', [])` and return `[:2]`. Defensive: filter to strings ≤ 15 words.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.3 In `merge_answer_into_note`, append `\n\n--- Reflection ---\n{answer}` to `note.content`, set `shadow_reader_answer`, status `answered`, and regenerate embedding via `text-embedding-3-small`. Schedule the embedding regen as a `BackgroundTask` so the HTTP response returns immediately.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.4 Update `backend/app/pipeline/processor.py::AIPipeline.process_note` — between `_stage_capture` and `_stage_organize`, fetch the user, call `run_shadow_reader_stage(note, user, openai_client, db)`. Stage 2 still runs regardless of Reflect outcome.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 3 API endpoints
  - [ ] 3.1 Create `backend/app/schemas/shadow_reader.py` — `ShadowReaderAnswer { answer }`, `ShadowReaderQuestionsOut { status, questions[] }`, `ShadowReaderSettings { enabled, disabled_categories[] }`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.2 Create `backend/app/api/shadow_reader.py` with router `prefix='/api/notes'` per addendum F2.2 — `GET '/{note_id}/shadow-reader'` (returns status + questions), `POST '/{note_id}/shadow-reader/answer'` (409 if status != 'asked', else `merge_answer_into_note`), `POST '/{note_id}/shadow-reader/dismiss'` (sets status `dismissed`)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.3 Create `backend/app/api/users.py` with `PUT /api/users/me/shadow-reader/settings` accepting `ShadowReaderSettings` and updating the columns on the current user
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.4 Wire shadow_reader and users routers into `backend/app/main.py`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 4 Frontend prompt component
  - [ ] 4.1 Create `frontend/src/api/shadowReader.ts` exposing `getQuestions(noteId)`, `answer(noteId, text)`, `dismiss(noteId)`, `updateSettings(payload)`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.2 Add a `slide-up` keyframe to `frontend/src/styles/animations.css` (translateY 100% → 0 over 240ms ease-out)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.3 Create `frontend/src/components/ShadowReaderPrompt.tsx` per addendum F2.2 — props `{noteId, onComplete?}`. Polls `/api/notes/{id}/shadow-reader` 5× at 1s intervals; sets state `loading | asked | hidden`. On `asked`, renders fixed-bottom bottom-sheet with Sparkles header, dismiss-X, list of question paragraphs, textarea + send button + voice-mic button (voice answer recording reuses `useVoiceRecorder` and submits transcribed text).
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.4 Update `frontend/src/pages/NoteDetailPage.tsx` to render `<ShadowReaderPrompt noteId={id} />` after a fresh capture (e.g. when `processing_status` is `processed` or `enriched` and `shadow_reader_status === 'asked'` or `pending`)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 5 Settings UI
  - [ ] 5.1 Create `frontend/src/components/ShadowReaderSettings.tsx` per addendum F2.2 — global enable checkbox + chip list of six categories (toggling adds/removes from `disabledCategories`). Save button calls `updateSettings`.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 5.2 Update `frontend/src/pages/SettingsPage.tsx` to also render `<ShadowReaderSettings />` below `<PersonalDictionary />`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 5.3 Persist initial settings load on SettingsPage mount — fetch current user via `/api/auth/me` to populate the form, then save back via `PUT /api/users/me/shadow-reader/settings`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
