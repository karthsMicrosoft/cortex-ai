# HANDOFF — Cortex Second Brain

> **Read this first.** This document briefs an incoming agent (Claude / Copilot / Aider / human) on the state of the project so work can resume without context loss.

**Last updated:** 2026-06-05 (Round 39 SHIPPED: deadline extractor handles "today at TIME" + LLM gets current-date context + CORTEX_DEFAULT_TZ=America/Los_Angeles live in production)
**Status:** Live on Azure. Phases 1–7 shipped. Brain View now 2D (Round 27) with title-as-label + mobile long-press (Round 34). Canvas feature gated behind `VITE_FEATURE_CANVAS` env var (Round 28). Per-user local data isolation enforced (Round 29). Voice-note audio playback CSP fixed (Round 30) + Azure Blob CORS rules added so iOS Safari can also play audio (Round 31). Bulk import script for Google Keep + Notion shipped (`docs/IMPORT.md`). Composite-scored auto-linking with phrase signal + two-path qualifier (Round 32–33 / §§ 22ar–22as). Pipeline now auto-generates meaningful titles for new notes (Round 34 / § 22at). **Round 35: full task model on notes (due_at / done_at / priority / recurring), hybrid save-first deadline extraction shared between TS + Python, Azure Container Apps Job dispatcher (cron every minute), Web Push (+ ACS email fallback), Tasks page at `/tasks` gated on `VITE_FEATURE_TASKS`, editable `DeadlinePill` on NoteDetail + Library — see `docs/REMINDERS.md`. Round 37: reverted the iOS Shortcuts deep link + launcher-record toggle. Round 38: VAPID keys generated + bound to `cortexks-api` env via Container App secrets; `cortexks-reminders` Container Apps Job provisioned via `az containerapp job create` (cron `* * * * *`, entrypoint `python -m scripts.dispatch_reminders`); smoke-tested clean. User can now enable reminder notifications in Settings → Reminders on the installed PWA. ACS Email fallback still pending (operator follow-up).** Backend: **1138 tests passing**. Frontend: **943 tests passing**, 7 pre-existing failures unchanged (api-ai jsdom). TypeScript clean.

---

## 1 — Where everything is

| Artifact | Path |
|---|---|
| **Project root** | `C:\Users\karths\dev\Projects\cortex\` |
| **Original spec (canonical)** | `SECOND_BRAIN_BUILD_SPEC.md` (1857 lines) |
| **Spec addendum (Personal Dictionary + Shadow Reader)** | `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md` (1022 lines) |
| **Workforce session state** | `features/cortex-second-brain/workforce.md` |
| **Requirements** | `features/cortex-second-brain/requirements/requirements.md` |
| **Design + research + critique** | `features/cortex-second-brain/designs/{design,research,critique}.md` |
| **9 user-story task files** | `features/cortex-second-brain/tasks/us-*.tasks.md` |
| **Review findings + fix tasks** | `features/cortex-second-brain/tasks/review-comments.tasks.md` |
| **Backend** (Python 3.11, FastAPI, async SQLAlchemy, asyncpg, pgvector) | `backend/` |
| **Frontend** (Vite + React 18 + TS + Tailwind + Dexie + PWA) | `frontend/` |
| **Infra** (Bicep + 5 modules + deploy.sh) | `infra/` |
| **Docs** (DEPLOYMENT, API_REFERENCE, ARCHITECTURE, EXTENDING) | `docs/` |
| **GitHub Actions** | `.github/workflows/` |
| **Workforce config** | `.claude/workforce.json`, `.claude/agents/reviewer-spec-auditor.md`, `.claude/settings.local.json` |

**Companion docs at project root:**
- `PLAN.md` — what we're building, what's done, what's left
- `PROGRESS.md` — chronological log + by-phase status
- `DECISIONS.md` — architecture decisions (B1–B17, OQ-1–OQ-9, deviations from spec)
- `KNOWN_ISSUES.md` — open bugs, test gaps, unfinished items
- `HANDOFF.md` — this file

---

## 2 — Live deployment (Azure)

| Resource | Endpoint / Identifier |
|---|---|
| **Frontend (PWA)** | https://gentle-river-06c1e4e10.7.azurestaticapps.net |
| **Backend API** | https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io |
| **API docs (Swagger)** | https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/docs |
| **Subscription** | Visual Studio Enterprise (`85f6cb53-9eec-43f1-84c3-bf701dcd4048`) |
| **Resource group** | `cortex-rg` (region: **`centralus`**, NOT westus2 — see DECISIONS.md) |
| **App name prefix** | `cortexks` (suffixed because `cortex` storage name was globally taken) |
| **Postgres Flexible Server** | `cortexks-db.postgres.database.azure.com` |
| **Database name** | `cortex` (created post-Bicep with `az postgres flexible-server db create`) |
| **DB admin user** | `cortexadmin` (password: stored in Container App secret `database-url`) |
| **Storage account** | `cortexksstorage` (blob container: `cortex-media`) |
| **ACR** | `cortexksacr.azurecr.io` (image: `cortexks-api:latest`) |
| **Azure OpenAI** | `cortexks-openai` in **`eastus`** (NOT centralus — model availability) |
| **Azure Speech** | `cortexks-speech` in `centralus` |
| **Azure AI Vision** | `cortexks-vision` in `centralus` |
| **Container App** | `cortexks-api` (centralus, 0.5 vCPU / 1 GB, minReplicas=1, maxReplicas=3) |
| **Static Web App** | `cortexks-app` (Free SKU, centralus) |

### Secrets (Azure-managed; NEVER on disk)
The DB admin password and JWT secret were generated inline during deploy and live ONLY in the Container App secrets store. To rotate or read:
```bash
az containerapp secret list --name cortexks-api --resource-group cortex-rg --show-values
```

---

## 3 — How to resume work

### 3a. If you are a new agent picking up this project

1. **Read the order:** `HANDOFF.md` → `PLAN.md` → `PROGRESS.md` → `KNOWN_ISSUES.md` → `DECISIONS.md`
2. **Glance at:** `features/cortex-second-brain/workforce.md`, `features/cortex-second-brain/designs/design.md`, `features/cortex-second-brain/tasks/work-sequence.md`, then any one or two `us-*.tasks.md` files for context.
3. **Don't re-run the workforce.** All 5 phases (Requirements → Design → Critique → Coding → Review) have completed. Resume mode = direct fixes / new features, not multi-agent kickoff.
4. **Use the same workforce config** (`.claude/workforce.json`) only if the user asks for a NEW feature pass (e.g., "add Phase 3 features"). For bugfixes, work directly.

### 3b. Common pickup tasks (in priority order — refreshed 2026-05-28)

| Priority | Task | Where to start |
|---|---|---|
| **P0 — NEXT** | _(none currently — Rounds 27 + 28 + 29 + 30 + 31 closed)_ | — |
| ✅ Round 31 | ~~iOS Safari voice playback still broken~~ ✅ Round 31 (2026-05-31) — after Round 30 CSP fix, iPhone Safari still failed. Root cause: Azure Blob storage account had no CORS rules; wavesurfer.js + Safari's strict cross-origin media policy require `Access-Control-Allow-Origin`. Fixed live with `az storage cors add`, codified in `infra/main.bicep` + `infra/modules/storage.bicep`, pinned with 13 bicep guard-rail tests. | `PROGRESS.md` Round 31, `DECISIONS.md` § 22aq |
| ✅ Round 30 | ~~Voice-note playback failed~~ ✅ Round 30 (2026-05-30) — CSP omitted `media-src` (fell back to `default-src 'self'` → blocked Azure Blob SAS audio URLs) and omitted blob.core in `connect-src` (broke WaveSurfer fetch). Added explicit media-src + connect-src additions + blob: scheme in img-src for offline previews. 5 new pinning tests. | `PROGRESS.md` Round 30, `DECISIONS.md` § 22ap |
| ✅ Round 29 | ~~Cross-user library leak~~ ✅ Round 29 (2026-05-30) — sign out of A, sign in as B left A's notes visible. New `clearLocalUserData()` wipes Dexie + Workbox caches on signOut (primary defense) and on user-change detection in SessionGate (defense-in-depth). 17 new tests | `PROGRESS.md` Round 29, `DECISIONS.md` § 22ao |
| ✅ Round 28 | ~~Hide Canvas feature~~ ✅ Round 28 (2026-05-29) — `VITE_FEATURE_CANVAS` env var (default off) gates Canvas tab + routes + "Open as Canvas" + "Add to Canvas". Implementation kept; flip env to re-enable | `PROGRESS.md` Round 28, `DECISIONS.md` § 22an |
| ✅ Round 27 | ~~Brain View 3D → 2D rewrite~~ ✅ Round 27 (2026-05-29) — replaced react-force-graph-3d + Three.js + GLB brain mesh with react-force-graph-2d + SVG brain outline. Three.js deps removed, `brain.glb` deleted, 24+2 Brain View tests + TypeScript clean | `PROGRESS.md` Round 27, `DECISIONS.md` § 22am |
| **P0** | ~~End-to-end smoke test in a real browser~~ ✅ Round 9 (2026-05-06) | Confirmed: auth/refresh, capture (text + AI pipeline), library, insights (patterns only), sync. See PROGRESS § Round 9. |
| **P0** | ~~Bootstrap Azure Key Vault for prod-grade secret rotation~~ ✅ Round 9 (2026-05-06) | `cortexks-kv` live; container app secrets reference KV via managed identity. See `docs/DEPLOYMENT.md` § "Key Vault — secret rotation" |
| **P0** | ~~Container App auto-restart + health-check alerts~~ ✅ Round 13 (2026-05-07) — auto-restart already wired via Bicep probes; added 3 Azure Monitor alerts (restart spike + 5xx rate + synthetic /api/health ping) routing to `karths@microsoft.com` via shared Action Group `cortex-alerts-ag` | `docs/DEPLOYMENT.md` § "Health-Check Alerts" |
| **P1** | ~~Move APScheduler distill cron OUT of Container App~~ ✅ Round 9 (2026-05-06) — **removed entirely** per user decision; daily/weekly summary UI + endpoints + table also dropped (alembic 007) | KNOWN_ISSUES.md § "P1 — APScheduler removed entirely" |
| **P1** | ~~Migrate refresh token back to first-party cookies~~ ⏸ Deferred 2026-05-07 (Round 14) — explicit user decision: cost ($12/yr domain or $108/yr SWA Standard) doesn't justify the work; localStorage workaround stays as accepted MVP trade-off (DECISIONS § 22v threat-model unchanged) | `DECISIONS.md` § 22ad |
| **P1** | ~~Wire GitHub Actions deploy secrets so push-to-main auto-deploys~~ ✅ Round 11 (2026-05-06) — OIDC-federated `cortex-github-actions` AAD app + 7 repo secrets; both workflows green on push and `workflow_dispatch` | KNOWN_ISSUES.md § "P1 — GitHub Actions deploys wired" |
| **P1** | ~~Triage 30 backend test-side failures~~ ✅ Round 12 (2026-05-07) — backend now 626/0/6 = **100%** | KNOWN_ISSUES.md § "Backend + frontend test failures" |
| **P2** | ~~Frontend `api-client.test.ts` mock-isolation flake~~ ✅ Closed PR #14 (2026-05-07) — beforeEach restores `useAuthStore.getState` mock state | n/a |
| **P2** | ~~Spec-auditor SA-M1 cosmetic migration cleanup~~ ✅ Round 14 (2026-05-07) — collapsed 3-statement embedding column dance into a single `ADD COLUMN`; +2 static tests; backend now 628/0/6 | `KNOWN_ISSUES.md` § "✅ P2 — Spec auditor SA-M1" |
| **P3** | ~~Phase 3 scope — Express UI polish, Settings export, image-capture UI, voice answer for Shadow Reader, E2E + perf~~ ✅ Round 15 (2026-05-08) — 6 PRs landed (#22-#27): Settings export+change-password, Express CreatePage polish, Image capture preview/resize, Lazy-load route splitting (-58 KB main bundle), Shadow Reader voice answer (FR-8.4), E2E Playwright runner + nightly cron workflow. E2E pass: 17/17 against live | `PROGRESS.md` § 15 |
| **P3** | ~~Phase 4 — AI Search & Synthesis (NotebookLM-style RAG)~~ ✅ Round 16 (2026-05-11) — 10 PRs landed (#29-#41): RAG `POST /api/ai/answer` with citations, Ask UI page (`/ask`), search filter sidebar, NDJSON streaming via fetch ReadableStream, multi-turn chat (client-side history). 75-note seed dataset for `karths@microsoft.com` + backfill_embeddings.py. 36 backend + 73 frontend tests added. | `PROGRESS.md` § 16 |
| **P3** | ~~Phase 5 — Web Clipper / External Ingest (PWA share_target, URL import with SSRF hardening, PDF chunking, Chrome MV3 extension with limited-scope token)~~ ✅ Round 17 (2026-05-11) — 6 PRs landed (#43-#48): alembic 008 source provenance, share_target + /share, /api/import/url, PDF ingestion + chunking, Capture URL tab, MV3 extension + clip-token | `PROGRESS.md` § 17 |
| **P3** | ~~Phase 6 — Knowledge Graph + Bidirectional Linking (note_links triple-uniqueness, title/aliases, backlinks, manual links, wiki-link `[[Title]]` parsing + backfill)~~ ✅ Round 18 (2026-05-11) — 8 PRs landed (#50-#57): foundation (alembic 009 + 010), backlinks API+UI, Brain View polish, manual links, title editing, wiki-link parser. **Closes the 4-feature initiative.** | `PROGRESS.md` § 18 |
| **P4** | Phase 7 — Visual thinking (Heptabase / Milanote canvas with note cards + drawn arrows). Acknowledged in Round 16 plan; deferred. Will get its own audit when prioritized. | session `plan.md` |
| **P3** | ~~JTI revocation in Redis or DB table (in-memory now; lost on Container App restart)~~ ✅ Round 19 (2026-05-12) — alembic 011 revoked_jtis table + two-tier (cache + DB) revoke; persists across restarts | `KNOWN_ISSUES.md` § "JTI revocation" |
| **P3** | ~~`/api/auth/logout` server-side revoke (currently client-only)~~ ✅ Round 19 (2026-05-12) — POST /api/auth/logout requires auth, revokes both access + refresh JTIs; logout button now visible in AppHeader + Settings + Profile | `KNOWN_ISSUES.md` § "/auth/logout" |
| **P4** | ~~Strict CSP header~~ ✅ Round 20 (2026-05-13) — PR #69: backend `default-src 'none'`, frontend strict policy with API-origin connect-src allowlist + `frame-ancestors 'none'` + `upgrade-insecure-requests` + Permissions-Policy. Closes the localStorage XSS-readability gap from § 22v. | `DECISIONS.md` § 22aj |
| **P4** | ~~Observability gaps (App Insights traces, custom RAG cost metrics)~~ ✅ Round 20 (2026-05-13) — 3 PRs (#66-#68): App Insights tracing wired, RAG cost counters emit on every LLM call, Workbook + cost-rate alert runbook. App Insights env var live. | `PROGRESS.md` § 20 + `docs/observability.md` |
| **P4** | KMS-grade rotation for `JWT_SECRET_KEY` | `PLAN.md` § 6 P4 |

### 3c. To redeploy from scratch

See `infra/deploy.sh` and `docs/DEPLOYMENT.md`. Tl;dr:
```bash
cd /c/Users/karths/dev/Projects/cortex
export DB_ADMIN_PASSWORD=$(python -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(32)))")
export JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(64))")
export RESOURCE_GROUP=cortex-rg LOCATION=centralus APP_NAME=cortexks
bash infra/deploy.sh
```
Note: `parameters.json` currently uses inline-secrets mode. For prod with KV, swap with `parameters.keyvault-template.json` after bootstrapping a Key Vault.

### 3d. To rebuild + redeploy backend only (after a code change)

```bash
PYTHONIOENCODING=utf-8 az acr build --registry cortexksacr --image cortexks-api:latest --no-logs ./backend
PYTHONIOENCODING=utf-8 az containerapp update --name cortexks-api --resource-group cortex-rg \
  --image cortexksacr.azurecr.io/cortexks-api:latest \
  --revision-suffix "v$(date +%s)"
```
Wait ~30s. Verify with `curl https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/api/health`.

### 3e. To rebuild + redeploy frontend only

```bash
cd frontend
npm run build
cp public/staticwebapp.config.json dist/staticwebapp.config.json
cd ..
SWA_TOKEN=$(az staticwebapp secrets list --name cortexks-app --resource-group cortex-rg --query "properties.apiKey" -o tsv)
npx --yes @azure/static-web-apps-cli@latest deploy ./frontend/dist --deployment-token "$SWA_TOKEN" --env production --no-use-keychain
```
PWA `skipWaiting: true` means clients get the new bundle on the next page load. No hard-refresh needed.

### 3f. To run alembic migrations against the live DB

```bash
PYTHONIOENCODING=utf-8 az containerapp exec --name cortexks-api --resource-group cortex-rg --command "alembic upgrade head"
```

---

## 4 — Tech stack at a glance

**Backend:**
- Python 3.11 (Docker base: `python:3.11-slim` + ffmpeg)
- FastAPI 0.115 + uvicorn 0.30 + slowapi 0.1 (rate limiting)
- SQLAlchemy 2.0 async + asyncpg 0.29 + alembic 1.13 + pgvector 0.3
- python-jose 3.5+ (JWT, NOT 3.3 — CVE) + passlib 1.7 + bcrypt 4.0.x (NOT 4.1+ — passlib incompat)
- openai 1.40 (Azure OpenAI client) + azure-cognitiveservices-speech 1.40 + azure-storage-blob 12.22 + azure-ai-vision-imageanalysis 1.0
- pydantic 2.13 + pydantic-settings 2.4 + email-validator 2.x
- tenacity 8.5 (retry decorator on Azure adapters)
- apscheduler 3.10 ~~(currently DISABLED via `SCHEDULER_ENABLED=false` env var; see KNOWN_ISSUES)~~ **REMOVED 2026-05-06** — daily/weekly distill cron functionality dropped entirely per user product decision (KNOWN_ISSUES § "P1 — APScheduler removed entirely")

**Frontend:**
- Vite 5.4 + React 18.3 + TypeScript 5.5 + Tailwind 3.4
- Zustand 4.5 (state) + Dexie 4.0 + dexie-react-hooks 1.1 (IndexedDB)
- react-router-dom 6.26
- vite-plugin-pwa 0.20 (service worker with `clientsClaim:true, skipWaiting:true`)
- react-force-graph-3d (lazy-loaded, Three.js/WebGL), wavesurfer.js 7.8 (dynamic import)
- Vitest 2 + @testing-library/react + jsdom + fake-indexeddb (tests)

**Infra:**
- Bicep ARM templates (main.bicep + 5 module files)
- Container App on Container App Environment, system-assigned managed identity, ingress `transport: 'auto'` (HTTP/1.1 + WebSocket), liveness + readiness probes on `/api/health`, CPU scaling rule
- Postgres Flexible Server B1ms (Burstable) with pgvector + uuid-ossp extensions, AllowAllAzureServicesAndResourcesWithinAzureIps firewall rule
- Static Web App Free SKU
- ACR Basic
- Storage StorageV2 LRS

---

## 5 — Critical resolutions baked into the implementation

These are the lasting answers to questions raised during the workforce. Keep them when refactoring.

| Tag | What it means | Where it lives |
|---|---|---|
| **OQ-1 / B1** | AOAI runs in `eastus`, NOT `centralus` (model availability) — separate `openaiLocation` Bicep param | `infra/main.bicep` line ~14 |
| **OQ-2 / B2** | python-jose ≥ 3.5 (CVE-2024-33663 fix) + bcrypt < 4.1 (passlib compat) | `backend/requirements.txt` |
| **OQ-5 / B4** | Postgres firewall rule `AllowAllAzureServicesAndResourcesWithinAzureIps` is in Bicep | `infra/main.bicep` |
| **OQ-7 / B4** | Container App resource is in Bicep (not just `az containerapp create` after the fact) | `infra/main.bicep` |
| **OQ-9 / B3** | `CREATE EXTENSION IF NOT EXISTS vector` (lowercase, NOT `pgvector`) — Azure allowlist requires this exact name | `backend/alembic/versions/001_initial_schema.py` |
| **B5** | OCR module lives at `pipeline/ocr.py`, NOT `services/vision.py` | `backend/app/pipeline/ocr.py` |
| **B6** | Dedicated `api/upload.py` and `api/tags.py` modules, not stuffed into `__init__.py` | `backend/app/api/` |
| **B7** | Hybrid search SQL has `tags EXISTS` subquery for tag filter | `backend/app/api/search.py` |
| **B8** | Manual override UI in NoteEditor (category, tags, mood, music_metadata) with AI-suggested badge | `frontend/src/components/NoteEditor.tsx` |
| **B9** | NFR-1 < 2s = local IndexedDB write, NOT transcript visible (transcript is US-9 streaming) | `frontend/src/components/VoiceCapture.tsx` |
| **B10** | Pipeline state machine: Stage 1 → Stage 2 → Stage 1.5 (Reflect runs AFTER Organize) | `backend/app/pipeline/processor.py` |
| **B11** | syncManager.pushChanges has imageBlob branch | `frontend/src/sync/syncManager.ts` |
| **B12** | WS token in URL query param has log-scrubbing middleware in `main.py` | `backend/app/main.py` |
| **B13** | Sync pull + ConflictsPage handle update conflicts | `frontend/src/pages/ConflictsPage.tsx` |
| **B14** | `minReplicas: 1` (cold-start avoidance — was previously kept alive for APScheduler distill, but the scheduler was removed entirely 2026-05-06; the floor stays at 1 to avoid 5–10 s scale-from-zero on free tier) | `infra/main.bicep` |
| **B15** | Test mocking: respx for HTTP-based Azure SDKs, unittest.mock for Speech SDK (gRPC) | `backend/tests/` |
| **B16** | us-7 owns NEW symbols in `services/speech.py` + file-mode `voice.py`; us-9 owns WebSocket `voice.py` route; soft-fail on missing imports | `backend/app/services/speech.py`, `backend/app/api/voice.py` |
| **B17** | Shadow Reader polling: 10×2s + 5×5s = 45s window; 3s NFR is "from Stage 2 complete" | `frontend/src/components/ShadowReaderPrompt.tsx` |
| **SEC-01** | Production guard: JWT_SECRET_KEY must be ≥32 chars and not equal to dev placeholder when `ENVIRONMENT=production` | `backend/app/config.py` |
| **SEC-02** | Refresh token in httpOnly cookie ONLY (not in JSON body) | `backend/app/api/auth.py` |
| **SEC-03** | Rate limits: register 10/min, login 5/min, refresh 5/min | `backend/app/api/auth.py` |
| **SEC-04** | password min_length=8, max_length=128 | `backend/app/schemas/auth.py` |
| **SEC-07** | JTI revocation on refresh rotation (in-memory deny set; Redis upgrade deferred) | `backend/app/auth/jwt.py` |
| **PERF-01** | Tag get-or-create batched (single SELECT + single INSERT...ON CONFLICT) | `backend/app/utils/db_helpers.py` |
| **PERF-04** | Patterns endpoint cached 24h via `users.patterns_cached_*` columns; `?refresh=true` to force | `backend/app/api/insights.py` |
| **PERF-05** | GIN FTS index on `notes.content` | migration 005 |
| **QA-04** | Shadow Reader 2-phase status: `answer_pending` → `answered` (with sweep retry; sweep currently disabled) | `backend/app/api/shadow_reader.py` |
| **QA-05** | Shared `_note_to_out` in `app/api/_note_serializers.py` (used by notes.py, voice.py, sync.py) | `backend/app/api/_note_serializers.py` |

---

## 6 — Auth model (one-pager)

| Aspect | Value |
|---|---|
| Mechanism | JWT bearer (HS256) + bcrypt password hash |
| Access token | 30 min TTL, returned in JSON body of `/login` and `/refresh`, sent as `Authorization: Bearer ...` |
| Refresh token | 30 day TTL, **httpOnly + Secure + SameSite=Lax** cookie ONLY (XSS-protected) |
| JTI revocation | In-memory set; refresh rotation revokes prior JTI |
| Storage on client | Access token in Zustand `authStore` MEMORY ONLY (no localStorage); refresh cookie auto-sent by browser |
| User isolation | All CRUD scoped by `current_user_id`; cross-user → 404 (existence-leak prevention) |
| Endpoints | `POST /api/auth/register` (10/min), `/login` (5/min), `/refresh` (5/min), `GET /api/auth/me` |
| Production guard | Pydantic validator on `JWT_SECRET_KEY` (≥32 chars, not placeholder) when `ENVIRONMENT=production` |

**Frontend gotcha (now fixed):** Login/Register call `loginApi()` then `me()`. The token must be stored via `useAuthStore.getState().setAccessToken(...)` BEFORE `me()` is awaited, otherwise `fetchWithAuth` reads the still-null token and `/me` returns 401.

---

## 7 — Things that look strange but are correct

1. **App prefix `cortexks` instead of `cortex`** — global storage account name `cortexstorage` was taken. Suffixed the prefix instead of changing the spec.
2. **Region `centralus` instead of `westus2`** — Visual Studio Enterprise subscription disallows Postgres Flexible Server in `westus2` and `eastus2`.
3. **Azure OpenAI is in `eastus`** — model availability (gpt-4o-mini + text-embedding-3-small not yet GA in centralus).
4. **`backend/app/services/vision.py` does NOT exist** — by design (B5). OCR is in `pipeline/ocr.py`.
5. **`SCHEDULER_ENABLED=false` removed entirely 2026-05-06** — the env var no longer exists; the daily/weekly distill cron was dropped per a user product decision. Migration 007 drops the `daily_summaries` table.
6. **Migration 001 creates `embedding` as TEXT then ALTERs to `vector(1536)`** — noted as SA-M1 (LOW). Cosmetic only.
7. **Two ACR images exist: `cortex-api` (orphan from first deploy) and `cortexks-api` (live)** — `cortex-api` can be safely deleted (`az acr repository delete --name cortexksacr --image cortex-api`) but isn't doing harm.
8. **30 backend tests still failing locally** — these are static-introspection tests asserting code patterns the implementation expressed differently. Production code is correct (reviewers passed Round 2). See KNOWN_ISSUES.

---

## 8 — Quick smoke test (5 minutes)

```bash
# Health
curl https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/api/health
# {"status":"ok"}

# Register
curl -X POST https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email":"newuser@example.com","password":"newpass123","display_name":"Smoke"}'
# 201 + UserOut JSON

# Login
TOKEN=$(curl -X POST https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/api/auth/login \
        -H "Content-Type: application/json" \
        -d '{"email":"newuser@example.com","password":"newpass123"}' \
        | grep -oE '"access_token":"[^"]+"' | sed 's/.*:"\([^"]*\)"/\1/')
echo "TOKEN=$TOKEN"

# Me
curl https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/api/auth/me \
     -H "Authorization: Bearer $TOKEN"
# 200 + UserOut

# Create text note
curl -X POST https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/api/notes \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"content":"This is a smoke-test text note","source_type":"text","category":"Ideas"}'
# 201 + NoteOut

# List notes
curl "https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/api/notes" \
     -H "Authorization: Bearer $TOKEN"
# 200 + {items, total}
```

End-to-end UI smoke: load https://gentle-river-06c1e4e10.7.azurestaticapps.net/ in a browser, register a fresh user, capture a voice note, verify it appears in the timeline.

---

## 9 — Where to learn more

- **Spec recap:** `SECOND_BRAIN_BUILD_SPEC.md` § 2 (architecture), § 4 (folder structure + deps), § 5 (deployment + tests)
- **Addendum:** `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md` § F1 (Personal Dictionary), § F2 (Shadow Reader)
- **Architecture details:** `features/cortex-second-brain/designs/design.md`
- **Phase-by-phase log:** `PROGRESS.md`
- **Open work:** `KNOWN_ISSUES.md`
- **Why-decisions:** `DECISIONS.md`
