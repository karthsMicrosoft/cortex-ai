# KNOWN ISSUES — Cortex Second Brain

> **Open work, bugs not fixed, gaps from "fully done."** Anything tagged P0/P1/P2 here is meant to be picked up by the next agent.

**Last updated:** 2026-05-01 (round 4 closed + bug 17)

---

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
- **P1.1** Move APScheduler distill cron to Container Apps Job (still gated on `SCHEDULER_ENABLED=false`; on-demand weekly summary works without it)

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

## P0 — Smoke test the deployed app end-to-end

**Status:** Auth flow validated (register + auto-login working). Pipeline + offline + Phase 2 features not yet validated in a real browser.

**Action:** Run `PLAN.md` § 5 smoke test plan in a real browser. Log any bugs here.

---

## P1 — Backend test failures (30 still red after fix-pair pass)

**Status:** 263 pass / 30 fail / 266 skip on local pytest. **Fix-pair agent ran ~94 minutes** (earlier session) and edited many tests but didn't drive failures to zero.

### 1a — Categorized failure list

Run from `backend/` with `.venv/Scripts/python.exe -m pytest tests/ --tb=short --no-cov -q` to reproduce.

| Cluster | Count | Sample failing tests | Triage notes |
|---|---|---|---|
| **Schedulers / lifespan introspection** | 8 | `test_scheduler.py::TestSchedulerModuleImport::test_main_has_lifespan_or_startup`, `test_main_references_scheduler`, `test_scheduler_has_nightly_daily_job`, `test_nightly_job_calls_generate_daily_summary`, `test_weekly_job_registered`, `test_scheduler_started_at_startup`, `test_scheduler_shutdown_at_teardown`, `test_scheduler_uses_cron_trigger`, `test_main_py_references_apscheduler`, `test_scheduler_runs_at_2359` | Tests assert `@app.on_event` or specific class names. Implementation uses `@asynccontextmanager` lifespan + the scheduler is now gated on `SCHEDULER_ENABLED` env var. **Action:** rewrite tests to look for the lifespan context manager + the gated import path. |
| **Speech SDK mocks** | 5 | `test_speech.py::TestTranscribeAudioFile::test_returns_transcript_string`, `test_default_language_en_us`, `test_explicit_language_passed_through`, `test_recognize_once_async_called`, `test_retries_on_transient_error` | Tests mock `recognize_once_async` differently than implementation calls it (we use `loop.run_in_executor(None, future.get)` to await the SDK's concurrent.futures-style future). **Action:** update mock to return a future-like object whose `.get()` returns the result, OR refactor implementation to use a simpler awaitable. |
| **Vocab usage_count Python-side assertions** | 3 | `test_voice_phrase_list.py::TestIncrementTermUsage::test_increments_usage_count_for_found_term`, `test_case_insensitive_match`, `test_multiple_terms_incremented` | PERF-02 fix moved logic from Python loop to single SQL UPDATE. Tests still mock `vocab_entry.usage_count == N` — the SQL UPDATE doesn't mutate the in-memory MagicMock. **Action:** rewrite to assert `db.execute()` was called with the UPDATE statement and ILIKE pattern; drop the in-memory state assertion. |
| **`_note_to_out` shadow_reader fields** | 3 | `test_voice_phrase_list.py::TestSingleNoteToOutHelper::test_voice_py_note_to_out_includes_shadow_reader_status`, `_questions`, `_answer` | Tests look for `shadow_reader_*` strings inside `voice.py` source code. After QA-05 fix, `voice.py` imports `_note_to_out` from `_note_serializers.py` (which has the fields). **Action:** rewrite to read `_note_serializers.py` instead OR import the function and inspect its output. |
| **Migration 003 introspection** | 3 | `test_shadow_reader.py::TestMigration003UsesAsyncCompatibleIdiom::test_migration_003_does_not_use_op_get_bind`, `test_migration_003_uses_op_execute`, `test_migration_003_upgrade_callable` | Tests use `importlib.util` to load the migration file and grep for substrings. The QA-01 fix removed `op.get_bind()` correctly but the test asserts `def upgrade(` exact pattern. **Action:** loosen the regex to `def upgrade` (with or without parens). |
| **Schema introspection** | 1 | `test_notes.py::TestNoteContentSizeLimit::test_note_update_schema_has_content_max_length` | Pydantic v2 reports `maxLength` differently than v1. **Action:** update to Pydantic v2 introspection — use `NoteUpdate.model_json_schema()` then check `properties.content.maxLength`. |
| **Router prefix tests** | 2 | `test_dictionary.py::TestDictionaryRouterImport::test_router_prefix`, `test_insights.py::TestInsightsModuleImport::test_insights_router_exists` | Tests assert specific prefix strings. **Action:** update assertions to match actual prefix (`/api/dictionary` vs whatever expected). |
| **Security config production guard** | 1 | `test_security_config.py::TestJWTSecretKeyProductionGuard::test_placeholder_rejected_in_production` | Test sets `JWT_SECRET_KEY="change-me-in-production"` + `ENVIRONMENT="production"` and expects `ValidationError`. The implementation raises `RuntimeError` from `check_production_secrets()` at module load (a different exception). **Action:** update test to expect `ValidationError` from the field validator, OR `RuntimeError` from the boot check, depending on which path triggers first. |
| **OCR race condition** | 1 | `test_ocr.py::TestOCRBackgroundTaskRefetchesByID::test_race_condition_note_not_yet_in_db_handled_without_simple_namespace` | Test asserts `SimpleNamespace` is NOT used. QA-06 fix removed it but the test grep pattern may also match a comment. **Action:** loosen the assertion or strengthen the source check. |
| **GIN FTS index migration assertion** | 1 | `test_search.py::TestPERF05FullTextIndex::test_migration_creates_gin_index_on_notes_content` | Test looks for `CREATE INDEX CONCURRENTLY` in migration 005. Lead removed `CONCURRENTLY` for first deploy. **Action:** drop `CONCURRENTLY` from the assertion OR set `transaction_per_migration=False` and restore `CONCURRENTLY`. |
| **WS auth tests marked async-but-sync** | 4 | `test_voice_ws.py::TestValidateWsToken::test_invalid_token_raises`, etc. | Tests are decorated with `@pytest.mark.asyncio` but the function bodies are sync. PytestWarning issued. **Action:** remove the `pytestmark = pytest.mark.asyncio` from those classes, or convert the bodies to `async def` (no functional change since they only call sync `validate_ws_token`). |

### 1b — Real production bug found in this set

`backend/app/services/speech.py:84`: `speechsdk.CancellationDetails.from_result(result)` — the `from_result` classmethod doesn't exist in azure-cognitiveservices-speech 1.40. Correct API is the constructor `CancellationDetails(result)`. **Already fixed.**

### 1c — Suggested triage approach

For each cluster:
1. Decide: real bug or test-side flake?
2. If real bug → fix in `backend/app/`
3. If test-side → fix in `backend/tests/` so the test asserts current behavior
4. Re-run pytest; expect ≥95% pass rate (≤2 acceptable acknowledged failures)

---

## P1 — APScheduler is disabled on the live Container App

**Status:** `SCHEDULER_ENABLED` env var defaults to `false`. The nightly distill cron + the answer_pending sweep job DO NOT run.

**Why disabled:** APScheduler's `BackgroundScheduler` runs each job in a separate thread. Each tick creates a fresh `asyncio.run(...)` event loop. The asyncpg connection pool is shared with the FastAPI event loop — asyncpg refuses to multiplex a connection across loops, causing `cannot perform operation: another operation is in progress` on concurrent request traffic. This was the root cause of the 500 the user saw on register.

**The right fix (P1):** Move the cron jobs OUT of in-process scheduling and into a dedicated **Container Apps Job** that triggers on cron schedule. Sketch:
```bicep
resource distillJob 'Microsoft.App/jobs@2024-03-01' = {
  name: '${appName}-distill-job'
  location: location
  properties: {
    environmentId: containerEnv.id
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: { cronExpression: '59 23 * * *' }
      replicaTimeout: 600
    }
    template: {
      containers: [{ name: 'distill', image: '<same image>', command: ['python', '-m', 'app.pipeline.distill'] }]
    }
  }
}
```
And expose `python -m app.pipeline.distill` as a CLI entry that calls `run_daily_distill()` synchronously (or a fresh asyncio loop).

**Workaround if you need the scheduler in-process for now:** Add a separate engine with `poolclass=NullPool` for scheduler-side sessions:
```python
from sqlalchemy.pool import NullPool
scheduler_engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
SchedulerSessionLocal = async_sessionmaker(scheduler_engine, expire_on_commit=False)
```
Use `SchedulerSessionLocal()` in `_retry_stale_answer_pending_async` instead of the shared `SessionLocal`. Each tick gets its own raw connection that closes when done — no pool sharing. Set `SCHEDULER_ENABLED=true` once tested.

**Side effect of disable:** The Shadow Reader QA-04 retry sweep doesn't run. If a `merge_answer_into_note` background task fails, the note stays in `answer_pending` forever. Workaround: a manual SQL fix or a manual API trigger. P1 fix above resolves this.

---

## P1 — GitHub Actions deploys aren't wired to secrets

**Status:** `.github/workflows/deploy-backend.yml` and `deploy-frontend.yml` exist and reference these secrets:

| Secret | Where to get it |
|---|---|
| `AZURE_CLIENT_ID` | Output of `az ad sp create-for-rbac` for an OIDC-federated app registration |
| `AZURE_TENANT_ID` | `az account show --query tenantId -o tsv` |
| `AZURE_SUBSCRIPTION_ID` | `85f6cb53-9eec-43f1-84c3-bf701dcd4048` |
| `ACR_NAME` | `cortexksacr` |
| `RESOURCE_GROUP` | `cortex-rg` |
| `APP_NAME` | `cortexks` |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | `az staticwebapp secrets list --name cortexks-app --resource-group cortex-rg --query properties.apiKey -o tsv` |

**Action:** Set these in the GitHub repo (Settings → Secrets and variables → Actions). Until they're set, push-to-main won't deploy. The current live deploy was from a local shell.

---

## P1 — No Azure Budget alerts

**Status:** `docs/DEPLOYMENT.md` references budget alerts at $100 (warning) and $140 (critical). They are NOT yet created.

**Action:**
```bash
az consumption budget create \
  --budget-name cortex-monthly \
  --amount 150 \
  --time-grain Monthly \
  --start-date 2026-04-01 \
  --end-date 2027-04-01 \
  --notifications '{"Actual_GreaterThan_67_Percent":{"enabled":true,"operator":"GreaterThan","threshold":67,"contactEmails":["karths@microsoft.com"],"thresholdType":"Actual"},"Actual_GreaterThan_93_Percent":{"enabled":true,"operator":"GreaterThan","threshold":93,"contactEmails":["karths@microsoft.com"],"thresholdType":"Actual"}}'
```
(Run with caution — `az consumption budget` is preview; consult docs for current syntax.)

---

## P2 — Frontend mock-isolation bug (1 known test failure)

**Status:** `frontend/src/__tests__/api-client.test.ts > apiPost > 'attaches Authorization header'` fails when run with the full suite but passes in isolation.

**Cause:** `vi.clearAllMocks()` in `afterEach` resets call history but NOT `mockReturnValue` set by `vi.mocked(useAuthStore.getState).mockReturnValue(...)` in a previous test. The stale `accessToken: 'old-token'` bleeds into the next test.

**Fix:** In the relevant `describe` block's `afterEach`, replace `vi.clearAllMocks()` with `vi.resetAllMocks()`. Or wrap the offending test with explicit `mockReturnValueOnce(...)`.

**Impact:** Implementation in `api/client.ts` is correct. This is a test-only flake.

---

## P2 — Key Vault not bootstrapped

**Status:** `infra/parameters.json` uses inline secrets passed via `--parameters` to deploy.sh. `infra/parameters.keyvault-template.json` is the production-track template waiting for KV bootstrap.

**Action (when ready):**
1. Create a Key Vault (`cortex-kv` or similar) in the same resource group.
2. Store the secrets:
   ```bash
   az keyvault secret set --vault-name <KV_NAME> --name cortex-db-admin-password --value "<the password>"
   az keyvault secret set --vault-name <KV_NAME> --name cortex-jwt-secret-key --value "<the JWT key>"
   ```
3. Replace placeholders in `parameters.keyvault-template.json` (`__SUBSCRIPTION_ID__`, `__KV_RESOURCE_GROUP__`, `__KEY_VAULT_NAME__`).
4. Rename `parameters.keyvault-template.json` → `parameters.json` (overwriting the inline-secrets one).
5. Grant the deployment principal `Key Vault Secret User` role on the KV.
6. Re-run `deploy.sh` — Bicep will pull secrets from KV instead of cmdline.

---

## P2 — Spec auditor SA-M1 (cosmetic migration cleanup)

**Status:** `backend/alembic/versions/001_initial_schema.py` creates `notes.embedding` as `sa.Text()` placeholder, then drops and re-adds as `vector(1536)` via raw DDL.

**Why it works:** Functionally correct — pgvector type isn't natively known to SQLAlchemy DDL, so the workaround inserts the column then alters it.

**Cleanup:** Replace the placeholder + drop + re-add with a single `op.execute("ALTER TABLE notes ADD COLUMN embedding vector(1536)")`. Lower risk: keep as-is (it's documented).

---

## P2 — Service Worker / PWA fragments

**Status:** PWA registered with `clientsClaim:true, skipWaiting:true`. SW updates take effect immediately on next page load.

**Polish ideas (not blocking):**
- Show a "New version available" toast for ~3s after `controllerchange` event so the user knows why the page refreshed
- Add `vite-plugin-pwa` `injectRegister: 'auto'` and `useRegisterSW(...)` from `virtual:pwa-register/react` for smoother UX
- Test offline launch from home screen on iOS Safari (some iOS versions cache differently)

---

## P3 — Phase 3 not implemented

Items 35-40 from spec § 4.2:
- 35: Backend Music-specific AI processing pipeline (mostly done in `pipeline/music.py` from us-6, but no dedicated route or UI flow)
- 36: Frontend Music player with waveform — DONE in us-6 `MusicPlayer.tsx`
- 37: Backend Express endpoints (song / practice / reflection) — DONE in us-6 `api/express.py` or `api/insights.py:generate_express`
- 37 (cont.): Frontend Settings page export data + change password — Settings page exists from us-7, but **export action button** in the UI is missing. `GET /api/export` endpoint is wired, but no UI calls it.
- 38: Backend image upload + OCR — DONE in us-2 `pipeline/ocr.py`
- 39: Frontend image capture/upload in Capture page — `CapturePage.tsx` has the file input but the offline branch (B11) is in syncManager only; **no end-to-end UI test of image capture**
- 40: E2E + perf optimization — NOT STARTED

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
- PERF-14: APScheduler `BackgroundScheduler` + `asyncio.run()` creates a second event loop per job (relevant only when scheduler is enabled — see P1)
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
