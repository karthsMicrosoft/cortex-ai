# User Story: US-2 — AI Pipeline (Blob, Speech, Capture, Organize, Search)

> Feature: cortex-second-brain
> Requirements: `/features/cortex-second-brain/requirements/requirements.md`
> Design: `/features/cortex-second-brain/designs/design.md`
> Spec: `SECOND_BRAIN_BUILD_SPEC.md` Phase 1 items 7–11 (section 4.2), pipeline 2.5, search 2.8

## Acceptance Criteria

- Audio uploads to Azure Blob via `services/blob_storage.py` and return SAS-signed URLs (24h read-only).
- Azure Speech file-mode transcription works; result populates `notes.raw_transcription`.
- Pipeline Stage 1 (CAPTURE) cleans `raw_transcription` into `notes.content` via GPT-4o-mini (max_tokens=1000, T=0.3); status `raw|transcribed → processed`.
- Pipeline Stage 2 (ORGANIZE) auto-tags, categorizes (six fixed categories), generates 1536d embedding via `text-embedding-3-small`, links similar notes (threshold=0.75, limit=5); status `processed → enriched`.
- `POST /api/search` returns hybrid (0.7 semantic + 0.3 ts_rank) results in < 500ms p50 against 1000-note seed.
- All Azure calls wrapped with `tenacity` exponential backoff; pipeline failures move note to `processing_status='failed'` without losing the raw record.
- Image OCR via Azure AI Vision: `POST /api/notes` with image URL extracts text into `notes.content`.

## Status
**Status**: Not Started
**Started**: TBD
**Completed**: TBD

## Relevant Documentation
- `/features/cortex-second-brain/designs/design.md` — AI Pipeline (CODE + Reflect), Semantic Search, Music Features
- `SECOND_BRAIN_BUILD_SPEC.md` § 2.5 (pipeline impl), § 2.8 (search SQL), § 2.9 (music processing), § 4.4 (env vars for OpenAI/Speech/Blob/Vision)

## TDD Hook
Tester writes failing tests in `backend/tests/` (test_pipeline.py, test_search.py, test_blob.py, test_speech.py, test_ocr.py) using `respx` to mock Azure SDK calls. Coder waits for failing-tests signal before each task.

---

## Tasks

- [ ] 1 Azure service clients and retry helper
  - [ ] 1.1 Create `backend/app/utils/retry.py` exposing a `tenacity` retry decorator (exponential backoff, max 3 attempts, on `Exception` minus `HTTPException`) — used by all Azure adapters
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.2 Create `backend/app/services/openai_client.py` exposing a singleton `AsyncAzureOpenAI` configured from `settings.AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION` and a `get_openai()` FastAPI dependency
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.3 Create `backend/app/services/blob_storage.py` with `upload_blob(container, path, data)` returning a 24h SAS URL, and `delete_blob(path)`. Use `AZURE_STORAGE_CONNECTION_STRING` and `AZURE_STORAGE_CONTAINER`. Wrap with retry decorator.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.4 Create `backend/app/services/speech.py` with `transcribe_audio_file(audio_bytes, language='en-US')` using Azure Speech SDK file recognition mode; returns transcript string. Wrap with retry decorator. (WebSocket streaming added in US-9.)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 2 Audio upload endpoint
  - [ ] 2.1 Create `backend/app/api/__init__.py` upload route: `POST /api/upload` accepts multipart `file`, uploads via `blob_storage.upload_blob`, returns `{url}`. Auth required.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.2 Add `POST /api/voice/upload` in `backend/app/api/voice.py` — accepts multipart audio, stores via `blob_storage`, calls `speech.transcribe_audio_file`, creates note with `raw_transcription`, `audio_url`, `source_type='voice'`, `processing_status='transcribed'`, schedules pipeline as `BackgroundTask`. Returns NoteOut.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 3 AI pipeline — Stage 1 CAPTURE
  - [ ] 3.1 Create `backend/app/pipeline/__init__.py` empty package init
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.2 Create `backend/app/pipeline/processor.py` with `class AIPipeline(openai_client, db)` and method `process_note(note_id)` orchestrating stages per design "AI Pipeline" — for US-2 only Stage 1 (CAPTURE) and Stage 2 (ORGANIZE) are implemented; Stage 1.5 hook is a no-op call site that US-8 will fill in
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.3 Implement `_stage_capture(note)` — GPT-4o-mini cleanup using prompt from spec § 2.5 verbatim; updates `note.content`, sets `processing_status='processed'`, commits. Skip cleanup if `source_type='text'` (already clean).
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 4 AI pipeline — Stage 2 ORGANIZE
  - [ ] 4.1 Implement `_auto_tag_and_categorize(note)` — GPT-4o-mini with `response_format={"type":"json_object"}`, returns `{tags, category, mood, summary, entities}`; persists to note and inserts/links rows in `tags`/`note_tags`. Category constrained to {Music, Fitness, Journal, Ideas, Spiritual, Learning}.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.2 Implement `_generate_embedding(note)` — call `text-embedding-3-small`, write 1536-dim vector to `note.embedding`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.3 Implement `_link_similar_notes(note, threshold=0.75, limit=5)` — pgvector cosine query verbatim from spec § 2.5 with `ON CONFLICT (source_note_id, target_note_id) DO UPDATE`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.4 Implement `_stage_organize(note)` running tag+embed in parallel via `asyncio.gather`, then linking, then setting `processing_status='enriched'`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.5 Wire pipeline into `backend/app/api/notes.py::POST /api/notes` and `voice.py::POST /api/voice/upload` — schedule via `BackgroundTasks`. Failures set `processing_status='failed'` and log error class only (no content)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.6 Add manual re-trigger endpoint `POST /api/ai/process/{note_id}` in `backend/app/api/notes.py` (idempotent — re-runs pipeline from current stage)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 5 Music note enrichment
  - [ ] 5.1 Create `backend/app/pipeline/music.py` with `process_music_note(note, openai_client, db)` per spec § 2.9 — extracts `tempo_guess`, `key_guess`, `genre`, `mood`, `instruments`, `description`, `development_suggestions` into `note.music_metadata`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 5.2 Call `process_music_note` from pipeline orchestrator after `_stage_organize` whenever `note.category == 'Music'`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 6 Image OCR
  - [ ] 6.1 Create `backend/app/services/vision.py` with `extract_text(image_url)` calling Azure AI Vision Image Analysis (`READ` feature). Wrap with retry decorator.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 6.2 Create `backend/app/pipeline/ocr.py` with `process_image_note(note)` — fetches image via `note.image_url`, runs `vision.extract_text`, writes result to `note.content`, sets `processing_status='transcribed'` so the rest of the pipeline runs
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 6.3 Wire OCR into `notes.py::POST /api/notes` when `source_type='image'` and `image_url` is present
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 7 Semantic + hybrid search
  - [ ] 7.1 Create `backend/app/schemas/search.py` Pydantic — `SearchRequest { query, category?, tags?[], date_from?, date_to?, limit=20 }` and `SearchResultItem`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 7.2 Create `backend/app/api/search.py` route `POST /api/search` — embed query via `text-embedding-3-small`, run hybrid SQL verbatim from spec § 2.8 (`0.7 * (1 - (embedding <=> :q_emb)) + 0.3 * ts_rank(...)` AS combined_score), apply optional filters, ORDER BY combined_score DESC LIMIT :limit
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 7.3 Add `GET /api/search/similar/{note_id}` returning top-N notes by cosine to the source note's embedding (excluding itself)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 7.4 Wire search router into `backend/app/main.py`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 8 Tags + sync push/pull
  - [ ] 8.1 Create `backend/app/api/__init__.py` `tags.py` with `GET /api/tags` (list all user's tags) and `POST /api/tags` (create manual tag, `is_auto=false`)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 8.2 Create `backend/app/schemas/sync.py` schemas for sync ops and `backend/app/api/sync.py` with `POST /api/sync/push` (accepts list of `{operation, entity_type, client_id, payload}`, applies them, returns `{synced_count, conflicts:[]}`) and `GET /api/sync/pull?since=<ISO8601>` (returns notes updated after timestamp + deletions list + server_time)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
