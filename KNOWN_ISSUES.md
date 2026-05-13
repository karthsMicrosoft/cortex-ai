# KNOWN ISSUES — Cortex Second Brain

> **Open work, bugs not fixed, gaps from "fully done."** Anything tagged P0/P1/P2 here is meant to be picked up by the next agent.

**Last updated:** 2026-05-13 (Round 20: Observability + Strict CSP via /fleet with worktrees — PRs #66-#69)

---

## ✅ Round 8 closed (2026-05-01) — see PROGRESS.md "Round 8"

User confirmed Round-7 fixed Bug 22 (refresh logout). Bug 23 progressed (no more "Network issue" toast) but exposed two new mobile-specific issues. 13 regression tests added.

| # | Bug | Status |
|---|---|---|
| 26 | Mobile recording produces no note (record + stop = silence) | ✅ `start(isMobile ? 1000 : 250)` so iOS Safari MediaRecorder emits chunks mid-stream; mobile branch in VoiceCapture.tsx now mirrors the response into Dexie + sets `syncStatus='synced'`; no degraded toast on mobile (file upload IS primary, not fallback); visible error on upload failure |
| 27 | Mobile can't play audio recorded by Chrome/Edge (iOS Safari has zero WebM support) | ✅ Backend transcodes incoming audio to MP4/AAC at upload time (`_transcode_to_m4a` in services/speech.py — `ffmpeg -c:a aac -b:a 128k -ar 44100`); blob stored as `.m4a` with content-type `audio/mp4`. One-time migration `backend/scripts/migrate_audio_to_m4a.py` converts existing webm/ogg blobs and updates `notes.audio_url` (idempotent) |

## ✅ Round 7 closed (2026-05-01) — see PROGRESS.md "Round 7"

Two persistent bugs fixed after Rounds 5 and 6 failed to resolve them due to environment-level cookie blocking.

| # | Bug | Status |
|---|---|---|
| 22 | Hard reload still logs out (Edge blocks third-party cookie) | ✅ Moved refresh token to localStorage+JSON body (Round-7 architectural decision). Backend /login, /register, /refresh all return `refresh_token` in the response body. Frontend stores it in localStorage on login/register, sends it in body on refresh, clears it on logout. Cookie delivery kept as defense-in-depth. |
| 23 | Mobile voice still shows "Network issue — using file upload fallback" | ✅ `IS_MOBILE` flag added to `useVoiceRecorder.ts`. WS is skipped entirely on mobile (iOS Safari throttling + mobile network instability make it unreliable). File upload is the primary path on mobile; DegradedToast is suppressed when `isMobileFallback=true`. |

**SEC-02 trade-off (accepted, track as P1):** localStorage is XSS-readable. Acceptable for single-user MVP without a CSP. Migrate to first-party cookies when a custom domain is set up or SWA Standard SKU is approved.

## P1 — Migrate refresh token to first-party cookies

**Why deferred:** Free-tier SWA + Container Apps = third-party cookie context. Edge "Balanced" tracking prevention blocks the httpOnly cookie even with SameSite=None+Secure. localStorage fallback added as Round-7 workaround.

**Right fix (P1):** Use a custom domain (e.g. `cortex.karths.dev`) that points both the SWA and the backend under the same eTLD+1, making the cookie first-party. Alternatively, upgrade to SWA Standard SKU ($9/mo) which provides a linked-backend reverse-proxy — the frontend and API share the same origin and the cookie is same-site.

**When ready:** Remove `localStorage.setItem/getItem('cortex_refresh')` calls from `frontend/src/api/auth.ts` and `client.ts`. The cookie path already works — just remove the localStorage augmentation.

---

## ✅ Round 6 closed (2026-05-01) — see PROGRESS.md "Round 6"

User filed 4 issues after Round 5 deploy. Two were Round-5 regressions where the static fix landed but the symptom persisted (22, 23). Two were new (24, 25). 26 regression tests added.

| # | Bug | Status |
|---|---|---|
| 22 | Hard reload still logs out | ✅ Added `credentials: 'include'` to 6 raw fetches in `syncManager.ts` + `uploadBlob` in `VoiceCapture.tsx`. **If symptom persists, root cause is environment-level (browser ITP / Set-Cookie response loss)** |
| 23 | Mobile voice still errors with "Network issue" | ✅ Added `credentials: 'include'` to `uploadBlob`. **If symptom persists, force-disable WS on mobile UA** |
| 24 | Library shows wrong category on receiving browser | ✅ Spread-order bug in `pullChanges()`: hardcoded `category: 'Ideas'` was overwriting `mapServerToLocal`'s spread. Reversed the order so the spread wins. Also added `scheduleEnrichmentRefetch` for receiving browsers |
| 25 | Voice transcription cut at first pause | ✅ Replaced `recognize_once_async()` (stops at first silence) with `start_continuous_recognition_async()` + recognized/session_stopped/canceled handlers that accumulate full transcript across pauses |

## ✅ Round 5 closed (2026-05-01) — see PROGRESS.md "Round 5"

User filed 4 new issues immediately after Round 4 deploy. Fixed via parallel coder + tester agent pair (TDD). 21 regression tests added.

| # | Bug | Status |
|---|---|---|
| 18 | Refresh page logs the user out (chrome debug window survived) | ✅ Two-layer fix: (a) `fetchWithAuth` in `client.ts` no longer recursively re-tries `/api/auth/refresh` on a 401 from itself; (b) `/api/auth/register` now plants the same `samesite=none + secure + httponly` refresh cookie as `/login` |
| 19 | Note delete doesn't propagate across browsers | ✅ New `NoteDeletion` tombstone model + alembic 006 migration; `delete_note`, `bulk_delete`, and the sync-push delete branch all insert a tombstone in the same transaction; `/api/sync/pull` returns it in the `deletions` array |
| 20 | Mobile voice "Network issue — using file upload fallback" then nothing | ✅ MediaRecorder probes `audio/webm`/`audio/mp4`/`audio/ogg` in order; backend `_audio_ext` maps `audio/m4a`/`audio/x-m4a`; `transcribe_audio_file` accepts `src_suffix` so ffmpeg detects the iOS Safari MP4 container; fallback failure shows a real error state (not silent) |
| 21 | Desktop voice creates duplicate (good + failed) | ✅ Frontend: `pushCreate` short-circuits when local note already has `syncStatus='synced' && serverId`. Backend: `create_note` deduplicates by `client_id` — second POST returns existing note instead of inserting |

## ✅ Bug 17 closed (2026-05-01) — see PROGRESS.md "Bug 17"

User reported: notes created in browser A invisible in browser B / incognito for the same logged-in user account.

| # | Bug | Status |
|---|---|---|
| 17 | Different browsers showed different data for the same user | ✅ `syncManager.start()` was seeding `lastPull = new Date()` on first boot — a fresh browser then pulled `since=now` and saw zero history. Reverted to epoch seed; existing buggy browsers auto-migrate when no synced notes exist locally |

## ✅ Round 4 closed (2026-05-01) — see PROGRESS.md "Round 4"

User-reported follow-up bug-bash with **5 issues** including a P0 voice-transcription regression. All fixed and deployed.

| # | Bug | Status |
|---|---|---|
| 12 | Delete note with audio/image attachments → 500 / "Failed to fetch" | ✅ Added `from app.config import settings` to `notes.py` (was used by `_blob_path_from_url` without import) |
| 13 (P0) | Voice notes show "(no speech detected)" despite real audible speech | ✅ MediaRecorder emits `audio/webm;opus`; Azure Speech file-mode expected WAV. Added `_write_temp` + `_ffmpeg_to_wav` helpers in `services/speech.py` so transcribe path converts WebM→16 kHz mono PCM WAV via the ffmpeg already present in the Docker image, then hands the WAV to the SDK |
| 14 | Image upload regressed to "(no speech detected)" after the OCR write | ✅ Stage 1 capture in `pipeline/processor.py` now skips `source_type in ("text", "image")` — image notes get content from OCR directly; the empty-`raw_transcription` guard no longer fires |
| 15 | Image notes had no default `image` tag → not filterable in Library | ✅ `create_note` in `api/notes.py` auto-merges `image` tag for `source_type == 'image'` |
| 16 | Shadow Reader was opt-in launcher button (Round-3 fix); user wanted auto-render restored without overlap with BottomNav | ✅ Rewrote `ShadowReaderPrompt.tsx` to auto-render an inline bottom-sheet on `status === 'asked'`, positioned `bottom-20` (clears 64 px BottomNav) with `sm:bottom-6` on desktop. NOT `role='dialog'` — non-blocking. Polling preserves B17 schedule (10×2 s + 5×5 s, 45 s window). |

**Tests:** New `backend/tests/test_regression_round4_fixes.py` with 14 cases (all pass). Existing `test_pipeline.py` (39/39) still green.

## ✅ Round 3 closed (2026-05-01) — see PROGRESS.md "Round 3"

User-reported bug-bash with **11 functional issues** + P0 polish. Fixed 10/11 plus 1 bonus bug. All deployed live and verified end-to-end via chrome-devtools.

| # | Bug | Status |
|---|---|---|
| P0 | `/api/auth/login` rate limit too aggressive | ✅ 5→30/min |
| 3  | Delete note (single + bulk) | ✅ Trash button on detail; Select mode + bulk-delete on Library; backend cascades blob storage |
| 4 + 5 | NoteEditor Save/Cancel were no-op | ✅ Real PUT + navigate(-1) |
| 6  | Voice notes show "Sure! Please provide…" | ✅ Stage 1 bails on empty transcription |
| 7  | Related notes click didn't navigate | ✅ NoteDetailPage handles serverId in URL |
| 8  | "Want to go deeper?" auto-popping bottom-sheet | ✅ Persistent launcher + opt-in modal |
| 9  | Image attachments not displayed | ✅ `<img>` rendered from `image_url` |
| 10 | Shadow Reader voice answer hung note state | ✅ Voice mic removed (text-only) |
| 11 | Library showed everything as "Ideas" | ✅ syncManager merges all enriched fields + auto-refetch |
| bonus | `/api/sync/pull` 500 with `answer_pending` | ✅ Pydantic Literal updated |

**Deferred:**
- **P1.1** ~~Move APScheduler distill cron to Container Apps Job~~ ✅ **Removed entirely 2026-05-06** — daily/weekly summary functionality dropped per user product decision; `daily_summaries` table dropped (alembic 007), UI cards removed, `apscheduler` dependency gone

## ✅ Round 2 closed (2026-05-01) — see PROGRESS.md "Round 2"

UX-tester agent's 4 filed issues triaged:
- ISSUE-01 (notes pending sync) — **already fixed by round 1** (embedding column + sync drain)
- ISSUE-02 (hard-reload bounces to /login) — **already fixed by round 1** (SameSite=None + SessionGate)
- ISSUE-03 (`/api/upload` 500 + CORS missing) — **fixed**: wrap `content_settings` in `ContentSettings()` object (azure-storage-blob 12.22 requires this)
- ISSUE-04 (`/api/ai/summary/weekly` 500 ProgrammingError) — **fixed**: replace `str(date)` with typed `datetime` bounds in `distill.py` daily + weekly summary queries

Plus defensive: voice upload returns 422 with helpful detail (instead of 500 + missing CORS) when audio is invalid/corrupt.

e2e suite is now **15/17 passing**. The two remaining failures are **test-infra flakiness**, not app bugs:
- Post-sign-out tests in the shared-auth Playwright suite hit `/login` 5/min rate limit on rapid re-login fallback. Either bump that route's limit or run sign-out test last via `serial` mode.

## ✅ Round 1 closed (2026-05-01) — see PROGRESS.md "Round 1"

Four production bugs fixed and verified live:
- `/api/notes` 500 (embedding column type mismatch) → fixed
- `/api/voice/upload` 422 (form field name) → fixed
- `/api/auth/refresh` 429 (rate limit too aggressive) → bumped 5→60/min
- AI pipeline NotFoundError (Azure OpenAI deployments missing) → created `gpt-4o-mini` + `text-embedding-3-small` deployments

Result: text note submission now reaches `Enriched` status end-to-end. Hard refresh preserves session.

Round-2 issues filed by the UX-tester agent live in `e2e/ISSUES.md` (next pickup).

## ✅ P0 — Container App auto-restart + health-check alerts (resolved 2026-05-07, Round 13)

**Status:** Closed.

**Auto-restart half** was already in place: `infra/modules/container-app.bicep` lines 133–148 configure Liveness + Readiness probes against `/api/health` with `failureThreshold: 3`. Container Apps platform automatically restarts the replica when liveness fails 3× consecutively. No infra change needed; just verified + documented.

**Alerts half** added: 3 Azure Monitor alerts in `cortex-rg` routing to `karths@microsoft.com` via shared Action Group `cortex-alerts-ag`.

| Alert | Severity | Fires when |
|---|---|---|
| `cortexks-api-restart-spike` | 2 | Container App `RestartCount` (max) >= 3 over 5 min |
| `cortexks-api-5xx-rate` | 2 | Container App `Requests` total >= 10 with `statusCodeCategory=5xx` over 5 min |
| `cortexks-api-availability` | 1 | App Insights synthetic ping to `/api/health` from Chicago drops availability < 100% over 5 min |

App Insights `cortexks-ai` (centralus, classic web kind) + classic URL-ping web test `cortexks-api-health-ping` (every 5 min from `us-il-ch1-azr`, expects HTTP 200 + content match `"ok"`) bootstrap the availability surface. Cost ~$1/month.

Rebuild recipe + Bicep-vs-CLI rationale in `docs/DEPLOYMENT.md` § "Health-Check Alerts". Decision history in `DECISIONS.md` § 22ac.

## P0 — Smoke test the deployed app end-to-end

**Status:** Auth flow validated (register + auto-login working). Pipeline + offline + Phase 2 features not yet validated in a real browser.

**Action:** Run `PLAN.md` § 5 smoke test plan in a real browser. Log any bugs here.

---

## ✅ P1 — Backend + frontend test failures (resolved 2026-05-07)

**Status:** Final round of test triage closed the remaining failures across both suites.

**Backend:** `626 passed | 0 failed | 6 skipped | 1 xfailed | 1 xpassed` — **100%** pass rate (target was ≥95%).
**Frontend:** `523 passed | 0 failed | 1 skipped` (30/30 test files green) — **99.8%** pass rate. The 1 skip is a documented order-dependent flake in `VoiceCapture.realtime.test.tsx` (`IndexedDB rawTranscription on stop`) — passes in isolation; deferred with an inline TODO to rework the mock useVoiceRecorder so mutating `mockHookState.isRecording` enqueues a React state update.

The triage was done as a 9-PR fleet sweep over 2026-05-06/05-07 (PRs #2 → #18, see PROGRESS § 12). Net delta: +30 backend passes, +90 frontend passes, 1 production bug found and fixed (PR #6 dictionary bulk SQLite portability), 0 production behavior regressions.

The original cluster-by-cluster breakdown that was here is now historical and is captured in PROGRESS § 12 alongside the per-PR root-cause / fix / verification table.

---

## ✅ P1 — APScheduler removed entirely (resolved 2026-05-06)

**Status:** Daily/weekly distill cron, the `app/pipeline/distill.py` module, the `daily_summaries` model and table, the APScheduler dependency, and the `/api/ai/summary/daily` + `/api/ai/summary/weekly` HTTP endpoints + their UI cards in `InsightsPage.tsx` were ALL removed entirely per a user product decision (2026-05-06). The Insights page now shows only AI-detected Recurring Patterns.

**What was deleted:**
- `backend/app/pipeline/distill.py`
- `backend/app/models/daily_summary.py`
- `backend/tests/test_scheduler.py`, `backend/tests/test_distill.py`
- The `lifespan` block + `SCHEDULER_ENABLED` env-gate in `backend/app/main.py`
- `apscheduler==3.10.*` from `backend/requirements.txt`
- `User.daily_summaries` relationship in `backend/app/models/user.py`
- The two summary endpoints + their schemas from `backend/app/api/insights.py`
- DailySummary import + `_serialise_summary` from `backend/app/api/export.py` (export still emits `summaries: []` for back-compat)
- "Today's Summary" + "This Week" cards from `frontend/src/pages/InsightsPage.tsx`
- Daily/weekly test cases from `backend/tests/test_insights.py` + `frontend/src/__tests__/InsightsPage.test.tsx`

**What was added:**
- `backend/alembic/versions/007_drop_daily_summaries.py` — drops the table (was empty in prod since `SCHEDULER_ENABLED=false` had been the default since deploy)
- `TestSchedulerRemoved` regression class in `backend/tests/test_regression_deploy_fixes.py` — guards against re-introduction (asserts `apscheduler` not in main, `app.pipeline.distill` raises ImportError, `app.models.daily_summary` raises ImportError, `apscheduler` not in requirements.txt)
- Regression assertion in frontend test that the page does not call the removed endpoints
- B14 comment update in `infra/main.bicep` + `infra/modules/container-app.bicep` — minReplicas=1 is now justified by cold-start avoidance only (no scheduler dep)

**Side effect:** The Shadow Reader QA-04 retry sweep (`retry_stale_answer_pending`) is no longer scheduled. The function still exists in `app/pipeline/shadow_reader.py` — if a `merge_answer_into_note` background task fails and a note gets stuck in `answer_pending`, you can invoke it manually. This was already not running in production (scheduler was off), so behaviour is unchanged.

---

## ✅ P1 — GitHub Actions deploys wired (resolved 2026-05-06)

**Status:** Both `.github/workflows/deploy-backend.yml` and `.github/workflows/deploy-frontend.yml` are live, OIDC-federated against `cortex-github-actions` AAD app, and verified green on push-to-main + on `workflow_dispatch`. Closes the long-standing P1 from this section.

**OIDC + RBAC (operational, not in repo):**

| Item | Value |
|---|---|
| AAD app | `cortex-github-actions` (clientId `976b4653-b915-412f-bc05-28036fd6e5e5`) |
| Federated credential | issuer `https://token.actions.githubusercontent.com`, subject `repo:karthsMicrosoft/cortex-ai:ref:refs/heads/main` |
| RBAC | `Contributor` on `cortex-rg` + `AcrPush` on `cortexksacr` |
| GitHub repo secrets | `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `ACR_NAME`, `CONTAINER_APP_NAME`, `RESOURCE_GROUP`, `AZURE_STATIC_WEB_APPS_API_TOKEN` (7 total) |

**What CI does now per push:**
- Frontend (on changes under `frontend/**` or the workflow yaml itself): npm ci + `npm run build` + copy SWA config into `dist/` + upload via `Azure/static-web-apps-deploy@v1`. ~1 min runtime.
- Backend (on changes under `backend/**` or the workflow yaml): Azure login (OIDC) + `az acr build` (image tagged with `${{ github.sha }}` + `latest`) + `az containerapp update --revision-suffix ci<ts>` + 60 s health-check loop on `/api/health`. ~3 min runtime.
- `workflow_dispatch` trigger added to both for manual re-fires.

### Caveat — alembic migrations stay manual

`az containerapp exec` requires a TTY (`tty.setcbreak(sys.stdin.fileno())`) which a GitHub Actions runner cannot provide. The CI workflow does NOT run `alembic upgrade head`. When schema changes ship as part of a deploy, run from a developer shell after the workflow goes green:

```bash
az containerapp exec --name cortexks-api --resource-group cortex-rg \
  --command "alembic upgrade head"
```

Future automation options:
1. Embed `alembic upgrade head` into the container's CMD/ENTRYPOINT (single-replica race safe since `minReplicas=1`).
2. Run migrations as a separate Container Apps Job triggered by the workflow.

Either is a P3 follow-up.

---

## ✅ P1 — Azure Budget alerts (resolved 2026-05-05)

**Status:** Created `cortex-monthly` budget on the `cortex-rg` resource group, $150/month, with three notification thresholds emailing `karths@microsoft.com`:
- **67% Actual (~$100)** — warning
- **93% Actual (~$140)** — critical
- **100% Forecasted** — leading-indicator (catches projected overspend before actual hits)

Period: 2026-05-01 → 2027-05-01 (monthly reset).

**Verify / inspect:**
```bash
az consumption budget show-with-rg --resource-group cortex-rg --budget-name cortex-monthly
```

**How it was created** (Azure CLI for the two Actual thresholds + REST PUT for the Forecasted threshold, since the CLI doesn't expose `thresholdType`):
```bash
# Step 1: create with two Actual thresholds (CLI defaults thresholdType=Actual)
cat > /tmp/notif.json <<'JSON'
{
  "Actual_GreaterThan_67_Percent": {"enabled": true, "operator": "GreaterThan", "threshold": 67, "contact-emails": ["karths@microsoft.com"]},
  "Actual_GreaterThan_93_Percent": {"enabled": true, "operator": "GreaterThan", "threshold": 93, "contact-emails": ["karths@microsoft.com"]}
}
JSON
echo '{"startDate":"2026-05-01T00:00:00Z","endDate":"2027-05-01T00:00:00Z"}' > /tmp/tp.json
az consumption budget create-with-rg \
  --resource-group cortex-rg \
  --budget-name cortex-monthly \
  --amount 150 --category cost --time-grain Monthly \
  --time-period @/tmp/tp.json --notifications @/tmp/notif.json

# Step 2: PUT full body via REST to add the Forecasted threshold
# (PATCH/REST PUT requires latest eTag from `show-with-rg`)
```

---

## P2 — Frontend mock-isolation bug (1 known test failure)

**Status:** `frontend/src/__tests__/api-client.test.ts > apiPost > 'attaches Authorization header'` fails when run with the full suite but passes in isolation.

**Cause:** `vi.clearAllMocks()` in `afterEach` resets call history but NOT `mockReturnValue` set by `vi.mocked(useAuthStore.getState).mockReturnValue(...)` in a previous test. The stale `accessToken: 'old-token'` bleeds into the next test.

**Fix:** In the relevant `describe` block's `afterEach`, replace `vi.clearAllMocks()` with `vi.resetAllMocks()`. Or wrap the offending test with explicit `mockReturnValueOnce(...)`.

**Impact:** Implementation in `api/client.ts` is correct. This is a test-only flake.

---

## ✅ P0 — Key Vault bootstrapped (resolved 2026-05-06)

**Status:** Live Key Vault `cortexks-kv` (centralus, RBAC mode) holds the two sensitive secrets — the asyncpg connection string and the JWT signing key. The Container App's system-assigned managed identity has the **Key Vault Secrets User** role on it, and its `database-url` + `jwt-secret-key` secrets are stored as `keyVaultUrl` references with `identity: system`. Rotating in KV propagates to new replicas; no Bicep redeploy needed (see `docs/DEPLOYMENT.md` § "Key Vault — secret rotation" for the rotation runbook).

**Verify live:**
```bash
az containerapp secret list --name cortexks-api --resource-group cortex-rg \
  --query "[?name=='database-url' || name=='jwt-secret-key'].{name:name, keyVaultUrl:keyVaultUrl, identity:identity}" -o json
```

`infra/parameters.keyvault-template.json` was updated with the live KV id, the correct `cortexks` / `centralus` / `eastus` values, and the SWA frontend origin so a brand-new from-scratch deploy can use it directly.

---

## ✅ P2 — Spec auditor SA-M1 (resolved 2026-05-07, Round 14)

**Status:** Closed.

**Was:** `backend/alembic/versions/001_initial_schema.py` declared `notes.embedding` as `sa.Text()` placeholder inside `op.create_table()`, then dropped + re-added as `vector(1536)` via raw DDL — three statements where one suffices.

**Now:** The placeholder column + the `DROP COLUMN` are gone. Single `op.execute("ALTER TABLE notes ADD COLUMN embedding vector(1536)")` after `create_table`. Same end-state schema (column position differs, invisible to SQLAlchemy ORM which addresses by name).

**Why safe to edit:** Migration 001 has already run on prod (alembic_version is at 007). Editing the file is a no-op for the live container; only affects from-scratch redeploys (e.g., disaster recovery, fresh dev DBs).

**Coverage:** 2 new static-introspection tests in `tests/test_database.py::TestAlembicMigrationFile`:
- `test_no_embedding_placeholder_dance_in_001` — asserts no `sa.Column("embedding"`, no `DROP COLUMN embedding`, exactly 1 `ADD COLUMN embedding vector(1536)`.
- `test_hnsw_index_still_present_after_001` — regression guard that `idx_notes_embedding` + HNSW + `vector_cosine_ops` survive the cleanup.

PR #21. Backend now at 628/0/6 (Round 12 baseline + 2 new tests).

---

## P2 — Service Worker / PWA fragments

**Status:** PWA registered with `clientsClaim:true, skipWaiting:true`. SW updates take effect immediately on next page load.

**Polish ideas (not blocking):**
- Show a "New version available" toast for ~3s after `controllerchange` event so the user knows why the page refreshed
- Add `vite-plugin-pwa` `injectRegister: 'auto'` and `useRegisterSW(...)` from `virtual:pwa-register/react` for smoother UX
- Test offline launch from home screen on iOS Safari (some iOS versions cache differently)

---

## ✅ P3 — Phase 3 (resolved 2026-05-08, Round 15)

Items 35-40 from spec § 4.2 — closed via 6 PRs (#22-#27). See `PROGRESS.md` § 15 for full per-PR root-cause + fix + verification table.

| Spec item | Shipped via |
|---|---|
| 35 — Music AI pipeline | DONE in us-6 `pipeline/music.py` (pre-Round 15) |
| 36 — Music player | DONE in us-6 `MusicPlayer.tsx` (pre-Round 15) |
| 37 — Express endpoints | DONE in us-6 `api/insights.py::generate_express` (pre-Round 15) |
| 37 — Settings export + change-password | **PR #22** (Round 15) — new `api/export.ts` + `SettingsPage` "Your Data" button calling `GET /api/export`, change-password form duplicated from `ProfilePage`, `AppHeader` profile-icon now points to `/settings` |
| 35-36 — Express UI polish | **PR #23** (Round 15) — Copy/Regenerate/Save-as-Note buttons, per-mode hints, retry on note-load failure, mode-switch resets selection, separated load/validation/generate error states |
| 38 — Backend image+OCR | DONE in us-2 `pipeline/ocr.py` (pre-Round 15) + **PR #24** (Round 15) added empty-OCR placeholder + 415/413 tests on `/api/upload` |
| 39 — Frontend image capture | **PR #24** (Round 15) — preview-before-upload, client-side resize ≤2048px / 5MB JPEG, "Uploading…" spinner + error toast, new `ImagePreview.tsx` |
| 40 — E2E + perf | **PR #25** lazy-load route splitting (-58 KB raw / -13 KB gzip main bundle, 6 new chunks for Insights/Create/Settings/Library/Search/NoteDetail) + **PR #26** Playwright runner (`npm run e2e`, GH Actions workflow `e2e.yml` with `workflow_dispatch` + nightly cron 09:00 UTC, 17/17 tests passing live) + **PR #27** Shadow Reader voice answer (FR-8.4) — restored mic UI on desktop, new `POST /api/notes/{id}/shadow-reader/answer-audio` that uses existing `/api/upload` + `transcribe_audio_url`, mobile UA still skips mic per § 22w |

**TDD pattern used:** red→green for every PR (frontend Vitest + backend pytest where applicable). Full backend now at **640 passed / 6 skipped / 1 xfailed / 1 xpassed** (Round 14 baseline 628 + ~12 added across PRs). Full frontend at **563 passed / 1 skipped** (Round 14 baseline 523 + ~40 added).

**Live verification:** chrome-devtools manual audit + cache-buster reload after each merge; before/after screenshots saved to session `files/`. E2E workflow (PR #26) provides ongoing regression coverage.

---

## P3 — Frontend deps stale (Researcher's MEDIUM)

| Spec | Current | Action |
|---|---|---|
| React 18.3 | latest is 19.x | Bump after Phase 3; React 19 is mostly compatible (deprecated `forwardRef` etc.) |
| Vite 5.4 | latest is 8.x | Bump; minimal breaking changes |
| Tailwind 3.4 | latest is 4.x | **Larger break** — Tailwind 4 drops `tailwind.config.js` for CSS-first config. Plan a separate migration. |
| Zustand 4.5 | latest is 5.x | Minor API tweaks; bump after Phase 3 |
| react-router-dom 6.26 | latest is 7.x | Some routing API changes; defer until needed |

Pinned for now per Lead decision in Phase 2 design phase: "spec is the frozen 2024-Q3 snapshot; bump after MVP stable."

---

## P3 — Backend deps stale (Researcher's MEDIUM)

| Spec / current | Latest | Action |
|---|---|---|
| `openai==1.40.*` | 2.33+ | API broadly compatible; bump after Phase 3 |
| `asyncpg==0.29.*` | 0.31+ | Adds Python 3.13 wheels; bump if you upgrade host Python |
| `alembic==1.13.*` | 1.18+ | Minor improvements; bump opportunistically |
| `pgvector==0.3.*` | 0.4+ | Some new operators; bump opportunistically |

---

## P3 — JTI revocation in-memory (SEC-07 followup)

**Limitation:** `_revoked_jtis: set[str]` lives in process memory. Container App restart loses the revocation state. A reused refresh token could theoretically bypass revocation if the original JTI was revoked but the deny set was wiped on restart.

**Fix (when you get to it):**
- Spin up Azure Cache for Redis (Basic C0 ~$15/mo) OR add a `refresh_token_revocations` table to Postgres
- Replace the in-memory set with calls to that store
- Add a TTL of 30 days (matches refresh token lifetime — entries expire naturally)

---

## P3 — `/api/auth/logout` endpoint not implemented

**What it would do:** Revoke the current session's refresh JTI explicitly + clear the cookie. Defense-in-depth — without it, "logout" is implicit (forget access token + wait for refresh expiry).

**Implementation sketch:**
```python
@router.post("/logout")
async def logout(request: Request, response: Response, current_user_id: UUID = Depends(get_current_user)):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = jwt.decode(refresh_token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
            revoke_jti(payload.get("jti"))
        except JWTError:
            pass  # already invalid, idempotent
    response.delete_cookie("refresh_token")
    return {"ok": True}
```

---

## P4 — Backup/restore strategy

**Current state:** Postgres Flexible Server has 7-day automated backup (default; configured via Bicep `backup.backupRetentionDays: 7`).

**Gaps:**
- No documented restore runbook
- Blob Storage has no backup (the audio/image files are irreplaceable)
- No DR / cross-region replication

**Action (P4 when scaling beyond MVP):** Document a restore runbook in `docs/DEPLOYMENT.md`. Consider GRS for storage if budget allows (~+$2/mo).

---

## P4 — Observability gaps

**Currently:**
- `az containerapp logs show` for Container App stdout
- Postgres metrics in the Azure portal

**Missing:**
- App Insights or OpenTelemetry instrumentation
- Custom metrics for pipeline stage durations
- Alerts on 5xx rate > X / minute
- Alert on B12 log-scrubber metric

**Action (P4):** Wire OpenTelemetry SDK to Azure Monitor; add `RED` metrics (Rate / Errors / Duration) per endpoint.

---

## P4 — Cosmetic / nit findings (not autofixed)

From `features/cortex-second-brain/tasks/review-comments.tasks.md` Tasks 1-3 LOW + NIT:
- PERF-12: Export endpoint loads all notes into memory (use `yield_per` for streaming)
- PERF-13: Insights graph endpoint has 200-UUID `IN` list with no `LIMIT` on returned links
- ~~PERF-14: APScheduler `BackgroundScheduler` + `asyncio.run()` creates a second event loop per job~~ (no longer relevant — APScheduler removed 2026-05-06)
- PERF-N1: `created_at` date filter casts to `str` instead of typed `datetime`
- PERF-N2: ShadowReaderPrompt first poll waits full 2s; could fire immediately
- QA-12, QA-15: misc style issues (TODO comments left, naming inconsistencies)
- SEC-08 followup: SAS URL uses 1-hour expiry; could shorten to 15 min for tighter security

---

## Test-side bugs found in this session (DOCUMENT, don't fix unless P0)

1. `backend/tests/test_shadow_reader.py` line 38-44: `FIFTY_WORD_CONTENT` was 36 words. Lead expanded it to ≥50. ✅ Fixed.
2. `backend/requirements-test.txt` was missing `respx`. Lead added `respx>=0.21,<1`. ✅ Fixed.

---

## Quick reference — running the test suite

```bash
# Backend
cd backend
.venv/Scripts/python.exe -m pytest tests/ -v --no-cov  # full output
.venv/Scripts/python.exe -m pytest tests/ -q --no-cov --tb=short  # short

# Run only specific test
.venv/Scripts/python.exe -m pytest tests/test_auth.py::TestRegister -v --no-cov

# Frontend
cd frontend
npm test                # vitest watch mode
npm run test -- --run   # single pass
```

---

## Quick reference — checking live deployment health

```bash
# Backend health
curl https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/api/health

# Frontend reachable
curl -I https://gentle-river-06c1e4e10.7.azurestaticapps.net/

# Live container logs (last 60 lines)
PYTHONIOENCODING=utf-8 az containerapp logs show --name cortexks-api --resource-group cortex-rg --tail 60 --container cortexks-api

# Live container revisions (status check)
az containerapp revision list --name cortexks-api --resource-group cortex-rg \
  --query "[].{name:name, active:properties.active, healthState:properties.healthState, runningState:properties.runningState}" -o table

# Postgres reachable from Azure (run inside container)
PYTHONIOENCODING=utf-8 az containerapp exec --name cortexks-api --resource-group cortex-rg \
  --command "python -c 'from app.database import engine; import asyncio; asyncio.run(engine.connect())'"
```

---

## When to reach for which doc

- **Just landed here, need orientation:** `HANDOFF.md`
- **Want the architecture / why-decisions:** `DECISIONS.md`
- **Want the chronological log of what happened:** `PROGRESS.md`
- **Want the roadmap forward:** `PLAN.md`
- **Want the open work / bugs:** `KNOWN_ISSUES.md` (this file)
- **Want the spec details:** `SECOND_BRAIN_BUILD_SPEC.md` + `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md`
- **Want the design contract:** `features/cortex-second-brain/designs/design.md`
- **Want the per-story tasks:** `features/cortex-second-brain/tasks/us-*.tasks.md`
- **Want the review findings + fix tasks:** `features/cortex-second-brain/tasks/review-comments.tasks.md`
- **Want the deployment runbook:** `docs/DEPLOYMENT.md`
