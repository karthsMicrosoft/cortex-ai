# DECISIONS — Cortex Second Brain

> **Architecture decisions and deviations from spec, with rationale.** When refactoring, preserve these unless the underlying constraint has changed.

**Last updated:** 2026-04-30

---

## Decision codes

- **OQ-N** = Open Question raised by the Researcher and resolved during workforce Phase 2/3
- **B-N** = Critic's BLOCKING challenge resolved by the Architect's Round 2 revision
- **SEC-N**, **PERF-N**, **QA-N**, **SA-N** = Reviewer findings (Phase 5 Round 1) addressed in fixes

---

## 1 — Region split (OQ-1, B1)

**Decision:** Resources go in `centralus` (originally `westus2` per spec § 5.2). Azure OpenAI lives in `eastus`.

**Why:**
- Visual Studio Enterprise subscriptions are restricted from provisioning Postgres Flexible Server in `westus2` and `eastus2` (`LocationIsOfferRestricted`).
- Azure OpenAI does not have `gpt-4o-mini` and `text-embedding-3-small` GA in `centralus`.
- `eastus` Postgres works, but Static Web Apps doesn't support `eastus` (only westus2, centralus, eastus2, westeurope, eastasia).
- `centralus` is the smallest set that supports Postgres + SWA + Speech + Vision; OpenAI is the one outlier and gets its own location parameter.

**Implementation:** `infra/main.bicep` exposes a separate `openaiLocation` parameter (default `'westus'`, parameters.json overrides to `'eastus'`). All non-OpenAI resources use the `location` parameter (default `resourceGroup().location` = `centralus`).

**Where:** `infra/main.bicep` lines 10-12 (param), line 75 (openai resource).

---

## 2 — Dependency overrides (OQ-2, OQ-4, B2, SA-H1, SA-H2, SA-H3)

**Decision:** Backend deps deviate from spec § 4.3 in 3 specific places:
| Spec pin | Actual | Why |
|---|---|---|
| `python-jose[cryptography]==3.3.*` | `python-jose[cryptography]>=3.5,<4` | CVE-2024-33663 (algorithm confusion JWT bypass) and CVE-2024-33664 fixed in 3.4.0/3.5.0 |
| `passlib[bcrypt]==1.7.*` | `passlib[bcrypt]>=1.7,<2` (range, not exact) | passlib 1.7.4 is the latest, kept; doesn't break |
| (not in spec) | `bcrypt>=4.0,<4.1` | `bcrypt>=4.1` raises `AttributeError` against passlib 1.7.x. Pinning <4.1 is the working compatibility window. |
| (not in spec) | `slowapi==0.1.*` | Used for rate limiting in SEC-03 (auth routes) |
| (not in spec) | `apscheduler==3.10.*` | Distill cron in us-6 (currently disabled via env var, see KNOWN_ISSUES) |
| (not in spec) | `email-validator>=2,<3` | Pydantic `EmailStr` requires this; not picked up by `pydantic[email]` extras directly in our config |

**Spec auditor reaction:** Initially flagged SA-H1/H2/H3 as HIGH deviations. Lead marked them DESIGN-JUSTIFIED — the design.md "Backend requirements.txt (pinned — OQ-2 + OQ-4 resolved)" section is the canonical override, and the rationale is documented inside design.md.

**Frontend deps:** Match spec § 4.3 exactly (with addition of test deps `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`, `vitest`, `fake-indexeddb`). Researcher noted React 18→19, Vite 5→8, Tailwind 3→4 are 1-3 majors stale; Lead chose to keep spec's frozen 2024-Q3 snapshot. P4 followup: bump after MVP stable.

---

## 3 — pgvector extension name (OQ-9, B3)

**Decision:** Use `CREATE EXTENSION IF NOT EXISTS vector` (lowercase, NOT `pgvector`).

**Why:** Azure Postgres Flexible Server has an allowlist (`azure.extensions` parameter) that uses uppercase identifiers (`VECTOR`). When `CREATE EXTENSION` is run, the actual in-DB name is lowercase `vector`. Spec § 2.3 line 249 said `CREATE EXTENSION IF NOT EXISTS "pgvector"` — that fails on Azure because there is no extension named `pgvector` in pg_available_extensions; the package is registered under `vector`.

**Implementation:** `backend/alembic/versions/001_initial_schema.py`:
```python
op.execute("CREATE EXTENSION IF NOT EXISTS vector")
op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
```

Plus the Bicep `azure.extensions` parameter set to `"VECTOR,UUID-OSSP"` (uppercase, comma-separated, the Azure-allowlist syntax).

---

## 4 — Bicep canonical template overrides spec § 5.2 (B4, OQ-5, OQ-6, OQ-7)

**Decision:** `infra/main.bicep` is the canonical Bicep, not spec § 5.2 verbatim. It adds:
- **Postgres firewall rule** `AllowAllAzureServicesAndResourcesWithinAzureIps` (start=0.0.0.0, end=0.0.0.0) — without it, the Container App can't reach Postgres
- **Container App resource** with system-assigned identity, `ingress.transport: 'auto'` (HTTP/1.1 + WebSocket), `allowInsecure: false`, full secrets array (DB URL, JWT, OpenAI key, Speech key, blob conn string, Vision key), env vars, CPU scaling rule, liveness + readiness probes on `/api/health`
- **Static Web App resource** (Free SKU)
- **Azure AI Vision (ComputerVision S1)** — was missing from spec § 5.2
- **`useBootstrapImage` parameter** — when true, Container App image is `mcr.microsoft.com/azuredocs/containerapps-helloworld:latest` (used for first deploy before ACR build); deploy.sh swaps to real image after `az acr build`

**Why:** Spec § 5.2 was a partial template — `az containerapp create` was supposed to be done outside Bicep in deploy.sh. That violates declarative IaC principles and causes drift. Inlining the Container App in Bicep makes the deploy reproducible. The chicken-and-egg problem (Container App needs ACR image, ACR needs to be deployed first) is solved with the `useBootstrapImage` flag.

**Trade-off acknowledged:** SA-L1/L2/L3 are marked DESIGN-JUSTIFIED; the deviations from spec § 5.2 are intentional.

---

## 5 — `pipeline/ocr.py`, NOT `services/vision.py` (B5)

**Decision:** Image OCR lives at `backend/app/pipeline/ocr.py`. There is no `backend/app/services/vision.py`.

**Why:** Spec § 4.1 lists `pipeline/ocr.py` in the project tree. Architect's Round 1 design.md inadvertently mentioned `services/vision.py` (line 172) as another service file, but the project tree (line 634) listed only 3 service files. To resolve the contradiction, Architect removed `services/vision.py` references and consolidated OCR in `pipeline/ocr.py` per spec.

**Implication:** When testing OCR, mock `app.pipeline.ocr.ImageAnalysisClient` (HTTP-based — use respx) not a separate vision module.

---

## 6 — Dedicated route modules, NOT `__init__.py` (B6)

**Decision:** New API routes go in dedicated modules (`api/upload.py`, `api/tags.py`), not stuffed into `api/__init__.py`.

**Why:** During design, US-2 task wording put `POST /api/upload` and `POST/GET /api/tags` in `api/__init__.py` for brevity. This is an anti-pattern: dunder modules should not contain feature code. Each route file is wired separately in `app/main.py`.

---

## 7 — Hybrid search SQL with tags EXISTS subquery (B7)

**Decision:** `_HYBRID_SQL` in `backend/app/api/search.py` includes a `EXISTS (SELECT 1 FROM note_tags ... WHERE tag.name = ANY(:tags))` subquery to filter by tags.

**Why:** Spec § 2.8 hybrid SQL didn't include the tags filter, but the API surface accepts `tags?` parameter. Without the filter, the parameter would either be silently dropped or the implementation would invent untested SQL. Architect added the canonical EXISTS pattern so the design body matches the API contract.

---

## 8 — Manual override UI in NoteEditor (B8)

**Decision:** `<NoteEditor />` exposes editable controls for `category` (6-option dropdown), `tags` (chip add/remove), `mood` (text or dropdown), and `music_metadata` quick-edit chips when `category='Music'`. Each AI-populated value shows an "AI-suggested" badge until the user edits it.

**Why:** Spec § 3.2 mitigation #6 lists "manual override UI for category/tags/mood" as a requirement. Architect's initial design dropped it. NoteUpdate Pydantic schema was undefined. Round 2 added explicit `NoteUpdate` schema with optional `content`, `category`, `tags`, `mood`, `music_metadata` fields, and the editor UI.

**Implementation detail:** `NoteEditor` tracks per-field origin in `LocalNote` (e.g., `categoryOrigin: 'ai' | 'user'`). When user edits, flips to `'user'`. AI badge renders only when origin is `'ai'`.

---

## 9 — NFR-1 reframed (B9)

**Decision:** "Voice feedback latency < 2s" applies to the **local IndexedDB write** that puts the raw note in the feed, NOT to transcript visibility. Transcript visibility (~5s in file-mode, ~1s in streaming mode) is a separate concern handled in US-9 streaming.

**Why:** File-mode Speech recognition takes 3-5s round-trip for a 10s clip. Holding NFR-1 to "transcript visible" was unmeetable in file-mode. Streaming (US-9) hits the original NFR-1 spirit.

**Implementation:** `frontend/src/components/VoiceCapture.tsx`:
- On stop, IMMEDIATELY insert note into Dexie with `syncStatus='pending'`, `processingStatus='raw'`. Library page reflects via `useLiveQuery`.
- Background fetch to `/api/voice/upload` updates the same `localId` row when transcription returns.

---

## 10 — Pipeline state machine (B10)

**Decision:** Sequence is **Stage 1 (Capture) → Stage 2 (Organize) → Stage 1.5 (Reflect)**.

| State | Set by |
|---|---|
| `raw` | Note creation (text/voice without transcript yet) |
| `transcribed` | Voice upload after STT |
| `processed` | After Stage 1 (clean transcription via gpt-4o-mini) |
| `enriched` | After Stage 2 (tags + category + embedding + links) |
| `failed` | On any pipeline failure (raw record preserved) |

**Reflect (Stage 1.5):** Runs only after `processing_status == 'enriched' AND shadow_reader_status == 'pending'`. Sets `shadow_reader_status` to `asked` (or `skipped`) — independent state from `processing_status`. After user answers, `merge_answer_into_note()` regenerates embedding in a serializable transaction.

**Why:** Original design left ordering ambiguous. Critic flagged the race: if Stage 2 regenerates embedding before user answers, and `merge_answer_into_note` regenerates again, ordering/overwrite semantics are undefined.

---

## 11 — Image offline branch in syncManager (B11)

**Decision:** `syncManager.pushChanges()` has explicit `imageBlob` branch for offline image notes:
- If a note in the sync queue has `imageBlob`: upload it via `/api/upload` to get a URL, then create the note via `/api/notes` with `image_url` and `source_type='image'`.

**Why:** Originally the design only handled `audioBlob` offline path. FR-1.5 (image upload + OCR) requires the same offline-first treatment. Without this, image notes captured offline can't sync.

---

## 12 — WebSocket token in URL query param + log scrubbing (B12)

**Decision:** `/api/voice/stream` WebSocket auth uses `?token=<access-jwt>` query param. Backend scrubs `?token=...` from access logs.

**Why:** Browsers can't set Authorization headers on WebSocket upgrade requests. Cookie-based auth requires same-origin or risky CORS-with-credentials handshake. Query param is the pragmatic standard. Mitigation: `_ScrubTokenFilter` in `backend/app/main.py` regex-replaces `?token=<value>` with `?token=REDACTED` in all log records (uvicorn.access logger included).

**Documented residual risk:** Azure Container Apps platform logs (Log Analytics workspace) may still log the URL. Mitigation: `docs/DEPLOYMENT.md` includes a KQL redaction query plus future hardening recommendation (opaque ticket exchange).

---

## 13 — Sync pull + Conflicts page (B13)

**Decision:** `syncManager.pullChanges()` fetches `/api/sync/pull?since=<lastPullISO>`. Server returns notes updated after that timestamp. Conflicts (server `updated_at` > local `lastServerVersion` AND local has unsynced edit) appear in `pages/ConflictsPage.tsx` with three actions: Keep Mine / Keep Server / Merge.

**Why:** Originally undesigned. Bidirectional sync needs explicit conflict handling.

**First-boot guard:** `lastPull` defaults to `new Date().toISOString()` (NOT epoch) on first start. Otherwise the first pull would treat all pending-not-yet-pushed local notes as conflicts.

---

## 14 — Container App `minReplicas: 1` (B14)

**Decision:** Container App scaling has `minReplicas: 1` (not 0).

**Why:** Original spec defaulted to scale-to-zero (cost saver). But APScheduler `BackgroundScheduler` runs in-process; if the Container App scales to zero, the nightly distill cron never fires. `minReplicas=1` keeps the scheduler alive.

**Caveat:** Scheduler is **currently disabled** (`SCHEDULER_ENABLED=false`) due to asyncpg pool conflict — see KNOWN_ISSUES § "Scheduler". When the scheduler is moved to a Container Apps Job (P1 followup), revisit `minReplicas` (could go to 0 then).

---

## 15 — Test mocking strategy (B15)

**Decision:**
- **respx** for HTTP-based Azure SDKs: OpenAI chat (Capture/Distill/Express), embeddings, Vision REST, Blob REST upload.
- **`unittest.mock.patch`** for Azure Speech SDK (gRPC/native — respx cannot intercept). Patch `azure.cognitiveservices.speech.SpeechRecognizer.recognize_once_async`.

**Why:** Speech SDK uses native code that bypasses Python's HTTP stack. respx works at the httpx layer.

---

## 16 — us-7 / us-9 source exclusivity in `voice.py` (B16)

**Decision (work-sequence Phase 5):**
- **us-7 (Personal Dictionary)** ships NEW symbols `load_user_phrase_list`, `increment_term_usage` in `services/speech.py`, and modifies `POST /api/voice/upload` in `api/voice.py` (file-mode integration only).
- **us-9 (Real-time STT)** ships NEW `@router.websocket('/api/voice/stream')` route in `api/voice.py` (a new symbol, NOT a modification of the existing function). It CONSUMES `load_user_phrase_list`/`increment_term_usage` via a `try/except ImportError` guard so us-9 stays mergeable even when us-7 hasn't landed yet (degrades gracefully — STT runs unboosted with WARN log).
- **us-7 task 3.4 is explicitly a NO-OP** — touching the WS handler is us-9's domain.

**Merge order rule:** us-7 SHOULD merge first. If they merge in reverse, us-9's soft-fail import-guard means STT still works (just without phrase boost) until us-7 lands and the next deploy picks up the helpers.

**Why:** Phase 5 had three parallel stories all touching different parts of `voice.py` and `speech.py`. Without explicit symbol-level exclusivity, the merge would conflict. The convention is documented in `tasks/work-sequence.md` AND mirrored in the relevant task file wording.

---

## 17 — Shadow Reader polling window (B17)

**Decision:** Frontend polls `/api/notes/{id}/shadow-reader` with **10 polls × 2s interval (first 20s) + 5 polls × 5s interval (next 25s) = 45s total window, ≤15 polls**.

**Why:** Original 5×1s window misses the 3s NFR. Stage 1 + Stage 2 + Stage 1.5 takes 5-15s typical. Polling for 45s with backoff catches all realistic cases without DoSing the API. The "3s NFR" is reframed as "from Stage 2 complete," not "from note creation" — which is what the user actually experiences.

---

## 18 — Security hardening (SEC-01 through SEC-08)

**SEC-01 (BLOCKING):** `JWT_SECRET_KEY` Pydantic validator enforces ≥32 chars and rejects the dev placeholder `"change-me-in-production"` when `ENVIRONMENT=production`. Plus a startup `check_production_secrets()` call that raises `RuntimeError` for fail-fast.

**SEC-02 (HIGH):** Refresh token NOT in JSON response body — only in httpOnly + Secure + SameSite=Lax cookie. XSS-protected.

**SEC-03 (HIGH):** slowapi rate limits on auth routes:
- `POST /api/auth/register` — 10/min
- `POST /api/auth/login` — 5/min
- `POST /api/auth/refresh` — 5/min
- Default global — 100/min

**SEC-04 (HIGH):** `RegisterRequest.password` has `Field(min_length=8, max_length=128)`.

**SEC-05 (MEDIUM):** `NoteCreate.content` and `NoteUpdate.content` have `Field(max_length=50_000)` to prevent unbounded GPT context.

**SEC-06 (MEDIUM):** WebSocket `?token=` URL exposure documented in `docs/DEPLOYMENT.md` with KQL redaction query.

**SEC-07 (MEDIUM):** JWT JTI claim added; `_revoked_jtis: set[str]` in-memory deny set; `/refresh` revokes prior JTI on rotation. **Limitation:** in-memory means revocations lost on Container App restart. P4 followup: move to Redis or DB.

**SEC-08 (LOW):** `_refresh_sas_url()` no longer a stub — calls `azure.storage.blob.generate_blob_sas` with fresh 1-hour expiry.

---

## 19 — Performance fixes (PERF-01 through PERF-11)

| ID | Decision | Where |
|---|---|---|
| PERF-01 | Tag get-or-create batched (one SELECT IN + one INSERT ON CONFLICT) | `backend/app/utils/db_helpers.py:get_or_create_tags_batch` |
| PERF-02 | Vocab usage_count single SQL UPDATE with ILIKE (was Python loop over all 2000 terms) | `backend/app/services/speech.py:increment_term_usage` |
| PERF-03 | Weekly summary skips notes query when daily_summaries non-empty | `backend/app/pipeline/distill.py:generate_weekly_summary` |
| PERF-04 | Insights patterns cached 24h via `users.patterns_cached_*` columns | `backend/app/api/insights.py` + migration 004 |
| PERF-05 | GIN FTS index on `notes.content` | migration 005 |
| PERF-06 | Bulk import single INSERT FROM `jsonb_to_recordset()` ON CONFLICT DO NOTHING | `backend/app/api/dictionary.py:bulk_import` |
| PERF-07 | useSync uses subscription emitter pattern (not setInterval) | `frontend/src/sync/syncManager.ts:onSyncingChange` |
| PERF-08 | _SIMILAR_SQL takes embedding parameter (no cross-join) | `backend/app/api/search.py` |
| PERF-09 | useNotes uses Dexie `.where('createdAt').between()` (was JS post-fetch filter) | `frontend/src/hooks/useNotes.ts` |
| PERF-10 | BrainViewPage `React.lazy()` + Suspense | `frontend/src/App.tsx` |
| PERF-11 | MusicPlayer dynamic `await import('wavesurfer.js')` | `frontend/src/components/MusicPlayer.tsx` |

---

## 20 — Quality fixes (QA-01 through QA-15)

| ID | Decision |
|---|---|
| QA-01 | Migration 003 uses `op.execute(sa.text(...))` (no `op.get_bind()` — async-incompatible) |
| QA-02 | `azure_retry` wires `_is_retryable` via `retry_if_exception` (was dead code; HTTPException now correctly excluded) |
| QA-03 | DELETE /api/dictionary/{id} returns 404 on missing (was silent 204) |
| QA-04 | Shadow Reader 2-phase status: `answer_pending` → `answered` (with APScheduler retry sweep — currently disabled) |
| QA-05 | Single shared `_note_to_out` in `backend/app/api/_note_serializers.py`; notes.py + voice.py + sync.py all import from it (omitting fields was a bug) |
| QA-06 | OCR background re-fetches note by id from a fresh DB session (no `SimpleNamespace` race) |
| QA-07 | `generate_questions` filters (drops) >15-word questions (does NOT truncate) |
| QA-08 | File-mode `voice_upload` loads phrase list from user dictionary before transcription |
| QA-09 | Sync first-boot guard: `lastPull` defaults to `now()` (not epoch) so pending-but-unsynced local notes aren't flagged as conflicts |
| QA-10 | All endpoints use `Depends(get_openai)` consistently (was mix of `OpenAIDep` TypeAlias and direct) |

---

## 21 — Custom workforce reviewer: spec auditor

**Decision:** Added a 4th custom reviewer `spec-auditor` to the workforce review array.

**Why:** User explicitly asked for an "auditor agent" to verify the implementation against the original spec. The 3 default reviewers (security, performance, quality) don't audit spec conformance.

**Implementation:** `.claude/agents/reviewer-spec-auditor.md` — checks folder structure (4.1), dependencies (4.3), env vars (4.4), Bicep template (5.2), acceptance criteria (5.3 + addendum F1.5/F2.5). Treats design-justified deviations (OQ-1, OQ-2, OQ-4 etc.) as ACCEPTED rather than HIGH findings.

---

## 22 — Resolved-but-noteworthy late-breaking issues

These came up after the workforce completed (during deploy + UI smoke):

### 22a — `speech.py` `CancellationDetails.from_result` (real bug)
The fix-pair never tested the speech.py cancellation path. The Azure Speech SDK doesn't have `CancellationDetails.from_result()` — it uses the constructor directly: `CancellationDetails(result)`. Caught when running pytest locally. Fixed.

### 22b — Migration JSONB defaults double-quoted
`server_default="'[]'::jsonb"` was producing `JSONB DEFAULT '''[]''::jsonb'` SQL — Postgres rejected as invalid JSON. Wrap with `sa.text("'[]'::jsonb")` so SQLAlchemy treats it as a SQL literal, not a quoted string. Applied to all JSONB defaults in migration 001.

### 22c — Migration 005 `CONCURRENTLY` inside transaction
`CREATE INDEX CONCURRENTLY` is incompatible with alembic's transaction wrapping (`transaction_per_migration=True` is the default). Removed `CONCURRENTLY` for first deploy (brief lock on a fresh table is fine). Production schema changes against a populated table should use `transaction_per_migration=False` in env.py.

### 22d — Container App image name mismatch
Bicep generated `${appName}-api` (`cortexks-api`) but `deploy.sh` hardcoded `cortex-api`. Fixed deploy.sh to use `${APP_NAME}-api`. The orphan `cortex-api` repo in ACR is harmless but can be cleaned.

### 22e — Bicep chicken-and-egg on Container App image
Bicep tried to deploy Container App with `cortexksacr.azurecr.io/cortexks-api:latest` BEFORE `az acr build` ran. Solution: added `useBootstrapImage` Bicep param (defaulting to `mcr.microsoft.com/azuredocs/containerapps-helloworld:latest`); deploy.sh uses it for first deploy, then `az containerapp update --image` swaps after build.

### 22f — `email-validator` missing from requirements.txt
Pydantic `EmailStr` lazy-imports `email-validator` at first model instantiation. Container App startup crashed with `ImportError: email-validator is not installed`. Added `email-validator>=2,<3` to `requirements.txt`.

### 22g — Frontend missing API base URL
Initial frontend deploy used relative `/api/...` paths. SWA host doesn't proxy POSTs to the backend (the `routes.rewrite` for external URLs strips POST bodies → 405). Solution: `VITE_API_BASE_URL=https://cortexks-api...` build-time env, fetch wrapper resolves URLs against the base. Plus `credentials: 'include'` so the cross-origin httpOnly refresh cookie works.

### 22h — APScheduler asyncpg pool conflict
`BackgroundScheduler` runs jobs in a separate thread with a fresh asyncio event loop. Each job created its own `SessionLocal()` context which used the shared asyncpg pool. asyncpg refuses to share connections across event loops — concurrent request traffic + a sweep tick → `cannot perform operation: another operation is in progress`. Solution: gated scheduler on `SCHEDULER_ENABLED` env var (default `false`). For production, run distill cron as a separate Container Apps Job.

### 22i — RegisterPage / LoginPage me() race
Both pages awaited `loginApi()` then immediately called `me()` — but the access token wasn't stored in Zustand yet. `fetchWithAuth` read `accessToken=null` and sent `/api/auth/me` without `Authorization` header → 401. Fix: call `useAuthStore.getState().setAccessToken(data.access_token)` BEFORE `me()`, then `login(token, user)` once me() returns.

### 22j — Service Worker cache stale after deploy
Vite-plugin-pwa registered with `registerType: 'autoUpdate'` which does NOT auto-activate the new SW until all clients close. Added `clientsClaim: true` and `skipWaiting: true` to workbox config so the new SW takes over immediately on the next page load.

### 22k — Postgres database `cortex` doesn't exist by default
Postgres Flexible Server creates only the `postgres` database by default. The Container App's `DATABASE_URL` points at `cortex` database. Solution: `az postgres flexible-server db create --resource-group cortex-rg --server-name cortexks-db --database-name cortex` after Bicep but before alembic.

### 22l — Cognitive Services soft-delete blocks redeploy
Failed deploys leave Cognitive Services accounts in soft-delete state for ~7 days. Subsequent deploys fail with `FlagMustBeSetForRestore`. Solution: `az cognitiveservices account purge --location <loc> --resource-group <rg> --name <name>` for each soft-deleted account before retry.

### 22m — Frontend TypeScript build excludes tests
`tsconfig.json` originally included `src/`. Production build (`tsc && vite build`) ran type checks against test files which had unused imports + node-specific globals (`global`, `process`, `fs`, `path`). Solution: added `"exclude": ["src/__tests__", "src/**/*.test.ts", "src/**/*.test.tsx"]`. Tests still type-check via `vitest` configuration which has its own tsconfig context.

### 22n — MediaRecorder webm/opus must be transcoded before Azure Speech file-mode (Round 4 / Bug 13)
Browsers' `MediaRecorder` produces `audio/webm; codecs=opus` (or `audio/ogg; opus`) for the live recording. Azure Speech `SpeechRecognizer.recognize_once_async()` in file mode expects WAV (PCM) by default and silently returns `NoMatch` when the file doesn't parse — there's no clear error to the caller. Renaming the file to `.wav` doesn't help; the SDK reads the container/codec.

**Decision:** in `services/speech.py`, write the inbound bytes to a `.webm` temp file and convert to **16 kHz mono PCM WAV** via the `ffmpeg` binary already present in the Docker image. Hand the resulting WAV path to `AudioConfig`. Two helpers: `_write_temp(data, suffix)` and `_ffmpeg_to_wav(src)`.

**Why ffmpeg over another codec adapter:**
- ffmpeg is already installed in the backend Dockerfile (`apt-get install -y ffmpeg`).
- It tolerates *any* MediaRecorder mime type the browser picks (Safari may emit `audio/mp4`, Firefox `audio/ogg`); a single ffmpeg invocation handles all.
- 60 s subprocess timeout is plenty for a one-shot recording (MVP caps voice notes well below that).

**Trade-off accepted:** an extra subprocess fork per upload (≤200 ms in our tests). The streaming WebSocket STT path (`/api/voice/stream`) is unaffected — it talks PCM frames directly to `PushAudioInputStream` and never sees the file.

### 22o — Stage 1 capture must skip image notes (Round 4 / Bug 14)
The OCR pipeline writes the recognized text directly to `note.content` and sets `processing_status='transcribed'`, then schedules the main pipeline. Stage 1 (`_stage_capture`) was originally only short-circuited for `source_type='text'`. For images, `raw_transcription` is `None`/empty, so the empty-transcription guard added in Round 1 (Bug 6) wrongly marked image notes `failed` with "(no speech detected)". The visible OCR text was overwritten in the UI by that marker.

**Decision:** treat `image` like `text` in Stage 1 — both already have clean content. Skip the LLM cleanup, advance status to `processed`, and let Stage 2 enrichment run. No new state machine, no separate code path; one tuple membership check.

### 22p — Image notes auto-tagged `'image'` at creation (Round 4 / Bug 15)
Library/sidebar tag filters needed a uniform way to find image notes. Decision: in `create_note`, if `source_type == 'image'`, merge `'image'` into the caller-supplied tag list (case-insensitive de-dup). Image-extracted text content can still produce additional Stage 2 LLM tags. We did **not** introduce a hard-coded `image` row in the DB — it's just another `Tag` row created on-demand via `_get_or_create_tags`, indistinguishable from any other tag.

### 22q — Shadow Reader auto-render restored, positioned above BottomNav (Round 4 / Bug 16)

### 22u — `recognize_once_async` → `start_continuous_recognition_async` (Bug 25)

`recognize_once_async()` is documented to return after the FIRST recognition result — i.e. the first segment of silence ends the session. A 20-second voice note with three natural pauses was returning only the first ~5 seconds of transcribed text. Users saw obviously-truncated content.

**Decision:** rewrite `transcribe_audio_file` in `services/speech.py` to use **continuous recognition**:

```python
loop = asyncio.get_event_loop()
done = asyncio.Event()
segments: list[str] = []

def on_recognized(evt):
    if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech and evt.result.text:
        segments.append(evt.result.text)

def on_session_stopped(evt):
    loop.call_soon_threadsafe(done.set)

def on_canceled(evt):
    # capture details, signal done so we don't hang
    loop.call_soon_threadsafe(done.set)

recognizer.recognized.connect(on_recognized)
recognizer.session_stopped.connect(on_session_stopped)
recognizer.canceled.connect(on_canceled)
recognizer.start_continuous_recognition_async().get()
await done.wait()
recognizer.stop_continuous_recognition_async().get()
return " ".join(segments)
```

**Watch out:** the SDK callbacks fire on a worker thread. All asyncio interaction (signaling the `done` event) MUST go through `loop.call_soon_threadsafe`. Don't await anything inside the callbacks — they're synchronous from the event loop's perspective.

**Trade-off accepted:** continuous recognition takes slightly longer end-to-end (an explicit `session_stopped` event arrives a few hundred ms after the audio ends). This is invisible to the user — the recording is already finished by the time `transcribe_audio_file` is called. Total latency change: < 200 ms in practice.

### 22s — Deletes propagate via a tombstone table, not soft-delete (Bug 19)

`/api/sync/pull` returns a `deletions: string[]` array but `DELETE /api/notes/{id}` was hard-deleting the row, leaving the array always empty — so other clients never learned about the delete.

**Decision:** add a `note_deletions` tombstone table (`id` mirroring the deleted note's id, `user_id` FK, `deleted_at` timestamptz) instead of converting `notes` to soft-delete. `DELETE` still hard-deletes the note row; `delete_note` / `bulk_delete` / sync-push-delete each insert one tombstone in the same transaction. `/api/sync/pull` queries `NoteDeletion.deleted_at >= since` and returns the IDs.

**Why tombstone over soft-delete:**
- Hard-delete keeps the `notes` table small; `note_deletions` is a write-once log we can prune on a schedule (TODO: a 30-day pruning job is P3 — not blocking).
- All existing queries (search, listing, embeddings) already assume rows that exist are live; soft-delete would have required adding `WHERE deleted_at IS NULL` everywhere with high regression risk.
- The tombstone payload is minimal (id + user_id + ts), so storage cost is negligible.

**SQLite test caveat:** `server_default=sa.text("now()")` returns a naive string in SQLite, breaking timezone-aware comparisons in tests. The model uses a Python-side `default=_utcnow` instead, where `_utcnow()` returns `datetime.now(tz=timezone.utc)`. The migration retains `server_default=sa.text("now()")` for Postgres compatibility — both produce timezone-aware timestamps in the prod DB.

### 22t — Voice recording: client-side MIME probing + server-side `client_id` dedup (Bugs 20 + 21)

Two related quirks surfaced in user testing:
- **iOS Safari** records `audio/mp4`, not `audio/webm`. Our recorder hard-coded `audio/webm`, so `MediaRecorder` either threw or produced silent output on iPhone.
- **Desktop voice** was creating *two* server rows per recording: the good one from `POST /api/voice/upload` (audio + transcript) and a redundant failed one from `syncManager.pushChanges()` pushing the local Dexie note via `POST /api/notes` (which the backend then tried to enrich with no audio_url and marked failed).

**Decisions:**
1. **MIME probing** — `useVoiceRecorder.ts` calls `MediaRecorder.isTypeSupported(['audio/webm','audio/mp4','audio/ogg'])` in priority order and uses the first hit. This is one if/else, not a polyfill — Safari falls into MP4, Chrome into WebM, Firefox into one of the first two.
2. **`src_suffix` plumbing** — `transcribe_audio_file(src_suffix=...)` in `services/speech.py` lets the caller hint the temp-file extension so ffmpeg detects the container. Default stays `.webm`; voice.py picks `.mp4`/`.m4a` based on the upload's content type.
3. **`client_id` dedup at `POST /api/notes`** — if a row with the same `(user_id, client_id)` already exists, return it instead of creating a new one. This is the server-side backstop for the race; cheap to add, hard to bypass.
4. **Frontend skip on synced-with-serverId** — `pushCreate` in `syncManager.ts` early-returns when `note.syncStatus === 'synced' && note.serverId`, removing the queue item. Belt + suspenders: even if the dedup at (3) fires, it still costs a network round-trip; this avoids it.

The fallback toast was also reworked: on fallback failure the local note flips to `processingStatus='failed'` and the toast hides. Previously the toast hung indefinitely because the failure path silently swallowed the error.

### 22r — `lastPull` seed on first boot must be epoch, not "now" (Bug 17)

QA-09 had introduced `db.meta.put({ key: 'lastPull', value: new Date().toISOString() })` on first boot to "avoid flagging local-only pending notes as conflicts." The downside, surfaced in Round 4 user testing: a fresh browser / incognito session asks `/api/sync/pull?since=<now>` and silently receives zero history. Each browser was effectively starting from "now."

**Decision:** seed `lastPull` to `'1970-01-01T00:00:00Z'` (epoch). The QA-09 concern was unfounded — `pullChanges()`'s conflict branch only fires when an incoming server note matches a local note by `serverId`, so local-only pending notes (no `serverId`) are never conflict candidates regardless of `lastPull`. This is verified by `frontend/src/__tests__/syncManager.test.ts` § QA-09 (3 tests, all pass with the new seed).

**Migration for existing buggy browsers:** if Dexie has zero notes with a `serverId`, no successful pull has ever happened — reset `lastPull` to epoch on next `start()`. Browsers that already have synced notes keep their cursor (no spurious re-pull of unchanged data).

**Trade-off accepted:** a brand-new user account (just registered, never synced anywhere) will pull `since=epoch` once and the server will return zero rows. Negligible cost.


Round 3 (Bug 8) had replaced the auto-rendering bottom-sheet with a manual launcher button after the user complained about the sheet randomly popping mid-scroll. Round 4 user feedback was that the launcher felt manual and they preferred auto-render — *but with proper alignment* (no overlap with the 64 px BottomNav).

**Decision:** rewrite `ShadowReaderPrompt.tsx` to:
1. Poll `/api/notes/{id}/shadow-reader` on mount via the B17 schedule (10×2 s + 5×5 s, 45 s total window). Stop on terminal status (`asked`/`answered`/`dismissed`/`skipped`).
2. When `status === 'asked'`, auto-render an inline bottom-sheet at `fixed inset-x-0 bottom-20 z-30 mx-auto w-full max-w-md sm:bottom-6`. The `bottom-20` (80 px) on mobile clears the BottomNav (h-16 = 64 px); on `≥ sm` the BottomNav is hidden so we drop to `bottom-6` (24 px).
3. Never use `role='dialog'` — this preserves the UI non-blocking guarantee codified in `ShadowReaderPrompt.test.tsx`.
4. Local "hidden" flag after dismiss/answer so the sheet doesn't reappear on the next poll.

The voice mic button stays out (Round 3 / Bug 10) — text answers only; voice answer remains a P3 follow-up.

---

## 23 — Things explicitly NOT done (and why)

| Decision | Why |
|---|---|
| No Redis for JTI revocation | Single-user MVP; in-memory is fine. Container App restart loses revocations — documented as P4 followup. |
| No Key Vault for first deploy | Adds bootstrap complexity. `parameters.json` uses inline secrets. `parameters.keyvault-template.json` is ready for production migration. |
| No SCSS / CSS-in-JS | Tailwind 3.4 CSS classes only. Per spec § 2.2. |
| No `/api/auth/logout` endpoint | Implicit logout = forget access token + clear refresh cookie via `/refresh` or wait 30 days. Explicit endpoint is P4 (defense-in-depth). |
| No 2FA / OAuth / SSO | Spec § 1.2 doesn't require. Single-user. |
| No CSRF token | We use JWT in Authorization header (XSS-immune from CSRF), and refresh cookie is SameSite=Lax (CSRF-safe by default for state-changing POSTs). |
| No PWA app shortcuts (manifest `shortcuts` array) | Spec § 2.7 didn't require. Add later if needed. |
| No image compression on upload | Backend accepts arbitrary size. Frontend could compress to <5MB before upload (P3). |
| No audio chunking for very long recordings | Single-blob upload for MVP. >5min recordings might OOM the SDK. (P3.) |
| No exit/wipe local data action in Settings | "Delete all my data" is a P4 GDPR feature. |
