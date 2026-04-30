# Design: cortex-second-brain

**Author:** Architect agent (translating SECOND_BRAIN_BUILD_SPEC.md sections 2, 4.1, 4.3, 4.4, 5.2 and SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md sections F1.2, F2.2)
**Last Updated:** 2026-04-29
**Status:** To Be Reviewed

## Reviewers

| Reviewer | Role | Status |
|----------|------|--------|
| Lead | Workforce Lead | To Be Reviewed |
| PM (Requirements) | Requirements agent | To Be Reviewed |
| Critic | Critique agent | To Be Reviewed |

---

## Summary

Cortex is a single-owner, voice-first PWA "second brain" backed by FastAPI on Azure Container Apps with a PostgreSQL/pgvector store, Azure Blob Storage for media, and Azure Speech / Azure OpenAI / Azure AI Vision for AI processing. The MVP delivers the CODE (Capture → Organize → Distill → Express) pipeline as an event-driven async chain that returns immediately to the UI and processes in the background, plus an offline-first frontend (IndexedDB + service worker + sync queue). Phase 2 adds Personal Dictionary (boosts STT via Azure PhraseListGrammar) and Shadow Reader (a new "Reflect" stage at 1.5 that generates 1–2 follow-up questions to deepen captured thought) — both designed to add < $0.20/month at expected volume and stay within the $150/month total budget.

## Goals

| Priority | Goal |
|---|---|
| **P0** | Voice capture: **raw note appears in feed within 2s of "stop recording"** via offline-first IndexedDB write (NFR-1, US-4 file-mode). The transcribed/cleaned content arrives later (~3–5s file mode; <2s streaming via US-9 WebSocket). |
| **P0** | Semantic search over personal corpus < 500ms p50 (NFR-2) |
| **P0** | Full offline capture + read; background sync on reconnect (NFR-3, FR-6.1) |
| **P0** | JWT auth with refresh; no unauthenticated access to notes or media (NFR-8) |
| **P0** | Mobile-first PWA, dark mode default, four-tab bottom nav, 1-tap voice FAB |
| **P0** | Auto-organize every note: clean text → tag → categorize → embed |
| **P0** | Total Azure spend ≤ $150/month at expected volume (NFR-4) |
| **P0** | Phase 2 — Shadow Reader off-toggle works immediately; questions are always dismissible (FR-8.2, FR-8.7) |
| **P1** | Lighthouse ≥ 90 on Performance, Accessibility, Best Practices (NFR-5) |
| **P1** | Hybrid keyword+semantic search (FR-3.4) |
| **P1** | Daily / weekly distill summaries; Brain View graph |
| **P1** | Music notes: waveform playback + tempo/mood/genre quick labels |
| **P1** | Phase 2 — Personal Dictionary CRUD; phrase list loaded into STT every WS connection (FR-7.4) |
| **P1** | Phase 2 — Shadow Reader stage produces 1–2 category-appropriate questions within 3s for notes ≥ 50 words |
| **P2** | Express generators (song ideas, practice plans, reflections) |
| **P2** | Bulk import for dictionary; pronunciation hints |
| **P2** | MIDI/DAW export placeholder; per-category opt-out for Shadow Reader |

## Non-Goals

Mirror of requirements doc Section 8 "Out of Scope":

- Multi-user, team, or collaboration features (single-owner MVP).
- Native iOS or Android binaries (PWA only).
- Real DAW/MIDI export beyond a UI placeholder (FR-5.4 ships as stub).
- Federated identity / SSO / SCIM.
- Payment / billing / subscription tiers.
- Formal API versioning beyond a single un-versioned surface (leave room for `/v1/`).
- Server-side music transcription, pitch/BPM detection — only audio format conversion + OCR.
- Real-time collaborative editing.
- User-mutable category taxonomy.
- External integrations (calendar, email, Slack, RSS, browser-extension capture).
- Anything that pushes monthly cost past $150.

## Business Impact / Success Metrics

- **Customer Impact:** Single user (the author) gets a voice-first second brain that organizes itself; Phase 2 adds personalized STT accuracy and a gentle "go deeper" loop.
- **Service Cost:** Estimated $77–$145/month total (spec section 2.11). Phase 2 additions ≤ $0.20/month.
- **Performance:** Voice capture < 2s feedback; semantic search < 500ms p50; CRUD p95 < 300ms.
- **Success Metrics:**
  - ≥ 5 captures/day average across first month.
  - ≥ 20 dictionary terms added in first week of Phase 2.
  - ≥ 30% of triggered Shadow Reader prompts answered (vs dismissed) — soft target.
  - Azure cost ≤ $150/month for ≥ 3 consecutive months.

## Scenarios (User Focused)

1. **Voice capture (Story 1, FR-1.1/1.2/1.3, FR-2.1/2.2):**
   Tap FAB → record → tap to stop. UI shows raw transcription within 2s; background pipeline cleans, tags, categorizes, embeds, links — UI updates silently. Unhappy: STT fails → note saves with raw text and `processing_status='failed'`; pipeline retries with backoff; user can manually edit category/tags.
2. **Text capture (Story 2, FR-1.4):** User types in editor → saves. Pipeline runs Capture (cleanup is a no-op for already-clean text) → Organize.
3. **Image capture (Story 3, FR-1.5):** Upload image → Azure AI Vision OCR extracts text → text becomes note content; original image URL preserved.
4. **Semantic search (Story 5, FR-3.1/3.2):** "Find my melody ideas from last week" → query embedded → pgvector cosine search + optional date filter → top-N notes returned in < 500ms.
5. **Offline capture (Story 15, FR-6.1):** No network → write to IndexedDB → queue sync op → UI confirms. On reconnect, sync engine pushes; conflicts marked with `sync_status='conflict'` for the user to resolve.
6. **Personal Dictionary add (Story 18, FR-7.1/7.4, Phase 2):** Settings → type "Phrygian mode" → tap +. Next WebSocket STT session loads top-500 phrases by `usage_count desc` into `PhraseListGrammar`.
7. **Shadow Reader prompt (Stories 21–23, FR-8.1/8.2/8.7/8.8, Phase 2):** Substantive note (≥ 50 words, category not opted out, global on) → Stage 1.5 generates ≤ 2 questions ≤ 15 words. Bottom-sheet slides up, never modal-blocks. User answers (voice or text) → "--- Reflection ---" appended → embedding regenerated async. Or user taps X → status `dismissed`, no retrigger.

## Key Decisions and Alternatives Considered

- **Database — PostgreSQL Flexible Server with pgvector vs Cosmos DB / Azure AI Search:**
  - **Chosen:** PostgreSQL B1ms + pgvector HNSW index (spec section 2.11; A.2 reference notes pgvector is simplest/cheapest for < 100K vectors).
  - **Rationale:** Single relational store for notes, tags, links, vocabulary, summaries; one connection, one backup. HNSW index meets < 500ms p50 at personal scale.
  - **Alternatives:** Azure AI Search (overkill, cost), Cosmos DB (no native vector at design time of spec), Pinecone (extra service, cost).

- **Backend — FastAPI vs Express / .NET:**
  - **Chosen:** FastAPI (Python 3.11+) per spec section 2.2.
  - **Rationale:** First-class async; Azure SDK + OpenAI SDK + Azure Speech SDK all Python-native; OpenAPI auto-docs. Pinned versions in section 4.3.

- **Background processing — FastAPI BackgroundTasks vs Celery+Redis:**
  - **Chosen:** `BackgroundTasks` + `asyncio` (spec section 2.2 — "no Redis needed for MVP").
  - **Rationale:** Single-user volume (~1000 notes/month); avoids extra infra cost.
  - **Alternative:** Celery+Redis — rejected for MVP cost; reserved for future scale.

- **Frontend offline strategy — IndexedDB local-first vs server-only with cache:**
  - **Chosen:** Dexie.js IndexedDB store + sync queue + service worker (spec sections 2.2, 2.7).
  - **Rationale:** NFR-3 mandates full offline capture/read; queue+FIFO sync is the proven pattern (spec A.2).

- **Container Apps consumption plan — minReplicas: 1 (B14 resolution):**
  - **Chosen:** Consumption plan with `minReplicas: 1` (was scale-to-zero in spec § 2.11 cost optimization #5).
  - **Rationale:** APScheduler runs nightly distill at 23:59 inside the same FastAPI process; scale-to-zero kills the scheduler. Pinning `minReplicas: 1` keeps the scheduler alive. Cost delta vs scale-to-zero is roughly +$10–15/mo for the API container; total monthly spend stays inside the $150 NFR-4 budget (see updated Cost Budget table).
  - **Alternatives considered:** (a) Azure Container Apps Jobs with cron trigger — more correct but requires a separate Bicep resource and image push. Deferred to a future ticket. (b) Lazy generation on next request — fails G3 acceptance ("on schedule").
  - **Caveat:** First-request latency on the *single* warm replica is the only burst risk; SW cache returns UI instantly and FastAPI start-time is sub-second.

- **Shadow Reader — sync stage in pipeline vs separate worker queue:**
  - **Chosen:** Synchronous Stage 1.5 between Capture (Stage 1) and Organize (Stage 2) within the existing async pipeline (addendum F2.2).
  - **Rationale:** Simpler — questions ready by the time UI polls; embedding regeneration on answer runs async.

- **Personal Dictionary — Azure PhraseListGrammar vs custom STT model:**
  - **Chosen:** PhraseListGrammar loaded per WS session (addendum F1.2).
  - **Rationale:** Free, dynamic, no model retrain; cap of ~500 phrases handled by ordering on `usage_count desc`.

- **Auth — JWT in memory + refresh in httpOnly cookie vs all tokens in localStorage:**
  - **Chosen:** Access token in memory; refresh token httpOnly+secure+sameSite cookie (spec section 2.10).
  - **Rationale:** XSS-safer; spec section 2.10 explicit pattern.

## Architecture

Architecture exactly matches spec section 2.1 diagram:

```
┌─────────────────────────────────────────────────────────────┐
│                    MOBILE DEVICE (PWA)                      │
│  Capture | Library | Insights | Create  (4-tab bottom nav)  │
│  ────────────────────────────────────────────────────────   │
│  Service Worker + IndexedDB (offline cache + bg sync)       │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTPS / WSS
                             ▼
┌─────────────────────────────────────────────────────────────┐
│         AZURE CONTAINER APPS (FastAPI Backend)              │
│  REST API  |  WebSocket (STT)  |  BackgroundTasks (CODE +   │
│                                   Reflect pipeline)         │
└─┬──────────────────┬──────────────────┬─────────────────┬───┘
  │                  │                  │                 │
  ▼                  ▼                  ▼                 ▼
PostgreSQL       Azure Blob          Azure Speech      Azure OpenAI
Flexible Srv     Storage             (STT +            (GPT-4o-mini
+ pgvector       (audio/image)       PhraseList)        + text-embedding
                                                         -3-small)
                                                       Azure AI Vision
                                                       (OCR)
```

### Components

| Component | Responsibility | Technology | Dependencies |
|---|---|---|---|
| **PWA frontend** | Capture / Library / Insights / Create UIs; offline cache; sync engine | React 18 + TS + Vite + Tailwind + Dexie + Zustand + vite-plugin-pwa (Workbox) | Azure Static Web Apps (free tier) |
| **FastAPI backend** | REST + WebSocket; pipeline orchestration | FastAPI 0.115 + SQLAlchemy 2.0[asyncio] + asyncpg + pgvector | Azure Container Apps (Consumption 0.5 vCPU / 1GB) |
| **Postgres + pgvector** | Notes, users, tags, links, summaries, vocabulary | PostgreSQL Flexible Server B1ms (16, 32GB), HNSW index | pgvector + uuid-ossp extensions |
| **Blob Storage** | Audio (.webm) and image originals | StorageV2, Hot LRS | SAS-token signed URLs |
| **Azure Speech** | Streaming STT + PhraseListGrammar | azure-cognitiveservices-speech 1.40.* | westus2 |
| **Azure OpenAI** | GPT-4o-mini (capture cleanup, organize, distill, shadow reader); text-embedding-3-small (1536d) | openai 1.40.* | API version `2024-10-21` |
| **Azure AI Vision** | OCR for image notes | azure-ai-vision-imageanalysis 1.0.* | — |
| **Azure Container Registry** | Backend image registry | ACR Basic | — |

### Data Flow

1. **Capture (online voice):** PWA opens WS to `/api/voice/stream` → streams 250ms audio chunks → backend pipes to Azure Speech (with PhraseList loaded for the user) → backend emits partial+final transcripts back over WS. On stop, audio blob uploads to Blob Storage (SAS POST), and a `POST /api/notes` creates the record with `processing_status='transcribed'`.
2. **Capture (offline):** Frontend writes `LocalNote` to IndexedDB and enqueues a sync op. UI shows note instantly. On reconnect, `SyncManager` POSTs the note + audio blob.
3. **AI pipeline (background):** `process_note(note_id)` runs as a `BackgroundTask`:
   - Stage 1 — CAPTURE: GPT-4o-mini cleans `raw_transcription` → `content`; `processing_status: raw|transcribed → processed`.
   - Stage 2 — ORGANIZE: parallel auto-tag/categorize + embedding; then link similar notes by cosine; `processing_status: processed → enriched`.
   - **Stage 1.5 — REFLECT (Phase 2, executed AFTER Stage 2 per B10):** check trigger conditions (≥ 50 words, user enabled, category not opted out); if true, generate 1–2 questions → `notes.shadow_reader_questions` + `shadow_reader_status='asked'`; else `'skipped'`.
4. **Distill (scheduled):** Daily/weekly summary tasks query the user's notes for the period, summarize via GPT-4o-mini, persist to `daily_summaries`.
5. **Search:** Embed query → hybrid SQL (cosine + ts_rank) → ranked results.

### Reusability

The `pipeline/processor.py` module is structured so each stage is an independent coroutine — Distill and Express stages plug into the same orchestration. The `services/` adapters (blob_storage, speech, openai_client) are reusable across pipeline stages and HTTP routes. **Image OCR lives in `pipeline/ocr.py`** (per spec § 4.1 — there is no `services/vision.py`); the Azure AI Vision `ImageAnalysisClient` is constructed inline in that module since it has only one call site.

## UX Changes

UX is a new application — no "before". Mobile-first PWA per spec section 2.6 and requirements Section 10:
- Dark mode default (`#0F172A` background, `#4F46E5` accent per PWA manifest).
- Four-tab bottom nav: Capture, Library, Insights, Create.
- Floating 1-tap voice action button (bottom-right, indigo idle / red+pulse recording).
- Timeline feed on home/Library; per-note status badge (`raw → transcribed → processed → enriched`) per critique mitigation #5.
- Brain View page: AI summaries + react-force-graph-2d of semantic links.
- Settings page hosts Personal Dictionary chip-list (type-color coded) and Shadow Reader toggle + per-category opt-out chips.
- Shadow Reader prompt: bottom-sheet slide-up, never modal, dismiss-X always visible, voice + text answer affordances.
- **Manual override (spec § 3.2 mitigation #6 — first-class UX requirement):** the `NoteEditor` component on `NoteDetailPage` MUST expose editable controls for **category** (six-option dropdown), **tags** (chip add/remove), **mood** (free-text input or dropdown of common moods), and for `category='Music'` notes, **music_metadata** quick-edit chips (tempo / key / genre / instruments). The "AI-suggested" badge appears next to each AI-populated value until the user edits it; once edited, the value is treated as user-authoritative and the pipeline does not re-overwrite it. Acceptance: a user must be able to flip an "Ideas"-tagged note to "Music" in ≤ 2 taps from the timeline.

Reference: spec section 2.6 (voice capture component), 2.7 (PWA manifest), addendum F1.2 (PersonalDictionary.tsx), F2.2 (ShadowReaderPrompt.tsx + ShadowReaderSettings.tsx).

## API / Interfaces

All endpoints require `Authorization: Bearer <access_token>` except `/api/auth/register` and `/api/auth/login`. Standard error envelope: `{ "detail": "...", "code": "..." }`. Pydantic schemas live under `backend/app/schemas/`.

### Auth (spec section 2.10)

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| POST | `/api/auth/register` | `{ email, password, display_name? }` | 201 `{ id, email, display_name }` | bcrypt hash, returns no tokens |
| POST | `/api/auth/login` | `{ email, password }` | 200 `{ access_token, refresh_token, token_type: "bearer" }` | refresh sent as httpOnly Set-Cookie |
| POST | `/api/auth/refresh` | refresh cookie | 200 `{ access_token }` | rotates refresh |
| GET | `/api/auth/me` | — | 200 `{ id, email, display_name }` | current user |

Access token TTL = 30 min, refresh = 30 days, HS256, secret from env `JWT_SECRET_KEY`.

### Notes CRUD (spec section 2.4)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/notes` | `{ content, source_type, category?, audio_url?, image_url?, client_id?, tags? }` | 201 NoteOut; pipeline scheduled |
| GET | `/api/notes` | query: `category, tag, date_from, date_to, q?, limit=50, offset=0` | 200 `{ items: NoteOut[], total }` |
| GET | `/api/notes/{id}` | — | 200 NoteOut |
| PUT | `/api/notes/{id}` | partial `NoteUpdate` (see schema below) | 200 NoteOut; embed re-generated if `content` changed; tag delta-applied if `tags` changed |
| DELETE | `/api/notes/{id}` | — | 204 |

`NoteOut` shape mirrors `notes` table columns + computed `tags: string[]`, `links: NoteLink[]?`. `processing_status ∈ {raw, transcribed, processed, enriched, failed}`. Phase 2 adds `shadow_reader_status`, `shadow_reader_questions[]`, `shadow_reader_answer?`.

**`NoteUpdate` schema (B8 — explicit definition, supports spec § 3.2 mitigation #6 manual-override of category/tags/mood):**

```python
class NoteUpdate(BaseModel):
    """All fields optional — partial update. Coder must use `model_dump(exclude_unset=True)`
    so that absence is distinguished from explicit None."""
    content: Optional[str]                                # if changed, re-pipeline (status -> 'raw')
    category: Optional[Literal['Music','Fitness','Journal','Ideas','Spiritual','Learning']]
    tags: Optional[list[str]]                             # delta-applied: missing tags created (is_auto=False), absent tags unlinked
    mood: Optional[str]                                   # mitigation #6 — manual mood override
    music_metadata: Optional[dict]                        # mitigation #6 — manual music-metadata override (Music category)
    image_url: Optional[str]
    audio_url: Optional[str]
```

Mutating `content` clears `processing_status` to `'raw'` so the pipeline re-runs on next opportunity. Mutating `category`, `tags`, `mood`, or `music_metadata` does **not** re-trigger the pipeline (mitigation #6 — user override is the source of truth and must not be overwritten by AI).

### Sync (spec section 2.4 + 2.7)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/sync/push` | `{ operations: SyncOp[] }` where SyncOp = `{ operation: 'create'|'update'|'delete', entity_type, client_id, payload }` | 200 `{ synced_count, conflicts: [] }` |
| GET | `/api/sync/pull?since={ISO8601}` | — | 200 `{ notes: NoteOut[], deletions: id[], server_time }` |

### Voice (spec section 2.6)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/voice/upload` | multipart audio → STT → returns NoteOut with `processing_status='transcribed'` |
| WS | `/api/voice/stream?token=<jwt>` | bidirectional: client sends raw audio bytes; server sends `{ type: 'partial'\|'transcription', text, is_final }`. Auth via query token (critique mitigation #4). On connect, server logs `Loaded {n} phrases for user {id}` (Phase 2 — observability). |

### Search (spec section 2.8)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/search` | `{ query, category?, tags?, date_from?, date_to?, limit=20 }` | 200 `[{ id, content, summary, category, created_at, semantic_score, text_score, combined_score }]` |
| GET | `/api/search/similar/{note_id}` | — | 200 similar notes by cosine |

### AI / Insights / Tags / Export (spec section 2.4)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/ai/process/{note_id}` | trigger pipeline manually (idempotent on stage) |
| GET | `/api/ai/summary/daily?date=` | returns latest daily summary |
| GET | `/api/ai/summary/weekly?week=` | weekly summary |
| POST | `/api/ai/generate` | `{ kind: 'song'\|'practice'\|'reflection', source_note_ids[] }` → text result |
| GET | `/api/insights/patterns` | detected themes/patterns |
| GET | `/api/insights/graph` | `{ nodes: [{id, label, category}], links: [{source, target, score}] }` |
| GET | `/api/tags` / POST | list/create |
| GET | `/api/export` | full data dump JSON + signed URLs for media |

### Personal Dictionary (Phase 2 — addendum F1.2)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/dictionary?term_type=` | — | 200 `[VocabTerm]` ordered by `usage_count desc` |
| POST | `/api/dictionary` | `{ term (1-200), term_type, pronunciation_hint?, boost_weight=1.0 (0-2) }` | 201 VocabTerm; 400 if at MAX_TERMS_PER_USER (2000); 409 if duplicate |
| PUT | `/api/dictionary/{id}` | partial | 200 |
| DELETE | `/api/dictionary/{id}` | — | 204 |
| POST | `/api/dictionary/bulk` | `[VocabTerm]` (≤ 500) | 201 `{ inserted, total }`; 400 if > 500 |
| GET | `/api/dictionary/export` | — | 200 JSON dump |

`term_type ∈ {name, music_term, technical, place, acronym, general}`.

### Shadow Reader (Phase 2 — addendum F2.2)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/notes/{id}/shadow-reader` | — | 200 `{ status, questions[] }`; 404 if not the user's note |
| POST | `/api/notes/{id}/shadow-reader/answer` | `{ answer }` | 200 `{ status: 'answered', updated_content }`; 409 if status != 'asked' |
| POST | `/api/notes/{id}/shadow-reader/dismiss` | — | 200 `{ status: 'dismissed' }` |
| PUT | `/api/users/me/shadow-reader/settings` | `{ enabled, disabled_categories[] }` | 200 |

### Cross-cutting

- **CORS:** Allow `CORS_ORIGINS` from env (`https://cortex-app.azurestaticapps.net,http://localhost:5173`).
- **Rate limit:** 100 requests/min per user (critique mitigation #8) — `slowapi` middleware.
- **Retries:** All Azure SDK calls wrapped via `tenacity` exponential backoff (critique mitigation #1).
- **SAS tokens:** Blob URLs signed read-only with 24h TTL (critique mitigation #3).
- **No versioning prefix in MVP** but routers register under `/api/...`; future move to `/v1/api/...` is a single config change.

## Data Model

PostgreSQL with `uuid-ossp` and `pgvector` extensions (spec section 2.3 + addendum F1.2 + F2.2).

### Required PostgreSQL extensions (canonical, Azure-compatible — resolves OQ-9)

The Alembic `001_initial_schema.py` migration MUST run these statements verbatim before any `CREATE TABLE`:

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
```

Notes:
- **`vector`** (lowercase, no quotes) is the in-DB extension name on Azure Database for PostgreSQL Flexible Server. The spec § 2.3 wording (`"pgvector"`) **fails** on Azure and MUST NOT be copied.
- The Bicep `azure.extensions` allowlist token is **`VECTOR`** (uppercase) — that's the Azure Resource Manager allowlist string, distinct from the in-DB extension name. Both forms appear in this design and are correct in their respective contexts (Bicep param vs SQL `CREATE EXTENSION`).
- Coder and Tester must reference this section, NOT the spec verbatim wording, when authoring the migration.

### Tables (final schema)

```sql
-- Spec 2.3: USERS (Phase 2 columns from F2.2 ALTER inlined for new builds)
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  display_name VARCHAR(100),
  shadow_reader_enabled BOOLEAN DEFAULT TRUE,
  shadow_reader_disabled_categories JSONB DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Spec 2.3: NOTES (Phase 2 columns from F2.2 inlined for new builds)
CREATE TABLE notes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  raw_transcription TEXT,
  summary TEXT,
  source_type VARCHAR(20) NOT NULL DEFAULT 'text'
    CHECK (source_type IN ('voice','text','image')),
  category VARCHAR(30) NOT NULL DEFAULT 'Ideas'
    CHECK (category IN ('Music','Fitness','Journal','Ideas','Spiritual','Learning')),
  audio_url TEXT,
  image_url TEXT,
  audio_duration_seconds FLOAT,
  entities JSONB DEFAULT '[]'::jsonb,
  mood VARCHAR(30),
  music_metadata JSONB DEFAULT '{}'::jsonb,
  processing_status VARCHAR(20) DEFAULT 'raw'
    CHECK (processing_status IN ('raw','transcribed','processed','enriched','failed')),
  embedding vector(1536),
  sync_status VARCHAR(20) DEFAULT 'synced'
    CHECK (sync_status IN ('pending','synced','conflict')),
  client_id VARCHAR(100),
  shadow_reader_questions JSONB DEFAULT NULL,
  shadow_reader_answer TEXT DEFAULT NULL,
  shadow_reader_status VARCHAR(20) DEFAULT 'pending'
    CHECK (shadow_reader_status IN ('pending','asked','answered','dismissed','skipped')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_notes_user_id     ON notes(user_id);
CREATE INDEX idx_notes_category    ON notes(user_id, category);
CREATE INDEX idx_notes_created_at  ON notes(user_id, created_at DESC);
CREATE INDEX idx_notes_processing  ON notes(processing_status);
CREATE INDEX idx_notes_sync        ON notes(sync_status);
CREATE INDEX idx_notes_source      ON notes(source_type);
CREATE INDEX idx_notes_embedding   ON notes
  USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);

-- Spec 2.3
CREATE TABLE tags (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(100) NOT NULL,
  is_auto BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, name)
);
CREATE TABLE note_tags (
  note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  tag_id  UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (note_id, tag_id)
);

-- Spec 2.3
CREATE TABLE note_links (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  target_note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  similarity_score FLOAT NOT NULL,
  link_type VARCHAR(30) DEFAULT 'semantic',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(source_note_id, target_note_id)
);
CREATE INDEX idx_note_links_source ON note_links(source_note_id);
CREATE INDEX idx_note_links_target ON note_links(target_note_id);

-- Spec 2.3
CREATE TABLE daily_summaries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  summary_date DATE NOT NULL,
  summary_text TEXT NOT NULL,
  key_themes JSONB DEFAULT '[]'::jsonb,
  note_count INTEGER DEFAULT 0,
  mood_summary VARCHAR(50),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, summary_date)
);

-- Addendum F1.2: USER_VOCABULARY
CREATE TABLE user_vocabulary (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  term VARCHAR(200) NOT NULL,
  term_type VARCHAR(30) NOT NULL DEFAULT 'general'
    CHECK (term_type IN ('name','music_term','technical','place','acronym','general')),
  pronunciation_hint VARCHAR(500),
  boost_weight FLOAT DEFAULT 1.0,
  usage_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, term)
);
CREATE INDEX idx_vocabulary_user ON user_vocabulary(user_id);
CREATE INDEX idx_vocabulary_type ON user_vocabulary(user_id, term_type);
```

### Migrations (Alembic, ordered)

| File | Purpose |
|---|---|
| `001_initial_schema.py` | users, notes, tags, note_tags, note_links, daily_summaries, indexes, HNSW (per spec 2.3) |
| `002_add_user_vocabulary.py` | user_vocabulary + indexes (per F1.2) |
| `003_add_shadow_reader.py` | ALTER users (shadow_reader_enabled, shadow_reader_disabled_categories); ALTER notes (shadow_reader_questions, shadow_reader_answer, shadow_reader_status with CHECK) (per F2.2) |

### IndexedDB schema (Dexie.js)

Per spec section 2.3 — `LocalNote` and `SyncQueue` tables:

```ts
// stores
notes:     'localId, serverId, sourceType, category, syncStatus, createdAt'
syncQueue: '++id, operation, entityType, timestamp'
```

Schema fields per spec section 2.3 verbatim (`localId`, `serverId?`, `content`, `rawTranscription?`, `sourceType`, `category`, `audioBlob?`, `imageBlob?`, `tags`, `mood?`, `syncStatus`, `processingStatus`, `createdAt`, `updatedAt`).

### Performance / scalability

- HNSW (m=16, ef_construction=64) handles up to ~100K vectors at < 500ms p50; well above expected 10× of 1000 notes/month.
- `idx_notes_created_at` covers timeline feed queries.
- B1ms 32GB storage covers years at this volume; auto-pause inactive hours saves ~30% (spec 2.11).

### Retention

- Notes and media retained indefinitely (single owner).
- Daily summaries idempotent on `(user_id, summary_date)`.
- Backups: 7-day retention, geo-redundant disabled (Bicep `backup` block).

## AI Pipeline (CODE + Reflect)

Adapted from spec section 2.5 with addendum F2.2 (Reflect stage) and the **B10 ordering fix** — Reflect runs AFTER Organize so it operates on a categorized + embedded note:

```
Stage 0: Ingest (STT or text/image input) — synchronous, < 2s — UI returns
   ▼
Stage 1: CAPTURE (clean text via GPT-4o-mini, max 1000 tokens, T=0.3) — async
   processing_status: raw|transcribed → processed
   ▼
Stage 2: ORGANIZE — async (5–15s)
   - parallel: auto_tag_and_categorize() + generate_embedding()
   - then link_similar_notes() via pgvector (threshold=0.75, limit=5)
   processing_status: processed → enriched
   ▼
Stage 1.5: REFLECT (Phase 2 — Shadow Reader)               — async, ≤ 3s
   gate: processing_status == 'enriched' AND shadow_reader_status == 'pending'
   - should_trigger_shadow_reader(note, user)
       enabled?  category not opted out?  word_count >= 50?
   - if no → shadow_reader_status='skipped', return
   - generate_questions(note) via GPT-4o-mini
       category-specific prompt (CATEGORY_PROMPTS dict, F2.2)
       max_tokens=200, T=0.7, response_format=json_object, cap 2 questions ≤ 15 words
   - persist questions, shadow_reader_status='asked'
   ▼
Stage 3: DISTILL — scheduled daily/weekly via APScheduler in-process (B14)
   - APScheduler `BackgroundScheduler` started at FastAPI startup (in main.py lifespan)
   - cron: 23:59 user-local (single user, MVP); 7-day weekly summary on Sunday 23:59
   - requires Container App minReplicas=1 (see Bicep + Cost Budget)
   - aggregate user's notes for the period → GPT-4o-mini summary
   - persist to daily_summaries
   ▼
Express (P2) — on-demand: song ideas, practice plans, reflections
```

The "Stage 1.5" name is preserved for traceability with the addendum, but in execution order it is the *last* of the create-time stages (after Organize). Embedding regeneration on user answer is the only path that mutates the note's vector after Stage 2.

Pipeline orchestration owned by `backend/app/pipeline/processor.py::AIPipeline.process_note(note_id)`. Stages are independent coroutines so each can be retried with exponential backoff (`tenacity`, critique mitigation #1). On any failure: `processing_status='failed'`, error logged (no note content in logs — NFR observability).

### Pipeline state machine (B10 — Reflect-aware ordering, prevents Stage 1.5 ↔ Stage 2 race)

`processing_status` and `shadow_reader_status` evolve together. The canonical transitions are:

```
                            ┌──────────────────────────────┐
                            │  processing_status state     │
                            │  shadow_reader_status state  │
                            └──────────────────────────────┘

  raw / pending
        │   _stage_capture(note)
        ▼
  processed / pending      ◄── checkpoint A: Stage 1 done, content cleaned
        │
        │   _stage_organize(note)   ── runs UNCONDITIONALLY here
        │   (auto_tag + embed + link)
        ▼
  enriched / pending       ◄── checkpoint B: Stage 2 done, embedding & links written
        │
        │   run_shadow_reader_stage(note, user)   ── reads enriched content
        ▼
  enriched / asked         (questions generated)
   OR
  enriched / skipped       (trigger said no — terminal)

   --- user interaction ---

  enriched / asked
        │   POST /api/notes/{id}/shadow-reader/answer
        │   merge_answer_into_note(note, answer)  in serializable transaction:
        │     1. append "--- Reflection ---" to content
        │     2. set shadow_reader_answer + status='answered'
        │     3. regenerate embedding via text-embedding-3-small
        │     4. re-run _link_similar_notes(note)   (relink based on new embedding)
        ▼
  enriched / answered      ◄── terminal happy path

  enriched / asked
        │   POST .../shadow-reader/dismiss
        ▼
  enriched / dismissed     ◄── terminal dismissed path

  Failures: any stage exception → processing_status='failed' (shadow_reader_status untouched)
```

**Key invariants** (resolves B10 race):

1. **Stage 2 (Organize) runs BEFORE Stage 1.5 (Reflect)** — not after. This is a deliberate change from the natural reading of the spec ("Stage 1.5 between Stage 1 and Stage 2") and from the previous design draft. Reason: Reflect questions are best generated against a *categorized + summarized* note, AND the embedding generated by Stage 2 is the canonical "pre-reflection" embedding.
2. **`run_shadow_reader_stage` reads from `processing_status='enriched'`** — never from `processed`. The orchestrator gates Stage 1.5 on `processing_status == 'enriched' AND shadow_reader_status == 'pending'`.
3. **`merge_answer_into_note` is a serializable transaction** (`SET TRANSACTION ISOLATION LEVEL SERIALIZABLE` in asyncpg). It (a) appends content, (b) regenerates embedding, (c) deletes existing `note_links` rows where `source_note_id = :id`, and (d) re-runs `_link_similar_notes(note)`. This guarantees no stale links survive after the embedding shift.
4. **No concurrent `_stage_organize` and `merge_answer_into_note`** — by invariant 1, organize completes before Reflect even begins; the answer flow is the only path that mutates `embedding` after Stage 2, and it acquires a `SELECT ... FOR UPDATE` lock on the note row.
5. **Idempotent re-trigger** (`POST /api/ai/process/{note_id}`): inspects current state and resumes from the appropriate checkpoint. If `processing_status='failed'`, it restarts from the last successful checkpoint. If `shadow_reader_status='asked'` and the user has not answered, it does NOT regenerate questions.

This ordering is also reflected in the diagram below (note Stage 1.5 is now after Stage 2).

**Reflect-stage answer flow:**
`merge_answer_into_note(note, answer)`:
1. Append `\n\n--- Reflection ---\n{answer}` to `notes.content`.
2. Set `shadow_reader_answer`, `shadow_reader_status='answered'`.
3. Re-call `text-embedding-3-small`; replace `notes.embedding`.
4. UI returns immediately; embedding regen runs as background task (NFR Phase 2 perf).

**Music note enrichment** (spec section 2.9): when `category='Music'`, after Organize, run `process_music_note(note)` to fill `music_metadata` (tempo_guess, key_guess, genre, mood, instruments, description, development_suggestions).

## Voice-First UX

Per spec section 2.6: < 2s feedback loop via WebSocket streaming STT.

- Client `MediaRecorder({ mimeType: 'audio/webm' })`, chunks every 250ms.
- WS `/api/voice/stream?token=<jwt>` — server validates token, opens Azure Speech `PushAudioInputStream`, attaches `recognizing` (partial) and `recognized` (final) handlers; emits over WS.
- **Phase 2 hook:** before recognition starts, call `load_user_phrase_list(recognizer, user_id, db, max_phrases=500)` and log the count (F1.2).
- On stop: client uploads audio blob via `POST /api/upload` → SAS-signed URL → `POST /api/notes` with `audio_url` + `client_id`.
- Offline: write to IndexedDB first, queue, upload on reconnect (spec section 2.7 sync engine).

## Offline-First

Per spec section 2.7 (with B11 image-sync + B13 pull/conflict UX additions):

- `vite-plugin-pwa` (Workbox) with NetworkFirst (`/api/.*` 200 entries, 24h max age, 3s timeout) and CacheFirst (`*.blob.core.windows.net` 100 entries, 7-day max age).
- PWA manifest exactly per spec 2.7 (`name`, `short_name`, `theme_color: #4F46E5`, `background_color: #0F172A`, `display: standalone`, icons 192/512/512-mask).

### Sync push flow (canonical, includes B11 image branch)

Pseudocode for `SyncManager.pushChanges()` — drains `syncQueue` FIFO; for each `create note` op:

```ts
async function pushOne(op: SyncOp) {
  const note = await db.notes.get(op.localId);
  let audioUrl: string | undefined;
  let imageUrl: string | undefined;

  // B11: image branch (was missing in spec § 2.7)
  if (note.imageBlob) {
    imageUrl = await this.uploadBlob(note.imageBlob, note.imageBlob.type || 'image/jpeg');
  }
  if (note.audioBlob) {
    audioUrl = await this.uploadBlob(note.audioBlob, 'audio/webm');
  }

  const created = await api.notes.create({
    content: note.content,
    source_type: note.sourceType,        // 'voice' | 'text' | 'image'
    audio_url: audioUrl,
    image_url: imageUrl,
    client_id: note.localId,
    tags: note.tags,
    category: note.category,
  });

  await db.notes.update(op.localId, { serverId: created.id, syncStatus: 'synced' });
  await db.syncQueue.delete(op.id);
}
```

### Sync pull flow (B13 — newly designed)

```ts
// 1. lastPull cursor lives in a dedicated Dexie 'meta' table:
//    db.version(2).stores({ ..., meta: 'key' });
//    Initial value: epoch (1970-01-01T00:00:00Z) so first pull returns everything.
// 2. SyncManager.pull() runs on:
//    - app boot (after auth)
//    - 'online' event
//    - every 60s while foreground
const lastPull = (await db.meta.get('lastPull'))?.value ?? '1970-01-01T00:00:00Z';
const { notes, deletions, server_time } = await api.sync.pull(lastPull);

await db.transaction('rw', db.notes, db.meta, async () => {
  for (const serverNote of notes) {
    const local = await db.notes.where('serverId').equals(serverNote.id).first();
    if (!local) {
      await db.notes.add({ ...mapServerToLocal(serverNote), syncStatus: 'synced' });
    } else if (local.updatedAt > new Date(lastPull) && local.syncStatus !== 'synced') {
      // Local was edited after lastPull AND has not yet been pushed → conflict
      await db.notes.update(local.localId, {
        ...mapServerToLocal(serverNote, { keepLocalContent: local.content }),
        syncStatus: 'conflict',
        conflictServerVersion: serverNote,   // freeze server payload for the conflict UI
      });
    } else {
      await db.notes.update(local.localId, { ...mapServerToLocal(serverNote), syncStatus: 'synced' });
    }
  }
  for (const deletedId of deletions) {
    const local = await db.notes.where('serverId').equals(deletedId).first();
    if (local) await db.notes.delete(local.localId);
  }
  await db.meta.put({ key: 'lastPull', value: server_time });
});
```

### Conflict UI (B13)

- `<SyncIndicator />` shows a red badge with the count of `notes` rows where `syncStatus='conflict'` (e.g. "Sync conflicts (3)").
- Tap → opens a Conflicts page listing each conflicted note with two cards (Local vs Server) and a "Keep Local / Keep Server / Merge" action row.
- "Keep Local" → `PUT /api/notes/{serverId}` with the local payload, then `syncStatus='synced'`.
- "Keep Server" → overwrite local content with `conflictServerVersion`, set `syncStatus='synced'`.
- "Merge" → opens `<NoteEditor />` prefilled with a textual diff; user edits + saves → same as "Keep Local".

### Sync engine

- `SyncManager` singleton: listens to `online` event, polls every 30s, FIFO drains `syncQueue`, retries with `retryCount`; after 5 failures move to dead-letter (critique mitigation #2 — separate IndexedDB table `deadLetter`).

## Semantic Search

Per spec section 2.8 (with B7 — tags filter wired into the SQL):

- Query embedding via `text-embedding-3-small`.
- Hybrid score: `0.7 * (1 - (embedding <=> :q_emb)) + 0.3 * ts_rank(to_tsvector('english', content), plainto_tsquery(:q_text))` AS `combined_score`.
- LIMIT 20 by default; ORDER BY `combined_score DESC`.

**Canonical SQL with all optional filters** (B7 — `tags` is now first-class; the API contract `POST /api/search` accepts `tags?: string[]` and the SQL applies an `EXISTS` subquery against `note_tags ⨝ tags`):

```sql
SELECT
  n.id, n.content, n.summary, n.category, n.created_at,
  (1 - (n.embedding <=> :q_emb))                              AS semantic_score,
  ts_rank(to_tsvector('english', n.content),
          plainto_tsquery('english', :q_text))                AS text_score,
  0.7 * (1 - (n.embedding <=> :q_emb)) +
  0.3 * ts_rank(to_tsvector('english', n.content),
                plainto_tsquery('english', :q_text))          AS combined_score
FROM notes n
WHERE n.user_id = :user_id
  AND (:category   IS NULL OR n.category   = :category)
  AND (:date_from  IS NULL OR n.created_at >= :date_from)
  AND (:date_to    IS NULL OR n.created_at <= :date_to)
  AND (
    :tags IS NULL
    OR EXISTS (
      SELECT 1
      FROM note_tags nt
      JOIN tags t ON t.id = nt.tag_id
      WHERE nt.note_id = n.id
        AND t.user_id  = :user_id
        AND t.name     = ANY(:tags)
    )
  )
ORDER BY combined_score DESC
LIMIT :limit;
```

Notes:
- `:tags` binds to a `text[]` (Pydantic `tags: list[str] | None`); `NULL` semantics mean "no filter".
- The `EXISTS` form prevents row duplication when a note has multiple matching tags.
- Performance gate: the design assumes `note_tags(note_id)` and `tags(user_id, name)` indexes — both are present (`note_tags` PK + `tags` UNIQUE(user_id, name)). The acceptance criterion "p50 < 500ms over 1000 notes" is measured against the **deployed** Postgres+pgvector instance, not local sqlite (see B18 follow-up: gate the perf assertion behind `--integration` + `RUN_PERF=1`).

## Music Features

Per spec section 2.9:
- `music_metadata` JSONB filled by `process_music_note` (GPT-4o-mini).
- Frontend uses `wavesurfer.js` (`waveColor='#6366F1'`, `progressColor='#4F46E5'`).
- Quick-label chips for tempo / mood / genre rendered on `NoteDetailPage` for `category='Music'`.
- MIDI/DAW export: UI placeholder only.

## Security

Per spec section 2.10 + critique mitigations:
- **JWT:** HS256, secret from env (sourced from Azure Key Vault in prod). Access TTL 30 min, refresh TTL 30 days; `pwd_context = CryptContext(schemes=['bcrypt'])`.
- **Storage:** access token in JS memory; refresh in httpOnly+secure+sameSite cookie.
- **Blob URLs:** SAS, time-limited (24h), read-only (critique mitigation #3).
- **WebSocket auth (B12 — log-leak mitigation):** the JWT is passed via `?token=<jwt>` query param **AND** Container Apps ingress is configured to scrub `token=` from access logs. Concretely:
  - Backend `/api/voice/stream` validates the token on connect (mitigation #4 — preserves the spec-prescribed pattern that browsers cannot send custom headers on `WebSocket(url)`).
  - The Container App's `ingress.corsPolicy` and Application Insights telemetry processor strip the `token` query parameter before persisting to logs. The deploy pipeline adds an Application Insights `ITelemetryProcessor` (or, where unavailable, a Container App `loggerOptions` regex `s/[?&]token=[^&]+/$1token=REDACTED/` over the URL field).
  - Backend code MUST NOT log the request URL on the WebSocket handshake; only `Loaded {n} phrases for user {id}` and `WS connected user={id}`.
  - Documented trade-off: the JWT is briefly visible in the network tab and any reverse proxy that ignores the redaction. Acceptable for single-user MVP; revisit with `Sec-WebSocket-Protocol` subprotocol auth at multi-user phase.
- **Rate limit:** 100 rpm/user via `slowapi` (mitigation #8).
- **Logging:** never log note content, raw_transcription, dictionary entries, or tokens. Log shape examples: `Loaded {n} phrases for user {id}`, `Pipeline complete for note {id}`, `Pipeline failed for note {id}: {err_class}`.
- **Encryption:** Azure default at-rest (NFR-7); TLS 1.2+ in transit (Container Apps default).

## Test Plan

Tester agent owns all test files in `backend/tests/` (pytest + httpx + pytest-asyncio + respx) and `frontend/tests/` or `frontend/src/__tests__/` (Vitest + @testing-library/react + jsdom). Coder waits for failing tests before implementing per TDD protocol.

- **Backend unit tests:**
  - `tests/test_auth.py` — register, login, refresh, JWT validation, current-user.
  - `tests/test_notes.py` — CRUD, pagination, filters, ownership isolation (spec section 5.1 example).
  - `tests/test_search.py` — semantic, hybrid, category/date filters; seeded notes (spec 5.1 example).
  - `tests/test_sync.py` — `/api/sync/push` batch with multiple operations (spec 5.1 example).
  - `tests/test_pipeline.py` — capture cleanup, organize tagging+embedding, link insert; mock Azure OpenAI via respx.
  - `tests/test_voice.py` — WS auth, audio framing, mocked Speech SDK with phrase list count assertion.
  - `tests/test_dictionary.py` — POST/GET/DELETE/bulk; max-2000 enforcement (400); 500-bulk-cap; 409 duplicate; usage_count increment.
  - `tests/test_shadow_reader.py` — trigger conditions (≥ 50 words, opt-out), question generation cap (≤ 2, ≤ 15 words), answer merge + embedding regen, dismiss.
- **Frontend unit tests:**
  - `__tests__/syncManager.test.ts` — offline queue, FIFO drain, retry+dead-letter (spec 5.1).
  - `__tests__/VoiceCapture.test.tsx` — mediaRecorder mock, partial/final WS messages, IndexedDB write.
  - `__tests__/PersonalDictionary.test.tsx` — add/list/remove via mocked fetch.
  - `__tests__/ShadowReaderPrompt.test.tsx` — polling, dismiss, submit answer, hidden states.
  - `__tests__/SearchBar.test.tsx` — mocked search response render.
- **Integration:** httpx AsyncClient against in-process FastAPI app with a real Postgres test container (or sqlite-fallback for unit-level non-vector tests; vector queries require pgvector — gate behind `--integration`).
- **E2E:** manual via PWA on iOS Safari + Android Chrome (Lighthouse run, voice flow, offline flow).
- **Performance:** locust or `httpx` script — 1000-note seed → 50 concurrent semantic searches → assert p50 < 500ms.
- **Manual pre-launch:** the spec section 5.3 final checklist + addendum F1.5 + F2.5.
- **No live Azure in tests** — mocking strategy per service (B15 — respx is HTTP-only and cannot intercept the Speech SDK's gRPC/native transport):

  | Service | SDK transport | Mock library | Hook |
  |---|---|---|---|
  | Azure OpenAI (chat + embeddings) | HTTP via `httpx` (`openai` 1.x uses httpx internally) | `respx` | mount on the OpenAI base URL pattern |
  | Azure AI Vision (Image Analysis) | HTTP REST | `respx` | mount on the vision endpoint pattern |
  | Azure Blob Storage | HTTP REST | `respx` | mount on `*.blob.core.windows.net` |
  | Azure Speech (file mode) | gRPC + native (`SpeechRecognizer.recognize_once_async`) | **`unittest.mock.patch`** | `patch('app.services.speech.SpeechRecognizer')` returning a fake whose `recognize_once_async()` resolves to a stub `SpeechRecognitionResult(text=...)` |
  | Azure Speech (WebSocket streaming, US-9) | native | **`unittest.mock.patch`** | patch `SpeechRecognizer`, `PushAudioInputStream`, fire `recognizing`/`recognized` callbacks via the fake's `events` attribute |

  Each task's TDD Hook in the relevant `us-*.tasks.md` files restates the per-service strategy so the Tester does not pick the wrong mock.

## Rollout / Rollback / Disaster Recovery

- **Rollout:** single user, cutover deployment. No feature flags needed for MVP. Phase 2 features (Personal Dictionary, Shadow Reader) ship behind no flag — new endpoints additive; existing endpoints unchanged.
- **Stages:**
  1. Local dev — full stack via `uvicorn` + `vite dev`, sqlite or local Postgres+pgvector.
  2. Azure dev resource group — Bicep deploy → smoke test all API surfaces → frontend smoke on Static Web App.
  3. Production cutover — same RG, single environment.
- **Rollback:**
  - Backend: `az containerapp update --image cortex-api:<previous-tag>` (revert single revision).
  - Database: Alembic `downgrade -1` (each migration must include `downgrade()`).
  - Frontend: SWA hosts last known good build via deployment slots.
- **Disaster:**
  - Postgres data loss: 7-day automated backup restore.
  - Container Apps outage: scale to 0 then back to 1; if region down, redeploy via Bicep to alternate region.
  - Speech / OpenAI outage: notes save with `processing_status='failed'`; UI shows raw text; pipeline auto-retries on next note creation (graceful degradation, mitigation #7).

## Migration

N/A — greenfield application, no existing data. The three Alembic migrations build the full schema from empty.

## Monitoring and Debuggability

- **Metrics:**
  - `pipeline_stage_duration_ms{stage=...}` histogram
  - `pipeline_failures_total{stage=...}` counter
  - `voice_ws_phrase_list_size` gauge (per session, log-only — Phase 2)
  - `azure_openai_tokens_consumed_total{model=...}` (cost monitoring)
  - `cost_alert_threshold` — Azure budget alerts at $100 and $140 (spec 2.11).
- **Logs (no content, no secrets):**
  - INFO: `note_created {note_id}`, `pipeline_stage_complete {stage} {note_id}`, `phrase_list_loaded {count} {user_id}`
  - WARN: `pipeline_retry {stage} {attempt}`
  - ERROR: `pipeline_failed {stage} {note_id} {error_class}`
- **Traces:** Container Apps default Application Insights integration; trace `request_id` through pipeline tasks via contextvars.
- **Alerts:**
  - Pipeline failure rate > 5% over 1h → email.
  - Azure cost > $140 → email (Azure Cost Management).
  - Postgres CPU > 80% sustained 5 min → email.
- **Dashboards:** Application Insights workbook showing capture rate, pipeline lag, search p50, daily token cost.

## Runbooks and Troubleshooting Guides

- **Pipeline stuck on a note (status=processed not advancing):** `POST /api/ai/process/{note_id}` to re-trigger; check Azure OpenAI quota.
- **Sync queue not draining:** check `/api/health` from PWA; check JWT expiry; check `deadLetter` IndexedDB table for poison messages.
- **Voice not transcribing:** check Speech key/region; verify WS auth token; check `phrase_list_loaded` log line; if zero phrases for user with vocabulary → check Postgres connectivity.
- **Cost spike alert:** open Azure Cost Management → look for OpenAI token surge → throttle pipeline by reducing concurrency in `processor.py`.

## Project Structure (canonical — derived from spec § 4.1 with B5/B6 deltas)

Deltas from spec § 4.1:
- **B6:** added `backend/app/api/upload.py` and `backend/app/api/tags.py` as dedicated router modules. The spec implicitly relied on stuffing these endpoints into `__init__.py`, which is a FastAPI anti-pattern.
- **B5:** kept `backend/app/pipeline/ocr.py` per spec; **removed** `backend/app/services/vision.py` from any narrative — the Vision SDK call is inlined in `pipeline/ocr.py`.

```
cortex/
├── README.md
├── .github/
│   └── workflows/
│       ├── deploy-frontend.yml
│       └── deploy-backend.yml
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── index.html
│   ├── public/
│   │   ├── manifest.json
│   │   ├── favicon.ico
│   │   └── icons/{icon-192.png, icon-512.png, icon-512-mask.png}
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── db.ts
│       ├── api/{client.ts, notes.ts, search.ts, auth.ts, dictionary.ts*, shadowReader.ts*}
│       ├── components/{VoiceCapture.tsx, NoteCard.tsx, NoteEditor.tsx, SearchBar.tsx,
│       │                MusicPlayer.tsx, BottomNav.tsx, ProcessingBadge.tsx,
│       │                SyncIndicator.tsx, PersonalDictionary.tsx*,
│       │                ShadowReaderPrompt.tsx*, ShadowReaderSettings.tsx*}
│       ├── pages/{CapturePage.tsx, LibraryPage.tsx, InsightsPage.tsx, CreatePage.tsx,
│       │          NoteDetailPage.tsx, SearchPage.tsx, LoginPage.tsx, BrainViewPage.tsx,
│       │          SettingsPage.tsx*}
│       ├── hooks/{useAuth.ts, useNotes.ts, useVoiceRecorder.ts, useSync.ts}
│       ├── store/{authStore.ts, noteStore.ts, uiStore.ts}
│       ├── sync/syncManager.ts
│       ├── styles/{globals.css, animations.css*}
│       └── utils/{audio.ts, formatters.ts}
├── backend/
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/versions/{001_initial_schema.py, 002_add_user_vocabulary.py*, 003_add_shadow_reader.py*}
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── models/{__init__.py, user.py, note.py, tag.py, daily_summary.py, vocabulary.py*}
│       ├── schemas/{__init__.py, note.py, search.py, auth.py, sync.py, dictionary.py*, shadow_reader.py*}
│       ├── api/{__init__.py, notes.py, search.py, voice.py, sync.py, insights.py, export.py,
│       │       auth.py, upload.py, tags.py, dictionary.py*, shadow_reader.py*, users.py*}
│       ├── auth/jwt.py
│       ├── pipeline/{__init__.py, processor.py, distill.py, music.py, ocr.py, shadow_reader.py*}
│       ├── services/{blob_storage.py, speech.py, openai_client.py}
│       └── utils/{audio.py, retry.py}
├── infra/
│   ├── main.bicep
│   ├── modules/{container-app.bicep, postgres.bicep, storage.bicep,
│   │            cognitive-services.bicep, static-web-app.bicep}
│   ├── deploy.sh
│   └── parameters.json
└── docs/{ARCHITECTURE.md, API_REFERENCE.md, DEPLOYMENT.md, EXTENDING.md}
```

`*` indicates Phase 2 additions.

## Technology Stack & Dependencies (verbatim from spec section 4.3)

### Frontend `package.json` dependencies (pinned)

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0",
    "zustand": "^4.5.0",
    "dexie": "^4.0.0",
    "dexie-react-hooks": "^1.1.0",
    "uuid": "^10.0.0",
    "recharts": "^2.12.0",
    "react-force-graph-2d": "^1.25.0",
    "wavesurfer.js": "^7.8.0",
    "lucide-react": "^0.400.0",
    "date-fns": "^3.6.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@types/uuid": "^10.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "vite-plugin-pwa": "^0.20.0",
    "vitest": "^2.0.0"
  }
}
```

Test additions for Tester (workforce.json `testing.identityExtension`): `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`.

### Backend `requirements.txt` (pinned — OQ-2 + OQ-4 resolved)

This pin set deviates from spec § 4.3 verbatim in TWO places (B2 / OQ-2 + OQ-4 resolution). The deviation is a documented spec-deviation:

| Spec § 4.3 (verbatim) | This design (canonical) | Reason |
|---|---|---|
| `python-jose[cryptography]==3.3.*` | `python-jose[cryptography]>=3.5,<4` | CVE-2024-33663 (alg-confusion JWT bypass) and CVE-2024-33664 (JWE DoS) are fixed in 3.5.0. Same `jwt.encode/decode` API — no code-shape change. |
| `passlib[bcrypt]==1.7.*` | `passlib[bcrypt]>=1.7,<2` + `bcrypt>=4.0,<4.1` | passlib 1.7.x raises `AttributeError: module 'bcrypt' has no attribute '__about__'` against `bcrypt>=4.1`. Pinning `bcrypt<4.1` keeps `passlib.context.CryptContext(schemes=['bcrypt'])` working without rewriting `auth/jwt.py`. |

Final list:

```
fastapi==0.115.*
uvicorn[standard]==0.30.*
sqlalchemy[asyncio]==2.0.*
asyncpg==0.29.*
pgvector==0.3.*
alembic==1.13.*
python-jose[cryptography]>=3.5,<4
passlib[bcrypt]>=1.7,<2
bcrypt>=4.0,<4.1
python-multipart==0.0.*
openai==1.40.*
azure-cognitiveservices-speech==1.40.*
azure-storage-blob==12.22.*
azure-ai-vision-imageanalysis==1.0.*
pydub==0.25.*
httpx==0.27.*
pydantic-settings==2.4.*
tenacity==8.5.*
slowapi==0.1.*
apscheduler==3.10.*
```

Test deps: `pytest`, `pytest-asyncio`, `respx`.

### Backend `Dockerfile` (verbatim from spec 4.3)

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./app ./app
COPY alembic.ini .
COPY alembic/ ./alembic/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Environment Variables (verbatim from spec section 4.4)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://cortexadmin:<password>@cortex-db.postgres.database.azure.com:5432/cortex

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://cortex-openai.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_API_VERSION=2024-10-21

# Azure Speech
AZURE_SPEECH_KEY=<your-key>
AZURE_SPEECH_REGION=westus2

# Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING=<your-connection-string>
AZURE_STORAGE_CONTAINER=cortex-media

# Azure AI Vision
AZURE_VISION_ENDPOINT=https://cortex-vision.cognitiveservices.azure.com/
AZURE_VISION_KEY=<your-key>

# JWT
JWT_SECRET_KEY=<generate-a-secure-random-string-64-chars>

# App
CORS_ORIGINS=https://cortex-app.azurestaticapps.net,http://localhost:5173
ENVIRONMENT=production
```

`backend/app/config.py` exposes these via `pydantic-settings`. JWT secret stored in Azure Key Vault in production; injected via Container App secret reference.

## Bicep Template (canonical, OQ-1/OQ-5/OQ-6/OQ-7 resolved)

This is the **canonical** Bicep template for the cortex-second-brain feature. It is derived from spec § 5.2 with the following deltas (resolutions of Open Questions baked in — Coder and Reviewer-Security must use this version, not the spec verbatim text):

- **OQ-1 resolved:** new `openaiLocation` parameter (default `westus`); `openai` resource uses it instead of the resource-group `location`. Reason: `gpt-4o-mini` and `text-embedding-3-small` are not GA in `westus2`. All other Cognitive Services resources stay in `location`.
- **OQ-5 resolved:** Postgres `firewallRules` child resource added (`AllowAllAzureServicesAndResourcesWithinAzureIps`, `0.0.0.0`/`0.0.0.0`).
- **OQ-7 resolved:** `Microsoft.App/containerApps` resource added with managed identity, `ingress.transport: 'auto'` (WebSocket support), `allowInsecure: false`, CPU scaling rule (target 70%, `minReplicas: 1`, `maxReplicas: 3` — see B14 resolution: minReplicas=1 to keep APScheduler distill cron alive), liveness + readiness probes on `/api/health`, and env-var bindings to outputs and Key-Vault-sourced secret references.
- **OQ-6 resolved:** `Microsoft.Web/staticSites` resource added so the SWA is reproducible from Bicep alone (rather than a bare `az staticwebapp create` in `deploy.sh`).
- **B14 resolved:** `minReplicas: 1` is the chosen approach so APScheduler can run nightly distill on schedule. Cost delta ≈ +$10–15/mo vs scale-to-zero — total still inside the $150 budget. See § "Cost Budget" for the updated table.

```bicep
// infra/main.bicep
targetScope = 'resourceGroup'

@description('Base name for all resources')
param appName string = 'cortex'

@description('Azure region for all resources except Azure OpenAI')
param location string = resourceGroup().location

@description('Azure OpenAI region (gpt-4o-mini + text-embedding-3-small not GA in westus2). See OQ-1.')
param openaiLocation string = 'westus'

@description('Container image tag deployed to the API Container App')
param containerImageTag string = 'latest'

@description('Frontend origin used for CORS in the backend')
param frontendOrigin string = 'https://${appName}-app.azurestaticapps.net'

@secure()
@description('PostgreSQL admin password')
param dbAdminPassword string

@secure()
@description('JWT secret key')
param jwtSecretKey string

// ---------- PostgreSQL Flexible Server ----------
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: '${appName}-db'
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: 'cortexadmin'
    administratorLoginPassword: dbAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
  }
}

// Enable pgvector extension via the Azure allowlist
resource pgvectorExt 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  parent: postgres
  name: 'azure.extensions'
  properties: { value: 'VECTOR,UUID-OSSP', source: 'user-override' }
}

// OQ-5: firewall rule so the Container App can reach Postgres.
resource postgresFwAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: postgres
  name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ---------- Storage Account ----------
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${appName}storage'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
}

resource storageBlob 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  name: '${storage.name}/default/cortex-media'
  properties: { publicAccess: 'None' }
}

// ---------- Azure OpenAI (OQ-1: must be in westus, NOT westus2) ----------
resource openai 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: '${appName}-openai'
  location: openaiLocation
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: { publicNetworkAccess: 'Enabled' }
}

// ---------- Azure Speech ----------
resource speech 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: '${appName}-speech'
  location: location
  kind: 'SpeechServices'
  sku: { name: 'S0' }
  properties: { publicNetworkAccess: 'Enabled' }
}

// ---------- Azure AI Vision ----------
resource vision 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: '${appName}-vision'
  location: location
  kind: 'ComputerVision'
  sku: { name: 'S1' }
  properties: { publicNetworkAccess: 'Enabled' }
}

// ---------- Container App Environment ----------
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${appName}-env'
  location: location
  properties: {}
}

// ---------- Container Registry ----------
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: '${appName}acr'
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: true }
}

// ---------- Container App (OQ-7) ----------
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${appName}-api'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'           // enables HTTP/1.1 + WebSocket
        allowInsecure: false        // HTTPS only
        traffic: [ { latestRevision: true, weight: 100 } ]
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.name
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password',                    value: acr.listCredentials().passwords[0].value }
        { name: 'database-url',                    value: 'postgresql+asyncpg://cortexadmin:${dbAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/cortex' }
        { name: 'jwt-secret-key',                  value: jwtSecretKey }
        { name: 'azure-openai-api-key',            value: openai.listKeys().key1 }
        { name: 'azure-speech-key',                value: speech.listKeys().key1 }
        { name: 'azure-storage-connection-string', value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=core.windows.net' }
        { name: 'azure-vision-key',                value: vision.listKeys().key1 }
      ]
    }
    template: {
      containers: [
        {
          name: '${appName}-api'
          image: '${acr.properties.loginServer}/${appName}-api:${containerImageTag}'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'DATABASE_URL',                   secretRef: 'database-url' }
            { name: 'JWT_SECRET_KEY',                 secretRef: 'jwt-secret-key' }
            { name: 'AZURE_OPENAI_ENDPOINT',          value: openai.properties.endpoint }
            { name: 'AZURE_OPENAI_API_KEY',           secretRef: 'azure-openai-api-key' }
            { name: 'AZURE_OPENAI_API_VERSION',       value: '2024-10-21' }
            { name: 'AZURE_SPEECH_KEY',               secretRef: 'azure-speech-key' }
            { name: 'AZURE_SPEECH_REGION',            value: location }
            { name: 'AZURE_STORAGE_CONNECTION_STRING',secretRef: 'azure-storage-connection-string' }
            { name: 'AZURE_STORAGE_CONTAINER',        value: 'cortex-media' }
            { name: 'AZURE_VISION_ENDPOINT',          value: vision.properties.endpoint }
            { name: 'AZURE_VISION_KEY',               secretRef: 'azure-vision-key' }
            { name: 'CORS_ORIGINS',                   value: frontendOrigin }
            { name: 'ENVIRONMENT',                    value: 'production' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/api/health', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/api/health', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1                          // B14: keep APScheduler alive for nightly distill
        maxReplicas: 3
        rules: [
          {
            name: 'cpu-rule'
            custom: {
              type: 'cpu'
              metadata: { type: 'Utilization', value: '70' }
            }
          }
        ]
      }
    }
  }
}

// ---------- Static Web App (OQ-6) ----------
resource staticWebApp 'Microsoft.Web/staticSites@2023-12-01' = {
  name: '${appName}-app'
  location: location
  sku: { name: 'Free', tier: 'Free' }
  properties: {
    repositoryUrl: ''        // CI/CD wiring done by deploy-frontend.yml; this resource hosts the static site only
    branch: ''
    buildProperties: {
      appLocation: 'frontend'
      apiLocation: ''
      outputLocation: 'dist'
    }
  }
}

// ---------- Outputs ----------
output postgresHost      string = postgres.properties.fullyQualifiedDomainName
output storageAccountName string = storage.name
output openaiEndpoint    string = openai.properties.endpoint
output openaiRegion      string = openaiLocation
output speechRegion      string = location
output visionEndpoint    string = vision.properties.endpoint
output acrLoginServer    string = acr.properties.loginServer
output containerAppFqdn  string = containerApp.properties.configuration.ingress.fqdn
output staticWebAppName  string = staticWebApp.name
output staticWebAppHost  string = staticWebApp.properties.defaultHostname
```

The `infra/modules/` files (`container-app.bicep`, `postgres.bicep`, `storage.bicep`, `cognitive-services.bicep`, `static-web-app.bicep`) decompose this template; `infra/deploy.sh` orchestrates the full deploy (spec section 5.2). The module decomposition must preserve every property, secret, and probe shown above.

## Cost Budget ($150/month — spec section 2.11)

| Service | SKU | Est. $/mo |
|---|---|---|
| Static Web Apps | Free | $0 |
| Container Apps | Consumption 0.5 vCPU/1GB, **minReplicas=1** (B14) | $25–40 |
| PostgreSQL | B1ms 1 vCPU/2GB/32GB | $25–35 |
| Blob Storage | Hot LRS ~10GB | $5–10 |
| Speech | PAYG ~5h STT | $10–15 |
| Azure OpenAI | GPT-4o-mini ~500K + emb-3-small ~1M | $15–30 |
| AI Vision | PAYG ~100 OCR | $2–5 |
| Container Registry | Basic | $5 |
| **Total** | | **$87–$160** (see note) |

> Note: top-of-range $160 nominally exceeds the $150 NFR-4 ceiling. Mitigation: Postgres B1ms is sized at the high end of usage; expected steady-state is the **$87–$130** band given single-user load. If the actual monthly spend trends toward $150 the team will (a) move Distill to Container Apps Jobs and revert API to scale-to-zero, or (b) right-size Postgres to Burstable B1ms with auto-pause overnight. Budget alert at $140 (spec 2.11) catches this.

Phase 2 add-on: Personal Dictionary $0; Shadow Reader ~$0.11/month at 1000 notes → still well under $150.

## Personal Dictionary (Phase 2 — addendum F1.2 verbatim integration)

- **Trigger:** every WebSocket STT session (`/api/voice/stream`).
- **Service:** `services/speech.py::load_user_phrase_list(recognizer, user_id, db, max_phrases=500)` — selects top 500 by `usage_count desc`, calls `PhraseListGrammar.from_recognizer(recognizer).addPhrase(term)` for each; if `pronunciation_hint` present, also `addPhrase(pronunciation_hint)`. Returns count for log line.
- **Service:** `services/speech.py::increment_term_usage(content, user_id, db)` — after final transcription, scans content (case-insensitive) for terms; increments `usage_count`.
- **Limits:**
  - `MAX_TERMS_PER_USER = 2000` enforced in `POST /api/dictionary` (HTTP 400).
  - Bulk import ≤ 500 per request (HTTP 400 if exceeded).
  - Duplicate term per user → HTTP 409 (UNIQUE constraint).
- **Pydantic:** `VocabularyTerm { term str(1-200), term_type str, pronunciation_hint str|None, boost_weight float[0..2]=1.0 }`.
- **Frontend:** `PersonalDictionary.tsx` chip-list with type-color map (blue=name, purple=music_term, green=technical, amber=place, rose=acronym, slate=general). Settings page hosts it.

## Shadow Reader (Phase 2 — addendum F2.2 verbatim integration)

- **Pipeline placement (B10):** Stage 1.5 (Reflect) executes AFTER Stage 2 (Organize) — see "Pipeline state machine" above. This is a deliberate departure from the addendum's "between Capture and Organize" wording: Reflect needs the categorized note + canonical pre-reflection embedding, and the answer flow is the only post-Organize mutation path.
- **Trigger function:** `should_trigger_shadow_reader(note, user)` — returns True iff `user.shadow_reader_enabled` AND `note.category not in user.shadow_reader_disabled_categories` AND `len(note.content.split()) >= 50`.
- **Question generation:** `generate_questions(note, openai_client)` uses category-specific prompt from `CATEGORY_PROMPTS` dict (Music / Journal / Ideas / Fitness / Spiritual / Learning), `gpt-4o-mini`, `max_tokens=200`, `temperature=0.7`, `response_format=json_object`. Returns first 2 strings from JSON `questions` array.
- **State transitions:** `pending → asked` (questions generated) → `answered` (user submitted) | `dismissed` (X tapped) | `skipped` (trigger said no).
- **Answer merge:** `merge_answer_into_note(note, answer)` appends `\n\n--- Reflection ---\n{answer}`, sets `shadow_reader_answer`, regenerates `embedding` via `text-embedding-3-small`. Embedding regen is async — UI returns immediately.
- **Constraints:**
  - Max 2 questions, max 15 words each (FR-8.10).
  - Single-shot per note: once status transitions out of `asked`, no retrigger (FR-8.11).
  - Dismissal does not affect future notes.
- **Frontend polling (B17 — reconciled with the 3s NFR):** the 3s acceptance is measured from **"Stage 2 (Organize) complete"**, not from "note creation". Stage 1 + Stage 2 together typically take 5–15s, so polling must extend past that. `ShadowReaderPrompt.tsx` therefore polls `GET /api/notes/{id}/shadow-reader` with the following window (canonical):
  - First 10 polls at 2s intervals (covers 0–20s after note creation, encompassing Stage 1+2 in the typical case).
  - Then 5 polls at 5s intervals (covers 20–45s — handles GPT-4o-mini cold-start outliers).
  - After 45s with no `status='asked'`, give up silently (status is treated as effectively `skipped`).
  - Polling stops immediately upon receiving any terminal status (`skipped|dismissed|asked|answered`).
  - Renders bottom-sheet on `status='asked'`; hides on `skipped|dismissed|answered`.
  - Future ticket: replace polling with SSE (`GET /api/notes/{id}/shadow-reader/stream`) once US-8 ships and we have utilization data — recorded as a follow-up, not blocking MVP.
- **Settings:** `PUT /api/users/me/shadow-reader/settings` updates `users.shadow_reader_enabled` and `users.shadow_reader_disabled_categories`.

## Integration Points

This is greenfield, so "integration points" means the exact files Phase 2 features extend (per addendum F1.4 + F2.4):

| Phase 1 file | Phase 2 modification |
|---|---|
| `backend/app/api/voice.py` | Call `load_user_phrase_list(...)` before recognition starts; log count |
| `backend/app/services/speech.py` | Add `load_user_phrase_list`, `increment_term_usage` |
| `backend/app/pipeline/processor.py` | Insert Stage 1.5 call to `run_shadow_reader_stage` |
| `backend/app/models/user.py` | Add `shadow_reader_enabled`, `shadow_reader_disabled_categories` |
| `backend/app/models/note.py` | Add `shadow_reader_questions`, `shadow_reader_answer`, `shadow_reader_status` |
| `backend/app/api/users.py` | Add settings endpoint |
| `frontend/src/pages/SettingsPage.tsx` | Add `<PersonalDictionary />` and `<ShadowReaderSettings />` |
| `frontend/src/pages/NoteDetailPage.tsx` | Render `<ShadowReaderPrompt />` for the just-captured note |
| `frontend/src/styles/animations.css` | Add `slide-up` keyframe |

## Resources, Secrets, Feature Toggles

- **Resources:** All provisioned by `infra/main.bicep` (see above).
- **Secrets:** `dbAdminPassword`, `jwtSecretKey`, Azure OpenAI key, Speech key, Storage connection string, Vision key — Container App secret references; production source is Azure Key Vault.
- **Feature toggles:** None at MVP. Phase 2 features are additive endpoints — Shadow Reader has a per-user runtime toggle (`users.shadow_reader_enabled`) which is the user-facing kill switch.
- **Dependencies on external services:** all Azure-native; no third-party SaaS.

## References

- **Requirements:** `C:\Users\karths\dev\Projects\cortex\features\cortex-second-brain\requirements\requirements.md`
- **Source spec (main):** `C:\Users\karths\dev\Projects\cortex\SECOND_BRAIN_BUILD_SPEC.md` — Sections 2 (Design), 4.1 (Repo structure), 4.3 (Dependencies), 4.4 (Env vars), 5.2 (Deployment + Bicep)
- **Source spec (addendum):** `C:\Users\karths\dev\Projects\cortex\SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md` — Sections F1.2 (Personal Dictionary), F2.2 (Shadow Reader)
- **Workforce config:** `C:\Users\karths\dev\Projects\cortex\.claude\workforce.json`

## Open Questions

After Round 2 review (see `designs/critique.md` § Round 2 Responses), all BLOCKING/HIGH OQs are RESOLVED in the design body itself. The table below records the resolution location for each item.

| # | Issue | Status (Round 2) | Resolution location |
|---|---|---|---|
| OQ-1 | Azure OpenAI not in `westus2` | **RESOLVED** | § "Bicep Template (canonical)" — `param openaiLocation string = 'westus'` + `openai.location: openaiLocation` |
| OQ-2 | `python-jose==3.3.*` CVE-2024-33663/33664 | **RESOLVED** | § "Backend requirements.txt (pinned — OQ-2 + OQ-4 resolved)" — bumped to `python-jose[cryptography]>=3.5,<4` |
| OQ-3 | Other deps 1–3 versions stale (no CVE) | DEFERRED | Spec pins kept; documented in this row. |
| OQ-4 | `passlib[bcrypt]==1.7.*` × `bcrypt>=4.1` | **RESOLVED** | § "Backend requirements.txt" — `passlib>=1.7,<2` + `bcrypt>=4.0,<4.1` |
| OQ-5 | Postgres firewall rule missing | **RESOLVED** | § "Bicep Template (canonical)" — `postgresFwAzure` resource (AllowAllAzureServicesAndResourcesWithinAzureIps) |
| OQ-6 | Static Web App missing from Bicep | **RESOLVED** | § "Bicep Template (canonical)" — `Microsoft.Web/staticSites` resource |
| OQ-7 | Container App resource missing from Bicep | **RESOLVED** | § "Bicep Template (canonical)" — `Microsoft.App/containerApps` resource (full ingress, scale, secrets, env, probes) |
| OQ-8 | `AZURE_OPENAI_API_VERSION=2024-10-21` not the latest GA | DEFERRED | Pin held; `docs/EXTENDING.md` notes bump path to `2025-01-01`. |
| OQ-9 | `CREATE EXTENSION pgvector` vs `vector` on Azure | **RESOLVED** | § "Required PostgreSQL extensions (canonical, Azure-compatible)" — `CREATE EXTENSION IF NOT EXISTS vector` |

For the Critic Round 2 BLOCKING/CONCERN items (B1–B20), see `designs/critique.md` § Round 2 Responses for the per-item REVISED-or-EVIDENCE response.
