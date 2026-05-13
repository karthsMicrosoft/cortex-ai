# PLAN — Cortex Second Brain

> **Living document.** Captures what we're building, what's done, what's next. Update as work progresses.

**Last updated:** 2026-05-13 (Phases 1-6 complete + P3 nits + Round 20 Observability + Strict CSP — see PROGRESS.md § 15-20)

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

### Phase 3 — Music + Express + Polish (items 35-40) ✅ DONE (Round 15, 2026-05-08)
| Item | Shipped via |
|---|---|
| 35-36 | PR #23 — CreatePage Copy/Regenerate/Save-as-Note + per-mode hints + retry on load failure + separate error states |
| 37 | PR #22 — SettingsPage "Your Data" + "Account" sections; Export button → `GET /api/export` blob download; change-password form duplicated from ProfilePage; AppHeader profile-icon link `/profile`→`/settings` |
| 38-39 | PR #24 — CapturePage preview-before-upload, client-side resize ≤2048px / 5MB JPEG, "Uploading…" spinner + error toast; backend `/api/upload` 415/413 tests; OCR placeholder for empty `READ` results |
| 40 | PR #25 lazy-load route splitting (-58 KB raw / -13 KB gzip main bundle, 6 new chunks) + PR #26 E2E Playwright runner + nightly cron workflow (17/17 passing against live) + PR #27 Shadow Reader voice answer (FR-8.4) |

### Phase 4 — AI Search & Synthesis (Round 16, NotebookLM-style RAG) ✅ DONE (2026-05-11)
| Item | Shipped via |
|---|---|
| RAG endpoint `POST /api/ai/answer` with citations | PR #33 (merged via #34) |
| Ask UI page `/ask` + 5th BottomNav tab + clickable citation chips | PR #35 |
| Search filter sidebar (category + tags + date, URL-shareable) | PR #36 |
| NDJSON streaming via `fetch()` + `ReadableStream` (NOT EventSource — bearer auth) | PR #39 |
| Multi-turn conversation with sessionStorage persistence | PR #40 |
| 75-note seed dataset for `karths@microsoft.com` + embedding backfill | PR #30 + #41 |

> Phase 4 closed 2026-05-11. See PROGRESS.md § 16.

### Phase 5 — Web Clipper / External Ingest (Round 17) ✅ DONE (2026-05-11)
| Item | Shipped via |
|---|---|
| Source provenance schema (alembic 008: `source_url`, `source_title`, `source_parent_id`) | PR #43 |
| PWA `share_target` manifest entry + public `/share` route + IndexedDB stash + drain-on-auth | PR #44 |
| `POST /api/import/url` with full SSRF hardening (IMDS block, redirect re-check, content-type allowlist) | PR #45 |
| PDF ingestion via `pypdf` with paragraph-boundary chunking + parent/child notes | PR #46 |
| Clip-from-URL UI on Capture page (4th tab) | PR #47 |
| Chrome MV3 extension (`extension/`) + `POST /api/auth/clip-token` (limited-scope JWT) | PR #48 |

> Phase 5 closed 2026-05-11. See PROGRESS.md § 17.

### Phase 6 — Knowledge Graph + Bidirectional Linking (Round 18) ✅ DONE (2026-05-11)
| Item | Shipped via |
|---|---|
| Foundation: `note_links` triple-uniqueness (semantic + manual + wiki coexist) + ShadowReader scoped delete + `notes.title` + `notes.aliases[]` (alembic 009 + 010) | PR #50 (+ #51, #52 follow-ups for alembic varchar fixes) |
| `GET /api/notes/{id}/links` + Backlinks panel on NoteDetailPage | PR #54 |
| Brain View polish: hover tooltip, resize observer, search/category/date filters, per-link_type edge styling | PR #53 |
| `POST /api/notes/{id}/links` manual link + `DELETE /api/notes/{id}/links/{link_id}` + LinkPicker autocomplete modal | PR #55 |
| Title + aliases editing on NoteDetailPage (H1 click-to-edit, debounced PATCH for aliases) | PR #56 |
| Wiki-link `[[Title]]` parsing pipeline stage + clickable `WikiContent` renderer + `backfill_wiki_links.py` | PR #57 |

> Phase 6 closed 2026-05-11. **Closes the 4-feature initiative the user proposed in Round 16.** See PROGRESS.md § 18.

> Phase 7 (visual canvas — Heptabase / Milanote-style) is acknowledged but deferred. No audit yet.

---

## 4 — Status snapshot (refreshed 2026-05-13)

| Phase / Round | Status | Notes |
|---|---|---|
| Workforce Phases 1-5 (Requirements → Review) | ✅ Done | See PROGRESS.md § 1 |
| **Phase 1 MVP** (items 1-21) | ✅ Done | All US-1..US-9 shipped + deployed |
| **Phase 2** (Insights + Personal Dictionary + Shadow Reader, items 22-34) | ✅ Done | See PROGRESS.md |
| **Phase 3** (Music + Express + Polish, items 35-40) | ✅ Round 15 (2026-05-08) | See PROGRESS.md § 15 |
| **Phase 4** (AI Search & Synthesis — NotebookLM-style RAG) | ✅ Round 16 (2026-05-11) | See PROGRESS.md § 16 |
| **Phase 5** (Web Clipper / External Ingest) | ✅ Round 17 (2026-05-11) | See PROGRESS.md § 17 |
| **Phase 6** (Knowledge Graph + Bidirectional Linking) | ✅ Round 18 (2026-05-11) | See PROGRESS.md § 18 — **closes the 4-feature initiative** |
| **Round 19** (P3 nits + sign-out option + JTI revocation) | ✅ 2026-05-12 | See PROGRESS.md § 19 |
| **Round 20** (Observability + Strict CSP) | ✅ 2026-05-13 | See PROGRESS.md § 20 |
| Backend tests | ✅ ~861 passing / 0 failing | Round 20 baseline |
| Frontend tests | ✅ ~767 passing / 0 failing | Round 20 baseline |
| Extension tests | ✅ 7 passing | New surface from PR #48 |
| TypeScript | ✅ Clean | |
| E2E nightly cron | ✅ Green | Last 3 nights |
| Live `/api/health` | ✅ 200 | At PR #66 image |
| App Insights tracing + cost metrics | ✅ Live (Round 20) | OTel SDK initialized; metrics flowing |
| Strict CSP (backend + SWA) | ✅ Live (Round 20) | Verified via curl + chrome-devtools no-violation |

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
3. ~~Add a basic **Container App auto-restart on failure** (already implicit via probes) plus health check alerts.~~ ✅ Done 2026-05-07 (Round 13) — Bicep probes already gave auto-restart; added 3 Azure Monitor alerts (`cortexks-api-restart-spike`, `cortexks-api-5xx-rate`, `cortexks-api-availability`) routing through Action Group `cortex-alerts-ag` to `karths@microsoft.com`. App Insights `cortexks-ai` + URL-ping web test on `/api/health` from Chicago. See `docs/DEPLOYMENT.md` § "Health-Check Alerts".

### P1 — Operational hygiene
4. ~~Move APScheduler distill cron OUT of Container App into Container Apps Job~~ ✅ **Removed entirely 2026-05-06 (Round 9)** — daily/weekly summary functionality dropped per user product decision; alembic 007 dropped the table; UI cards gone.
5. ~~Wire GitHub Actions secrets so push-to-main auto-deploys (currently workflows exist but secrets are empty).~~ ✅ Done 2026-05-06 (Round 11) — OIDC-federated `cortex-github-actions` AAD app + 7 repo secrets; both workflows green on push and `workflow_dispatch`. Caveat: alembic migrations stay manual (no TTY in CI for `az containerapp exec`).
6. ~~Set up Azure Budget alerts (`$100` warning, `$140` critical) per `docs/DEPLOYMENT.md`.~~ ✅ Done 2026-05-05 — `cortex-monthly` budget on `cortex-rg`, $150/mo, three thresholds (67% Actual / 93% Actual / 100% Forecasted) → karths@microsoft.com.
7. Set up Log Analytics alert on the B12 log-scrubber metric for any leaked tokens.

### P2 — Test debt
8. Triage the 30 backend test failures: per-failure determine real bug vs test-side flake. Update tests or code accordingly. Goal: ≥95% pass rate. See `KNOWN_ISSUES.md` § "Test failures".
9. Fix the frontend `api-client.test.ts` mock-isolation bug (use `vi.resetAllMocks()` instead of `vi.clearAllMocks()` in afterEach).

### P3 — Phase 3 scope ✅ DONE (Round 15, 2026-05-08)
10. ~~Items 37-40 from spec § 4.2 — Express UI polish, Settings export, image-capture UI, E2E + perf optimization.~~ ✅ Closed via 6 PRs (#22-#27). See § 3 above and PROGRESS.md § 15.

### P4 — Production hardening
11. ~~Move JTI revocation from in-memory set to Redis or DB table (SEC-07 follow-up)~~ ✅ Round 19 (2026-05-12) — alembic 011 `revoked_jtis` table + two-tier (cache + DB) revoke; persists across Container App restarts.
12. ~~Add `/api/auth/logout` endpoint that revokes current refresh JTI~~ ✅ Round 19 (2026-05-12) — POST /api/auth/logout revokes both access + refresh JTIs; logout button visible in AppHeader + Settings + Profile.
13. Address remaining 20 LOW/NIT review findings noted in `review-comments.tasks.md` Tasks 1-3.
14. Bootstrap proper KMS-grade key rotation for JWT_SECRET_KEY (90-day rotation).
15. Migrate frontend dependencies forward (React 19, Vite 8, Tailwind 4 — Researcher flagged these as 1-3 majors stale; decision to defer was design-justified at the time).
16. ~~Strict CSP header~~ ✅ Round 20 (2026-05-13) — backend `default-src 'none'`, frontend strict policy with API-origin connect-src + Permissions-Policy.
17. ~~Observability gaps (App Insights traces, custom RAG cost metrics)~~ ✅ Round 20 (2026-05-13) — OTel autoinstrumentation + 3 cost counters + Workbook + cost-rate alert runbook.
18. **Phase 7 — Visual thinking canvas** (Heptabase / Milanote-style: freeform canvas with note cards + drawn arrows + grouping). Acknowledged in Round 16 plan; deferred. Will get its own audit when prioritized.

### Open ops follow-ups (post-Round 20, user-runs)
- Import the workbook JSON into App Insights via `az portal workbook create` (commands in `docs/observability.md`).
- Wire the cost-rate alert (>0.50 USD/hr → cortex-alerts-ag) via `az monitor metrics alert create`.

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
