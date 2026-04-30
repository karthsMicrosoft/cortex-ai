# User Story: US-7 — Personal Dictionary (STT Vocabulary Boost)

> Feature: cortex-second-brain
> Requirements: `/features/cortex-second-brain/requirements/requirements.md` (Stories 18–20, FR-7)
> Design: `/features/cortex-second-brain/designs/design.md` (Personal Dictionary section)
> Spec: `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md` § F1.2, F1.4

## Acceptance Criteria

- Migration `002_add_user_vocabulary.py` creates `user_vocabulary` table + indexes per addendum F1.2.
- CRUD endpoints `GET/POST/PUT/DELETE /api/dictionary` work end-to-end.
- `POST /api/dictionary` enforces 2000-term hard limit (HTTP 400 when exceeded).
- `POST /api/dictionary/bulk` accepts up to 500 terms (HTTP 400 if larger).
- Duplicate term per user returns HTTP 409.
- WebSocket voice handler loads top-500 terms by `usage_count desc` into `PhraseListGrammar` on each connection; logs `Loaded {n} phrases for user {id}`.
- After STT, `usage_count` is incremented for terms found in the transcription.
- `GET /api/dictionary/export` returns full JSON dump.
- Settings page renders `<PersonalDictionary />` with chip-style list, type selector, color-coded chips, type filter, and instant add/delete.

## Status
**Status**: Not Started
**Started**: TBD
**Completed**: TBD

## Relevant Documentation
- `/features/cortex-second-brain/designs/design.md` — Personal Dictionary section, API/Interfaces (Personal Dictionary), Data Model (user_vocabulary)
- `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md` § F1.2 (verbatim implementation reference), § F1.4 (file modifications), § F1.5 (acceptance)

## TDD Hook
Tester writes failing tests in `backend/tests/test_dictionary.py` (CRUD, limits, duplicates, bulk, usage_count) and `backend/tests/test_voice_phrase_list.py` (mocked Speech SDK verifies phrase count loaded), plus `frontend/src/__tests__/PersonalDictionary.test.tsx`. Coder waits for failing-tests signal before each task.

---

## Tasks

- [ ] 1 Database migration and model
  - [ ] 1.1 Create `backend/alembic/versions/002_add_user_vocabulary.py` — creates `user_vocabulary` table with all columns and CHECK constraint per design Data Model `user_vocabulary` block, plus `idx_vocabulary_user` and `idx_vocabulary_type` indexes. Include `downgrade()` that drops cleanly.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.2 Create `backend/app/models/vocabulary.py` with `UserVocabulary` SQLAlchemy model — fields per addendum F1.2 verbatim (id, user_id, term, term_type, pronunciation_hint, boost_weight, usage_count, created_at, updated_at)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.3 Register `UserVocabulary` in `backend/app/models/__init__.py` exports
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 2 Pydantic schemas and CRUD endpoints
  - [ ] 2.1 Create `backend/app/schemas/dictionary.py` with `VocabularyTerm` (per F1.2 — term 1-200, term_type with literal enum, pronunciation_hint optional, boost_weight 0-2 default 1.0), `VocabularyTermOut`, `BulkImportRequest`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.2 Create `backend/app/api/dictionary.py` with router `prefix='/api/dictionary'`. Constant `MAX_TERMS_PER_USER = 2000`. Implement `GET ''` (filterable by `term_type`, ordered by `usage_count desc`); `POST ''` (201, 400 on limit, 409 on duplicate via IntegrityError); `PUT '/{id}'` (200); `DELETE '/{id}'` (204); `POST '/bulk'` (≤500, 400 otherwise, returns `{inserted,total}`); `GET '/export'` (full JSON list)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.3 Wire dictionary router into `backend/app/main.py`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 3 Speech service integration
  - [ ] 3.1 Add `load_user_phrase_list(recognizer, user_id, db, max_phrases=500)` to `backend/app/services/speech.py` per addendum F1.2 — selects user's vocab ordered by `usage_count desc` LIMIT 500, calls `PhraseListGrammar.from_recognizer(recognizer).addPhrase(term)` for each (and again for `pronunciation_hint` if present), returns count
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.2 Add `increment_term_usage(content, user_id, db)` to `backend/app/services/speech.py` — case-insensitive substring scan for each user term; increments `usage_count` and commits
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.3 Update `backend/app/api/voice.py` `POST /api/voice/upload` (file mode) — call `load_user_phrase_list` before recognition, log `Loaded {n} phrases for user {id}`, then call `increment_term_usage` after the transcript is final
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.4 **(NO-OP — moved to US-9 per work-sequence merge-order convention, B16):** US-7 does NOT modify the WebSocket handler in `backend/app/api/voice.py`. US-9 owns the new `@router.websocket('/api/voice/stream')` route and is responsible for calling `load_user_phrase_list` from inside that handler. This keeps the two stories on non-overlapping symbols inside `voice.py` (US-7 → file-mode upload only; US-9 → WS handler only), which is the source-exclusivity rule documented in `tasks/work-sequence.md` § Phase 5. Leave this task as a no-op or delete locally.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 4 Frontend API client and component
  - [ ] 4.1 Create `frontend/src/api/dictionary.ts` exposing `listTerms(filter?)`, `addTerm(payload)`, `updateTerm(id, patch)`, `deleteTerm(id)`, `bulkImport(terms)`, `exportTerms()` typed against backend Pydantic shapes
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.2 Create `frontend/src/components/PersonalDictionary.tsx` per addendum F1.2 — controlled input + type selector + add button + chip list with `TYPE_COLORS` map (name=blue-900, music_term=purple-900, technical=green-900, place=amber-900, acronym=rose-900, general=slate-700). Each chip shows term + X button → `deleteTerm`. Inline error display for limit/duplicate (parse 400/409 from API errors).
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.3 Create `frontend/src/pages/SettingsPage.tsx` (or update if a stub from US-3 exists) — section heading + `<PersonalDictionary />`. Add `Settings` route to `App.tsx` (no bottom-nav slot — accessed via gear icon in header)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.4 Optional bulk-import affordance on SettingsPage — file input that parses CSV/JSON in the browser and POSTs to `/api/dictionary/bulk` (chunked into ≤500-per-request batches if file is larger)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
