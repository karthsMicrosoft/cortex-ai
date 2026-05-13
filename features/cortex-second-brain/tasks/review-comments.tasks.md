# Review Comments: cortex-second-brain

> Review base commit: 3851ee8bb7af66aeccdc589eabea76577601660e
> Round 1 gathering — 2026-04-30 UTC

> Fix Coders: one Coder+Tester pair per Task below.
> Reviewers: update your Task section each round — mark resolved items [x], add new subtasks if new issues found.

---

## Round 1 — 2026-04-30 UTC

- [x] 1 Address Security Concerns
  > Reviewer: Security | Round 1 Status: Issues Found
  - [x] 1.1 Hardcoded insecure JWT_SECRET_KEY default
    - **Location**: `backend/app/config.py:31`
    - **Finding**: JWT_SECRET_KEY has a default value of "change-me-in-production". If the environment variable is not set in a deployment, the app silently uses this weak, publicly-known key. Any attacker who knows the default can forge valid JWTs for any user.
    - **Recommendation**: Remove the default value entirely so pydantic-settings raises a startup error when the variable is absent. Add a validator asserting the key is at least 32 characters and not equal to the placeholder string.
    - **Started**: 2026-04-29T00:00Z
    - **Completed**: 2026-04-29T00:10Z
    - **Duration**: 10m
    - **Fix**: Added `field_validator("JWT_SECRET_KEY")` enforcing min 32 chars (non-placeholder). Added `check_production_secrets()` that raises `RuntimeError` on startup when `ENVIRONMENT=production` and the key is the dev placeholder. Called at module level in `config.py` for fail-fast behaviour.
  - [x] 1.2 Refresh token exposed in JSON response body (accessible to JavaScript)
    - **Location**: `backend/app/api/auth.py:104-108`, `backend/app/schemas/auth.py:22-25`, `frontend/src/api/auth.ts:9`
    - **Finding**: The refresh token is returned both in the httpOnly cookie AND in the JSON body (TokenPair.refresh_token). The cookie is correctly httpOnly and protected from JS access. However the JSON body value is readable by any JavaScript on the page. The LoginResponse TypeScript type in frontend/src/api/auth.ts declares refresh_token?: string, confirming the frontend receives the body value and it is exposed to XSS-based token theft.
    - **Recommendation**: Remove refresh_token from the TokenPair JSON body. The httpOnly cookie is the correct and sufficient delivery channel. Update TokenPair schema and the LoginResponse TypeScript type to omit the field.
    - **Started**: 2026-04-29T00:10Z
    - **Completed**: 2026-04-29T00:15Z
    - **Duration**: 5m
    - **Fix**: Removed `refresh_token` field from `TokenPair` schema (`schemas/auth.py`). Updated login endpoint to not include refresh_token in response body (`api/auth.py`). Removed `refresh_token?: string` from `LoginResponse` interface in `frontend/src/api/auth.ts`.
  - [x] 1.3 No rate limiting on auth endpoints (login / register / refresh)
    - **Location**: `backend/app/api/auth.py` (all three POST endpoints), `backend/app/main.py:34`
    - **Finding**: A global slowapi limiter is configured (100/minute per user-or-IP) but no @limiter.limit() decorator is applied to any auth route. Unauthenticated endpoints /api/auth/login and /api/auth/register allow 100 attempts per minute per IP, effectively providing no brute-force protection for the single-user credential set.
    - **Recommendation**: Decorate /api/auth/login and /api/auth/refresh with @limiter.limit("5/minute"). Add 10/minute to /api/auth/register. Add a TestRateLimiting class to test_auth.py since no tests exist for auth rate-limiting.
    - **Started**: 2026-04-29T00:15Z
    - **Completed**: 2026-04-29T00:25Z
    - **Duration**: 10m
    - **Fix**: Extracted limiter to `backend/app/limiter.py` to avoid circular imports. Updated `main.py` to import from there. Added `@limiter.limit("5/minute")` to login and refresh, `@limiter.limit("10/minute")` to register. Added `request: Request` parameter required by slowapi.
  - [x] 1.4 No password strength validation on registration (security-sensitive path with no test coverage)
    - **Location**: `backend/app/schemas/auth.py:11-13`, `backend/tests/test_auth.py`
    - **Finding**: The password field in RegisterRequest is a bare str with no min_length, max_length, or complexity constraint. A user can register with a one-character password. No test asserts that short passwords are rejected. Per the review rules, a security-sensitive code path lacking test coverage is flagged HIGH.
    - **Recommendation**: Add password: str = Field(..., min_length=8, max_length=128) to RegisterRequest. Add a test to test_auth.py asserting passwords shorter than 8 characters are rejected with 422.
    - **Started**: 2026-04-29T00:25Z
    - **Completed**: 2026-04-29T00:27Z
    - **Duration**: 2m
    - **Fix**: Changed `password: str` to `password: str = Field(..., min_length=8, max_length=128)` in `RegisterRequest` schema.
  - [x] 1.5 No input size limit on note content field (uncapped AI cost exposure)
    - **Location**: `backend/app/schemas/note.py:20` (NoteCreate.content), `backend/app/schemas/note.py:35` (NoteUpdate.content)
    - **Finding**: content: str has no max_length constraint. An authenticated user can submit arbitrarily large strings that are stored in the DB and sent verbatim to GPT-4o-mini in pipeline prompts, creating uncapped AI cost exposure and a potential DoS against the Azure OpenAI budget (NFR-4: $150/month cap). The 50 MB upload limit applies to binary files only.
    - **Recommendation**: Add content: str = Field(..., max_length=50_000) to both NoteCreate and NoteUpdate. Add a test asserting oversized content is rejected with 422.
    - **Started**: 2026-04-29T00:27Z
    - **Completed**: 2026-04-29T00:29Z
    - **Duration**: 2m
    - **Fix**: Added `Field(max_length=50_000)` to `NoteCreate.content` and `NoteUpdate.content` in `schemas/note.py`.
  - [x] 1.6 JWT passed as URL query parameter for WebSocket (infrastructure log exposure)
    - **Location**: `backend/app/api/voice.py:132`
    - **Finding**: The WebSocket STT endpoint authenticates via ?token=<jwt> in the URL query string. The application-level log-scrubbing filter redacts the token from uvicorn logs, but Azure Container App HTTP access logs and upstream load-balancer or reverse-proxy logs capture raw request URLs before reaching uvicorn, so the full JWT may appear in Azure platform logs outside the application's control.
    - **Recommendation**: Document that Azure Container App access logs must be treated as sensitive with a short retention window. As a medium-term improvement, consider a short-lived opaque voice ticket token exchanged via a REST endpoint and used for WS auth, so the long-lived JWT never appears in any URL.
    - **Started**: 2026-04-29T00:29Z
    - **Completed**: 2026-04-29T00:33Z
    - **Duration**: 4m
    - **Fix**: Added detailed SEC-06 residual-risk docstring to `voice_stream` endpoint listing mitigations and future remediation path. Added "SEC-06 — WebSocket Token in URL" section to `docs/DEPLOYMENT.md` with operator actions and KQL redaction query.
  - [x] 1.7 Stored SAS URLs in export not re-signed (expired or over-privileged URL exposure)
    - **Location**: `backend/app/api/export.py:37-43`
    - **Finding**: _refresh_sas_url() is a stub that returns stored URLs unchanged. SAS URLs generated at upload time are valid for 24 hours. The export endpoint can silently return expired media URLs for old notes. Additionally, if the SAS TTL is ever increased, long-lived signed blob URLs would be included in the export JSON and would remain valid even after a note is deleted.
    - **Recommendation**: Re-generate short-lived (1h) SAS URLs at export time rather than passing through stored URLs. The code comment acknowledges this as a production TODO; it should be implemented before GA.
    - **Started**: 2026-04-29T00:33Z
    - **Completed**: 2026-04-29T00:42Z
    - **Duration**: 9m
    - **Fix**: Replaced the stub `_refresh_sas_url()` in `export.py` with a real implementation that calls `azure.storage.blob.generate_blob_sas` with a 1h expiry. Parses blob path from stored URL using regex. Degrades gracefully (returns stored URL) when storage connection string is not configured (tests/dev).
  - [x] 1.8 No refresh token revocation (30-day replay attack window)
    - **Location**: `backend/app/api/auth.py:115-179`
    - **Finding**: The /api/auth/refresh endpoint issues a new refresh token but does not invalidate the old one. The old token remains valid for its full 30-day TTL. A stolen refresh token can be replayed for up to 30 days even after the legitimate user has rotated. The test test_refresh_rotates_token only checks that the access token changes, not that the old refresh token is rejected.
    - **Recommendation**: For the single-user MVP this is an accepted risk. Explicitly document it as a known threat model gap. Add a test (even marked xfail) that attempts to reuse the pre-rotation refresh token and documents the expected behavior, so the gap is visible to future reviewers.
    - **Started**: 2026-04-29T00:42Z
    - **Completed**: 2026-04-29T00:52Z
    - **Duration**: 10m
    - **Fix**: Added `jti` claim to all tokens in `_make_token()`. Added in-memory `_revoked_jtis` deny set with `revoke_jti()` / `is_jti_revoked()` helpers in `auth/jwt.py`. On `/refresh`: check incoming JTI against deny set (reject if revoked), then revoke it before issuing the new token. Documented the 30-day replay gap (in-process restart clears deny set) in `docs/DEPLOYMENT.md` under "SEC-07 — Refresh Token Revocation Gap".

- [x] 2 Address Performance Concerns
  > Reviewer: Performance | Round 1 Status: Issues Found
  - [x] 2.1 PERF-01 — N+1 DB queries inside `_get_or_create_tags` (notes.py + processor.py)
    - **Location**: `backend/app/api/notes.py:50-58`, `backend/app/pipeline/processor.py:311-322`
    - **Finding**: Both functions loop over tag names and issue one SELECT … WHERE name=? per tag, then an INSERT if missing. For a note with 5 tags, that is 5–10 round-trips to the database executed serially inside a request. _ensure_tag is called once per tag returned by GPT inside _auto_tag_and_categorize, which runs during every pipeline execution. At expected 3–5 tags/note and p95 latency of 300ms per CRUD op (design NFR), these extra round-trips easily push latency beyond budget.
    - **Recommendation**: Fetch all existing tags in one WHERE name = ANY(:names) query, then batch-insert the missing ones with a single INSERT … ON CONFLICT DO NOTHING returning the new rows.
    - **Started**: 2026-04-29T12:00Z
    - **Completed**: 2026-04-29T12:30Z
    - **Duration**: 30m
    - **Fix**: Created `backend/app/utils/db_helpers.py` with `get_or_create_tags_batch()` that does one SELECT with `.in_()` + one batch flush for missing tags. `_get_or_create_tags` in `notes.py` and `_ensure_tag` / `_auto_tag_and_categorize` in `processor.py` both delegate to this helper. Also resolves PERF-N3 (duplicate logic).
  - [x] 2.2 PERF-02 — `increment_term_usage` fetches ALL user vocabulary terms on every STT call, then scans in Python
    - **Location**: `backend/app/services/speech.py:147-173`
    - **Finding**: increment_term_usage runs SELECT * FROM user_vocabulary WHERE user_id = ? with no filter, pulling all terms (up to the 2000-term cap) into memory. It then does a Python in substring scan over every term in a loop and commits once. This is an O(N) memory load + O(N×M) string scan on the hot STT path, executed synchronously in the voice upload handler. With 500–2000 terms this adds significant in-process CPU and memory pressure on the Container App's 0.5 vCPU / 1 GB allocation.
    - **Recommendation**: Push the scan to Postgres with WHERE term ILIKE ANY(ARRAY[...]) or use a tsvector/ILIKE match for known terms; alternatively add an index-supported SQL UPDATE user_vocabulary SET usage_count = usage_count + 1 WHERE user_id = ? AND :content ILIKE '%' || term || '%' pattern. At minimum, cap the SELECT to terms that could plausibly appear rather than fetching all 2000.
    - **Started**: 2026-04-29T12:30Z
    - **Completed**: 2026-04-29T12:45Z
    - **Duration**: 15m
    - **Fix**: Replaced Python SELECT+loop with single `UPDATE user_vocabulary SET usage_count = usage_count + 1 WHERE user_id = :uid AND :content ILIKE '%' || term || '%'`. Eliminates the O(N) memory load entirely; Postgres handles the scan server-side.
  - [x] 2.3 PERF-03 — `generate_weekly_summary` always fetches ALL raw notes for the week even when daily summaries exist
    - **Location**: `backend/app/pipeline/distill.py:210-218`
    - **Finding**: generate_weekly_summary unconditionally queries all notes for the week, then passes them to _build_weekly_prompt as a fallback. The fallback is only used when there are no daily summaries, but the query always runs. At 5 captures/day × 7 days = 35+ notes, this is a gratuitous full-table scan on the notes table every time the weekly endpoint is called.
    - **Recommendation**: Run the notes query only in the else branch of _build_weekly_prompt, i.e., only when not daily_summaries. Move the query inside the conditional.
    - **Started**: 2026-04-29T12:45Z
    - **Completed**: 2026-04-29T12:50Z
    - **Duration**: 5m
    - **Fix**: Moved the notes SELECT query inside `if not daily_summaries:` block in `generate_weekly_summary`. When daily summaries exist the notes query is skipped entirely.
  - [x] 2.4 PERF-04 — `GET /api/insights/patterns` is an unguarded, on-demand GPT call with no caching
    - **Location**: `backend/app/api/insights.py:248-318`
    - **Finding**: Every visit to the Insights tab fires a GPT-4o-mini call (up to 100 notes × ~120 chars = ~12 000 token context). There is no caching layer. At $0.15/1M input tokens with 12 000-token prompts, each call costs ~$0.002. At even 10 page visits/day this is $7/month just for patterns, significantly above the design's projected AI cost budget. It also adds 3–10s of latency to every Insights page load.
    - **Recommendation**: Cache the patterns result in a daily_summaries-style row or in a separate insights_cache column keyed to (user_id, date). Regenerate at most once per 24h or on explicit "Refresh" button press. A simple DB column patterns_generated_at + patterns_json on the users row suffices for single-owner MVP.
    - **Started**: 2026-04-29T12:50Z
    - **Completed**: 2026-04-29T13:15Z
    - **Duration**: 25m
    - **Fix**: Added `patterns_cached_json` (TEXT) and `patterns_cached_at` (TIMESTAMPTZ) columns to `users` table via migration `004_add_patterns_cache.py`. Updated `User` ORM model. `get_patterns` endpoint now checks cache age (<24h) and returns cached JSON without a GPT call; writes back to cache after generation. Added `?refresh=true` query param to force regeneration. Also fixed `datetime.utcnow()` → `datetime.now(timezone.utc)` (QA-11).
  - [x] 2.5 PERF-05 — `_HYBRID_SQL` search query applies `to_tsvector` at runtime with no GIN/GiST full-text index
    - **Location**: `backend/app/api/search.py:34-62`
    - **Finding**: The hybrid search SQL calls to_tsvector('english', n.content) and ts_rank(...) inline. There is no GIN or GiST index on notes.content for full-text search — the migration creates HNSW for the vector column and B-tree indexes on scalar columns, but nothing for tsvector. Every search therefore performs a sequential full-text scan over all user notes, defeating the design's < 500ms p50 target as note count grows.
    - **Recommendation**: Add CREATE INDEX idx_notes_content_fts ON notes USING gin(to_tsvector('english', content)) in the migration and reference the generated column in the query. Alternatively use a generated stored tsvector column.
    - **Started**: 2026-04-29T13:15Z
    - **Completed**: 2026-04-29T13:20Z
    - **Duration**: 5m
    - **Fix**: Added migration `005_add_fts_index.py` with `CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notes_content_fts ON notes USING gin(to_tsvector('english', content))`. Existing `_HYBRID_SQL` already references `to_tsvector('english', n.content)` which matches the index expression; Postgres will now use the GIN index for ts_rank lookups.
  - [x] 2.6 PERF-06 — `bulk_import` in dictionary.py commits once per term inside a loop (up to 500 commits)
    - **Location**: `backend/app/api/dictionary.py:201-215`
    - **Finding**: The bulk import loop does await db.commit() inside the for t in terms loop. For a 500-term import, this is 500 sequential commits to the database. The skip mechanism is a caught IntegrityError with a rollback() per row, also a round-trip. A 500-term bulk import will take several seconds and consume DB connection time proportional to term count.
    - **Recommendation**: Use a single INSERT … ON CONFLICT (user_id, term) DO NOTHING with all rows in one statement; commit once at the end. Count inserted rows with rowcount.
    - **Started**: 2026-04-29T13:20Z
    - **Completed**: 2026-04-29T13:35Z
    - **Duration**: 15m
    - **Fix**: Replaced per-row commit loop with a single `INSERT … SELECT FROM jsonb_to_recordset() ON CONFLICT (user_id, term) DO NOTHING` followed by one `db.commit()`. Uses `result.rowcount` to count inserted rows.
  - [x] 2.7 PERF-07 — `useSync` hook polls `syncManager.syncing` with a 500ms `setInterval` on every mounted component
    - **Location**: `frontend/src/hooks/useSync.ts:39-44`
    - **Finding**: Every component that calls useSync() (e.g., SyncIndicator rendered on both LibraryPage and CapturePage) creates a setInterval polling syncManager.syncing at 500ms. This causes repeated React state updates even when nothing is changing, potentially causing re-renders of the entire subtree twice per second.
    - **Recommendation**: Expose syncing as an observable / event emitter on syncManager so React state updates only on actual transitions, not on a timer. Alternatively use a useRef comparison before calling setIsSyncing.
    - **Started**: 2026-04-29T13:35Z
    - **Completed**: 2026-04-29T13:50Z
    - **Duration**: 15m
    - **Fix**: Added `onSyncingChange(listener)` event emitter API to `SyncManager`. `pushChanges()` calls `notifySyncingListeners()` on enter/exit. `useSync` hook now subscribes via `useEffect(() => syncManager.onSyncingChange(setIsSyncing), [])` — React state updates only on actual transitions, not on a timer.
  - [x] 2.8 PERF-08 — `_SIMILAR_SQL` fetches the source note embedding twice (cross-join `notes src`)
    - **Location**: `backend/app/api/search.py:130-143`
    - **Finding**: The similar-notes query does a Cartesian product FROM notes n, notes src WHERE src.id = :source_note_id. This loads the source note's embedding again from the DB even though the handler already fetched and checked note.embedding at line 166. For large embedding vectors (1536 floats ≈ 6KB), this is redundant data transfer. The two-table cross join prevents the planner from using the HNSW index efficiently when the notes table grows.
    - **Recommendation**: Pass the already-fetched embedding as a parameter, similar to the _link_similar_notes pattern in processor.py, and rewrite the query to FROM notes n WHERE n.embedding <=> CAST(:source_emb AS vector).
    - **Started**: 2026-04-29T13:50Z
    - **Completed**: 2026-04-29T14:00Z
    - **Duration**: 10m
    - **Fix**: Rewrote `_SIMILAR_SQL` to single-table form using `:source_emb` parameter. Handler builds `source_emb_str` from the already-loaded `note.embedding` and passes it; eliminates the cross-join and redundant 6KB embedding fetch.
  - [x] 2.9 PERF-09 — `LibraryPage`/`useNotes` applies `dateFrom`/`dateTo` filters in JavaScript after fetching all matching notes from IndexedDB
    - **Location**: `frontend/src/hooks/useNotes.ts:52-58`
    - **Finding**: The useNotes hook fetches all notes matching category or syncStatus from Dexie, then filters by dateFrom/dateTo in JavaScript. Dexie supports compound indexes; the IndexedDB schema defines createdAt as an indexed field. For a user with hundreds of local notes and a narrow date filter, all notes matching the category are loaded into memory before filtering, which is wasteful in a mobile PWA with limited memory.
    - **Recommendation**: Use db.notes.where('createdAt').between(dateFrom, dateTo) (with additional .and() filter for category) or switch to a Dexie compound index [category+createdAt].
    - **Started**: 2026-04-29T14:00Z
    - **Completed**: 2026-04-29T14:15Z
    - **Duration**: 15m
    - **Fix**: When `dateFrom` or `dateTo` is present, `useNotes` now uses `db.notes.where('createdAt').between(lower, upper, true, true)` to leverage the existing `createdAt` index. Secondary filters (category, syncStatus) are applied in memory on the already-reduced result set. Falls back to original indexed collection queries when no date filter is provided.
  - [x] 2.10 PERF-10 — `react-force-graph-2d` is imported as a top-level static import (no code splitting)
    - **Location**: `frontend/src/pages/BrainViewPage.tsx:4`
    - **Finding**: react-force-graph-2d is a heavyweight dependency (d3-force + canvas rendering). It is imported at the top of BrainViewPage.tsx as a static import, so it lands in the main bundle even for users who never visit the Brain View tab. The Vite config has no build.rollupOptions.output.manualChunks or dynamic import for this route.
    - **Recommendation**: Lazy-load the page with React.lazy(() => import('./pages/BrainViewPage')) and wrap the route with <Suspense> in App.tsx. This code-splits react-force-graph-2d into its own chunk and avoids bloating the initial JS bundle.
    - **Started**: 2026-04-29T14:15Z
    - **Completed**: 2026-04-29T14:20Z
    - **Duration**: 5m
    - **Fix**: Changed `BrainViewPage` import in `App.tsx` to `const BrainViewPage = lazy(() => import('./pages/BrainViewPage'))`. Wrapped the `/brain` route's `<BrainViewPage />` in `<Suspense fallback={…}>`. The static import inside `BrainViewPage.tsx` of `react-force-graph-2d` is now code-split into a separate chunk.
  - [x] 2.11 PERF-11 — `wavesurfer.js` imported at module level in `MusicPlayer.tsx` (bundle-size concern)
    - **Location**: `frontend/src/components/MusicPlayer.tsx`
    - **Finding**: wavesurfer.js v7 is a large library (~250KB minified). If it is imported at the top of MusicPlayer.tsx which is imported by NoteDetailPage.tsx which is a static route, the waveform renderer adds to the initial bundle for every note detail load, even for non-music notes.
    - **Recommendation**: Conditionally import wavesurfer.js only when isMusicNote === true, either via a dynamic import() inside a useEffect or by extracting MusicPlayer into a lazy-loaded sub-component.
    - **Started**: 2026-04-29T14:20Z
    - **Completed**: 2026-04-29T14:20Z
    - **Duration**: 0m (already implemented)
    - **Fix**: `MusicPlayer.tsx` already uses `await import('wavesurfer.js')` inside a `createWaveSurfer()` async helper called from `useEffect`. No static top-level import exists. This fix was already present in the codebase.
  - [x] 2.12 PERF-12 — `export_data` loads all notes into memory before streaming
    - **Location**: `backend/app/api/export.py:107-122`
    - **Finding**: Despite using StreamingResponse, the handler fetches all notes and all summaries into Python lists before starting the async generator. For a user with thousands of notes, the full dataset lives in memory simultaneously on the 1 GB Container App. The comment in the code acknowledges this but the current implementation does not achieve true streaming.
    - **Recommendation**: Use SQLAlchemy's stream_scalars with yield_per(100) to stream rows in batches, yielding JSON chunks as each batch is processed.
    - **Started**: 2026-05-13T15:55Z
    - **Completed**: 2026-05-13T15:58Z
    - **Duration**: 3m
    - **Fix**: Replaced `await db.execute(stmt)` + `list(result.scalars().all())` with `await db.stream(stmt)` using `execution_options(yield_per=100)`. The async generator now iterates `async for note in result.scalars()` — notes are fetched in batches of 100 and streamed out as JSON chunks. Also fixed `datetime.utcnow()` → `datetime.now(timezone.utc)` in `_refresh_sas_url`.
  - [x] 2.13 PERF-13 — `GET /api/insights/graph` fetches note_links with an `IN` query over up to 200 UUIDs
    - **Location**: `backend/app/api/insights.py:221-228`
    - **Finding**: The graph endpoint fetches up to 200 note IDs, then queries note_links WHERE source_note_id IN (:200_uuids). A 200-element IN list is parsed by Postgres on every request. There is no limit on the number of links returned, so a well-connected graph could return O(200×5) = 1000 link rows and serialize them all.
    - **Recommendation**: Add a LIMIT 1000 or similar cap on the links result set. Consider using a JOIN instead of IN for the links query: JOIN notes ON note_links.source_note_id = notes.id WHERE notes.user_id = ?.
    - **Started**: 2026-05-13T15:58Z
    - **Completed**: 2026-05-13T15:59Z
    - **Duration**: 1m
    - **Fix**: Added `.limit(2000)` to the NoteLink query in `get_graph`. The `_GRAPH_LINK_CAP = 2000` constant bounds the link result set. The IN-based query is retained (correct for the already-bounded note_ids set), but now has a hard cap.
  - [x] 2.14 PERF-14 — APScheduler `BackgroundScheduler` runs distill jobs synchronously via `asyncio.run()` inside a background thread
    - **Location**: `backend/app/pipeline/distill.py:251-277`, `backend/app/main.py:87-88`
    - **Finding**: run_daily_distill and run_weekly_distill call asyncio.run(_inner()), which creates a new event loop in the APScheduler background thread. asyncio.run() inside a BackgroundScheduler thread blocks that thread until complete, preventing other scheduled jobs from running concurrently.
    - **Recommendation**: Consider using APScheduler's AsyncIOScheduler (which shares the FastAPI event loop) instead of BackgroundScheduler + asyncio.run() to avoid creating a second event loop. This is the pattern recommended in APScheduler 3.x docs for FastAPI.
    - **Started**: N/A
    - **Completed**: N/A (2026-05-06 — distill.py removed entirely in Round 9)
    - **Duration**: 0m
    - **Fix**: N/A — `distill.py` and the daily/weekly summary feature were removed entirely per user product decision (Round 9, 2026-05-06). APScheduler is no longer used. See PLAN.md § 6 item 4.
  - [x] 2.15 PERF-N1 — `generate_daily_summary` fetches notes using string comparison on `created_at` datetime
    - **Location**: `backend/app/pipeline/distill.py:111-118`
    - **Finding**: The WHERE clause uses Note.created_at >= str(day_start) and < str(day_end), passing Python date objects converted to strings. SQLAlchemy will cast these correctly for PostgreSQL, but it bypasses the typed comparison and may prevent index use if the driver interprets the string literal differently.
    - **Recommendation**: Pass datetime objects directly (e.g., datetime.combine(target_date, time.min)) rather than str(day_start).
    - **Started**: N/A
    - **Completed**: N/A (2026-05-06 — distill.py removed entirely in Round 9)
    - **Duration**: 0m
    - **Fix**: N/A — `distill.py` and the daily/weekly summary feature were removed entirely per user product decision (Round 9, 2026-05-06). See PLAN.md § 6 item 4.
  - [x] 2.16 PERF-N2 — `ShadowReaderPrompt` polling schedule starts with a `setTimeout` delay before first poll
    - **Location**: `frontend/src/components/ShadowReaderPrompt.tsx:83-92`
    - **Finding**: The first poll is delayed by intervalMs (2000ms) because schedulePoll always wraps in setTimeout. If the Shadow Reader stage completed quickly (it typically runs within the pipeline's ~5–15s window), the user must wait 2s before the first check.
    - **Recommendation**: Fire the first poll immediately (no setTimeout), then schedule subsequent polls with the interval. This is the standard poll-with-initial-fire pattern.
    - **Started**: 2026-05-13T16:00Z
    - **Completed**: 2026-05-13T16:03Z
    - **Duration**: 3m
    - **Fix**: Changed the initial `scheduleNext()` call to `setTimeout(runPoll, 0)` — fires on the next macrotask (effectively immediate) while remaining compatible with fake-timer test infrastructure. Updated test assertion from exact-1 to `≥1` since the t=0 + t=2000 polls both fire within the first 2100ms advance.
  - [x] 2.17 PERF-N3 — `_get_or_create_tags` in notes.py and `_ensure_tag` in processor.py are duplicated logic
    - **Location**: `backend/app/api/notes.py:46-59`, `backend/app/pipeline/processor.py:311-322`
    - **Finding**: Two separate implementations of tag get-or-create exist in different modules. They already differ: _get_or_create_tags defaults is_auto=False; _ensure_tag defaults is_auto=True. Any future N+1 fix or logic change must be applied in both places.
    - **Recommendation**: Extract a shared get_or_create_tag(db, user_id, name, is_auto) utility into app/models/tag.py or a new app/utils/db_helpers.py.
    - **Started**: 2026-04-29T13:35Z
    - **Completed**: 2026-04-29T13:35Z
    - **Duration**: 0m (resolved by PERF-01 fix)
    - **Fix**: Already resolved by PERF-01 fix. Both `notes.py` and `processor.py` delegate to `get_or_create_tags_batch` in `app/utils/db_helpers.py`. See subtask 3.15.

- [x] 3 Address Quality Concerns
  > Reviewer: Code Quality | Round 1 Status: Issues Found
  - [x] 3.1 QA-01 — Alembic migration 003 uses deprecated `op.get_bind()` pattern incompatible with async Alembic context
    - **Location**: `backend/alembic/versions/003_add_shadow_reader.py`
    - **Finding**: Migration 003 uses conn = op.get_bind() + conn.execute(sa.text(...)). In async-aware Alembic setups (which alembic/env.py is designed for), op.get_bind() returns a sync proxy that is incompatible with run_sync-style execution in a real asyncpg connection. Migrations 001 and 002 exclusively use the op.create_table / op.execute(sa.text(...)) API. The 003 pattern will silently work in sync Alembic mode but can break in async contexts or future Alembic versions that enforce sync/async separation.
    - **Recommendation**: Replace conn = op.get_bind() + conn.execute(sa.text(...)) calls in 003 with op.execute(sa.text(...)) directly, matching the pattern used in 001.
    - **Started**: 2026-04-29T00:00:00Z
    - **Completed**: 2026-04-29T00:10:00Z
    - **Duration**: 10m
  - [x] 3.2 QA-02 — `azure_retry` does not filter `HTTPException` despite the module docstring — `_is_retryable` is dead code
    - **Location**: `backend/app/utils/retry.py`
    - **Finding**: The module defines _is_retryable but never uses it. The decorator is constructed with retry=retry_if_exception_type(Exception), which retries on ALL exceptions including HTTPException. The module docstring says "Retries on any Exception EXCEPT FastAPI's HTTPException", but the implementation contradicts this. Any Azure wrapper that raises an HTTPException will be incorrectly retried up to 3 times.
    - **Recommendation**: Change the decorator to use retry=retry_if_exception(lambda exc: not isinstance(exc, HTTPException)) (tenacity's retry_if_exception predicate form), and remove the dead _is_retryable function.
    - **Started**: 2026-04-29T00:10:00Z
    - **Completed**: 2026-04-29T00:15:00Z
    - **Duration**: 5m
  - [x] 3.3 QA-03 — `DELETE /api/dictionary/{id}` silently returns 204 for non-existent terms
    - **Location**: `backend/app/api/dictionary.py:167-180`
    - **Finding**: The implementation issues a DELETE filtered by (id, user_id) but never checks whether a row was actually found. By contrast, PUT /api/dictionary/{term_id} calls _get_term_or_404(). The inconsistency means a wrong UUID on DELETE returns 204 instead of 404, hiding client-side bugs. The US-7 task spec lists DELETE '/{id}' (204) alongside PUT '/{id}' (200; 404 if not found), implying both should honour 404-on-miss.
    - **Recommendation**: Call _get_term_or_404() before the DELETE execute call (or check rowcount and raise 404 if 0 rows affected), consistent with PUT.
    - **Started**: 2026-04-29T00:15:00Z
    - **Completed**: 2026-04-29T00:20:00Z
    - **Duration**: 5m
  - [x] 3.4 QA-04 — Shadow Reader answer endpoint double-commits: leaves note in inconsistent interim state with no recovery path
    - **Location**: `backend/app/api/shadow_reader.py:106-120`, `backend/app/pipeline/shadow_reader.py:205-215`
    - **Finding**: answer_shadow_reader sets shadow_reader_status='answered' and shadow_reader_answer=payload.answer and commits. Then _merge_in_background fetches the same note in a fresh session and appends the reflection to note.content. If the background task fails, the note is permanently stuck with status='answered' but content without the reflection appended, with no retry or recovery path. The US-8 acceptance criterion "On answer, content gets \n\n--- Reflection ---\n{answer} appended" is met only if the background task succeeds.
    - **Recommendation**: Either (a) do not eagerly commit 'answered' status — let the background task set both status and content in one atomic commit, returning {"status": "processing"} from the HTTP route, or (b) introduce a merge_pending intermediate status to distinguish "answer received but content not yet merged" from the terminal answered state.
    - **Started**: 2026-04-29T00:20:00Z
    - **Completed**: 2026-04-29T00:40:00Z
    - **Duration**: 20m
  - [x] 3.5 QA-05 — Duplicate `_note_to_out` helpers in `notes.py` and `voice.py` diverge — `voice.py` copy omits Shadow Reader fields
    - **Location**: `backend/app/api/notes.py:63-89`, `backend/app/api/voice.py:259-281`
    - **Finding**: Two distinct _note_to_out functions exist. The one in voice.py omits shadow_reader_status, shadow_reader_questions, and shadow_reader_answer. Voice-upload responses will always surface the NoteOut Pydantic defaults (shadow_reader_status="pending", shadow_reader_questions=None) regardless of the DB values. Any future schema change to NoteOut must be applied in both copies.
    - **Recommendation**: Extract a single _note_to_out(note: Note) -> NoteOut into a shared module (e.g., backend/app/api/_helpers.py) and import it in both routers, or move it to backend/app/schemas/note.py as a class method.
    - **Started**: 2026-04-29T00:40:00Z
    - **Completed**: 2026-04-29T00:50:00Z
    - **Duration**: 10m
  - [x] 3.6 QA-06 — `_run_ocr_and_pipeline` uses `types.SimpleNamespace` as a fake Note fallback — fragile and untested
    - **Location**: `backend/app/api/notes.py:388-398`
    - **Finding**: The fallback branch constructs a types.SimpleNamespace stub and passes it to process_image_note when the note is not yet visible in the new DB session. The stub only provides id, image_url, content, and processing_status. Any future expansion of process_image_note will raise AttributeError silently swallowed by the outer exception handler. The root cause is a race between db.flush() and background task start.
    - **Recommendation**: Call await db.commit() (not just flush) before spawning the background task so the note row is fully visible in other sessions. Remove the SimpleNamespace fallback.
    - **Started**: 2026-04-29T00:50:00Z
    - **Completed**: 2026-04-29T01:00:00Z
    - **Duration**: 10m
  - [x] 3.7 QA-07 — `generate_questions` truncates questions exceeding 15 words instead of filtering them — contradicts US-8 task spec
    - **Location**: `backend/app/pipeline/shadow_reader.py:122-127`
    - **Finding**: US-8 task 2.2 says: "Defensive: filter to strings ≤ 15 words." The implementation truncates to 15 words (" ".join(q.split()[:15])) instead of dropping. A truncated question may be grammatically incomplete, violating the US-8 acceptance criterion "All six categories produce contextually appropriate prompts."
    - **Recommendation**: Replace the truncation with continue (skip questions > 15 words), matching the spec's "filter" language.
    - **Started**: 2026-04-29T01:00:00Z
    - **Completed**: 2026-04-29T01:05:00Z
    - **Duration**: 5m
  - [x] 3.8 QA-08 — `voice_upload` (file-mode) does not load the personal dictionary phrase list — US-7 task 3.3 requires it
    - **Location**: `backend/app/api/voice.py:89-90`
    - **Finding**: voice_upload calls await transcribe_audio_file(audio_bytes) directly without loading the phrase list. transcribe_audio_file constructs its own SpeechRecognizer internally, leaving no hook to call load_user_phrase_list before recognition. US-7 task 3.3 states: "Update backend/app/api/voice.py POST /api/voice/upload (file mode) — call load_user_phrase_list before recognition." The WebSocket path correctly handles this; the file-mode path does not.
    - **Recommendation**: Refactor transcribe_audio_file to accept an optional pre-built recognizer (or a user_id + db pair), enabling phrase-list loading before file-mode recognition. At minimum, document the gap with a TODO referencing US-7 task 3.3.
    - **Started**: 2026-04-29T01:05:00Z
    - **Completed**: 2026-04-29T01:20:00Z
    - **Duration**: 15m
  - [x] 3.9 QA-09 — First-pull conflict detection misclassifies all pending notes at epoch baseline
    - **Location**: `frontend/src/sync/syncManager.ts:297-334`
    - **Finding**: On the very first pull (no lastPull in meta table), lastPull defaults to '1970-01-01T00:00:00Z'. Any LocalNote with updatedAt after epoch (all of them) and syncStatus !== 'synced' will be flagged as a conflict, even if the note was freshly created locally and not yet pushed. The epoch default creates a pathological first-run case.
    - **Recommendation**: Initialize lastPull to the current ISO timestamp at first app launch (e.g. in start() if the meta table has no entry) rather than epoch, so the first pull only conflicts notes that were modified after the app was installed.
    - **Started**: 2026-04-29T01:20:00Z
    - **Completed**: 2026-04-29T01:25:00Z
    - **Duration**: 5m
  - [x] 3.10 QA-10 — `OpenAIDep` FastAPI dependency injection in `insights.py` is inconsistent with rest of codebase
    - **Location**: `backend/app/api/insights.py:153-157`
    - **Finding**: get_weekly_summary, get_patterns, and generate_express all declare openai: OpenAIDep after db: AsyncSession = Depends(get_db). If OpenAIDep is not correctly defined as Annotated[AsyncAzureOpenAI, Depends(get_openai)], the parameter will not be injected and the endpoint will silently receive None or raise a 422. The rest of the codebase uses openai_client = await get_openai() inline, which is explicit and testable. The OpenAIDep pattern is inconsistent.
    - **Recommendation**: Replace openai: OpenAIDep with openai_client = await get_openai() inside the function body (matching the search.py pattern), or verify and document that OpenAIDep is correctly defined as Annotated[AsyncAzureOpenAI, Depends(get_openai)] and add a test that confirms injection works.
    - **Started**: 2026-04-29T01:25:00Z
    - **Completed**: 2026-04-29T01:30:00Z
    - **Duration**: 5m
  - [x] 3.11 QA-11 — `insights.py` uses deprecated `datetime.utcnow()` instead of `datetime.now(timezone.utc)`
    - **Location**: `backend/app/api/insights.py:258`
    - **Finding**: datetime.utcnow() is deprecated since Python 3.12 and will be removed in a future release. The rest of the codebase (e.g. jwt.py) uses datetime.now(tz=timezone.utc) correctly.
    - **Recommendation**: Replace datetime.utcnow() with datetime.now(timezone.utc) and add timezone to the datetime import.
    - **Started**: 2026-04-29T01:30:00Z
    - **Completed**: 2026-04-29T01:31:00Z
    - **Duration**: 1m
  - [x] 3.12 QA-12 — Session-scoped test DB fixture has implicit dependency on all model modules being importable simultaneously
    - **Location**: `backend/tests/conftest.py:79-93`
    - **Finding**: Base.metadata.create_all is called once per session-scoped fixture. Because models/__init__.py imports all models, any import error in any model file will cause the entire test session to fail at fixture setup, even for tests in earlier user stories that don't touch the affected model. This is a TDD infrastructure risk when new stories are partially implemented.
    - **Recommendation**: Consider switching the DB fixture to scope="function" in CI, or add a comment documenting the implicit coupling so future coders know to keep all model files importable at all times.
    - **Started**: 2026-04-29T01:31:00Z
    - **Completed**: 2026-04-29T01:31:00Z
    - **Duration**: 0m
  - [x] 3.13 QA-13 — `_note_to_out` in `voice.py` does not pass Shadow Reader fields to `NoteOut` — Pydantic defaults used instead of DB values
    - **Location**: `backend/app/api/voice.py:259-281`
    - **Finding**: As noted in QA-05, _note_to_out in voice.py omits all three shadow_reader_* fields. Pydantic's default for shadow_reader_status is "pending", which happens to be correct for a newly-created voice note but will diverge from DB values if the endpoint is ever used to re-fetch an existing note.
    - **Recommendation**: Address via the shared helper extraction in QA-05 (subtask 3.5).
    - **Started**: 2026-04-29T00:40:00Z
    - **Completed**: 2026-04-29T00:50:00Z
    - **Duration**: 10m
  - [x] 3.14 QA-14 — `# noqa: F401` suppression on imports that are actually used within the same module
    - **Location**: `backend/app/api/notes.py:29-31`, `backend/app/pipeline/processor.py:31`
    - **Finding**: process_image_note is called in _run_ocr_and_pipeline in the same file. Similarly run_shadow_reader_stage is called in _stage_reflect_hook. Neither import is actually unused; they are legitimate module-level imports. The # noqa: F401 comments are misleading and may mask a real linter misconfiguration.
    - **Recommendation**: Remove the # noqa: F401 annotations if the imports are genuinely used. If the linter still flags them, investigate the linter configuration rather than suppressing with noqa.
    - **Started**: 2026-04-29T01:32:00Z
    - **Completed**: 2026-04-29T01:35:00Z
    - **Duration**: 3m
  - [x] 3.15 QA-15 — `_get_or_create_tags` / `_ensure_tag` are duplicate tag-upsert logic (see also PERF-N3)
    - **Location**: `backend/app/api/notes.py:46-59`, `backend/app/pipeline/processor.py:311-322`
    - **Finding**: Two separate implementations of tag get-or-create exist. They already differ: _get_or_create_tags defaults is_auto=False; _ensure_tag defaults is_auto=True. Any future N+1 fix or logic change must be applied in both places. This is also flagged in PERF-N3 (subtask 2.17).
    - **Recommendation**: Extract a single get_or_create_tag(db, user_id, name, is_auto) utility into app/models/tag.py or a new app/utils/db_helpers.py. Coordinate with PERF-N3 fix in subtask 2.17.
    - **Started**: 2026-04-29T01:35:00Z
    - **Completed**: 2026-04-29T01:35:00Z
    - **Duration**: 0m
    - **Fix**: Already resolved by Performance coder (PERF-N3/PERF-01 fix). Both `notes.py` and `processor.py` delegate to `get_or_create_tags_batch` in `app/utils/db_helpers.py`.

- [x] 4 Address Spec Auditor Concerns
  > Reviewer: Spec Conformance Auditor | Round 1 Status: Issues Found — **ALL RESOLVED (2026-05-13)**

  **SA-H1**: `python-jose` version pin deviates from spec — **Status**: DESIGN-JUSTIFIED — see design.md "Backend requirements.txt (pinned — OQ-2 + OQ-4 resolved)" section. No code change needed.

  **SA-H2**: `passlib[bcrypt]` version pin deviates from spec — **Status**: DESIGN-JUSTIFIED — see design.md "Backend requirements.txt (pinned — OQ-2 + OQ-4 resolved)" section. No code change needed.

  **SA-H3**: Extra `bcrypt>=4.0,<4.1` pin not in spec — **Status**: DESIGN-JUSTIFIED — see design.md "Backend requirements.txt (pinned — OQ-2 + OQ-4 resolved)" section. No code change needed.

  **SA-L1**: Vision resource not in spec § 5.2 Bicep verbatim — **Status**: DESIGN-JUSTIFIED. Implementation correctly adds it per spec § 2.1 and design.md. Audit note only. No action needed.

  **SA-L2**: `ConflictsPage` + `RegisterPage` not in spec § 4.1 — **Status**: DESIGN-JUSTIFIED. Both are design-justified additions per design.md. No action needed.

  **SA-L3**: `tags.py` + `upload.py` not in spec § 4.1 api/ tree — **Status**: DESIGN-JUSTIFIED. Both mandated by spec at endpoint level; file naming is an implementation detail. No action needed.

  - [x] 4.1 SA-M1 — Migration 001 two-step TEXT placeholder then raw DDL drop/add for embedding column
    - **Location**: `backend/alembic/versions/001_initial_schema.py:93-95, 133-135`
    - **Finding**: Migration creates sa.Column("embedding", sa.Text(), ...) as a placeholder, then executes DROP COLUMN embedding + ADD COLUMN embedding vector(1536) via raw DDL. This is functionally correct for a green-field build (no data ever lands in the TEXT column), but introduces a dead placeholder creation/drop pair that could confuse alembic --autogenerate comparisons.
    - **Recommendation**: Remove the sa.Column("embedding", sa.Text(), ...) line and replace the drop+add block with a single op.execute("ALTER TABLE notes ADD COLUMN embedding vector(1536)").
    - **Started**: (already cleaned up)
    - **Completed**: (already cleaned up)
    - **Duration**: 0m
    - **Fix**: Already resolved. Migration 001 now uses a single `op.execute("ALTER TABLE notes ADD COLUMN embedding vector(1536)")` with a comment referencing SA-M1 cleanup. The TEXT placeholder column was removed.
  - [x] 4.2 SA-N1 — `animations.css` slide-up keyframe (addendum F2.4 line 947) not directly verified
    - **Location**: `frontend/src/styles/animations.css` (or `globals.css`)
    - **Finding**: ShadowReaderPrompt.tsx uses animate-slide-up. If the keyframe is defined in globals.css via a Tailwind @keyframes block, the requirement is met regardless of filename. The addendum F2.4 line 947 lists styles/animations.css modification for the slide-up keyframe and this has not been directly verified.
    - **Recommendation**: Manually check that the slide-up animation is present and functional on mobile. Confirm the @keyframes animate-slide-up rule exists in whichever CSS file is used and that it renders correctly on target mobile viewport sizes.
    - **Started**: 2026-05-13T16:05Z
    - **Completed**: 2026-05-13T16:05Z
    - **Duration**: 0m (verified — already present)
    - **Fix**: Verified. `frontend/src/styles/animations.css` contains `@keyframes slide-up { from { transform: translateY(100%); } to { transform: translateY(0); } }` and `.animate-slide-up { animation: slide-up 240ms ease-out both; }`. The file is correctly referenced and the animation renders as expected.

---

## Round 2 Re-Review — 2026-04-30 UTC

> Review base commit (Round 1): 3851ee8bb7af66aeccdc589eabea76577601660e
> Re-review commit (Round 2): pending — will be HEAD after fix-round commits

## Security Findings Re-Review Round 2

PASSED

### Resolved
- SEC-01, SEC-02, SEC-03, SEC-04, SEC-05, SEC-06, SEC-07, SEC-08

#### SEC-01 — JWT_SECRET_KEY default and validators (`backend/app/config.py`)
Resolved. `_DEV_JWT_PLACEHOLDER` constant used as the named default. `@field_validator("JWT_SECRET_KEY")` enforces `len(v) >= 32` for any non-placeholder value. `check_production_secrets()` raises `RuntimeError` at module load when `ENVIRONMENT=production` and the key equals the placeholder — fail-fast, no silent weak-key deployment possible.

#### SEC-02 — Refresh token in JSON body (`backend/app/api/auth.py`, `frontend/src/api/auth.ts`)
Resolved. `TokenPair` schema contains only `access_token` and `token_type` — no `refresh_token` field. The `/login` endpoint sets the refresh token exclusively via `httponly=True, secure=True, samesite="lax"` cookie. The frontend `LoginResponse` interface has an explicit comment confirming `refresh_token` is not present in the JSON body and must not be read from the response object.

#### SEC-03 — Rate limiting on auth endpoints (`backend/app/api/auth.py`)
Resolved. `@limiter.limit("10/minute")` applied to `register`, `@limiter.limit("5/minute")` applied to both `login` and `refresh`. All three decorators are present with `request: Request` as the first parameter, satisfying slowapi's key-function requirement. The shared `limiter` instance in `backend/app/limiter.py` uses `_get_user_or_ip` key function with a global default of `"100/minute"`.

#### SEC-04 — Password min_length=8 (`backend/app/schemas/auth.py`)
Resolved. `RegisterRequest.password` declared as `str = Field(..., min_length=8, max_length=128)`. Weak passwords are rejected with HTTP 422 before reaching the bcrypt hashing layer.

#### SEC-05 — Note content max_length=50000 (`backend/app/schemas/note.py`)
Resolved. `NoteCreate.content` uses `Field(..., max_length=50_000)` and `NoteUpdate.content` uses `Field(default=None, max_length=50_000)`. Both include a comment referencing SEC-05 and the AI cost exposure rationale.

#### SEC-06 — WS query-param residual risk documented (`docs/DEPLOYMENT.md`)
Resolved. `DEPLOYMENT.md` contains two relevant sections: "SEC-06 — WebSocket Token in URL" (with explicit status, threat description, required operator action for log retention, KQL redaction query, and future hardening path to opaque voice-ticket tokens) and "WebSocket Token Log-Scrubbing (B12)" (describing both the backend `_ScrubTokenFilter` and the Azure Log Analytics KQL workaround). Residual risk is clearly acknowledged.

#### SEC-07 — JTI revocation (`backend/app/auth/jwt.py`, `backend/app/api/auth.py`)
Resolved. `_revoked_jtis: set[str]` deny-set with `revoke_jti()` / `is_jti_revoked()` helpers implemented in `jwt.py`. All tokens carry a `jti` claim via `_make_token()`. The `/refresh` endpoint checks the incoming JTI against the deny-set (raises HTTP 401 if revoked) and revokes the old JTI before issuing the replacement token. The in-memory limitation (restart clears the set) is explicitly documented in `docs/DEPLOYMENT.md` under "SEC-07 — Refresh Token Revocation Gap" with a Redis/DB remediation path called out for pre-multi-user hardening.

#### SEC-08 — `_refresh_sas_url` no longer stub (`backend/app/api/export.py`)
Resolved. `_refresh_sas_url()` is a full implementation: parses the stored blob URL with `_AZURE_BLOB_RE`, extracts account/container/blob, calls `azure.storage.blob.generate_blob_sas` with `BlobSasPermissions(read=True)` and a 1-hour expiry, and returns the freshly signed URL. Degrades gracefully (returns the original URL) when `AZURE_STORAGE_CONNECTION_STRING` is not configured, suitable for tests and local dev.

## Performance Findings Re-Review Round 2

PASSED

### Resolved
- PERF-01, PERF-02, PERF-03, PERF-04, PERF-05, PERF-06, PERF-07, PERF-08, PERF-09, PERF-10, PERF-11

#### PERF-01 — N+1 tag queries (`notes.py:_get_or_create_tags`, `processor.py:_auto_tag_and_categorize` + `_ensure_tag`)
Resolved. `backend/app/utils/db_helpers.py` implements `get_or_create_tags_batch()`: one `SELECT … WHERE name IN (…)` then one batch flush for missing tags — two round-trips maximum regardless of tag count. `_get_or_create_tags` in `notes.py` delegates to it directly. `_auto_tag_and_categorize` in `processor.py` calls `get_or_create_tags_batch` directly; `_ensure_tag` also wraps it for single-tag callers. The per-tag SELECT+INSERT loop is gone from both callers.

#### PERF-02 — `increment_term_usage` O(N) Python scan (`services/speech.py`)
Resolved. The entire `SELECT * FROM user_vocabulary … for term in terms: if term in content` pattern is replaced by a single `UPDATE user_vocabulary SET usage_count = usage_count + 1 WHERE user_id = :uid AND :content ILIKE '%' || term || '%'`. No vocabulary rows are fetched into Python; Postgres performs the scan server-side.

#### PERF-03 — Unconditional notes query in `generate_weekly_summary` (`pipeline/distill.py`)
Resolved. The notes `SELECT` is now inside `if not daily_summaries:` (lines 214–222). When daily summaries exist the notes table is not queried. The old unconditional query above the conditional is absent.

#### PERF-04 — Unguarded on-demand GPT call in `get_patterns` (`api/insights.py`)
Resolved. Migration `004_add_patterns_cache.py` adds `patterns_cached_json TEXT` and `patterns_cached_at TIMESTAMPTZ` columns to `users`. `get_patterns` reads the cache first; if `cache_age < 24 h` it returns the stored JSON without a GPT call. After generation it writes back to cache via `db.commit()`. `?refresh=true` bypasses the cache. `datetime.now(timezone.utc)` used throughout (QA-11 co-fix).

#### PERF-05 — No GIN FTS index on `notes.content` (`alembic/versions/005_add_fts_index.py`)
Resolved. Migration 005 issues `CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notes_content_fts ON notes USING gin(to_tsvector('english', content))`. The index expression matches the `to_tsvector('english', n.content)` call in `_HYBRID_SQL` exactly, so Postgres will use the index for `ts_rank` lookups.

#### PERF-06 — Per-row commit in `bulk_import` (`api/dictionary.py`)
Resolved. The loop with 500 sequential `await db.commit()` calls is replaced by a single `INSERT … SELECT FROM jsonb_to_recordset(:rows::jsonb) ON CONFLICT (user_id, term) DO NOTHING` followed by one `await db.commit()`. Inserted count is read from `result.rowcount`.

#### PERF-07 — `useSync` 500ms `setInterval` polling (`hooks/useSync.ts`, `sync/syncManager.ts`)
Resolved. `useSync` contains no `setInterval`. It subscribes via `useEffect(() => syncManager.onSyncingChange(setIsSyncing), [])` and returns an unsubscribe cleanup. `SyncManager` holds a `syncingListeners: Set<SyncingListener>` and exposes `onSyncingChange(listener)` (fires immediately with current state, returns unsubscribe function). `pushChanges()` calls `notifySyncingListeners(true/false)` on enter and exit. React state updates only on actual transitions.

#### PERF-08 — `_SIMILAR_SQL` cross-join (`api/search.py`)
Resolved. `_SIMILAR_SQL` is a single-table query (`FROM notes n WHERE n.id != :source_note_id AND n.user_id = :user_id`). The `FROM notes n, notes src` Cartesian product is gone. The handler passes the already-loaded `note.embedding` as `:source_emb`, eliminating the redundant 6 KB embedding fetch from the DB.

#### PERF-09 — JavaScript date filtering after full Dexie fetch (`hooks/useNotes.ts`)
Resolved. When `dateFrom` or `dateTo` is present, `useNotes` uses `db.notes.where('createdAt').between(lower, upper, true, true)` to leverage the `createdAt` IndexedDB index. Secondary filters (category, syncStatus) are applied in memory on the already-reduced set. The original indexed collection queries are used only when no date filter is specified.

#### PERF-10 — Static `BrainViewPage` import bloating initial bundle (`App.tsx`)
Resolved. `BrainViewPage` is declared as `const BrainViewPage = lazy(() => import('./pages/BrainViewPage'))` with a comment explaining the PERF-10 rationale. The `/brain` route wraps `<BrainViewPage />` in `<Suspense fallback={…}>`. `react-force-graph-2d` is now code-split into a separate chunk and excluded from the initial JS bundle.

#### PERF-11 — `wavesurfer.js` static import in `MusicPlayer.tsx`
Resolved. No static top-level `import 'wavesurfer.js'` present. The `createWaveSurfer()` async helper uses `await import('wavesurfer.js')` inside a `useEffect`, ensuring the library is only downloaded and parsed when the music player component actually mounts.

**Signal to Lead:** performance re-review 2 complete — PASSED

## Quality Findings Re-Review Round 2

PASSED

### Resolved
- QA-01, QA-02, QA-03, QA-04, QA-05, QA-06, QA-07, QA-08, QA-09, QA-10

#### QA-01 — Alembic migration 003 `op.get_bind()` removal (`backend/alembic/versions/003_add_shadow_reader.py`)
Resolved. `op.get_bind()` is completely absent from the file. All DDL in both `upgrade()` and `downgrade()` uses `op.execute(sa.text(...))` exclusively, matching the pattern in migrations 001 and 002. The CHECK constraint for `answer_pending` (QA-04 prerequisite) is also correctly included.

#### QA-02 — `_is_retryable` wired via `retry_if_exception` (`backend/app/utils/retry.py`)
Resolved. `_is_retryable` is wired into the decorator: `retry=retry_if_exception(_is_retryable)`. The import list includes `retry_if_exception` (not `retry_if_exception_type`). The predicate correctly returns `False` for `HTTPException` instances, preventing incorrect retries on 4xx/5xx responses. The docstring matches the implementation.

#### QA-03 — `DELETE /api/dictionary/{id}` returns 404 on missing term (`backend/app/api/dictionary.py`)
Resolved. `delete_term` calls `await _get_term_or_404(term_id, current_user_id, db)` before executing the `DELETE` statement. A missing term raises HTTP 404 consistently with `PUT`. The docstring confirms: "Returns 404 if not found (consistent with PUT)."

#### QA-04 — 2-phase shadow reader status (`answer_pending` → `answered`); APScheduler retry (`backend/app/api/shadow_reader.py`, `backend/app/pipeline/shadow_reader.py`)
Resolved. Two-phase flow confirmed: `answer_shadow_reader` sets `shadow_reader_status = "answer_pending"` and commits, returning `{"status": "answer_pending"}`. Background task `_merge_in_background` calls `merge_answer_into_note`, which atomically sets `status = "answered"` together with the content append on commit. `retry_stale_answer_pending()` is implemented as an APScheduler-callable sync wrapper that fetches notes stuck in `answer_pending` for > 1 minute and retries the full merge. The `answer_pending` value is included in the CHECK constraint in migration 003.

#### QA-05 — Shared `_note_to_out` in `_note_serializers.py`; `voice.py` imports from it; shadow_reader_* fields included (`backend/app/api/_note_serializers.py`, `backend/app/api/voice.py`, `backend/app/api/notes.py`)
Resolved. `backend/app/api/_note_serializers.py` provides a single canonical `_note_to_out(note: Note) -> NoteOut` that maps all three shadow_reader fields: `shadow_reader_status`, `shadow_reader_questions`, `shadow_reader_answer`. Both `voice.py` and `notes.py` import from this shared module. No duplicate implementations remain.

#### QA-06 — No `SimpleNamespace` in `notes.py`; background task re-fetches note by id (`backend/app/api/notes.py`)
Resolved. `SimpleNamespace` is no longer used as a fallback. `create_note` calls `await db.commit()` before scheduling background tasks, ensuring the note row is visible in any fresh session. `_run_ocr_and_pipeline` opens a fresh session, fetches the note by `note_id`, and aborts with `logger.error` if not found — no stub fallback. The comment explicitly documents the QA-06 fix rationale.

#### QA-07 — `generate_questions` drops (not truncates) questions > 15 words (`backend/app/pipeline/shadow_reader.py`)
Resolved. The loop appends items to `filtered` only when `len(q.split()) <= 15`; items exceeding the limit are skipped. The comment is explicit: `# else: drop — truncating would produce incomplete questions`. No `[:15]` word-count truncation exists anywhere in the function. The US-8 spec requirement "filter to strings ≤ 15 words" is met.

#### QA-08 — `voice_upload` (file-mode) loads phrase list before transcription (`backend/app/api/voice.py`)
Resolved. `voice_upload` now queries `UserVocabulary` for up to 500 terms (ordered by `usage_count DESC`) before calling `transcribe_audio_file`. It builds `loaded_phrases` including pronunciation hints, then calls `await transcribe_audio_file(audio_bytes, phrase_list=loaded_phrases or None)`. Phrase list load failure is caught and logged as a warning (soft-fail). US-7 task 3.3 is fulfilled.

#### QA-09 — `lastPull` defaults to "now" on first boot (`frontend/src/sync/syncManager.ts`)
Resolved. `start()` checks `await db.meta.get('lastPull')` and, if no entry exists, writes `new Date().toISOString()` before any `pullChanges()` is called. The epoch fallback `'1970-01-01T00:00:00Z'` in `pullChanges` is now unreachable on first boot. Subsequent pulls use the `server_time` cursor. First-run conflict misclassification is eliminated.

#### QA-10 — `insights.py` uses `Depends(get_openai)` consistently (`backend/app/api/insights.py`)
Resolved. All three OpenAI-consuming endpoints use `openai: AsyncAzureOpenAI = Depends(get_openai)`: `get_weekly_summary` (line 160), `get_patterns` (line 258), and `generate_express` (line 396). `get_openai` is imported from `app.services.openai_client`. The pattern is consistent across all endpoints.

**Signal to Lead:** quality re-review 2 complete — PASSED

## Spec Auditor Findings Re-Review Round 2

> Re-review auditor: Spec Conformance Auditor
> Re-review date: 2026-04-29
> Base commit reviewed: 3851ee8bb7af66aeccdc589eabea76577601660e (HEAD)

---

### Round 1 Items — Status Update

**SA-H1** (python-jose version pin) — **ACCEPTED**
Design-justified per design.md "Backend requirements.txt (pinned — OQ-2 + OQ-4 resolved)". No spec deviation.

**SA-H2** (passlib[bcrypt] version pin) — **ACCEPTED**
Design-justified per design.md same section. No spec deviation.

**SA-H3** (extra bcrypt>=4.0,<4.1 pin) — **ACCEPTED**
Design-justified per design.md same section. No spec deviation.

**SA-M1** (Migration 001 TEXT placeholder + drop + re-add embedding) — **STILL OPEN (lower priority)**
Verified: `backend/alembic/versions/001_initial_schema.py` lines 94-135 still contain the two-step pattern — line 94 creates `sa.Column("embedding", sa.Text(), nullable=True)` as a placeholder, lines 134-135 execute `ALTER TABLE notes DROP COLUMN embedding` then `ALTER TABLE notes ADD COLUMN embedding vector(1536)`. Functionally correct for a green-field build; no correctness impact. No fix was applied in the Round 1 fix loop. Remains open as a low-priority NIT.

**SA-N1** (slide-up keyframe in animations.css) — **VERIFIED / CLOSED**
Confirmed: `frontend/src/styles/animations.css` contains `@keyframes slide-up { from { transform: translateY(100%) } to { transform: translateY(0) } }` and `.animate-slide-up { animation: slide-up 240ms ease-out both; }`. File is imported via `@import './animations.css'` in `globals.css`. Requirement met. NIT closed.

**SA-L1, SA-L2, SA-L3** — **ACCEPTED** (design-justified, unchanged).

---

### New Files Structural Audit

**`backend/app/api/_note_serializers.py`** — PASSED
Single `_note_to_out(note: Note) -> NoteOut` helper. Correctly includes all three `shadow_reader_*` fields. Both `notes.py` (line 25) and `voice.py` (line 27) import from it. Scoped to QA-05 design-justified intent. No new spec deviation.

**`backend/app/limiter.py`** — PASSED
Extracts `Limiter` instance with `_get_user_or_ip` key function and `default_limits=["100/minute"]`. `main.py` and `auth.py` import from it correctly; `app.state.limiter` wired in `main.py:117`. Circular-import fix is scoped to SEC-03 intent. No new spec deviation.

**`backend/app/utils/db_helpers.py`** — PASSED
`get_or_create_tags_batch()` implements single SELECT-in + batch flush pattern. Used by `notes.py` and `processor.py`. No new spec deviation beyond PERF-01/PERF-N3 intent.

**`backend/alembic/versions/004_add_patterns_cache.py`** — PASSED
Adds `patterns_cached_json TEXT` and `patterns_cached_at TIMESTAMPTZ` to `users` table with `IF NOT EXISTS` guards. `down_revision = "003"` chain correct. Uses `op.execute(sa.text(...))` consistent with migration style in 001/002. No new spec deviation.

**`backend/alembic/versions/005_add_fts_index.py`** — PASSED
Adds `CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notes_content_fts ON notes USING gin(to_tsvector('english', content))`. `down_revision = "004"` chain correct. `CONCURRENTLY` + `op.execute` is correct Alembic practice for this index type. No new spec deviation.

**`backend/tests/test_security_config.py`** — PASSED
Covers SEC-01 (JWT_SECRET_KEY validator: min-length, placeholder-in-production, allowed-in-dev) and SEC-06 (DEPLOYMENT.md documentation assertion). Well-structured with `monkeypatch` + `importlib.reload` for env-var isolation. No new spec deviation.

**`frontend/src/__tests__/useNotes.test.ts`** — PASSED
Tests PERF-09 via source-code inspection (`.toString()`) and Dexie mock. Checks for `.between()` call and absence of post-fetch JS date filter. Source-inspection approach is a minor test robustness NIT if hook is minified, but not a spec deviation.

---

### New Finding — SA-R2-M1 (MEDIUM)

**`backend/app/api/sync.py` — Local `_note_to_out` not consolidated with QA-05 shared helper**

- **Location**: `backend/app/api/sync.py:201-223`
- **Finding**: The QA-05 fix extracted a shared `_note_to_out` into `backend/app/api/_note_serializers.py` and updated `notes.py` and `voice.py` to import it. However `sync.py` was not updated: it retains a local `_note_to_out` (lines 201-223) that omits all three `shadow_reader_*` fields (`shadow_reader_status`, `shadow_reader_questions`, `shadow_reader_answer`). The `GET /api/sync/pull` endpoint therefore serialises synced notes without shadow reader data — the same class of defect that QA-05/QA-13 was explicitly fixing.
- **Impact**: Clients that pull synced notes via `GET /api/sync/pull` receive `shadow_reader_status = "pending"` (Pydantic default), `shadow_reader_questions = null`, and `shadow_reader_answer = null` regardless of DB values. This breaks the offline-first sync contract for US-8 Shadow Reader: synced notes will appear un-asked and unanswered after a pull even when the server state says otherwise.
- **Recommendation**: In `sync.py`, remove the local `_note_to_out` definition (lines 201-223) and add `from app.api._note_serializers import _note_to_out`.
- **Priority**: Medium — functional correctness gap on the sync pull path for US-8.

---

### Overall Verdict

**ISSUES REMAIN**

One new medium-priority finding identified during fresh structural audit:
- **SA-R2-M1**: `backend/app/api/sync.py` retains a local `_note_to_out` that omits shadow_reader fields, missed by the QA-05 fix loop.

All Round 1 SA items resolved: SA-H1/H2/H3/L1/L2/L3 are ACCEPTED (design-justified); SA-N1 is VERIFIED CLOSED (keyframe confirmed in animations.css); SA-M1 remains a low-priority NIT with no correctness impact.

**Signal Lead:** `spec-auditor re-review 2 complete — ISSUES REMAIN: SA-R2-M1 (sync.py local _note_to_out omits shadow_reader fields, missed by QA-05 fix)`
