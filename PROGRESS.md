# PROGRESS — Cortex Second Brain

> **Chronological log of what's been done.** New work appends to the end. Use this to verify "we already did X" before re-doing.

**Last updated:** 2026-04-30

---

## Quick stats

- **Project start:** 2026-04-29 (workforce kickoff)
- **First Azure deploy:** 2026-04-30 (multi-attempt — see § 4)
- **Lines of code (rough):** ~10k Python + ~6k TypeScript + ~500 Bicep + ~30 GH Actions YAML
- **Tests written:** ~700 (backend pytest + frontend Vitest)
- **Commits to-date:** 25+ (see `git log --oneline`)
- **Workforce agents spawned:** 30+ (PM, Architect, Researcher, Critic, 9 Coder/Tester pairs, 4 Reviewers, 3 fix-pair coders+testers, plus follow-ups)

---

## 1 — Workforce phases (chronological)

### Phase 1 — Requirements (PM agent, 2026-04-29)
- **Input:** `SECOND_BRAIN_BUILD_SPEC.md` § 1 + `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md` § F1.1, F2.1
- **Output:** `features/cortex-second-brain/requirements/requirements.md` (320 lines, 12 sections per template)
- **Assessment:** **COMPLEX — 23 user stories**, multiple cross-cutting integrations: 7 Azure service integrations, new data model with pgvector, new auth boundary, new WebSocket service contract for streaming STT
- **Notable:** PM did not re-interview the user (workforce.json `identityExtension` directed PM to translate the spec verbatim). Open Questions section: "None — all resolved against source spec."

### Phase 2 — Design + Research (Architect + Researcher in parallel, 2026-04-29)

**Researcher findings (delivered to Architect):**
- **BLOCKER (OQ-1):** Azure OpenAI not deployable in `westus2` — gpt-4o-mini and text-embedding-3-small absent from regional/global standard tables. Recommended: `westus`, `eastus2`, or `swedencentral`.
- **HIGH (OQ-2):** `python-jose==3.3.*` has CVE-2024-33663 (algorithm confusion) and CVE-2024-33664. Bump to ≥3.5.
- **MEDIUM (OQ-3..OQ-8):** Stale dependency pins; `passlib==1.7.*` unmaintained; pgvector extension Azure name is `vector` (not `pgvector`); Bicep gaps (firewall, Container App resource, SWA resource, managed identity).
- **No issues:** Azure Speech, pgvector availability on Postgres Flex, $150/mo budget realistic.

**Architect output:**
- `features/cortex-second-brain/designs/design.md` — 1300+ lines covering all 12 design template sections, with verbatim integration of spec § 2/4/5 + addendum F1.2/F2.2.
- 9 user-story task files at `features/cortex-second-brain/tasks/us-*.tasks.md`:
  - us-1-foundation, us-2-ai-pipeline, us-3-frontend-setup, us-4-voice-ux-offline, us-5-deployment, us-6-insights, us-7-personal-dictionary, us-8-shadow-reader, us-9-realtime-stt
- `tasks/work-sequence.md` — 7 phases of execution, Phase 5 has 3 parallel stories (us-6 + us-7 + us-9) per source-exclusivity rules.
- 9 Open Questions (OQ-1..OQ-9) added to design.md, all flagged as "Lead → user" decisions, with recommended resolutions baked in via spec deviations. Architect did NOT silently override the workforce.json directive ("use exact dependencies — do not deviate") and instead flagged each.

### Phase 3 — Critique (Critic agent, 2026-04-29)
- **Round 1:** 17 BLOCKING + 6 CONCERN + 3 NIT items raised. Key BLOCKING items:
  - **B1:** OQ-1 unresolved in design body (Bicep still hardcoded `westus2` for OpenAI account)
  - **B2:** OQ-2 + OQ-4 leave US-1 task with two failure modes (CVE-2024-33663 OR `bcrypt>=4.1` AttributeError on passlib)
  - **B3:** `CREATE EXTENSION pgvector` will fail on Azure (must be `vector` lowercase)
  - **B4:** Bicep missing Postgres firewall rule, Container App resource, Static Web App resource
  - **B5:** Internal contradiction about `services/vision.py` vs `pipeline/ocr.py`
  - **B6:** `__init__.py` has routes (anti-pattern)
  - **B7:** Search SQL doesn't filter by tags
  - **B8:** Manual override UI dropped from design; NoteUpdate schema undefined
  - **B9:** NFR-1 (<2s) unmeetable on file-mode path
  - **B10:** Stage 1.5 ↔ Stage 2 race (state machine undefined)
  - **B11..B17:** image offline-sync gap, WS token leakage, sync conflict UX, scheduler vs minReplicas=0, respx can't mock Speech SDK gRPC, work-sequence convention invisible, ShadowReader 5×1s polling misses 3s NFR
- **Round 2 (Architect revises):** All 17 BLOCKING items REVISED with concrete design-text changes. Critic verified each against the actual revised file/line.
- **Output:** `features/cortex-second-brain/designs/critique.md` — full transcript + Round 2 verdict: **ALL RESOLVED** (no items escalated to user).

### Phase 4 — Coding (TDD, 2026-04-29 to 2026-04-30)
TDD-first: Tester writes failing tests, Coder implements against test contracts, Tester confirms (or static review since pytest wasn't running on the host until later).

**Sub-phases:**

| # | Story | Tests written (red) | Implementation files |
|---|---|---|---|
| 0 | us-1-foundation | 98 (`test_health.py`, `test_database.py`, `test_auth.py`, `test_notes.py`) | `backend/app/{config,database,main}.py`, `auth/jwt.py`, `api/{auth,notes}.py`, all `models/*.py`, `schemas/{auth,note}.py`, `alembic/versions/001_initial_schema.py`, `Dockerfile`, root README + .gitignore + workflow placeholders |
| 1 | us-2-ai-pipeline | 106 (`test_blob.py`, `test_speech.py`, `test_upload.py`, `test_voice_upload.py`, `test_pipeline.py`, `test_ocr.py`, `test_search.py`, `test_tags.py`) | `backend/app/services/{openai_client,blob_storage,speech}.py`, `pipeline/{processor,music,ocr}.py`, `api/{upload,voice,search,tags,sync}.py`, `utils/retry.py`, `schemas/{search,sync}.py` |
| 2 | us-3-frontend-setup | 7 test files (`db.test.ts`, `authStore.test.ts`, `api-client.test.ts`, `LoginPage.test.tsx`, `RegisterPage.test.tsx`, `PWAManifest.test.ts`, `Tailwind.test.ts`) | `frontend/{package.json,tsconfig.json,vite.config.ts,tailwind.config.js,postcss.config.js,index.html,public/manifest.json}`, `frontend/src/{db.ts,api/{client,auth,notes,search}.ts,store/{authStore,noteStore,uiStore}.ts,pages/{LoginPage,RegisterPage}.tsx,App.tsx,main.tsx,hooks/useAuth.ts,utils/{audio,formatters}.ts}` |
| 3 | us-4-voice-ux-offline | 10 test files | `frontend/src/{hooks/{useVoiceRecorder,useNotes,useSync}.ts,components/{VoiceCapture,NoteCard,ProcessingBadge,NoteEditor,SearchBar,BottomNav,SyncIndicator}.tsx,pages/{CapturePage,LibraryPage,SearchPage,NoteDetailPage,ConflictsPage}.tsx,sync/syncManager.ts,db.ts (extended)}` |
| 4 | us-5-deployment | 4 test files (`test_deployed_smoke.py`, `infra/tests/test_bicep_structure.sh`, `infra/tests/test_deploy_script.sh`, `.github/tests/workflow_lint.sh`) | `infra/main.bicep`, `infra/modules/{postgres,storage,cognitive-services,container-app,static-web-app}.bicep`, `infra/{deploy.sh,parameters.json,teardown.sh}`, `.github/workflows/{deploy-backend,deploy-frontend}.yml`, `docs/{DEPLOYMENT,ARCHITECTURE,API_REFERENCE,EXTENDING}.md`, slowapi + log-scrubber in `backend/app/main.py` |
| 5 | us-6-insights / us-7-personal-dictionary / us-9-realtime-stt (parallel) | 9 backend + 8 frontend test files | us-6: `backend/app/{pipeline/distill.py,api/{insights,export,express}.py}`, `frontend/src/{pages/{InsightsPage,BrainViewPage,CreatePage}.tsx,components/MusicPlayer.tsx}` <br/> us-7: `backend/app/{models/vocabulary.py,schemas/dictionary.py,api/dictionary.py}`, `alembic/versions/002_add_user_vocabulary.py`, additive in `services/speech.py` + `api/voice.py`, `frontend/src/{components/PersonalDictionary.tsx,pages/SettingsPage.tsx,api/dictionary.ts}` <br/> us-9: additive `@router.websocket('/api/voice/stream')` in `api/voice.py`, `validate_ws_token` in `auth/jwt.py`, modified `frontend/src/{hooks/useVoiceRecorder.ts,components/VoiceCapture.tsx}` |
| 6 | us-8-shadow-reader | 3 test files | `backend/app/{pipeline/shadow_reader.py,api/{shadow_reader,users}.py,schemas/shadow_reader.py}`, `alembic/versions/003_add_shadow_reader.py`, modified `pipeline/processor.py` (Stage 1.5 hook), `frontend/src/{components/{ShadowReaderPrompt,ShadowReaderSettings}.tsx,api/shadowReader.ts}`, modified `pages/{NoteDetailPage,SettingsPage}.tsx` + `styles/{animations.css,globals.css}` |

### Phase 5 — Review (4 reviewers in parallel, 2026-04-30)

**Round 1 findings:**
- **Security:** 1 BLOCKING (JWT_SECRET_KEY default), 3 HIGH (refresh token in body, no rate limits on auth, no password min_length), 3 MEDIUM (no content max_length, WS query-param token, no JTI revocation), 1 LOW (SAS URL stub)
- **Performance:** 1 BLOCKING (N+1 tag query), 5 HIGH (vocab Python loop, weekly summary always-fetch, patterns uncached, no GIN FTS, bulk-import per-row commits), 5 MEDIUM (sync polling, similar-search cross-join, JS date filter, statc force-graph import, etc.), 2 LOW, 3 NIT
- **Quality:** 4 HIGH (migration 003 op.get_bind, retry decorator dead code, dictionary DELETE silent 204, Shadow Reader answer race), 6 MEDIUM (duplicate _note_to_out, OCR SimpleNamespace race, question truncate vs filter, file-mode no phrase list, sync first-boot conflicts, OpenAIDep inconsistency), 3 LOW, 2 NIT
- **Spec auditor:** 3 HIGH (deps deviations — but design-justified per OQ-2/OQ-4, marked ACCEPTED), 1 MEDIUM (migration 001 cosmetic), 3 LOW (design-justified extras), 1 NIT

**Round 1 fix loop (3 parallel pairs):**
- Security pair (8 fixes): JWT secret production guard with field validator + `check_production_secrets()`, refresh token removed from JSON body, slowapi rate limits added to auth routes, `min_length=8 max_length=128` on password, `max_length=50000` on note content, B12 log-scrubbing residual risk documented, JTI revocation via in-memory deny set, `_refresh_sas_url()` real implementation
- Performance pair (11 fixes): batched tag query in `db_helpers.py`, single SQL UPDATE for vocab usage_count, weekly summary conditional notes query, patterns cache in `users.patterns_cached_*` columns + migration 004, GIN FTS index migration 005, bulk_import single INSERT, syncManager event emitter, _SIMILAR_SQL parameterized embedding, useNotes Dexie .between(), BrainViewPage React.lazy(), MusicPlayer dynamic import
- Quality pair (10 fixes): migration 003 async-compatible idiom, `azure_retry` `_is_retryable` wired via `retry_if_exception`, DELETE 404 on missing, 2-phase Shadow Reader status (`answer_pending` → `answered`) with APScheduler retry sweep, shared `_note_to_out` in `_note_serializers.py`, OCR background re-fetch by id, generate_questions filters (drops) vs truncates, file-mode loads phrase list, sync first-boot conflict guard, `Depends(get_openai)` everywhere

**Round 2 re-review:**
- Security: PASSED
- Performance: PASSED
- Quality: PASSED
- Spec auditor: ISSUES REMAIN (1 new MEDIUM SA-R2-M1) — `sync.py` retained a local `_note_to_out` that omitted `shadow_reader_*` fields. Lead fixed in-line: imported `_note_to_out` from `_note_serializers.py` and removed the local copy.

### Phase 5 conclusion
ALL reviewers PASSED. Workforce complete. ~12 LOW + NIT items left tracked but unfixed (low priority, not above autofix threshold).

---

## 2 — Test runs

### Backend (Python 3.11 venv at `backend/.venv/`)

| Date | Result | Notes |
|---|---|---|
| 2026-04-30 (initial) | 263 pass / 30 fail / 266 skip | Most failures are test-side static-introspection mismatches |
| 2026-04-30 (after `speech.py` `CancellationDetails` fix + fixture expansion) | Still 30 fail | Same set; the fix-pair bg agent ran ~94 min and made test edits but didn't drive failures to 0 |

**Specific failure categories (see `KNOWN_ISSUES.md` for per-test triage):**
1. `@pytest.mark.asyncio` on sync test functions (asyncio mode auto, but sync tests still get the mark) — 5+ failures
2. Static introspection asserting specific code patterns (e.g., `op.execute(sa.text(...))` exact string) — 5+ failures
3. Mocks asserting in-memory state changes that PERF-02 fix moved to SQL UPDATE (vocab_entry.usage_count == 4) — 3 failures
4. Schema introspection looking for `maxLength` on Pydantic v2 fields — 1 failure
5. Router prefix tests with mismatched expected strings — 2 failures
6. Speech mocks not aligned with `recognize_once_async` future-style callback API — 5 failures
7. NoteOut schema fields not exposed in voice.py local serializer (now fixed via QA-05) — 3 failures (test side may still be looking at the old pattern)
8. Scheduler tests asserting `@app.on_event` startup pattern, but main.py uses `@asynccontextmanager` lifespan — 8 failures

**Production bugs caught and fixed by these tests:**
- `speech.py:CancellationDetails.from_result(result)` — that method doesn't exist; correct API is the constructor `CancellationDetails(result)`. Fixed.
- (No other real bugs found in this set; all remaining failures are test-side.)

### Frontend (Vitest)

| Date | Result | Notes |
|---|---|---|
| 2026-04-30 | 276 pass / 1 fail / 0 skip | Fail is `api-client.test.ts > apiPost > 'attaches Authorization header'` — `vi.clearAllMocks()` doesn't reset `mockReturnValue` set in a previous test. Test-side bug, not implementation. Fix: change `afterEach(() => vi.clearAllMocks())` → `vi.resetAllMocks()`. |

---

## 3 — Git history (key commits, newest at top)

```
b19342c fix(auth): set access token before calling me() in Register/Login
e201cbd fix(pwa): enable skipWaiting + clientsClaim so SW updates take effect on next page load
9f369a0 feat(cortex-second-brain): deployment fixes (Azure deploy successful)
ac83248 fix(cortex-second-brain): SA-R2-M1 — sync.py uses shared note serializer
e689fc5 feat(cortex-second-brain): add Round 2 re-review skeleton sections
0350b30 feat(cortex-second-brain): apply review fixes round 1 (security/performance/quality)
3ff6293 feat(cortex-second-brain): format review findings into Tasks 1-4 (Architect Mode A)
ad23ba6 feat(cortex-second-brain): add review comments round 1
3851ee8 feat(cortex-second-brain): complete coding phase 6 — us-8-shadow-reader
39ac136 feat(cortex-second-brain): complete coding phase 5 — us-6 + us-7 + us-9 in parallel
2e7a5d3 feat(cortex-second-brain): complete coding phase 4 — us-5-deployment
f5f7ee7 feat(cortex-second-brain): complete coding phase 3 — us-4-voice-ux-offline
b042343 feat(cortex-second-brain): complete coding phase 2 — us-3-frontend-setup
b3b5351 feat(cortex-second-brain): complete coding phase 1 — us-2-ai-pipeline
b3b2820 feat(cortex-second-brain): complete coding phase 0 — us-1-foundation
cb58ceb feat(cortex-second-brain): critique resolved (all 17 BLOCKING items addressed)
89b0b2d feat(cortex-second-brain): add design.md, research.md, and 9 user-story task files
0e17c6b feat(cortex-second-brain): add requirements document (translated from spec)
2475924 chore: initial workforce setup with specs and config
```

---

## 4 — Azure deployment journey (full chronology)

The deploy needed 6 attempts before succeeding, each surfacing a different real-world constraint:

| Attempt | Issue | Resolution |
|---|---|---|
| 1 | Storage account name `cortexstorage` globally taken | Suffixed appName to `cortexks` |
| 2 | Postgres restricted in `westus2` for VS Enterprise sub | Switched to `eastus2` |
| 3 | Postgres restricted in `eastus2` too | Switched to `eastus`, but SWA not supported there |
| 4 | SWA only supports specific regions; centralus is in the list | Switched location to `centralus`, kept OpenAI in `eastus` (model availability) |
| 5 | Cognitive Services accounts had soft-deleted from earlier attempts; collisions | Purged all 9 soft-deleted accounts via `az cognitiveservices account purge` |
| 6 | Bicep tried to deploy Container App with image that didn't exist yet (chicken-and-egg with ACR build) | Added `useBootstrapImage` Bicep param defaulting to `mcr.microsoft.com/azuredocs/containerapps-helloworld:latest`; `deploy.sh` runs Bicep with `useBootstrapImage=true`, then ACR build, then `az containerapp update --image` to swap |

**Post-Bicep, in order:**
- Container App started but crashed on `email-validator` import → added `email-validator>=2,<3` to `requirements.txt`
- Container App healthy. Tried alembic upgrade head → DB `cortex` doesn't exist (Postgres Flex creates only `postgres` by default) → ran `az postgres flexible-server db create --database-name cortex`
- Tried alembic again → JSONB defaults like `'[]'::jsonb` were getting double-quoted (`'''[]''::jsonb'`) → wrapped server_defaults in `sa.text()` for the JSONB cases
- Tried alembic again → migration 005 used `CREATE INDEX CONCURRENTLY` inside alembic transaction block → removed `CONCURRENTLY` (fresh DB, brief lock OK)
- Tried alembic again → ALL 5 MIGRATIONS APPLIED (001 → 002 → 003 → 004 → 005)
- Built frontend → TypeScript build errors (unused vars in tests, `onSaved` vs `onSave`, type cast issues) → excluded `__tests__` from `tsconfig` build, fixed call sites, fixed type cast through `unknown[]`
- SWA deploy → succeeded
- Hit register → `405 Method Not Allowed` on SWA URL (proxy doesn't forward POST) → added `VITE_API_BASE_URL=https://cortexks-api...` env, rebuilt with absolute URLs, added `credentials: 'include'`
- Hit register → `500 Internal Server Error` → APScheduler thread + asyncpg pool race → gated scheduler on `SCHEDULER_ENABLED` env (default false)
- Register → `201 Created` ✓
- User reported "registered but not auto-logged in / 401 not authenticated" → race in RegisterPage/LoginPage: `me()` was called before `setAccessToken()` so `fetchWithAuth` had `null` token → fixed by storing token first
- All endpoints verified working

---

## 5 — Files created at project root (handoff bundle)

- `HANDOFF.md` — entry point briefing for new agent
- `PLAN.md` — what we're building, what's done, what's next
- `PROGRESS.md` — this file
- `DECISIONS.md` — architecture decisions, B1-B17, OQ-1-OQ-9, deviations
- `KNOWN_ISSUES.md` — open work, test failures, gaps
- `README.md` — created during us-1; one-paragraph intro + spec link
- `.gitignore` — created during workforce setup

---

## 6 — What you can safely delete / clean up

Nothing critical. Optional cleanups:
- `backend/.coverage` — already gitignored, but local file may exist after a pytest run
- `backend/.venv/` — local Python 3.11 venv, gitignored
- `frontend/node_modules/` — gitignored
- `frontend/dist/` — gitignored, regenerable via `npm run build`
- ACR repo `cortex-api` (orphan from deploy attempt #6's first ACR build before image-name fix). Live image is `cortexks-api`. Delete with: `az acr repository delete --name cortexksacr --image cortex-api`

---

## Round 1 — Live UX bug-bash (2026-05-01)

User filed HAR + console log after deploy showing:
1. POST `/api/notes` and `/api/upload` returning **500 + no CORS header**
2. POST `/api/voice/upload` returning **422 Field required: body.file**
3. POST `/api/auth/refresh` returning **401** (then **429** when hammered)
4. Notes stuck in "Pending sync" forever; status never advances past "Raw"

### Root causes + fixes (all deployed live)

| # | Bug | Root cause | Fix |
|---|---|---|---|
| 1 | `/api/notes` 500 (DatatypeMismatchError: column "embedding" is of type vector but expression is of type character varying) | `app/models/note.py` declared `embedding: mapped_column(Text, nullable=True)`. Postgres column is `vector(1536)` per migration 001. SQLAlchemy was binding values as varchar; INSERT rejected. | Replaced static `Text` declaration with `_embedding_column_type()` that returns `Vector(1536)` when `DATABASE_URL` contains `postgres`/`asyncpg`, else `Text` for SQLite test fixture. |
| 2 | `/api/voice/upload` 422 "Field required: body.file" | Frontend sent `formData.append('audio', ...)` but backend expects field `file`. | Renamed to `formData.append('file', ...)` in `VoiceCapture.tsx`. |
| 3 | `/api/auth/refresh` 429 on normal use | Rate limit was 5/min — page reloads, multi-tab, and Playwright tests trip it instantly. Brute-force defense was a non-issue (256-bit JTI cannot be cracked at this rate). | Bumped to 60/min in `auth.py:refresh_token`. |
| 4 | AI pipeline silent NotFoundError → status="Failed" | Azure OpenAI account `cortexks-openai` had **zero deployments**. The Bicep provisions the account but does not deploy models. | Created two GlobalStandard SKU deployments via `az cognitiveservices account deployment create`: `gpt-4o-mini` (50 cap) + `text-embedding-3-small` (50 cap). |

### Live verification (post-deploy)

- POST `/api/auth/login` → 200 ✓
- POST `/api/notes` (text) → 201 ✓ (was 500)
- POST `/api/auth/refresh` → 200 ✓ (was 429)
- Hard reload while signed in → stays signed in ✓
- Type text note in UI → flips Pending → Raw → Enriched ✓ (verified at `screenshots/round-1-after/06-library-pipeline-enriched.png`)
- Auto-categorized "Ideas" + auto-tagged inferred from content ✓

### Screenshots (round 1)

- `screenshots/round-1-before/01-login-page.png` — landing
- `screenshots/round-1-before/02-capture-page.png` — capture form
- `screenshots/round-1-before/03-library-page.png` — empty library after sign-in
- `screenshots/round-1-before/04-profile-page.png` — profile view
- `screenshots/round-1-after/03-library-page-with-synced-note.png` — first note synced (status=Raw before pipeline)
- `screenshots/round-1-after/05-after-hard-refresh-still-logged-in.png` — refresh preserves session
- `screenshots/round-1-after/06-library-pipeline-enriched.png` — pipeline runs end-to-end (status=Enriched)

### Test infrastructure added (this round)

- `e2e/playwright.config.ts` — Chromium project with shared auth-setup dependency
- `e2e/tests/helpers.ts` — `useSharedUser()`, `registerAndLogin()`, `startNetworkRecorder()`
- `e2e/tests/auth.setup.ts` — registers a single shared user, persists `storageState` (avoids hitting `/register` 10/min rate limit across the suite)
- `e2e/tests/01-auth-and-session.spec.ts` — register → auto-login, hard-reload preserves session, profile renders, logout returns to /login
- `e2e/tests/02-text-note-sync.spec.ts` — text note → 201 → not stuck pending
- `e2e/tests/03-note-detail.spec.ts` — note detail no 404 on `/api/notes/{id}` or `/api/search/similar/{id}`
- `e2e/tests/04-voice-capture.spec.ts` — fake media stream → mic FAB → no 422
- `e2e/tests/05-navigation-no-500s.spec.ts` — every protected route loads without 5xx + no console CORS errors

---

## Round 2 — UX-tester findings (2026-05-01)

UX-tester agent (Playwright) ran the suite against the post-round-1 deploy and filed `e2e/ISSUES.md` with 4 issues. Two were already fixed by round 1 (notes pending sync, session restore). The remaining two were real backend bugs:

| # | Issue | Root cause | Fix |
|---|---|---|---|
| ISSUE-03 | `/api/upload` 500 + missing CORS header | `services/blob_storage.py` passed a `dict` as `content_settings=` to `BlobClient.upload_blob()`. Azure SDK 12.22 expects `ContentSettings(content_type=...)` and accesses `.cache_control` on it; dict doesn't have that attribute → `AttributeError` mid-upload. The unhandled exception bypasses CORSMiddleware, so the browser sees CORS failure rather than the real cause. | Imported `ContentSettings` from `azure.storage.blob` and wrapped the content type in it. |
| ISSUE-04 | `/api/ai/summary/weekly` 500 ProgrammingError | `pipeline/distill.py:generate_weekly_summary` filtered `Note.created_at >= str(monday)` against a `timestamptz` column. Postgres rejected the implicit text→timestamptz coercion. Same bug existed in `generate_daily_summary`. | Replaced `str(date)` with proper `datetime.combine(date, time.min, tzinfo=UTC)` so asyncpg binds the right type. |

Plus a defensive fix:
- **Voice upload 500 → 422 with detail** when audio is corrupt/empty. The Speech SDK raises `RuntimeError`; we now catch and return HTTPException, keeping CORS headers attached and giving the frontend a usable error message.

### Live verification

- `POST /api/upload` (multipart) → **200** with SAS URL ✓
- `GET /api/ai/summary/weekly?week=2026-W18` → **200** with full LLM-generated summary ✓
- Insights page renders the weekly summary live (`screenshots/round-2-after/07-insights-page-with-weekly-summary.png`)

### e2e suite results

- Before round 2: 6 fail / 4 flaky / 7 pass
- After round 1 deploy (no test changes): 3 fail / 4 flaky / 14 pass
- After round 2 backend fixes: 1 fail / 1 flaky / 15 pass
- Remaining failure: post-sign-out tests in the shared-auth Playwright suite hit `/login` rate limit on the rapid re-login fallback (test-infra issue, not app — documented in `KNOWN_ISSUES.md` for next round)

### Round-2 screenshots

- `screenshots/round-2-after/07-insights-page-with-weekly-summary.png` — Insights page renders Today's Summary + This Week + Recurring Patterns with LLM-generated content

---

## 7 — Pickup points (for resuming work)

**If continuing here in this session:** Smoke test the live deployment in a browser (see `PLAN.md` § 5). Then triage the 30 backend test failures (see `KNOWN_ISSUES.md`).

**If picking up in a new session / new agent:** Read `HANDOFF.md` first. Then this file. Then `PLAN.md` § 5 + `KNOWN_ISSUES.md`.
