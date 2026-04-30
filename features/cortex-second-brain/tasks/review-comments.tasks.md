# Review Comments: cortex-second-brain

> Review base commit: 3851ee8bb7af66aeccdc589eabea76577601660e
> Round 1 gathering — 2026-04-30 UTC

## Security Findings
ISSUES FOUND

### Hardcoded insecure JWT_SECRET_KEY default
- Severity: BLOCKING
- Location: backend/app/config.py:31
- Finding: JWT_SECRET_KEY has a default value of "change-me-in-production". If the environment variable is not set in a deployment, the app silently uses this weak, publicly-known key. Any attacker who knows the default can forge valid JWTs for any user.
- Recommendation: Remove the default value entirely so pydantic-settings raises a startup error when the variable is absent. Add a validator asserting the key is at least 32 characters and not equal to the placeholder string.

### Refresh token exposed in JSON response body (accessible to JavaScript)
- Severity: HIGH
- Location: backend/app/api/auth.py:104-108, backend/app/schemas/auth.py:22-25, frontend/src/api/auth.ts:9
- Finding: The refresh token is returned both in the httpOnly cookie AND in the JSON body (TokenPair.refresh_token). The cookie is correctly httpOnly and protected from JS access. However the JSON body value is readable by any JavaScript on the page. The LoginResponse TypeScript type in frontend/src/api/auth.ts declares refresh_token?: string, confirming the frontend receives the body value and it is exposed to XSS-based token theft.
- Recommendation: Remove refresh_token from the TokenPair JSON body. The httpOnly cookie is the correct and sufficient delivery channel. Update TokenPair schema and the LoginResponse TypeScript type to omit the field.

### No rate limiting on auth endpoints (login / register / refresh)
- Severity: HIGH
- Location: backend/app/api/auth.py (all three POST endpoints), backend/app/main.py:34
- Finding: A global slowapi limiter is configured (100/minute per user-or-IP) but no @limiter.limit() decorator is applied to any auth route. Unauthenticated endpoints /api/auth/login and /api/auth/register allow 100 attempts per minute per IP, effectively providing no brute-force protection for the single-user credential set.
- Recommendation: Decorate /api/auth/login and /api/auth/refresh with @limiter.limit("5/minute"). Add 10/minute to /api/auth/register. Add a TestRateLimiting class to test_auth.py since no tests exist for auth rate-limiting.

### No password strength validation on registration (security-sensitive path with no test coverage)
- Severity: HIGH
- Location: backend/app/schemas/auth.py:11-13, backend/tests/test_auth.py
- Finding: The password field in RegisterRequest is a bare str with no min_length, max_length, or complexity constraint. A user can register with a one-character password. No test asserts that short passwords are rejected. Per the review rules, a security-sensitive code path lacking test coverage is flagged HIGH.
- Recommendation: Add password: str = Field(..., min_length=8, max_length=128) to RegisterRequest. Add a test to test_auth.py asserting passwords shorter than 8 characters are rejected with 422.

### No input size limit on note content field (uncapped AI cost exposure)
- Severity: MEDIUM
- Location: backend/app/schemas/note.py:20 (NoteCreate.content), backend/app/schemas/note.py:35 (NoteUpdate.content)
- Finding: content: str has no max_length constraint. An authenticated user can submit arbitrarily large strings that are stored in the DB and sent verbatim to GPT-4o-mini in pipeline prompts, creating uncapped AI cost exposure and a potential DoS against the Azure OpenAI budget (NFR-4: $150/month cap). The 50 MB upload limit applies to binary files only.
- Recommendation: Add content: str = Field(..., max_length=50_000) to both NoteCreate and NoteUpdate. Add a test asserting oversized content is rejected with 422.

### JWT passed as URL query parameter for WebSocket (infrastructure log exposure)
- Severity: MEDIUM
- Location: backend/app/api/voice.py:132
- Finding: The WebSocket STT endpoint authenticates via ?token=<jwt> in the URL query string. The application-level log-scrubbing filter redacts the token from uvicorn logs, but Azure Container App HTTP access logs and upstream load-balancer or reverse-proxy logs capture raw request URLs before reaching uvicorn, so the full JWT may appear in Azure platform logs outside the application's control.
- Recommendation: Document that Azure Container App access logs must be treated as sensitive with a short retention window. As a medium-term improvement, consider a short-lived opaque voice ticket token exchanged via a REST endpoint and used for WS auth, so the long-lived JWT never appears in any URL.

### Stored SAS URLs in export not re-signed (expired or over-privileged URL exposure)
- Severity: LOW
- Location: backend/app/api/export.py:37-43
- Finding: _refresh_sas_url() is a stub that returns stored URLs unchanged. SAS URLs generated at upload time are valid for 24 hours. The export endpoint can silently return expired media URLs for old notes. Additionally, if the SAS TTL is ever increased, long-lived signed blob URLs would be included in the export JSON and would remain valid even after a note is deleted.
- Recommendation: Re-generate short-lived (1h) SAS URLs at export time rather than passing through stored URLs. The code comment acknowledges this as a production TODO; it should be implemented before GA.

### No refresh token revocation (30-day replay attack window)
- Severity: MEDIUM
- Location: backend/app/api/auth.py:115-179
- Finding: The /api/auth/refresh endpoint issues a new refresh token but does not invalidate the old one. The old token remains valid for its full 30-day TTL. A stolen refresh token can be replayed for up to 30 days even after the legitimate user has rotated. The test test_refresh_rotates_token only checks that the access token changes, not that the old refresh token is rejected.
- Recommendation: For the single-user MVP this is an accepted risk. Explicitly document it as a known threat model gap. Add a test (even marked xfail) that attempts to reuse the pre-rotation refresh token and documents the expected behavior, so the gap is visible to future reviewers.

## Performance Findings

> Reviewer: Performance agent | Date: 2026-04-29

### BLOCKING

**PERF-01 — N+1 DB queries inside `_get_or_create_tags` (notes.py + processor.py)**
- **File:** `backend/app/api/notes.py:50-58` (`_get_or_create_tags`) and `backend/app/pipeline/processor.py:311-322` (`_ensure_tag`)
- **Problem:** Both functions loop over tag names and issue one `SELECT … WHERE name=?` per tag, then an `INSERT` if missing. For a note with 5 tags, that is 5–10 round-trips to the database executed serially inside a request. `_ensure_tag` is called once per tag returned by GPT inside `_auto_tag_and_categorize`, which runs during every pipeline execution.
- **Impact:** At expected 3–5 tags/note and p95 latency of 300ms per CRUD op (design NFR), these extra round-trips easily push latency beyond budget. In bulk-sync scenarios the multiplier compounds.
- **Fix:** Fetch all existing tags in one `WHERE name = ANY(:names)` query, then batch-insert the missing ones with a single `INSERT … ON CONFLICT DO NOTHING` returning the new rows.

---

### HIGH

**PERF-02 — `increment_term_usage` fetches ALL user vocabulary terms on every STT call, then scans in Python**
- **File:** `backend/app/services/speech.py:147-173`
- **Problem:** `increment_term_usage` runs `SELECT * FROM user_vocabulary WHERE user_id = ?` with no filter, pulling all terms (up to the 2000-term cap) into memory. It then does a Python `in` substring scan over every term in a loop and commits once. This is an O(N) memory load + O(N×M) string scan (N terms, M = len(transcript)) on the hot STT path, executed synchronously in the voice upload handler.
- **Impact:** With 500–2000 terms this adds significant in-process CPU and memory pressure on the Container App's 0.5 vCPU / 1 GB allocation, directly on the voice upload latency path.
- **Fix:** Push the scan to Postgres with `WHERE term ILIKE ANY(ARRAY[...])` or use a `tsvector`/`ILIKE` match for known terms; alternatively add an index-supported SQL `UPDATE user_vocabulary SET usage_count = usage_count + 1 WHERE user_id = ? AND :content ILIKE '%' || term || '%'` pattern. At minimum, cap the SELECT to terms that could plausibly appear rather than fetching all 2000.

**PERF-03 — `generate_weekly_summary` always fetches ALL raw notes for the week even when daily summaries exist**
- **File:** `backend/app/pipeline/distill.py:210-218`
- **Problem:** `generate_weekly_summary` unconditionally queries all notes for the week (`select(Note) … WHERE created_at >= monday`), then passes them to `_build_weekly_prompt` as a fallback. The fallback is only used when there are no daily summaries, but the query always runs. At 5 captures/day × 7 days = 35+ notes, this is a gratuitous full-table scan on the notes table every time the weekly endpoint is called.
- **Fix:** Run the notes query only in the `else` branch of `_build_weekly_prompt`, i.e., only when `not daily_summaries`. Move the query inside the conditional.

**PERF-04 — `GET /api/insights/patterns` is an unguarded, on-demand GPT call with no caching**
- **File:** `backend/app/api/insights.py:248-318`
- **Problem:** Every visit to the Insights tab fires a GPT-4o-mini call (up to 100 notes × ~120 chars = ~12 000 token context). There is no caching layer — no Redis, no DB-level `patterns_cached_at`, nothing. The design explicitly decided against Redis for MVP, but no substitute mechanism exists. If the user refreshes the Insights page or the frontend mounts/unmounts, a fresh paid GPT call fires each time.
- **Impact:** At $0.15/1M input tokens with 12 000-token prompts, each call costs ~$0.002. At even 10 page visits/day this is $7/month just for patterns, significantly above the design's projected AI cost budget. It also adds 3–10s of latency to every Insights page load.
- **Fix:** Cache the patterns result in `daily_summaries`-style row or in a separate `insights_cache` column keyed to `(user_id, date)`. Regenerate at most once per 24h or on explicit "Refresh" button press. A simple DB column `patterns_generated_at` + `patterns_json` on the `users` row suffices for single-owner MVP.

**PERF-05 — `_HYBRID_SQL` search query applies `to_tsvector` at runtime with no GIN/GiST full-text index**
- **File:** `backend/app/api/search.py:34-62`
- **Problem:** The hybrid search SQL calls `to_tsvector('english', n.content)` and `ts_rank(...)` inline. There is no GIN or GiST index on `notes.content` for full-text search — the migration (`001_initial_schema.py`) creates HNSW for the vector column and B-tree indexes on scalar columns, but nothing for `tsvector`. Every search therefore performs a sequential full-text scan over all user notes, defeating the design's < 500ms p50 target as note count grows.
- **Fix:** Add `CREATE INDEX idx_notes_content_fts ON notes USING gin(to_tsvector('english', content))` in the migration and reference the generated column in the query with `WHERE to_tsvector('english', content) @@ plainto_tsquery(...)` to exploit the index. Alternatively use a generated stored `tsvector` column.

**PERF-06 — `bulk_import` in dictionary.py commits once per term inside a loop (up to 500 commits)**
- **File:** `backend/app/api/dictionary.py:201-215`
- **Problem:** The bulk import loop does `await db.commit()` inside the `for t in terms` loop. For a 500-term import, this is 500 sequential commits to the database. Each commit is a round-trip to Postgres. The method comment says "Duplicate terms are skipped" but the skip mechanism is a caught `IntegrityError` with a `rollback()` per row, also a round-trip.
- **Impact:** A 500-term bulk import will take several seconds and consume DB connection time proportional to term count, blocking the single asyncpg connection during the request.
- **Fix:** Use a single `INSERT … ON CONFLICT (user_id, term) DO NOTHING` with all rows in one statement; commit once at the end. Count inserted rows with `rowcount`.

---

### MEDIUM

**PERF-07 — `useSync` hook polls `syncManager.syncing` with a 500ms `setInterval` on every mounted component**
- **File:** `frontend/src/hooks/useSync.ts:39-44`
- **Problem:** Every component that calls `useSync()` (e.g., `SyncIndicator` rendered on both `LibraryPage` and `CapturePage`) creates a `setInterval` polling `syncManager.syncing` at 500ms. This causes repeated React state updates even when nothing is changing, potentially causing re-renders of the entire subtree twice per second.
- **Fix:** Expose `syncing` as an observable / event emitter on `syncManager` (e.g., a simple callback/event) so React state updates only on actual transitions, not on a timer. Alternatively use a `useRef` comparison before calling `setIsSyncing`.

**PERF-08 — `_SIMILAR_SQL` fetches the source note embedding twice (cross-join `notes src`)**
- **File:** `backend/app/api/search.py:130-143`
- **Problem:** The similar-notes query does a Cartesian product `FROM notes n, notes src WHERE src.id = :source_note_id`. This loads the source note's embedding again from the DB even though the handler already fetched and checked `note.embedding` at line 166. For large embedding vectors (1536 floats ≈ 6KB), this is redundant data transfer.
- **Impact:** Minor at single-user scale, but the two-table cross join prevents the planner from using the HNSW index for the source embedding lookup efficiently when the notes table grows.
- **Fix:** Pass the already-fetched embedding as a parameter, similar to the `_link_similar_notes` pattern in `processor.py`, and rewrite the query to `FROM notes n WHERE n.embedding <=> CAST(:source_emb AS vector)`.

**PERF-09 — `LibraryPage`/`useNotes` applies `dateFrom`/`dateTo` filters in JavaScript after fetching all matching notes from IndexedDB**
- **File:** `frontend/src/hooks/useNotes.ts:52-58`
- **Problem:** The `useNotes` hook fetches all notes matching `category` or `syncStatus` from Dexie, then filters by `dateFrom`/`dateTo` in JavaScript. Dexie supports compound indexes; the IndexedDB schema defines `createdAt` as an indexed field. Date filtering should be pushed into the Dexie query (`.where('createdAt').between(...)`) instead of post-fetch.
- **Impact:** For a user with hundreds of local notes and a narrow date filter, all notes matching the category are loaded into memory before filtering, which is wasteful in a mobile PWA with limited memory.
- **Fix:** Use `db.notes.where('createdAt').between(dateFrom, dateTo)` (with additional `.and()` filter for category) or switch to a Dexie compound index `[category+createdAt]`.

**PERF-10 — `react-force-graph-2d` is imported as a top-level static import (no code splitting)**
- **File:** `frontend/src/pages/BrainViewPage.tsx:4`
- **Problem:** `react-force-graph-2d` is a heavyweight dependency (d3-force + canvas rendering). It is imported at the top of `BrainViewPage.tsx` as a static import, so it lands in the main bundle even for users who never visit the Brain View tab. The Vite config has no `build.rollupOptions.output.manualChunks` or dynamic import for this route.
- **Fix:** Lazy-load the page with `React.lazy(() => import('./pages/BrainViewPage'))` and wrap the route with `<Suspense>` in `App.tsx`. This code-splits `react-force-graph-2d` into its own chunk and avoids bloating the initial JS bundle.

**PERF-11 — `wavesurfer.js` imported at module level in `MusicPlayer.tsx` (similar bundle-size concern)**
- **File:** `frontend/src/components/MusicPlayer.tsx` (inferred from `package.json` dependency and component name)
- **Problem:** `wavesurfer.js` v7 is a large library (~250KB minified). If it is imported at the top of `MusicPlayer.tsx` which is imported by `NoteDetailPage.tsx` which is a static route, the waveform renderer adds to the initial bundle for every note detail load, even for non-music notes.
- **Fix:** Conditionally import `wavesurfer.js` only when `isMusicNote === true`, either via a dynamic `import()` inside a `useEffect` or by extracting `MusicPlayer` into a lazy-loaded sub-component.

---

### LOW

**PERF-12 — `export_data` loads all notes into memory before streaming**
- **File:** `backend/app/api/export.py:107-122`
- **Problem:** Despite using `StreamingResponse`, the handler fetches all notes and all summaries into Python lists (`notes = list(...)`) before starting the async generator. For a user with thousands of notes, the full dataset lives in memory simultaneously on the 1 GB Container App. True streaming would use server-side cursors or `yield_per`.
- **Impact:** Low at expected volume (design: ~1000 notes/month) but creates an OOM risk if the export is triggered after months of use. The comment in the code acknowledges this: "Uses streaming so large exports … don't OOM the container" — but the current implementation does not achieve true streaming.
- **Fix:** Use SQLAlchemy's `stream_scalars` with `yield_per(100)` to stream rows in batches, yielding JSON chunks as each batch is processed.

**PERF-13 — `GET /api/insights/graph` fetches note_links with an `IN` query over up to 200 UUIDs**
- **File:** `backend/app/api/insights.py:221-228`
- **Problem:** The graph endpoint fetches up to 200 note IDs, then queries `note_links WHERE source_note_id IN (:200_uuids)`. A 200-element `IN` list is parsed by Postgres on every request. There is no limit on the number of links returned, so a well-connected graph could return O(200×5) = 1000 link rows and serialize them all.
- **Impact:** Minor at current scale. No `LIMIT` on the links query means edge cases with highly-linked notes could return unexpectedly large payloads.
- **Fix:** Add a `LIMIT 1000` or similar cap on the links result set. Consider using a JOIN instead of `IN` for the links query: `JOIN notes ON note_links.source_note_id = notes.id WHERE notes.user_id = ?`.

**PERF-14 — APScheduler `BackgroundScheduler` runs distill jobs synchronously via `asyncio.run()` inside a background thread**
- **File:** `backend/app/pipeline/distill.py:251-277`, `backend/app/main.py:87-88`
- **Problem:** `run_daily_distill` and `run_weekly_distill` call `asyncio.run(_inner())`, which creates a new event loop in the APScheduler background thread. This is correct for isolation, but if the FastAPI event loop is also running on the main thread, the scheduler job blocks the background thread for the entire duration of the GPT call (up to several seconds). For a single-user MVP this is acceptable, but `asyncio.run()` inside a `BackgroundScheduler` thread blocks that thread until complete, preventing other scheduled jobs from running concurrently.
- **Fix:** Consider using APScheduler's `AsyncIOScheduler` (which shares the FastAPI event loop) instead of `BackgroundScheduler` + `asyncio.run()` to avoid creating a second event loop. This is the pattern recommended in APScheduler 3.x docs for FastAPI.

---

### NIT

**PERF-N1 — `generate_daily_summary` fetches notes using string comparison on `created_at` datetime**
- **File:** `backend/app/pipeline/distill.py:111-118`
- **Problem:** The WHERE clause uses `Note.created_at >= str(day_start)` and `< str(day_end)`, passing Python `date` objects converted to strings. SQLAlchemy will cast these correctly for PostgreSQL, but it bypasses the typed comparison and may prevent index use if the driver interprets the string literal differently. The existing `idx_notes_created_at` is on `(user_id, created_at DESC)` and should be used — but the string cast adds ambiguity.
- **Fix:** Pass `datetime` objects directly (e.g., `datetime.combine(target_date, time.min)`) rather than `str(day_start)`.

**PERF-N2 — `ShadowReaderPrompt` polling schedule starts with a `setTimeout` delay before first poll**
- **File:** `frontend/src/components/ShadowReaderPrompt.tsx:83-92`
- **Problem:** The first poll is delayed by `intervalMs` (2000ms) because `schedulePoll` always wraps in `setTimeout`. If the Shadow Reader stage completed quickly (it typically runs within the pipeline's ~5–15s window), the user must wait 2s before the first check.
- **Impact:** Minor UX latency. Not a correctness issue.
- **Fix:** Fire the first poll immediately (no `setTimeout`), then schedule subsequent polls with the interval. This is the standard poll-with-initial-fire pattern.

**PERF-N3 — `_get_or_create_tags` in notes.py and `_ensure_tag` in processor.py are duplicated logic**
- **File:** `backend/app/api/notes.py:46-59`, `backend/app/pipeline/processor.py:311-322`
- **Problem:** Two separate implementations of tag get-or-create exist in different modules. They will diverge over time (one already missing the `is_auto` field the other sets). This is a maintainability issue that also means any future N+1 fix must be applied in two places.
- **Fix:** Extract a shared `get_or_create_tag(db, user_id, name, is_auto)` utility into `app/models/tag.py` or a new `app/utils/db_helpers.py`.

## Quality Findings

> Reviewer: Code Quality | Round 1 | 2026-04-30

### QA-01 [HIGH] — Alembic migration 003 uses deprecated `op.get_bind()` pattern incompatible with async Alembic context

**File:** `backend/alembic/versions/003_add_shadow_reader.py`

Migration 003 uses `conn = op.get_bind()` + `conn.execute(sa.text(...))`. In async-aware Alembic setups (which `alembic/env.py` is designed for), `op.get_bind()` returns a sync proxy that is incompatible with `run_sync`-style execution in a real asyncpg connection. Migrations 001 and 002 exclusively use the `op.create_table` / `op.execute(sa.text(...))` API. The 003 pattern will silently work in sync Alembic mode but can break in async contexts or future Alembic versions that enforce sync/async separation.

**Recommendation:** Replace `conn = op.get_bind()` + `conn.execute(sa.text(...))` calls in 003 with `op.execute(sa.text(...))` directly, matching the pattern used in 001.

---

### QA-02 [HIGH] — `azure_retry` does not filter `HTTPException` despite the module docstring — `_is_retryable` is dead code

**File:** `backend/app/utils/retry.py`

The module defines `_is_retryable` but never uses it. The decorator is constructed with `retry=retry_if_exception_type(Exception)`, which retries on ALL exceptions including `HTTPException`. The function `_is_retryable` is dead code. The module docstring says "Retries on any Exception EXCEPT FastAPI's HTTPException", but the implementation contradicts this. Any Azure wrapper that raises an `HTTPException` (e.g. to propagate a 4xx upstream) will be incorrectly retried up to 3 times.

**Recommendation:** Change the decorator to use `retry=retry_if_exception(lambda exc: not isinstance(exc, HTTPException))` (tenacity's `retry_if_exception` predicate form), and remove the dead `_is_retryable` function.

---

### QA-03 [HIGH] — `DELETE /api/dictionary/{id}` silently returns 204 for non-existent terms — diverges from task spec pattern

**File:** `backend/app/api/dictionary.py`, lines 167–180

The implementation issues a `DELETE` filtered by `(id, user_id)` but never checks whether a row was actually found, and the inline comment says "Silently succeeds even if not found." By contrast, `PUT /api/dictionary/{term_id}` calls `_get_term_or_404()`. The inconsistency means a wrong UUID on DELETE returns 204 instead of 404, hiding client-side bugs. The US-7 task spec lists `DELETE '/{id}'` (204) alongside `PUT '/{id}'` (200; 404 if not found), implying both should honour 404-on-miss.

**Recommendation:** Call `_get_term_or_404()` before the DELETE execute call (or check `rowcount` and raise 404 if 0 rows affected), consistent with PUT.

---

### QA-04 [HIGH] — Shadow Reader answer endpoint double-commits: status set eagerly, but reflection content appended only in background — leaves note in inconsistent interim state with no recovery path

**File:** `backend/app/api/shadow_reader.py` lines 106–120; `backend/app/pipeline/shadow_reader.py` lines 205–215

`answer_shadow_reader` sets `shadow_reader_status='answered'` and `shadow_reader_answer=payload.answer` and commits. Then `_merge_in_background` fetches the same note in a fresh session and calls `merge_answer_into_note`, which appends `\n\n--- Reflection ---\n{answer}` to `note.content`. If the background task fails, the note is permanently stuck with `status='answered'` but `content` without the reflection appended, and `shadow_reader_answer` already set. There is no retry or recovery path. The US-8 acceptance criterion "On answer, content gets `\n\n--- Reflection ---\n{answer}` appended" is met only if the background task succeeds.

**Recommendation:** Either (a) do not eagerly commit `answered` status — let the background task set both status and content in one atomic commit, returning `{"status": "processing"}` from the HTTP route, or (b) introduce a `merge_pending` intermediate status to distinguish "answer received but content not yet merged" from the terminal `answered` state.

---

### QA-05 [MEDIUM] — Duplicate `_note_to_out` helpers in `notes.py` and `voice.py` diverge — the `voice.py` copy omits Shadow Reader fields

**Files:** `backend/app/api/notes.py` lines 63–89; `backend/app/api/voice.py` lines 259–281

Two distinct `_note_to_out` functions exist. The one in `voice.py` omits `shadow_reader_status`, `shadow_reader_questions`, and `shadow_reader_answer`. Voice-upload responses will always surface the `NoteOut` Pydantic defaults (`shadow_reader_status="pending"`, `shadow_reader_questions=None`) regardless of the DB values. Any future schema change to `NoteOut` must be applied in both copies.

**Recommendation:** Extract a single `_note_to_out(note: Note) -> NoteOut` into a shared module (e.g., `backend/app/api/_helpers.py`) and import it in both routers, or move it to `backend/app/schemas/note.py` as a class method.

---

### QA-06 [MEDIUM] — `_run_ocr_and_pipeline` uses `types.SimpleNamespace` as a fake Note fallback — fragile and untested

**File:** `backend/app/api/notes.py`, lines 388–398

The fallback branch constructs a `types.SimpleNamespace` stub and passes it to `process_image_note` when the note is not yet visible in the new DB session. The stub only provides `id`, `image_url`, `content`, and `processing_status`. Any future expansion of `process_image_note` (e.g. accessing `note.user_id` for logging or `note.category`) will raise `AttributeError` silently swallowed by the outer exception handler. The root cause (race between `db.flush()` and background task start) should be fixed instead.

**Recommendation:** Call `await db.commit()` (not just `flush`) before spawning the background task so the note row is fully visible in other sessions. Remove the `SimpleNamespace` fallback.

---

### QA-07 [MEDIUM] — `generate_questions` truncates questions exceeding 15 words instead of filtering them — contradicts US-8 task spec

**File:** `backend/app/pipeline/shadow_reader.py`, lines 122–127

US-8 task 2.2 says: "Defensive: filter to strings ≤ 15 words." The implementation truncates to 15 words (`" ".join(q.split()[:15])`) instead of dropping. A truncated question may be grammatically incomplete, violating the US-8 acceptance criterion "All six categories produce contextually appropriate prompts."

**Recommendation:** Replace the truncation with `continue` (skip questions > 15 words), matching the spec's "filter" language.

---

### QA-08 [MEDIUM] — `voice_upload` (file-mode) does not load the personal dictionary phrase list — US-7 task 3.3 requires it

**File:** `backend/app/api/voice.py`, lines 89–90

`voice_upload` calls `await transcribe_audio_file(audio_bytes)` directly without loading the phrase list. `transcribe_audio_file` constructs its own `SpeechRecognizer` internally, leaving no hook to call `load_user_phrase_list` before recognition. US-7 task 3.3 states: "Update `backend/app/api/voice.py` `POST /api/voice/upload` (file mode) — call `load_user_phrase_list` before recognition." The WebSocket path correctly handles this; the file-mode path does not.

**Recommendation:** Refactor `transcribe_audio_file` to accept an optional pre-built recognizer (or a `user_id` + `db` pair), enabling phrase-list loading before file-mode recognition. At minimum, document the gap with a TODO referencing US-7 task 3.3.

---

### QA-09 [MEDIUM] — First-pull conflict detection misclassifies all pending notes at epoch baseline

**File:** `frontend/src/sync/syncManager.ts`, lines 297–334

On the very first pull (no `lastPull` in meta table), `lastPull` defaults to `'1970-01-01T00:00:00Z'`. Any `LocalNote` with `updatedAt` after epoch (all of them) and `syncStatus !== 'synced'` will be flagged as a conflict, even if the note was freshly created locally and not yet pushed. The US-4 acceptance criterion for the pull flow specifies conflict detection at "local.updatedAt > lastPull AND local.syncStatus !== 'synced'", which the implementation follows literally, but the epoch default creates a pathological first-run case.

**Recommendation:** Initialize `lastPull` to the current ISO timestamp at first app launch (e.g. in `start()` if the meta table has no entry) rather than epoch, so the first pull only conflicts notes that were modified after the app was installed.

---

### QA-10 [MEDIUM] — `OpenAIDep` Fastapi dependency injection in `insights.py` mixes dependency syntax with positional parameters in a fragile way

**File:** `backend/app/api/insights.py`, lines 153–157

`get_weekly_summary`, `get_patterns`, and `generate_express` all declare `openai: OpenAIDep` after `db: AsyncSession = Depends(get_db)`. FastAPI resolves `OpenAIDep` as a Depends annotation only if `OpenAIDep` is defined as `Annotated[AsyncAzureOpenAI, Depends(get_openai)]`. If `openai_client.py` exports `OpenAIDep` differently (e.g., just as a type alias without the Depends wrapper), the parameter will not be injected and the endpoint will silently receive `None` or raise a 422. The rest of the codebase uses `openai_client = await get_openai()` inline, which is explicit and testable. The `OpenAIDep` pattern is inconsistent with the rest of the codebase.

**Recommendation:** Replace `openai: OpenAIDep` with `openai_client = await get_openai()` inside the function body (matching the search.py pattern), or verify and document that `OpenAIDep` is correctly defined as `Annotated[AsyncAzureOpenAI, Depends(get_openai)]` and add a test that confirms injection works.

---

### QA-11 [LOW] — `insights.py` uses deprecated `datetime.utcnow()` instead of `datetime.now(timezone.utc)`

**File:** `backend/app/api/insights.py`, line 258

`datetime.utcnow()` is deprecated since Python 3.12 and will be removed in a future release. The rest of the codebase (e.g. `jwt.py`) uses `datetime.now(tz=timezone.utc)` correctly.

**Recommendation:** Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` and add `timezone` to the `datetime` import.

---

### QA-12 [LOW] — Session-scoped test DB fixture has implicit dependency on all model modules being importable simultaneously

**File:** `backend/tests/conftest.py`, lines 79–93

`Base.metadata.create_all` is called once per `session`-scoped fixture. Because `models/__init__.py` imports all models (including `UserVocabulary` and Phase 2 shadow reader columns), any import error in any model file will cause the entire test session to fail at fixture setup, even for tests in earlier user stories that don't touch the affected model. This is a TDD infrastructure risk when new stories are partially implemented.

**Recommendation:** Consider switching the DB fixture to `scope="function"` in CI, or add a comment documenting the implicit coupling so future coders know to keep all model files importable at all times.

---

### QA-13 [LOW] — `_note_to_out` in `voice.py` does not pass Shadow Reader fields to `NoteOut` — Pydantic defaults used instead of DB values

**File:** `backend/app/api/voice.py`, lines 259–281

As noted in QA-05, `_note_to_out` in `voice.py` omits all three `shadow_reader_*` fields. Pydantic's default for `shadow_reader_status` is `"pending"`, which happens to be correct for a newly-created voice note but will diverge from DB values if the endpoint is ever used to re-fetch an existing note (e.g., after a voice re-upload to an existing note ID).

**Recommendation:** Address via the shared helper extraction in QA-05.

---

### QA-14 [NIT] — `# noqa: F401` suppression on imports that are actually used within the same module

**Files:** `backend/app/api/notes.py` lines 29–31; `backend/app/pipeline/processor.py` line 31

`from app.pipeline.ocr import process_image_note  # noqa: F401 (patched by tests)` — `process_image_note` is called in `_run_ocr_and_pipeline` in the same file. Similarly `run_shadow_reader_stage` is called in `_stage_reflect_hook`. Neither import is actually unused; they are legitimate module-level imports. The `# noqa: F401` comments are misleading and may mask a real linter misconfiguration.

**Recommendation:** Remove the `# noqa: F401` annotations if the imports are genuinely used. If the linter still flags them, investigate the linter configuration rather than suppressing with noqa.

---

### QA-15 [NIT] — `_get_or_create_tags` (notes.py) and `_ensure_tag` (processor.py) are duplicated tag-upsert logic

**Files:** `backend/app/api/notes.py:46-59`, `backend/app/pipeline/processor.py:311-322`

Two separate implementations of tag get-or-create exist. They already differ: `_get_or_create_tags` defaults `is_auto=False`; `_ensure_tag` defaults `is_auto=True`. This is also flagged in PERF-N3. Any future N+1 fix or logic change must be applied in both places.

**Recommendation:** Extract a single `get_or_create_tag(db, user_id, name, is_auto)` utility into `app/models/tag.py` or a new `app/utils/db_helpers.py`.

---

### Summary

| ID | Severity | Area |
|----|----------|------|
| QA-01 | HIGH | Migration 003 uses deprecated `op.get_bind()` — incompatible with async Alembic |
| QA-02 | HIGH | `azure_retry` does not filter `HTTPException`; `_is_retryable` is dead code |
| QA-03 | HIGH | `DELETE /api/dictionary/{id}` silently 204 on missing term |
| QA-04 | HIGH | Shadow Reader answer double-commit leaves note in unrecoverable inconsistent state |
| QA-05 | MEDIUM | Duplicate `_note_to_out` helpers diverge; voice.py omits Shadow Reader fields |
| QA-06 | MEDIUM | `SimpleNamespace` stub OCR fallback is fragile; root race condition unresolved |
| QA-07 | MEDIUM | `generate_questions` truncates instead of filters questions > 15 words |
| QA-08 | MEDIUM | File-mode voice upload skips personal dictionary phrase list (US-7 task 3.3) |
| QA-09 | MEDIUM | First-pull sync misclassifies all pending notes as conflicts at epoch baseline |
| QA-10 | MEDIUM | `OpenAIDep` dependency injection in insights.py is inconsistent with rest of codebase |
| QA-11 | LOW | `datetime.utcnow()` deprecated; use `datetime.now(timezone.utc)` |
| QA-12 | LOW | Session-scoped test DB fixture has implicit full-model-import dependency |
| QA-13 | LOW | `voice.py _note_to_out` uses Pydantic defaults for shadow_reader fields instead of DB values |
| QA-14 | NIT | `# noqa: F401` on imports that are not actually unused |
| QA-15 | NIT | `_get_or_create_tags` / `_ensure_tag` are duplicate tag-upsert logic (see also PERF-N3) |

## Spec Auditor Findings

> Reviewer: Spec Conformance Auditor | Date: 2026-04-29
> Spec sources: `SECOND_BRAIN_BUILD_SPEC.md` + `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md`
> Design-justified deviations (OQ-1 through OQ-9, B1–B17) are treated as ACCEPTED and not flagged as issues.

---

### BLOCKING

_(None found.)_

---

### HIGH

**SA-H1 — `python-jose` version pin deviates from spec § 4.3 line 1478**

- **File:** `backend/requirements.txt:7`
- **Spec says:** `python-jose[cryptography]==3.3.*`
- **Actual:** `python-jose[cryptography]>=3.5,<4`
- **Impact:** Spec mandates an exact major-minor pin. The range `>=3.5,<4` allows future `3.x` releases not tested against this codebase. If a future minor version introduces a breaking API change, deployment silently picks it up. This is not design-justified; design.md references the spec's pinned list without overriding `python-jose`.
- **Fix:** Pin to `python-jose[cryptography]==3.3.*` per spec, or explicitly document the override in design.md as an accepted B-series decision.

**SA-H2 — `passlib[bcrypt]` version pin deviates from spec § 4.3 line 1479**

- **File:** `backend/requirements.txt:8`
- **Spec says:** `passlib[bcrypt]==1.7.*`
- **Actual:** `passlib[bcrypt]>=1.7,<2`
- **Impact:** Same reasoning as SA-H1. The range allows `1.8` or `1.9` not validated against this codebase. Not design-justified in design.md.
- **Fix:** Pin to `passlib[bcrypt]==1.7.*` per spec.

**SA-H3 — Extra `bcrypt>=4.0,<4.1` pin not in spec § 4.3 and not design-justified**

- **File:** `backend/requirements.txt:9`
- **Spec § 4.3 line 1479:** `passlib[bcrypt]==1.7.*` only — no separate `bcrypt` line.
- **Actual:** `bcrypt>=4.0,<4.1` added as a direct dependency.
- **Impact:** `passlib[bcrypt]` pulls `bcrypt` as a transitive dependency; pinning it directly to `>=4.0,<4.1` may introduce a version conflict (passlib 1.7 was validated against bcrypt 3.x, not 4.x). Not listed in design.md as an OQ resolution.
- **Fix:** Remove the separate `bcrypt` pin, or add a comment in `requirements.txt` explaining the compatibility reason (e.g., a known CVE in bcrypt 3.x).

---

### MEDIUM

**SA-M1 — Migration 001 creates the `embedding` column via a two-step TEXT placeholder then raw DDL drop/add**

- **File:** `backend/alembic/versions/001_initial_schema.py:93-95, 133-135`
- **Spec § 2.3 line 298:** `embedding vector(1536)` — the column must be the pgvector vector type.
- **Design § Required PostgreSQL extensions:** mandates `ALTER TABLE notes ADD COLUMN embedding vector(1536)` after dropping the placeholder text column.
- **Actual:** Migration creates `sa.Column("embedding", sa.Text(), ...)` as a placeholder at line 94, then executes `DROP COLUMN embedding` + `ADD COLUMN embedding vector(1536)` via raw DDL. This is functionally correct for a green-field build (no data ever lands in the TEXT column), but introduces a dead placeholder creation/drop pair that could confuse `alembic --autogenerate` comparisons and is not mandated by the design.
- **Fix:** Remove the `sa.Column("embedding", sa.Text(), ...)` line and replace the drop+add block with a single `op.execute("ALTER TABLE notes ADD COLUMN embedding vector(1536)")`.

---

### LOW

**SA-L1 — Spec § 5.2 Bicep verbatim (lines 1690–1781) omits Azure AI Vision resource; implementation correctly adds it**

- **File:** `infra/main.bicep:89-96`
- **Assessment:** The spec § 5.2 Bicep code block does not include the Vision resource, but spec § 2.1 architecture diagram, spec § 4.3 (`azure-ai-vision-imageanalysis==1.0.*`), and design.md all require it. Adding the Vision resource is correct and design-compliant. Flagged for audit traceability only — no action needed.

**SA-L2 — `frontend/src/pages/` has `ConflictsPage.tsx` and `RegisterPage.tsx` not listed in spec § 4.1 lines 1275–1279**

- **Files:** `frontend/src/pages/ConflictsPage.tsx`, `frontend/src/pages/RegisterPage.tsx`
- **Assessment:** `RegisterPage` is a necessary companion to `LoginPage` for the auth flow (spec § 2.10); its omission from the spec file tree is a spec gap. `ConflictsPage` implements the sync conflict resolution UX required by design.md § Sync pull flow (B13). Both are design-justified additions. No action needed.

**SA-L3 — `backend/app/api/` has `tags.py` and `upload.py` not listed in spec § 4.1 lines 1319–1327**

- **Files:** `backend/app/api/tags.py`, `backend/app/api/upload.py`
- **Assessment:** `tags.py` serves `GET /api/tags` + `POST /api/tags` from spec § 2.4 line 462. `upload.py` serves blob upload required by the sync flow. Both are mandated by the spec at the endpoint level; their extraction into named files is an implementation detail. No action needed.

---

### NIT

**SA-N1 — Addendum F2.4 line 947 lists `styles/animations.css` modification for `slide-up` keyframe; not directly verified**

- **Assessment:** `ShadowReaderPrompt.tsx` uses `animate-slide-up`. If the keyframe is defined in `globals.css` via a Tailwind `@keyframes` block, the requirement is met regardless of filename. Recommend manual check that the slide-up animation is present and functional on mobile.

---

### Acceptance Criteria Coverage Summary

**Spec § 5.3 Functional criteria** — all 8 items have >= 1 corresponding test: ✓ (see test_notes.py, test_pipeline.py, test_search.py, test_auth.py, syncManager.test.ts, test_voice_upload.py)

**Spec § 5.3 NFR criteria** — Lighthouse >= 90, API p95 < 300ms, voice < 2s: no automated tests — ACCEPTED (manual / load-test scope).

**Addendum F1.5 Personal Dictionary** — all 8 acceptance criteria covered by tests: ✓ (test_dictionary.py, test_voice_phrase_list.py, PersonalDictionary.test.tsx, SettingsPage.test.tsx)

**Addendum F2.5 Shadow Reader** — all 10 acceptance criteria covered by tests: ✓ (test_shadow_reader.py, ShadowReaderPrompt.test.tsx, ShadowReaderSettings.test.tsx)

---

### Summary

| ID | Severity | Finding |
|----|----------|---------|
| SA-H1 | HIGH | `python-jose` pin is `>=3.5,<4` instead of spec `==3.3.*` (spec § 4.3 line 1478) |
| SA-H2 | HIGH | `passlib[bcrypt]` pin is `>=1.7,<2` instead of spec `==1.7.*` (spec § 4.3 line 1479) |
| SA-H3 | HIGH | Extra `bcrypt>=4.0,<4.1` pin not in spec § 4.3 and not design-justified |
| SA-M1 | MEDIUM | Migration 001 two-step TEXT→vector(1536) placeholder pattern; simplify to single raw DDL |
| SA-L1 | LOW | Vision resource not in spec § 5.2 Bicep verbatim — correct implementation, audit note only |
| SA-L2 | LOW | `ConflictsPage` + `RegisterPage` not in spec § 4.1 — design-justified, no action |
| SA-L3 | LOW | `tags.py` + `upload.py` not in spec § 4.1 api/ tree — design-justified, no action |
| SA-N1 | NIT | `animations.css` slide-up keyframe (addendum F2.4 line 947) not verified; manual check recommended |

spec-auditor review complete — ISSUES FOUND: SA-H1 (`python-jose` version pin), SA-H2 (`passlib` version pin), SA-H3 (extra `bcrypt` pin), SA-M1 (migration 001 two-step embedding column)
