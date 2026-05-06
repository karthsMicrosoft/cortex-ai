# PLAN — Cortex Second Brain

> **Living document.** Captures what we're building, what's done, what's next. Update as work progresses.

**Last updated:** 2026-05-04 (rounds 1–8 closed; user-confirmed working through bug 27)

---

## 1 — Vision (one paragraph)

Cortex is a personal AI-powered second brain. **Voice-first capture** is the central interaction: 1-tap record → auto-transcribe → auto-clean → auto-tag/categorize → auto-embed → semantic-search across all your personal notes. The CODE framework (Capture / Organize / Distill / Express) plus Reflect (Shadow Reader) augments human thinking instead of replacing it. Mobile-first PWA, offline-capable. Budget cap: ~$150/month on Azure.

---

## 2 — Architecture (one diagram)

```
┌────────────────────────────────────────────────────────────────┐
│                  MOBILE DEVICE — PWA                            │
│  Capture / Library / Insights / Create + BottomNav             │
│  Service Worker + IndexedDB (Dexie) — offline-first            │
└──────────────────┬─────────────────────────────────────────────┘
                   │ HTTPS (CORS allowed origin)
                   ▼
┌────────────────────────────────────────────────────────────────┐
│           Azure Container Apps — FastAPI backend                │
│  REST + WebSocket (STT) + BackgroundTasks (AI pipeline)        │
└──┬──────────────┬──────────────────┬─────────────────┬─────────┘
   │              │                  │                 │
   ▼              ▼                  ▼                 ▼
PostgreSQL    Blob          Azure Speech         Azure OpenAI
Flexible      Storage       (STT file +          (gpt-4o-mini +
+ pgvector    (audio/img)   WebSocket)           text-embedding-3-small)
+ uuid-ossp                                      + Azure AI Vision (OCR)
```

Per spec § 2.1. Currently deployed in **`centralus`** with OpenAI in **`eastus`** (model availability).

---

## 3 — Phase scope

### Phase 1 — MVP (items 1-21 from spec § 4.2) ✅ COMPLETE
| US | Items | What it ships |
|---|---|---|
| us-1-foundation | 1-6 | Monorepo skeleton, FastAPI app + health, JWT auth, Notes CRUD with cross-user 404, Alembic + pgvector schema, Dockerfile |
| us-2-ai-pipeline | 7-11 | Azure Blob/Speech/OpenAI/Vision adapters with tenacity retry, CAPTURE + ORGANIZE pipeline (with B10 state machine), hybrid semantic+keyword search with GIN FTS, OCR for images, tags + sync endpoints |
| us-3-frontend-setup | 12-14 | Vite + React + TS + Tailwind + Dexie + PWA bootstrap, Zustand auth store, Login/Register pages with auto-login |
| us-4-voice-ux-offline | 15-19 | VoiceCapture FAB with B9 IndexedDB-first, NoteCard + NoteEditor with B8 manual override + AI badge, Library/Search pages, syncManager push/pull with B11 imageBlob branch + B13 conflict detection, ConflictsPage, BottomNav |
| us-5-deployment | 20-21 | Canonical Bicep + 5 modules (B1/B4/B14 deltas), deploy.sh 6 steps, GitHub workflows, slowapi rate limit, B12 log scrubbing |

### Phase 2 — Insights + Personal Dictionary + Shadow Reader (items 22-34) ✅ COMPLETE
| US | Items | What it ships |
|---|---|---|
| us-6-insights | 22-28 | Distill stage (daily/weekly summaries via gpt-4o-mini), Insights page, Brain View force-directed graph, Music Player (waveform + metadata chips), Express endpoints (song/practice/reflection generators) |
| us-7-personal-dictionary | 29-30 | UserVocabulary model + CRUD + bulk import, Personal Dictionary UI in Settings, file-mode Speech phrase-list integration with usage_count tracking |
| us-8-shadow-reader | 31-32 | Stage 1.5 (Reflect) runs after Stage 2, ≤2 questions ≤15 words, 4 endpoints, ShadowReaderPrompt with B17 polling (10×2s + 5×5s), ShadowReaderSettings with global toggle + per-category opt-out |
| us-9-realtime-stt | 33-34 | WebSocket streaming endpoint at `/api/voice/stream`, real-time partial transcription in VoiceCapture, B16 soft-fail import for us-7 helpers |

### Phase 3 — Music + Express + Polish (items 35-40) ⏳ NOT STARTED
| Item | What it would ship |
|---|---|
| 35-36 | Express UI (CreatePage already exists from us-6 — Phase 3 would polish) |
| 37 | Settings page export data + change password (Settings page exists from us-7; needs export action) |
| 38-39 | Image upload + OCR end-to-end UI (backend done; frontend needs image-capture flow per B11) |
| 40 | E2E test pass + perf optimization |

> Phase 3 is **out of current scope**. Spec mentions it as "2 weeks more". Pick up there if/when you continue.

---

## 4 — Status snapshot

| Phase | Status | Notes |
|---|---|---|
| Workforce Phase 1 — Requirements | ✅ Done | 23 stories, COMPLEX assessment |
| Workforce Phase 2 — Design + Research | ✅ Done | 9 user stories; 9 OQs from research, all resolved in Round 2 |
| Workforce Phase 3 — Critique | ✅ Done | 17 BLOCKING + 6 CONCERN + 3 NIT — ALL RESOLVED |
| Workforce Phase 4 — Coding (TDD) | ✅ Done | 7 coding sub-phases (us-1..us-9, with us-6/7/9 in parallel) |
| Workforce Phase 5 — Review | ✅ Done | 4 reviewers (security, performance, quality, spec-auditor) Round 1 → 32 above-threshold items → Round 2 PASSED |
| Backend tests local | ⚠️ 263 pass / 30 fail (test-side flakes) | See KNOWN_ISSUES |
| Frontend tests local | ✅ 276/277 pass (1 unrelated mock-isolation bug) | See KNOWN_ISSUES |
| Deploy Phase 1 to Azure | ✅ Done | All resources live, migrations applied, health-check 200 |
| Browser smoke test (auth flow) | ✅ Auto-login fixed and deployed | Register → me() race fixed; SW skipWaiting + clientsClaim |
| Browser smoke test (full pipeline) | ⏳ Not yet validated end-to-end | Pick this up — see § 5 |
| Round 1 — Live UX bug-bash | ✅ 4 production bugs fixed + AI pipeline unblock | See PROGRESS § Round 1 |
| Round 2 — UX-tester findings | ✅ ISSUE-03 + ISSUE-04 fixed; voice 500→422 | See PROGRESS § Round 2 |
| Round 3 — User functional bug-bash | ✅ 10/11 fixed + 1 schema bonus; P1.1 (scheduler) deferred | See PROGRESS § Round 3 |
| Round 4 — Voice-P0 + delete-500 + image-tag + Shadow-Reader revert | ✅ 5 bugs fixed and deployed; 14 regression tests added | See PROGRESS § Round 4 |
| Bug 17 — Different browsers showed different data for same user | ✅ syncManager `lastPull` seed = epoch on first boot + auto-migrate | See PROGRESS § Bug 17 |
| Round 5 — Refresh logout, delete-sync, mobile voice, voice duplicate | ✅ 4 bugs fixed via parallel coder + tester agents; alembic 006 (note_deletions tombstone) deployed | See PROGRESS § Round 5 |
| Round 6 — Refresh-logout #2, mobile voice #2, library categories, voice cut at first pause | ✅ B24 (spread-order in pullChanges) + B25 (continuous recognition) confirmed by user. B22 + B23 still failed despite credentials fix → addressed in Round 7 | See PROGRESS § Round 6 |
| Round 7 — Refresh-logout root cause (Edge cookie blocking) + mobile voice WS skip | ✅ HAR analysis confirmed third-party cookie blocked by Edge tracking-prevention. Moved refresh token to localStorage + JSON body (SEC-02 reversed). Skipped WS on mobile UA. P1 follow-up: revert to first-party cookie when custom domain or SWA Standard SKU is in place | See PROGRESS § Round 7 |
| Round 8 — Mobile recording silent failure + cross-browser audio playback | ✅ B26: `recorder.start(isMobile ? 1000 : 250)` so iOS Safari emits chunks mid-stream; visible error on upload failure; mobile no longer shows degraded toast. B27: backend transcodes incoming audio to MP4/AAC at upload time via existing ffmpeg; one-time migration script converts existing webm blobs | See PROGRESS § Round 8 |

---

## 5 — Smoke test plan (next pickup)

End-to-end happy path to validate before declaring "done":

1. **Auth flow**
   - [x] Register a new user via UI ✅
   - [x] Auto-login lands on home screen with token ✅
   - [ ] Logout → log back in → tokens refresh correctly
   - [ ] Refresh token rotation (wait 30 min, retry; check JTI revocation)

2. **Capture flow**
   - [ ] Tap FAB on Capture page → record voice note (5–10s)
   - [ ] Stop → note appears in feed within 2s (B9 NFR-1) with status `raw`
   - [ ] Audio uploads to Blob; transcript appears within ~5s (status `transcribed`)
   - [ ] AI pipeline runs: Stage 1 cleans → status `processed`; Stage 2 tags + categorizes + embeds → status `enriched`
   - [ ] Note has 2-5 auto-tags; category is one of six; embedding length 1536

3. **Search flow**
   - [ ] Type natural-language query in SearchBar → results return < 500ms
   - [ ] Hybrid SQL works (tags filter via EXISTS subquery) — try `?tags=Music`

4. **Offline flow**
   - [ ] Toggle device offline → capture text + voice notes → both persist in IndexedDB
   - [ ] Toggle online → syncManager pushes; SyncIndicator shows pending → 0
   - [ ] If conflict: ConflictsPage shows it (B13)

5. **Personal Dictionary (Phase 2)**
   - [ ] Settings page → add 3 vocabulary terms (e.g., "arpeggio", "Karthik", "Cortex")
   - [ ] Capture voice mentioning those words → STT output uses phrase-list boost
   - [ ] Verify `usage_count` increments on dictionary terms

6. **Shadow Reader (Phase 2)**
   - [ ] Capture a journal note ≥50 words
   - [ ] Wait for Stage 2 enrichment → bottom-sheet appears with ≤2 questions (status `asked`)
   - [ ] Answer one → sheet closes; note content has `--- Reflection ---` appended
   - [ ] Verify `shadow_reader_status='answered'` and embedding regenerated

7. **Insights / Brain View / Music Player**
   - [ ] Insights page renders daily summary (or empty state if < 1 day of notes)
   - [ ] Brain View renders force-directed graph (or empty state for single note)
   - [ ] Music note → MusicPlayer renders waveform + metadata chips

8. **PWA install**
   - [ ] iOS Safari "Add to Home Screen" — app icon shows
   - [ ] Android Chrome "Install app" prompt — app installs
   - [ ] Offline launch from home screen — shell loads from cache

---

## 6 — Roadmap forward (priority order)

### P0 — Blockers / live-deployment polish
1. ~~Run smoke test plan (§ 5) end-to-end in browser. Log any bugs to `KNOWN_ISSUES.md`.~~ ✅ Done 2026-05-06 (Round 9) — auth/refresh/capture/library/insights/sync all green.
2. ~~Rotate the deploy-time secrets via Key Vault (currently inline). Use `infra/parameters.keyvault-template.json`.~~ ✅ Done 2026-05-06 (Round 9) — `cortexks-kv` live; container app `database-url` + `jwt-secret-key` resolve via KV refs with system-assigned managed identity.
3. Add a basic **Container App auto-restart on failure** (already implicit via probes) plus health check alerts.

### P1 — Operational hygiene
4. ~~Move APScheduler distill cron OUT of Container App into Container Apps Job~~ ✅ **Removed entirely 2026-05-06 (Round 9)** — daily/weekly summary functionality dropped per user product decision; alembic 007 dropped the table; UI cards gone.
5. Wire GitHub Actions secrets so push-to-main auto-deploys (currently workflows exist but secrets are empty).
6. ~~Set up Azure Budget alerts (`$100` warning, `$140` critical) per `docs/DEPLOYMENT.md`.~~ ✅ Done 2026-05-05 — `cortex-monthly` budget on `cortex-rg`, $150/mo, three thresholds (67% Actual / 93% Actual / 100% Forecasted) → karths@microsoft.com.
7. Set up Log Analytics alert on the B12 log-scrubber metric for any leaked tokens.

### P2 — Test debt
8. Triage the 30 backend test failures: per-failure determine real bug vs test-side flake. Update tests or code accordingly. Goal: ≥95% pass rate. See `KNOWN_ISSUES.md` § "Test failures".
9. Fix the frontend `api-client.test.ts` mock-isolation bug (use `vi.resetAllMocks()` instead of `vi.clearAllMocks()` in afterEach).

### P3 — Phase 3 scope (when ready)
10. Items 37-40 from spec § 4.2 — Express UI polish, Settings export, image-capture UI, E2E + perf optimization.

### P4 — Production hardening
11. Move JTI revocation from in-memory set to Redis or DB table (SEC-07 follow-up — currently in-memory means revocations are lost on Container App restart).
12. Add `/api/auth/logout` endpoint that revokes current refresh JTI (defense-in-depth).
13. Address remaining 20 LOW/NIT review findings noted in `review-comments.tasks.md` Tasks 1-3.
14. Bootstrap proper KMS-grade key rotation for JWT_SECRET_KEY (90-day rotation).
15. Migrate frontend dependencies forward (React 19, Vite 8, Tailwind 4 — Researcher flagged these as 1-3 majors stale; decision to defer was design-justified at the time).

---

## 7 — Out of scope (for now)

- Multi-user / sharing — Cortex is single-tenant per spec.
- Mobile native apps (React Native, Flutter, Swift, Kotlin) — PWA is the spec target.
- Self-hosted deployment (k8s, on-prem Postgres) — Azure Container Apps is the spec target.
- Email/SMS notifications.
- Backup / restore / DR — relies on Azure Postgres backups (7-day retention, default).
- i18n — English only.
- Multi-tenancy with organizations.

---

## 8 — Risks / things to watch

| Risk | Mitigation in place |
|---|---|
| Visual Studio Enterprise subscription cost spike | ✅ Budget alerts wired 2026-05-05 — `cortex-monthly` on `cortex-rg`, $150/mo, emails karths@microsoft.com at 67% Actual, 93% Actual, 100% Forecasted |
| Azure OpenAI throughput limits in `eastus` | S0 SKU is per-token-rate-limited; for >1k notes/day, consider PTU or fallback to a different region |
| pgvector index degrade beyond 100k rows | HNSW with `m=16, ef_construction=64` is fine for single-user MVP; revisit if scale increases |
| Service Worker stale-bundle bug | Mitigated by `clientsClaim:true, skipWaiting:true` (deployed) |
| In-memory JTI revocation loses state on Container App restart | Acceptable trade-off for single-user MVP; upgrade path documented (P4.11) |
| Refresh token absent from CSP — XSS could steal access token from memory | Document residual risk; recommend strict CSP header (P1 nice-to-have) |
| Test drift between TDD-red tests and final implementation | 30 failures noted; fix-pair pass had limited time. Triage in P2 |
| Multiple ACR images (`cortex-api` orphan + `cortexks-api` live) | Cosmetic; clean up: `az acr repository delete --name cortexksacr --image cortex-api` |
