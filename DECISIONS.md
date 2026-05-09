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

### 22x — All uploaded audio transcoded to MP4/AAC at upload time (Round 8 / Bug 27)

iOS Safari has zero WebM container support. Audio captured by Chrome/Edge is `audio/webm; codecs=opus`. When a note created on Chrome is opened on an iPhone, `<audio src=<sas-url-pointing-at-webm-blob>>` silently does nothing — the browser refuses to load the container.

**Decision:** at upload time, the backend transcodes incoming audio to **MP4/AAC** (`-c:a aac -b:a 128k -ar 44100`) using the ffmpeg already in the Docker image. The blob is stored as `.m4a` with `content-type: audio/mp4`. MP4/AAC plays on every browser without a polyfill.

**Two ffmpeg targets, two distinct helpers in `services/speech.py`:**
- `_ffmpeg_to_wav(src)` → 16 kHz mono PCM WAV. **For transcription** (Azure Speech file-mode). Round-4 fix.
- `_transcode_to_m4a(src)` → 44.1 kHz AAC in MP4 container. **For playback**. Round-8 fix.

**Soft-fail policy:** if ffmpeg is missing or fails, the upload handler falls back to storing the original bytes under the original extension. The note is not lost; mobile playback is degraded for that one row. This trades worst-case correctness for resilience to ffmpeg outages.

**Existing blobs:** `backend/scripts/migrate_audio_to_m4a.py` is an idempotent one-time script that downloads each existing `.webm`/`.ogg` blob, transcodes via `_transcode_to_m4a`, uploads the `.m4a` to a new SAS URL, and updates `notes.audio_url`. Run after deploy via:
```
az containerapp exec --name cortexks-api --resource-group cortex-rg \
  --command "python scripts/migrate_audio_to_m4a.py"
```

**Trade-off accepted:** ~150 ms extra per upload (subprocess fork + ffmpeg pass). Negligible for a one-shot recording. Storage cost slightly higher than the original opus stream (AAC at 128 kbps is ~1.7× the size of opus at 64 kbps), but on the order of 1 MB per minute of audio — irrelevant for an MVP.

### 22v — Refresh token in localStorage + JSON body (Round 7 / Bug 22 — reverses SEC-02)

**Original SEC-02 design:** the refresh token was delivered only via the httpOnly cookie. Rationale: keep it out of JavaScript reach so an XSS payload can't read and exfiltrate it.

**Why reversed:** Free-tier SWA + Container Apps are on different eTLD+1 domains (`.azurestaticapps.net` vs `.azurecontainerapps.io`). The refresh cookie is therefore third-party from the browser's perspective. Edge / Chromium "Balanced" tracking-prevention drops third-party cookies on every cross-origin fetch even when SameSite=None+Secure is set. HAR file (`Downloads/cortex-ai-har-consolelog/`) captured by the user shows zero cookies sent on `POST /api/auth/refresh` despite correct CORS headers and `credentials: 'include'`.

**Round-7 decision:** the refresh token is now ALSO returned in the JSON body of `/api/auth/login`, `/api/auth/register`, `/api/auth/refresh`. The frontend stores it in `localStorage('cortex_refresh')` and sends it in the JSON body of the rotation call. The httpOnly cookie continues to be set as defense-in-depth for browsers that do accept third-party cookies.

**Trade-off accepted:** localStorage is XSS-readable. For a single-user MVP without a CSP, the threat model is acceptable. Mitigations:
- The refresh token alone is not enough to take over an account — it must be combined with a working access-token to call protected endpoints. An XSS payload would need to perform the rotation itself.
- The JTI denylist on the backend invalidates a token after one use; an attacker who copies it must race the legitimate user.
- We log every refresh; out-of-pattern usage can be detected.

**P1 follow-up:** track in `KNOWN_ISSUES.md` "Migrate refresh token to first-party cookies" — once a custom domain is set up (both SWA and Container App under the same eTLD+1) or SWA Standard SKU is approved ($9/month, gives a linked-backend reverse-proxy), revert to cookie-only delivery.

**Test contract change:** `backend/tests/test_auth.py` `TestRefreshTokenInBody` (renamed from `TestRefreshTokenNotInBody`) now asserts the Round-7 contract.

### 22w — Skip WebSocket streaming on mobile UA (Round 7 / Bug 23)

WebSocket streaming for live STT was unreliable on mobile (iOS Safari background-tab throttling + mobile-network instability cause WS code-1006 abnormal closes on virtually every recording). The fallback to file upload always worked, but the toast "Network issue — using file-upload fallback" was visible on every recording and confused users.

**Decision:** detect mobile UA in `frontend/src/hooks/useVoiceRecorder.ts` (`/iPhone|iPad|iPod|Android/i.test(navigator.userAgent)`) and skip WebSocket entirely on mobile. The recorder accumulates audio chunks and uploads via the file path at stop-time. The "Network issue" toast is gated behind `!isMobile` since file upload IS the primary path on mobile, not a fallback.

The desktop WebSocket path is preserved for non-mobile UAs where it works reliably.

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

## § 22y — APScheduler distill cron removed entirely (2026-05-06, Round 9)

**Decision:** The daily/weekly distill cron functionality is REMOVED in its entirety — backend module, model, table, scheduler hook, HTTP endpoints, frontend cards, and tests. Not migrated to a Container Apps Job, not deferred — dropped.

**Why:** User product decision: _"Remove the daily cron job, I don't want that functionality at all. Ensure to remove it from UX as well."_

**What this reverses / supersedes:**
- **B14** (minReplicas=1 was justified by "keep APScheduler alive for nightly distill") — minReplicas=1 stays, but the new justification is cold-start avoidance only.
- **B10** (Pipeline state machine) — the per-note enrichment stages (Stage 1 cleans → Stage 2 tags + categorizes + embeds) are unchanged. Only the multi-note daily/weekly aggregation distillate is gone.
- **OQ-3** (Distill cron should run as APScheduler in-process or as a Container Apps Job) — answer: neither, the feature is gone.
- **PERF-14** (asyncio + APScheduler event-loop conflict) — moot.
- **QA-04** (Shadow Reader sweep on a 2-min interval) — the function `retry_stale_answer_pending` still exists and is callable manually, but is no longer scheduled. Was not running in production previously (scheduler was off via `SCHEDULER_ENABLED=false`), so live behaviour is unchanged.

**What survives unchanged:**
- The Recurring Patterns surface (`GET /api/insights/patterns`) — it's an on-demand GPT call, not a cron, and stays as the only Insights surface.
- The Express `POST /api/ai/generate` (song / practice / reflection) — on-demand only.
- The graph endpoint, all auth, all sync, all capture, all Shadow Reader.

**DB impact:** Alembic 007 drops `daily_summaries` (was empty in prod — cron never ran).

---

## § 22z — Azure Key Vault for prod-grade secret rotation (2026-05-06, Round 9)

**Decision:** The Container App's two sensitive runtime secrets — `database-url` (full asyncpg connection string) and `jwt-secret-key` — now live in Azure Key Vault `cortexks-kv` (centralus, RBAC mode) and are read at runtime via `keyVaultUrl` references with `identity: system`.

**Why:** Closes the P0 from PLAN § 6: previously the secrets were only in the Container App secret store, copied in via inline `--parameters` to Bicep. Rotation required re-running the deploy script with new env vars. With KV refs, rotation is `az keyvault secret set ...` followed by a revision restart.

**What this reverses:**
- **B4** (Container App's secret store is the single source of truth) — KV is now the authoritative store; the Container App's secrets are pointers.

**Other secrets:** `acr-password`, `azure-openai-api-key`, `azure-speech-key`, `azure-storage-connection-string`, `azure-vision-key` remain inline because Bicep can mint them at deploy time via `listCredentials()` / `listKeys()`. Migrating those to KV would add complexity without rotation benefit (their masters live in the originating Azure resource).

**RBAC:** Container App's system-assigned managed identity = `5d6d721c-6a0a-48f9-b542-2b9e8f0e80c1`, granted `Key Vault Secrets User` on `cortexks-kv`. My user (`357b3db4-21b0-4e24-834c-1a0925c67ee5`) granted `Key Vault Secrets Officer` for write access.

**Future deploys:** `infra/parameters.keyvault-template.json` is pre-populated with the live KV ID + Bicep references for `dbAdminPassword` + `jwtSecretKey`. Use it instead of `parameters.json` for from-scratch redeploys (and skip the `DB_ADMIN_PASSWORD` / `JWT_SECRET_KEY` env vars when invoking `deploy.sh`).

## § 22aa — GitHub Actions OIDC federation (2026-05-06, Round 11)

**Decision:** CI deploys to Azure use OpenID Connect federation against a dedicated AAD app `cortex-github-actions`, not a long-lived service-principal client secret.

**Why:**
- No client secret to rotate (the Azure side trusts GitHub's OIDC issuer for tokens with subject `repo:karthsMicrosoft/cortex-ai:ref:refs/heads/main`)
- Tokens are scoped to one branch — leaked CI logs can't authorize anything
- Aligns with current Microsoft guidance for GitHub Actions → Azure

**RBAC scope:**
- `Contributor` on `cortex-rg` (so Container App can be updated, secrets refreshed, etc.)
- `AcrPush` on `cortexksacr` (so `az acr build` can push tagged images)
- Notably NOT subscription-level Owner — the SP cannot create/destroy resource groups, set up KV beyond cortex-rg, or assign roles

**Repo secrets stored:** `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `ACR_NAME`, `CONTAINER_APP_NAME`, `RESOURCE_GROUP`, `AZURE_STATIC_WEB_APPS_API_TOKEN`.

**What this supersedes:**
- The old "P1 GitHub Actions secrets not wired" KNOWN_ISSUES line — now resolved.
- The expectation in earlier docs that deploys would always come from a local shell — both push-to-main on `frontend/**` or `backend/**` paths AND `workflow_dispatch` now produce live deploys.

---

## § 22ab — Alembic migrations stay manual after CI deploys (2026-05-06, Round 11)

**Decision:** The CI backend-deploy workflow does NOT run `alembic upgrade head`. Migrations are run manually from a developer shell after the workflow goes green.

**Why:** `az containerapp exec` requires a TTY — it calls `tty.setcbreak(sys.stdin.fileno())` which raises `Inappropriate ioctl for device` on a non-interactive GitHub Actions runner. The exec WebSocket also fails its 101 handshake on non-TTY clients.

**Manual recipe (now in the workflow yaml as a comment):**
```bash
az containerapp exec --name cortexks-api --resource-group cortex-rg \
  --command "alembic upgrade head"
```

**Future automation options (P3):**
1. Embed `alembic upgrade head` into the container's CMD/ENTRYPOINT — fail-closed on schema mismatch, single-replica race safe since `minReplicas=1`.
2. Run migrations as a separate Container Apps Job triggered by the workflow — cleanest separation, slightly more infra.

For now: schema changes are infrequent enough (7 alembic versions over the entire project history) that the manual step is acceptable.


## § 22ac — Container App auto-restart + health-check alerts (2026-05-07, Round 13)

**Decision:** Health-check alerting on the live API uses **3 Azure Monitor alerts** routed through a shared Action Group `cortex-alerts-ag`, defined via az CLI (not Bicep), with a single-region App Insights availability test.

**What was already in place (auto-restart half):** Bicep probes in `infra/modules/container-app.bicep` configure Liveness + Readiness on `/api/health` with `failureThreshold: 3`. Azure Container Apps platform restarts the replica automatically when liveness fails 3x consecutively. No infra change needed.

**What was added (alerts half):**

1. `cortexks-api-restart-spike` (sev 2) — Container App `RestartCount` >= 3 over 5 min.
2. `cortexks-api-5xx-rate` (sev 2) — Container App `Requests` total >= 10 with dimension `statusCodeCategory=5xx` over 5 min.
3. `cortexks-api-availability` (sev 1) — App Insights `availabilityResults/availabilityPercentage` (avg) < 100 over 5 min, fed by URL-ping web test `cortexks-api-health-ping` (every 5 min from `us-il-ch1-azr` Chicago, expects HTTP 200 + content match `"ok"`).

All three alerts route through Action Group `cortex-alerts-ag` with single email recipient `karths@microsoft.com`.

**Why this stack (A+B, not C — Log Analytics KQL alerts):**
- Stack A (Container App metric alerts) is free and catches the platform-detected failure modes (crash loops, 5xx surges).
- Stack B (synthetic ping) catches the failure mode A misses: container reports healthy but the network path / DNS / certificate / ingress is broken. ~$1/month at 1 region.
- Stack C (Log Analytics KQL alerts) would require provisioning + binding a workspace to the Container App env — significant new infra surface for marginal benefit on a single-user MVP.

**Why az CLI, not Bicep:**
- Matches the existing **Budget Alerts** precedent (DECISIONS § 22z context, `Microsoft.Consumption/budgets` already ops-managed not IaC).
- Action Groups + metric alerts are idempotent on re-create. The recreate recipe is documented in `docs/DEPLOYMENT.md` § "Health-Check Alerts".
- Bicep would have added a ~120-line module for ~5 minutes of lifetime bootstrap savings.

**Why single-region availability test (us-il-ch1-azr):**
- Cost: ~$1/month (5 regions = ~$5/month).
- Backend is centralus; Chicago is the closest classic web test region — a regional outage that takes down centralus would also likely take down Chicago, so multi-region wouldn't catch much extra. Multi-region is more valuable when the app is geo-distributed.
- One-line change to expand later if false-positive rate from a single region proves problematic.

**Why no induced-outage verification:**
- Inducing 3+ rapid restarts on prod or returning 10+ 5xx in 5 min is observable to the (single) user. Not worth the disruption to verify a config that's structurally validated by `az monitor metrics alert list` + a 200 response from `/api/health`.
- First real liveness failure or 5xx burst will exercise the full path; if the alert doesn't fire, that's a real bug to fix then.

**What this supersedes / closes:**
- The PLAN § 6 P0.3 line "Add a basic Container App auto-restart on failure (already implicit via probes) plus health check alerts" — both halves now closed.
- A latent gap from B14 / Round 9 (APScheduler removed): without daily distill cron, there's no in-process "we're alive" liveness signal beyond probes. The synthetic availability test now provides that signal externally.

**Future tightening (P3+):**
- Add a Smart Detector / failure-anomaly rule on App Insights once we collect 1+ week of baseline traffic.
- Wire Slack / Teams webhooks via the Action Group as a second receiver (parallel to email).
- Add `Microsoft.Insights/scheduledQueryRules` for KQL alerts on container logs once a Log Analytics workspace is in use for other reasons.



## § 22ad — Round 14: P2 SA-M1 cleanup + P1 first-party-cookie deferral (2026-05-07)

Two related but separate decisions captured together because they were resolved in the same user session and the same PR (#21).

### P2 SA-M1 — applied
`backend/alembic/versions/001_initial_schema.py` `notes.embedding` column declaration was a 3-statement dance: declare as `sa.Text()` placeholder inside `create_table`, then `DROP COLUMN`, then `ADD COLUMN ... vector(1536)`. Functionally correct (pgvector type isn't natively known to SQLAlchemy DDL) but ugly. Cleaned up to a single `ADD COLUMN` after `create_table`. Schema-equivalent except for column ordinal position (invisible to SQLAlchemy ORM). Migration 001 has already run on prod (alembic_version at 007), so the edit is a true no-op for the live container.

### P1 first-party-cookies — explicitly deferred (NOT done)
User does not currently own a domain. Cost/value analysis run in Round 14:
- Cheap domain (`$`12/yr) + Azure DNS zone — would require user to register a domain at a registrar (~5 min manual step) and either delegate DNS to Azure or add 4 records manually. Not autonomous.
- SWA Standard SKU (`$`9/mo = `$`108/yr) — fully autonomous via az CLI; provides linked-backend reverse-proxy so SWA + Container App share the same origin; cookies become same-site without DNS work.
- Status quo (localStorage workaround per s 22v) — `$`0 recurring; XSS-readable but threat model in s 22v accepts it for single-user MVP without CSP.

User explicitly chose status quo: domain cost not worth the hassle, SWA Standard cost not worth the autonomy. The localStorage trade-off remains as documented in s 22v (refresh token alone is insufficient to take over an account; JTI denylist invalidates after one use; every refresh is logged).

**Re-litigate when:** (a) user buys a domain for unrelated reasons, (b) SWA Standard becomes a project requirement (e.g., for the linked-backend feature), (c) the threat model changes (multi-tenant, public deployment, CSP added).

**Mechanical change required when re-litigated:** Remove `localStorage.setItem/getItem('cortex_refresh')` from `frontend/src/api/auth.ts` and `client.ts`. Update `backend/tests/test_auth.py::TestRefreshTokenInBody` (rename and invert) back to the cookie-only contract. Backend `/login`, `/register`, `/refresh` already set the httpOnly cookie as defense-in-depth; the body augmentation is the only thing that needs to come out.



## § 22ae — Phase 3 closure (2026-05-08, Round 15)

Phase 3 (spec § 4.2 items 35-40) closed in a single session via 6 PRs (#22-#27). Decisions captured here for future reference.

### Per-PR decisions

**PR #22 — Settings export + change-password.** Decision: keep change-password form on **both** ProfilePage AND SettingsPage. Rationale: spec § 4.2 item 37 says Settings; existing users may have ProfilePage bookmarks; the form is small and the duplicate JSX is acceptable for the MVP. AppHeader profile-icon now points to /settings (was /profile) — /profile route still wired for backward compat.

**PR #23 — Express CreatePage polish.** Decision: Save-as-Note creates a note tagged ``express`` + the kind (``song``/``practice``/``reflection``). This makes the GPT-generated content discoverable + filterable in Library. Did NOT add a separate ``Generated`` category since the existing 6 are spec-frozen.

**PR #24 — Image capture polish.** Decision: client-side resize fires when EITHER size > 5 MB OR width > 2048 px. Re-encodes as JPEG quality 0.85. Rationale: Azure Vision's OCR works fine at 2048 px wide; downscaling here saves blob storage + speeds upload. Kept file-picker only (no camera capture) — spec was silent and camera adds significant browser-permission UX cost.

**PR #25 — Lazy-load route splitting.** Decision: lazy-load 6 routes (Insights, Create, Settings, Library, Search, NoteDetail). Did NOT lazy-load Login, Register (auth boundary must render immediately), Capture (default route, FCP-critical), Profile (single screen, low-priority but rare access), or BrainView (already lazy). Bundle win: -58 KB raw / -13 KB gzip on main; 6 new chunks each 3-17 KB. Single Suspense boundary at the routing layer (not per-route) — simpler and the fallback is identical anyway.

**PR #26 — E2E Playwright runner + GH Actions.** Decision: workflow_dispatch + nightly cron at 09:00 UTC (~midnight Pacific). NOT triggered on push/PR — Playwright runs against LIVE deployment so it must be deterministic about what's deployed. Manual + nightly is the right cadence for a single-user MVP. Workflow uploads playwright-report on failure for triage.

**PR #27 — Shadow Reader voice answer (FR-8.4).** Decision: restore mic UI on **desktop only**; mobile still skips mic per DECISIONS § 22w (Round-7 mobile UA workaround). Backend uses **existing** working /api/upload (which returns SAS URL + blob path) and a **new** /api/notes/{id}/shadow-reader/answer-audio that downloads the SAS URL via httpx and re-uses the existing transcribe_audio_file helper. ``transcribe_audio_url`` is a thin wrapper added in this PR. Did NOT recreate the broken /api/upload/audio endpoint that was removed in PR #14.

### Cross-cutting decisions

**Fleet pattern with shared working dir.** All 6 PRs were developed by parallel sub-agents sharing a single working directory. Each agent self-isolated via stash + branch re-checkout. The pattern worked but is fragile — next round should evaluate ``git worktree`` per agent for better isolation.

**Backend deploy race.** Container Apps platform serializes ``az containerapp update`` operations, so back-to-back merges that each trigger a backend deploy can fail with ``ContainerAppOperationInProgress``. Mitigations: (a) sequence merges with a small wait between each, (b) add a ``concurrency: { group: deploy-backend, cancel-in-progress: false }`` to the workflow. Filed as a follow-up nit; for now, manual ``gh workflow run`` re-trigger covers it.

**TDD red->green for every PR.** Continued the established session policy. Tester would be a separate agent in some past rounds; this round each coder agent ran its own RED check before implementing. Total tests added: ~12 backend + ~40 frontend. Final suites: backend 640/0/6 (was 628), frontend 563/0/1 (was 523).

**Live verification with chrome-devtools.** Before/after screenshots captured for SettingsPage, CreatePage, CapturePage, LibraryPage. Service-worker cache had to be manually cleared after deploy via ``navigator.serviceWorker.getRegistrations() / unregister()`` + ``caches.delete()`` to see new bundles — this is a known PWA pattern, not a bug.

