# Design Critique: cortex-second-brain

> Critic agent — challenges raised against `designs/design.md`, `designs/research.md`, and the nine `tasks/us-*.tasks.md` files.
> Reviewed against `SECOND_BRAIN_BUILD_SPEC.md` (sections 2.1–2.11, 3.2, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3) and `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md` (F1.2, F1.4, F1.5, F2.2, F2.4, F2.5).

---

## Round 1 — 2026-04-29 23:48 UTC

### Conviction standard

I am convinced by **REVISED design text** or **EVIDENCE** (specific spec line, file path, measurement). I am not convinced by confident restatement.

Items flagged from the design's own Open Questions table (OQ-1 … OQ-9) are valid blocking challenges in their own right; they do not get a free pass simply because the Architect already labelled them "open". Some of them have a "Recommended resolution" written into the design but the design also says "Lead → user" — meaning the design has *not yet been revised* to incorporate the resolution. As written, the design is not implementable.

---

### Challenges

---

**B1: OQ-1 (AOAI not in westus2) is unresolved in the design itself** *(BLOCKING)*

- **Scenario:** Design § "Bicep Template" (lines 759–844) is verbatim copy of spec § 5.2: every Cognitive Services account uses `location: location` where `location = resourceGroup().location = westus2`. Research § 3 (lines 102–123) and the design's own OQ-1 row both confirm that `gpt-4o-mini` and `text-embedding-3-small` are NOT available in `westus2` for either Standard or Global Standard. The design text itself still pins `westus2` for AOAI. US-5 task 1.1 instructs the Coder to "add a new param `openaiLocation string = 'westus'`" — but the design's Bicep block does NOT contain that parameter. There is a contradiction inside the design between (a) the verbatim Bicep block and (b) the OQ-1 resolution and US-5 task wording. A Coder reading the design Bicep block will deploy a non-functional AOAI account.
- **Needs:** REVISE the design's "Bicep Template" section to include `param openaiLocation string = 'westus'` and `location: openaiLocation` on the `openai` resource, OR explicitly state in that section "Bicep is verbatim per spec § 5.2 BUT the `openai` resource MUST be deployed to `openaiLocation` per OQ-1; see § Bicep Template – Override". A future Coder/Reviewer must not have to chase the OQ table to find the correct resource location.

---

**B2: OQ-2 + OQ-4 (python-jose CVE + passlib/bcrypt incompat) leave US-1 task 4 with two valid implementations** *(BLOCKING)*

- **Scenario:** US-1 task 4.1 instructs the Coder: *"if no decision, default to spec pins and add a `# SECURITY: pending OQ-2/OQ-4 review` comment so the Reviewer-Security agent will catch it."* This is the design telling the Coder to **knowingly ship CVE-2024-33663/33664 to production**. CVE-2024-33663 is an algorithm-confusion vulnerability that lets an attacker bypass JWT signature verification on `python-jose < 3.4.0` — directly defeats NFR-8. The design's own research (§1, line 39) calls this "Vulnerable at 3.3". The same task tells the Coder that `passlib[bcrypt]==1.7.*` will literally raise `AttributeError` against `bcrypt>=4.1` at app startup. So this task has two equally-plausible failure modes baked in: a CVE *or* a runtime crash. There is no single implementable path.
- **Needs:** REVISE the design to pick ONE of (a) `python-jose[cryptography]>=3.5,<4` + `bcrypt<4.1`, (b) `pyjwt>=2.10` + direct `bcrypt>=4.2`, and update the spec-deviation note. The design must either bump `requirements.txt` or document a working compatible matrix. "Coder picks at implementation time" is not a design — it is a deferred decision.

---

**B3: OQ-9 (`CREATE EXTENSION pgvector` fails on Azure) — design § "Project Structure" still uses spec verbatim wording elsewhere** *(BLOCKING)*

- **Scenario:** The design's Data Model section never shows the `CREATE EXTENSION` statement directly — it just says "PostgreSQL with `uuid-ossp` and `pgvector` extensions" (line 280) — but US-1 task 3.1 says to use `CREATE EXTENSION IF NOT EXISTS vector`. The spec it's translating (§ 2.3 line 249) explicitly says `CREATE EXTENSION IF NOT EXISTS "pgvector"`, which fails on Azure. A TDD-first Tester writing the migration test will copy the spec's wording. The OQ note is buried at the bottom of the design (line 934). Same disconnect as B1: a Coder following the design body will write the wrong SQL.
- **Needs:** REVISE the design Data Model section to include the canonical `CREATE EXTENSION IF NOT EXISTS vector` statement explicitly (with note that Azure's allowlist token is `VECTOR` uppercase, the in-DB extension name is `vector` lowercase). Remove ambiguity for the Tester and Coder.

---

**B4: OQ-5 (Postgres firewall rule) and OQ-7 (Container App resource missing) are not in design Bicep block** *(BLOCKING)*

- **Scenario:** The design's "Bicep Template" section (lines 759–844) is the canonical reference. It does NOT include:
  - A `Microsoft.DBforPostgreSQL/flexibleServers/firewallRules` rule (OQ-5) — without it the Container App cannot connect to the database. First request fails. Verified against research § 13 line 267.
  - The `Microsoft.App/containerApps` resource itself (OQ-7) — only `containerEnv` is in the spec/design Bicep. The deploy.sh in spec § 5.2 calls `az containerapp create` outside Bicep, but US-5 task 1.5 says "the Microsoft.App/containerApps resource must include identity, ingress.transport: 'auto', allowInsecure: false, CPU scaling rule, liveness + readiness HTTP probes". That resource is not in the design's Bicep.
  - The `Microsoft.Web/staticSites` resource for SWA (OQ-6) — same problem.
  Three resources called out in US-5 tasks have NO design block. The Coder cannot write Bicep against a design that doesn't define the resource shape.
- **Needs:** REVISE the design's "Bicep Template" section to include three additional resource blocks (Postgres firewall rule, Container App with all the properties listed in US-5 task 1.5, and `Microsoft.Web/staticSites`). OR move them to dedicated subsections referenced from the main block. Design parity with the task instructions is required.

---

**B5: Design contains an internal contradiction about `services/vision.py`** *(BLOCKING for US-2)*

- **Scenario:** Design line 172 (Reusability section): *"The `services/` adapters (blob_storage, speech, openai_client, vision) are reusable across pipeline stages and HTTP routes."* — claims four files. But design line 634 (Project Structure tree): `services/{blob_storage.py, speech.py, openai_client.py}` — only three. US-2 task 6.1 says: *"Create `backend/app/services/vision.py` with `extract_text(image_url)`."* The spec § 4.1 (line 1335–1338) lists only blob_storage / speech / openai_client. A Tester writing tests against the design tree won't know whether to mock `services/vision.py` or `pipeline/ocr.py`. The spec puts OCR at `pipeline/ocr.py` (line 1334).
- **Needs:** REVISE the design Project Structure tree to include `services/vision.py` if you want to keep US-2 task 6.1 as written, OR remove `services/vision.py` from US-2 task 6.1 and merge the Azure AI Vision SDK call directly into `pipeline/ocr.py` to match spec § 4.1. Pick one and reflect it in the design tree, US-2 tasks, and the test plan.

---

**B6: API surface puts upload + tags routes inside `__init__.py`** *(BLOCKING for US-2)*

- **Scenario:** US-2 task 2.1 literally says: *"Create `backend/app/api/__init__.py` upload route: `POST /api/upload`..."*. Task 8.1 says: *"Create `backend/app/api/__init__.py` `tags.py` with..."*. Both task descriptions stuff endpoints into `__init__.py` instead of creating dedicated `upload.py` and `tags.py` modules. The design API surface table (lines 222–246) refers to `/api/upload` (used by the frontend syncManager — see spec § 2.7 line 947 — `fetch('/api/upload')`) and `/api/tags`, but the Project Structure tree (line 630) does NOT list `upload.py` or `tags.py`. Spec § 4.1 also doesn't include these as files. The current task wording will produce un-loadable / un-routable code (FastAPI routers in `__init__.py` is an anti-pattern; the current placement masks the missing files).
- **Needs:** REVISE the design Project Structure tree to add `backend/app/api/upload.py` and `backend/app/api/tags.py` (or fold tags into `notes.py`); fix US-2 task wording to match. Same for the test plan — `tests/test_upload.py`, `tests/test_tags.py` must be added or the tasks must place them somewhere existing.

---

**B7: Search SQL filters list `tags?` but the spec's hybrid SQL has no tag filter** *(CONCERN, escalates to BLOCKING for US-2)*

- **Scenario:** Design line 230: `POST /api/search` accepts `{ query, category?, tags?, date_from?, date_to?, limit=20 }`. Spec § 2.8 hybrid SQL (lines 985–1010) has filter clauses for `category`, `date_from`, `date_to` only — no `tags` join. Acceptance criteria for US-2 (line 14) says "< 500ms p50 against 1000-note seed". A `tags` filter requires a `JOIN note_tags ... JOIN tags ...` which is not designed. The Coder will either (a) drop the parameter silently (breaks API contract) or (b) invent an SQL shape that has not been latency-tested.
- **Needs:** REVISE the design's "Semantic Search" section (line 485–491) to include the SQL form for the tag filter (e.g. `AND n.id IN (SELECT note_id FROM note_tags JOIN tags ON ... WHERE tags.name = ANY(:tags))`). OR remove `tags?` from the API request schema. Either way, the Tester needs to know which to test.

---

**B8: Spec mitigation #6 (manual override UI for category/tags/mood) is not a first-class design element** *(CONCERN, escalates to BLOCKING for review acceptance)*

- **Scenario:** Spec § 3.2 line 1212 lists eight required mitigations. The design references mitigations #1–#5, #7, #8 explicitly (see grep results). Mitigation #6 is mentioned only obliquely in scenario 1 (line 73): *"user can manually edit category/tags."* No design section, no API surface for `mood` editing, no acceptance criterion in US-4 task 2.3 (NoteEditor.tsx) about mood. The PUT `/api/notes/{id}` accepts a "partial NoteUpdate" (line 209) — but the Pydantic shape `NoteUpdate` is not defined anywhere in the design and US-1 task 5.1 says only "all optional" without enumerating fields. A Reviewer-Security or Reviewer-UX agent will flag this gap.
- **Needs:** REVISE design to (a) explicitly call out mitigation #6 in the UX section, (b) enumerate `NoteUpdate` fields including `category`, `tags`, `mood`, `music_metadata`, and (c) update US-4 task 2.3 to confirm mood editor (currently says only "category dropdown + tag chips"). Otherwise spec § 3.2 mitigation #6 is silently dropped.

---

**B9: NFR-1 (< 2s voice feedback) is not achievable on the US-4 file-mode path** *(BLOCKING)*

- **Scenario:** Acceptance criterion in US-4 line 11: *"After capture, raw transcript displays within 2 seconds (NFR-1) — for US-4 this uses `POST /api/voice/upload` (file mode); WS streaming arrives in US-9."* File-mode upload sequence = (1) audio.webm to `/api/upload` (network upload, ~200ms for a 10s clip), (2) `/api/voice/upload` calls Azure Speech `SpeechRecognizer` *file-mode* recognition which runs the entire clip end-to-end, (3) GPT-4o-mini cleanup. Azure Speech file-mode for a 10-second clip in `westus2` is ~3–5s round-trip alone (verified by Azure docs — real-time STT is the only path that streams partials). Design § "Voice-First UX" (line 470) says "< 2s feedback loop via WebSocket streaming STT" — that's only US-9. So NFR-1 is unmeetable in the US-4 timeframe; US-4 cannot honestly claim "≤ 2s".
- **Needs:** REVISE either (a) US-4 acceptance criteria to scope the < 2s claim to "raw note appears in feed within 2s" — which is satisfied by the offline-first IndexedDB write, even if transcription lags — and document that the **transcribed** content arrives later, OR (b) move the NFR-1 acceptance criterion entirely to US-9 and drop it from US-4. The current wording is unmeetable.

---

**B10: Pipeline sequencing — `process_note()` re-trigger semantics are ambiguous** *(BLOCKING for US-2 + US-8)*

- **Scenario:** Spec § 2.5 lines 548–561 show `process_note(note_id)` advances the note based on current `processing_status`: `if status in ('raw', 'transcribed'): _stage_capture; if status == 'processed': _stage_organize`. US-2 task 4.6 says `POST /api/ai/process/{note_id}` is "idempotent — re-runs pipeline from current stage". But US-8 task 2.4 inserts Stage 1.5 (Reflect) **between** `_stage_capture` and `_stage_organize` — and the gating `if note.processing_status == 'processed'` does NOT include the Reflect status states (`asked`, `skipped`, `dismissed`, `answered`). Question: after Stage 1.5 sets `shadow_reader_status='asked'` but `processing_status` is still `processed`, the Stage 2 gate runs again. Does it run *with* the questions already generated, or wait? The design says (line 165): *"Stage 2 still runs regardless of Reflect outcome"* — but the actual gate logic is `if processing_status == 'processed'` and that flag is set *by* Stage 1 — so Stage 1.5 does not change it, meaning Stage 2 always runs. So far so good. But what happens when `_stage_organize` regenerates the embedding *before* the user answers? Then `merge_answer_into_note` *also* regenerates the embedding. That's two embedding calls per substantive note. At 1000 substantive notes/month × 2 embeddings × 300 input tokens × $0.02/M = +$0.012/mo (negligible cost-wise) but it duplicates work and risks the *answered embedding* being overwritten if Stage 2 races with the answer flow.
- **Needs:** REVISE the pipeline section to specify: (a) what happens when `_stage_organize` runs while `shadow_reader_status='asked'` (does it skip embedding generation? does Stage 2 wait?), (b) what happens to `note_links` if `_link_similar_notes` was computed pre-reflection but the answered note's embedding has shifted post-reflection, (c) the explicit ordering vs concurrency contract. Right now the design has "stages are independent coroutines" + "regenerate embedding on answer" + "Stage 2 generates embedding" without a state machine that prevents the race.

---

**B11: Frontend offline-sync — image notes have no path** *(CONCERN)*

- **Scenario:** Design § "Offline-First" + spec § 2.7 sync engine handle audio: `if (note.audioBlob) { audioUrl = await this.uploadBlob(...) }`. Image capture (FR-1.5, Story 3) is a P1 requirement and the design surfaces it as `image_url` on `notes.create`. But neither the Dexie schema (line 410: `audioBlob?, imageBlob?` is mentioned) nor the syncManager logic in spec § 2.7 actually uploads `imageBlob`. US-4 task 3.2 mentions "image upload input for FR-1.5" but US-4 task 4.1 only handles `audioBlob` upload in syncManager. Result: an image captured offline is stored locally but never syncs.
- **Needs:** REVISE syncManager pseudocode in design "Offline-First" section to include the image upload branch (`if (note.imageBlob) { imageUrl = await this.uploadBlob(note.imageBlob, 'image/...') }`); update US-4 task 4.1 wording.

---

**B12: WebSocket auth mitigation #4 — `?token=` query param leaks JWT to logs** *(CONCERN)*

- **Scenario:** Design line 226: *"Auth via query token (critique mitigation #4)"*. Spec § 3.2 mitigation #4 says: *"WebSocket authentication via query parameter token (validated on connect)"*. This is the prescribed pattern. But query strings are routinely logged by Azure Container Apps' built-in HTTP access log and Application Insights. The design § "Security" line 509 says *"never log... tokens"* — but the platform itself logs request URLs by default. The chosen mitigation pattern violates the stated security posture.
- **Needs:** REVISE design § "Security" to either (a) acknowledge the trade-off and add log-scrubbing config to the Container App ingress (`logFilter` to strip `token=` from URLs), (b) move the WS token to the `Sec-WebSocket-Protocol` subprotocol header (the modern recommended pattern), or (c) explicitly accept the leak and document it. The current wording is internally inconsistent.

---

**B13: SyncManager state — `pushChanges()` is in spec § 2.7 but `pull` flow is not designed** *(CONCERN)*

- **Scenario:** Design § "Sync (spec section 2.4 + 2.7)" exposes `GET /api/sync/pull?since={ISO8601}` returning `{ notes, deletions, server_time }`. The corresponding frontend logic is in US-4 task 4.4: *"useNotes.ts — Dexie-backed hook combining IndexedDB local reads with server pulls via /api/sync/pull?since=<lastPull>; merges by serverId, prefers server version on conflict but flags syncStatus='conflict' if local was edited after pull"*. But the design § "Offline-First" section (lines 479–483) only describes the *push* side. There is no design text for: (a) where `lastPull` is persisted, (b) how the `deletions` list interacts with locally-edited-but-server-deleted records, (c) what surfaces a `sync_status='conflict'` to the user (no UI is designed). NFR-3 says offline read works fully — but pull is the only path that backfills new notes from other devices (Story 20: cross-device sync of dictionary). Without a designed pull/conflict UX, US-4 task 4.4 is too thin to write tests against.
- **Needs:** REVISE design with (a) a sync-state diagram showing push and pull, (b) how `lastPull` timestamp is stored (suggest `localStorage` or a Dexie `meta` table), (c) explicit conflict-resolution UI sketch (e.g., a "Sync conflicts (3)" badge on the timeline). Tester needs a contract before US-4 can ship.

---

**B14: Distill scheduler — APScheduler vs Container Apps Jobs is hand-waved** *(CONCERN)*

- **Scenario:** US-6 task 1.3: *"APScheduler hook attached at FastAPI startup that runs `generate_daily_summary` for the current user nightly at 23:59 local. (For single-user MVP this is sufficient; production scale would move to Container Apps Jobs.)"* Design § "AI Pipeline" line 451 says: *"Stage 3: DISTILL — scheduled daily/weekly"* — no implementation note. Container Apps with `minReplicas: 0` (per design line 102 and US-5 task 1.5 *"minReplicas 0"*) means the container is **stopped** at 23:59. APScheduler in a scaled-to-zero container will never fire. This is a genuine production failure: G3 (acceptance: "Daily and weekly summaries are generated on schedule" — requirements line 274) cannot be met.
- **Needs:** REVISE design to use Azure Container Apps Jobs (cron schedule trigger) for distill, OR pin `minReplicas: 1` for the API container (raises monthly cost ~$10–15 — still under budget but should be acknowledged), OR document that distill runs on next request (lazy generation, not "on schedule"). Each option has a budget/UX trade-off the design must pick.

---

**B15: TDD readiness — several task TDD Hooks reference test files that cannot exist before their dependencies** *(CONCERN)*

- **Scenario:** US-2 TDD Hook (line 28): *"Tester writes failing tests in `backend/tests/` (test_pipeline.py, test_search.py, test_blob.py, test_speech.py, test_ocr.py) using `respx` to mock Azure SDK calls."* But Azure Speech SDK uses gRPC + native Speech recognizers; respx mocks HTTP only. Speech file-mode `transcribe_audio_file` calls `speech_sdk.SpeechRecognizer.recognize_once_async()` — that doesn't go through httpx. respx will not mock it. Same issue for `azure-cognitiveservices-speech` WebSocket recognition in US-9: respx cannot intercept it. The design's test plan line 535 says *"No live Azure in tests — mock Speech, OpenAI, Blob, Vision via respx / unittest.mock"* — but the only viable mock pattern for Speech is `unittest.mock.patch('app.services.speech.SpeechRecognizer')` style, not respx.
- **Needs:** REVISE design § "Test Plan" to clarify which Azure clients use respx (OpenAI HTTP, Vision REST, Blob HTTP) vs `unittest.mock` (Speech SDK, native). Update each task's TDD Hook accordingly so the Tester knows the mocking strategy per service. Without this, the Tester will write red tests that never go green.

---

**B16: Work sequence — us-7 / us-9 shared-file rule is brittle and undocumented in either task file** *(BLOCKING for parallel execution)*

- **Scenario:** `work-sequence.md` lines 44–48 establishes a *convention*: us-7 ships phrase-list helpers in `services/speech.py` and the file-mode call site in `voice.py`; us-9 ONLY adds the new `@router.websocket` route in `voice.py` and CONSUMES (does not modify) `services/speech.py`. But:
  - US-7 task 3.4: *"If a WebSocket handler stub exists in `backend/app/api/voice.py`, add the same phrase-list loader call before `start_continuous_recognition()`"* — this **violates** the convention because US-7 is being asked to modify the WS handler directly.
  - US-9 task 1.3: *"call `await load_user_phrase_list(recognizer, user_id, db)` (from US-7) and log..."* — claims a US-7 dependency that may not exist when US-9 begins, since work-sequence Phase 5 puts both stories in parallel.
  - Neither us-7.tasks.md nor us-9.tasks.md cite the work-sequence convention. The Lead's "merge order us-7 first" rule lives only in work-sequence.md.
- **Needs:** REVISE us-7 task 3.4 to be a no-op (drop the WS hook in US-7; US-9 will write it itself) and REVISE us-9 task 1.3 to NOT call `load_user_phrase_list` if the helper hasn't been merged yet (gate behind `try: from ... import load_user_phrase_list`). OR sequence us-7 strictly before us-9 and update work-sequence.md to drop them from the same parallel phase. Right now the design plan is brittle to merge order and the convention is invisible to the agents implementing it.

---

**B17: ShadowReader frontend polling — 5× at 1s misses the 3s perf goal** *(CONCERN)*

- **Scenario:** Requirements G6 / NFR Phase-2 perf: *"Shadow Reader questions must appear within 3 seconds of note creation"*. Design § "Shadow Reader" line 887: *"polls `GET /api/notes/{id}/shadow-reader` 5× at 1s intervals"*. Pipeline ordering: Stage 1 (Capture, ~5–15s per spec § 2.5) → Stage 1.5 (Reflect, "≤ 3s" per design line 437). So the *earliest* the questions can possibly be ready is ~5s after note creation — i.e. AFTER the 5×1s polls have already exhausted. The frontend will give up before the backend has the data. The 3s NFR appears unmeetable as designed.
- **Needs:** REVISE design to reconcile: either (a) 3s NFR is measured from "Stage 1 complete" not "note creation" — and document that, (b) increase polling to e.g. 20×1s or 10×2s with a longer window, (c) move from polling to WebSocket / SSE push, or (d) accelerate Stage 1 (skip cleanup for Reflect-only path) so questions arrive in <3s. Pick one.

---

**B18: Acceptance criterion "1000 stored notes < 500ms p50" cannot be verified in CI** *(NIT)*

- **Note:** Requirements line 268 + US-2 line 14: search p50 < 500ms across 1000 notes. The design's Test Plan line 533 says *"Performance: locust or `httpx` script — 1000-note seed → 50 concurrent semantic searches → assert p50 < 500ms"*. In CI without a real Postgres + pgvector + HNSW index, this test is meaningless. The design footnote line 531 hints at this: *"vector queries require pgvector — gate behind `--integration`"*. But there's no design statement that the perf assertion runs against *deployed* Postgres, not local sqlite. Reviewer will flag.

---

**B19: Personal Dictionary – `boost_weight` schema mismatch** *(NIT)*

- **Note:** Design line 873 says Pydantic shape is `boost_weight float[0..2]=1.0`. Addendum F1.2 (research) confirms PhraseListGrammar weight is `[0.0, 2.0]`, default 1.0. But neither the SQL schema (line 385: `boost_weight FLOAT DEFAULT 1.0`) nor the migration in US-7 task 1.1 enforces a CHECK constraint at the DB level. Pydantic will reject out-of-range writes, but a manual SQL insert (e.g. via the bulk import from CSV/JSON) bypasses Pydantic if the implementor hooks the bulk import to raw SQL. Suggest adding `CHECK (boost_weight BETWEEN 0 AND 2)`.

---

**B20: Bulk import (POST /api/dictionary/bulk) — silent vs strict on duplicate** *(NIT)*

- **Note:** Design line 256: `POST /api/dictionary/bulk` returns `{ inserted, total }` with `400 if > 500`. But what if the request contains 50 terms and 3 are duplicates? Does it return `{ inserted: 47, total: 50 }` (silent skip)? Or `409 Conflict`? F1.2 spec doesn't say. Tester for US-7 (test_dictionary.py — task 1) will need to pick a contract. Recommend defining: bulk skips duplicates silently and returns `{ inserted, skipped, total }`.

---

### Summary of Round 1 ask

| ID | Title | Severity |
|---|---|---|
| B1 | OQ-1 not in design Bicep | BLOCKING |
| B2 | OQ-2 + OQ-4 leave US-1.4 with two failure modes | BLOCKING |
| B3 | OQ-9 not in design Data Model section | BLOCKING |
| B4 | OQ-5/OQ-6/OQ-7 missing Bicep blocks | BLOCKING |
| B5 | services/vision.py contradiction | BLOCKING |
| B6 | upload + tags routes in `__init__.py` | BLOCKING |
| B7 | tags filter missing from search SQL | BLOCKING |
| B8 | mitigation #6 (manual override) silent | BLOCKING |
| B9 | NFR-1 unmeetable in US-4 file-mode | BLOCKING |
| B10 | Stage 1.5 ↔ Stage 2 race | BLOCKING |
| B11 | image offline sync missing | CONCERN |
| B12 | WS `?token=` leaks to logs | CONCERN |
| B13 | sync pull / conflict UX undesigned | CONCERN |
| B14 | Distill scheduler vs scale-to-zero | CONCERN |
| B15 | respx vs Speech SDK mocking | CONCERN |
| B16 | us-7/us-9 shared-file convention not in tasks | BLOCKING |
| B17 | Shadow Reader 5×1s polls miss the 3s NFR | CONCERN |
| B18 | 1000-note p50 perf in CI | NIT |
| B19 | boost_weight CHECK constraint | NIT |
| B20 | bulk import duplicate semantics | NIT |

I will now message the Architect with this list.

---

*Awaiting Architect response. Will mark each item RESOLVED only on receipt of REVISED design text or a specific spec line / file path / measurement that addresses the gap.*

---

## Round 2 Responses — 2026-04-29 Architect

**B1 (OQ-1 AOAI not in westus2):** REVISED — replaced spec-verbatim Bicep with a canonical block in `design.md` § "Bicep Template (canonical, OQ-1/OQ-5/OQ-6/OQ-7 resolved)". Added `param openaiLocation string = 'westus'`; the `openai` resource now uses `location: openaiLocation` while every other resource keeps the resource-group `location`. Section header explicitly notes the deviation; outputs include `openaiRegion` so deploy.sh can verify. US-5 task 1.1 rewritten to reference the canonical template. US-5 task 1.4 updated to parameterize OpenAI location.

**B2 (OQ-2 + OQ-4 python-jose CVE + passlib/bcrypt):** REVISED — `design.md` § "Backend requirements.txt (pinned)" now lists `python-jose[cryptography]>=3.5,<4`, `passlib[bcrypt]>=1.7,<2`, `bcrypt>=4.0,<4.1` as the canonical pins (table-formatted spec deviation). US-1 task 2.1 updated to point at this pin set; task 4.1 rewritten — the "Coder picks" wording and the `# SECURITY: pending` comment instruction are gone. Also added `slowapi==0.1.*` and `apscheduler==3.10.*` to the canonical list since they are referenced by US-5 task 5.1 and the B14 distill resolution.

**B3 (OQ-9 CREATE EXTENSION pgvector):** REVISED — `design.md` § "Data Model" now opens with a new "Required PostgreSQL extensions (canonical, Azure-compatible)" subsection with the verbatim `CREATE EXTENSION IF NOT EXISTS vector;` and `CREATE EXTENSION IF NOT EXISTS "uuid-ossp";` statements and an explicit note that the Bicep allowlist token `VECTOR` (uppercase) is distinct from the in-DB extension name `vector` (lowercase). Coder/Tester are directed to this section.

**B4 (OQ-5/OQ-6/OQ-7 missing Bicep blocks):** REVISED — canonical Bicep block now contains: (a) `Microsoft.DBforPostgreSQL/flexibleServers/firewallRules` `AllowAllAzureServicesAndResourcesWithinAzureIps` (`0.0.0.0/0.0.0.0`) — OQ-5; (b) `Microsoft.App/containerApps` resource with system identity, `ingress.transport: 'auto'`, `allowInsecure: false`, full secrets + env arrays, CPU scaling rule (`minReplicas: 1`, `maxReplicas: 3`), liveness + readiness probes — OQ-7; (c) `Microsoft.Web/staticSites` Free SKU — OQ-6. US-5 tasks 1.1, 1.4, 1.5 updated to point at the canonical template. Also added `Microsoft.CognitiveServices/accounts` for Vision and a blob container resource that were implicitly assumed but not declared.

**B5 (services/vision.py contradiction):** REVISED — chose spec § 4.1 location: OCR lives in `pipeline/ocr.py`, no `services/vision.py`. Updated `design.md` § "Reusability" wording. US-2 task 6.1 rewritten to construct the `ImageAnalysisClient` inline in `pipeline/ocr.py`; the redundant task 6.2 was merged. Project tree comment also notes the deletion.

**B6 (upload + tags routes in `__init__.py`):** REVISED — `design.md` project tree now lists `backend/app/api/upload.py` and `backend/app/api/tags.py` as dedicated modules (with a "canonical — derived from spec § 4.1" header explaining the deviation). US-2 tasks 2.1 and 8.1 rewritten to create those files with `prefix='/api'` and `prefix='/api/tags'` respectively, and both tasks instruct the Coder to wire the new routers in `main.py`.

**B7 (search SQL missing tags filter):** REVISED — `design.md` § "Semantic Search" now contains the canonical hybrid SQL with the `tags` `EXISTS` subquery against `note_tags ⨝ tags` (`t.user_id = :user_id AND t.name = ANY(:tags)`). The API surface keeps `tags?: string[]`; the SQL is implementable. US-2 tasks 7.1 and 7.2 updated to point at the canonical SQL (and explicitly call out that the spec § 2.8 SQL is NOT to be copied because it omits the tags filter).

**B8 (NoteUpdate schema + manual override UI):** REVISED — `design.md` § "API / Interfaces" now defines the explicit `NoteUpdate` Pydantic shape (content, category Literal, tags list, mood, music_metadata, image_url, audio_url; all optional; `model_dump(exclude_unset=True)` semantics; mutation rules — `content` re-pipelines, manual category/tags/mood/music_metadata do NOT). A new bullet in § "UX Changes" calls out mitigation #6 as a first-class requirement (mood + music_metadata quick-edit row, AI-suggested badge until edited). US-1 task 5.1 rewritten to enumerate the fields; US-4 task 2.3 (NoteEditor) rewritten to require category/tags/mood/music_metadata controls; US-4 acceptance criteria add a manual-override line.

**B9 (NFR-1 < 2s unmeetable on file mode):** REVISED — Goals table P0 row now reads "raw note appears in feed within 2s of stop recording via offline-first IndexedDB write; transcribed/cleaned content arrives 3–5s later (file mode) or <2s (US-9 streaming)". US-4 acceptance criteria rewritten to explicitly state the 2s claim refers to the IndexedDB-backed feed update, not the transcript; the "transcript visible < 2s" claim moved to US-9.

**B10 (Stage 1.5 ↔ Stage 2 race):** REVISED — `design.md` § "AI Pipeline (CODE + Reflect)" now contains a dedicated "Pipeline state machine (B10 — Reflect-aware ordering)" subsection. The canonical execution order is **Stage 1 → Stage 2 → Stage 1.5 (Reflect)**, not the spec/addendum's "Stage 1.5 between Stage 1 and Stage 2". Five invariants are spelled out: (1) ordering, (2) Reflect gate is `processing_status == 'enriched' AND shadow_reader_status == 'pending'`, (3) `merge_answer_into_note` is a SERIALIZABLE transaction with `SELECT ... FOR UPDATE`, deletes existing `note_links`, and reruns `_link_similar_notes` after embedding regen, (4) no concurrent organize/answer, (5) idempotent re-trigger semantics. US-2 task 3.2 and US-8 tasks 2.3 + 2.4 updated to match.

**B11 (image offline sync missing):** REVISED — `design.md` § "Offline-First / Sync push flow (canonical, includes B11 image branch)" now contains the explicit pseudocode with the `if (note.imageBlob)` upload branch. US-4 task 4.1 rewritten to follow that pseudocode; US-4 acceptance criteria add a line for image offline sync.

**B12 (WebSocket `?token=` leaks JWT to logs):** REVISED — `design.md` § "Security" now acknowledges the trade-off, requires Container Apps log scrubbing of the `token=` query parameter (Application Insights TelemetryProcessor or `loggerOptions` regex), forbids logging the request URL on the WS handshake, and documents the residual risk + future mitigation (`Sec-WebSocket-Protocol` subprotocol auth at multi-user phase). US-5 task 1.5 includes the log-scrubbing requirement.

**B13 (sync pull / conflict UX undesigned):** REVISED — `design.md` § "Offline-First" now contains a "Sync pull flow (B13)" subsection with canonical pseudocode (Dexie `meta` table for `lastPull`, foreground polling cadence, conflict-flag rule, `conflictServerVersion` freeze) AND a "Conflict UI" subsection describing the SyncIndicator badge + Conflicts page + Keep-Local/Keep-Server/Merge actions. US-4 task 4.4 rewritten to follow the canonical pseudocode; new task 4.5 added for the Conflicts page.

**B14 (Distill scheduler vs scale-to-zero):** REVISED — chose `minReplicas: 1` for the API Container App so APScheduler runs nightly distill on schedule. Documented in `design.md` § "Key Decisions and Alternatives Considered" (replaced the scale-to-zero choice), in the Bicep canonical block (`scale.minReplicas: 1`), and in § "Cost Budget" (Container Apps row updated to $25–40, total band updated to $87–$160 with a note on remediation paths if usage drifts toward $150). US-5 task 1.5 updated to require `minReplicas: 1`.

**B15 (respx vs Speech SDK mocking):** REVISED — `design.md` § "Test Plan" now contains a per-service mocking-strategy table (respx for HTTP-based SDKs: OpenAI, Vision, Blob; `unittest.mock.patch` for the Speech SDK file mode and WebSocket streaming because both are gRPC/native). US-2 TDD Hook rewritten to point at the table; US-7 and US-9 tests already use `unittest.mock.patch` for Speech.

**B16 (us-7/us-9 shared-file convention not in tasks):** REVISED — US-7 task 3.4 turned into an explicit no-op (the WS phrase-list call is owned by US-9, not US-7). US-9 task 1.3 rewritten with a `try/except ImportError` guard so US-9 stays mergeable when US-7 has not yet landed (degrades to unboosted STT with a WARN log). US-9 task 1.5 similarly soft-fails on `increment_term_usage`. `tasks/work-sequence.md` Phase 5 commentary rewritten to make the convention explicit and to note the soft-fail safety net.

**B17 (Shadow Reader 5×1s polls miss the 3s NFR):** REVISED — `design.md` § "Shadow Reader" reconciles the 3s acceptance to mean "from Stage 2 complete" not "from note creation"; polling window expanded to 10×2s + 5×5s (45s total). US-8 acceptance criteria + task 4.3 rewritten accordingly. SSE upgrade noted as future work.

**C1..C6 (CONCERN items):** Above B11–B17 already addressed each CONCERN in flight. Specifically:
- C1 (image offline sync) → covered by B11 above.
- C2 (WS token leak) → covered by B12 above.
- C3 (sync pull / conflict UX) → covered by B13 above.
- C4 (distill scheduler) → covered by B14 above.
- C5 (respx vs Speech SDK) → covered by B15 above.
- C6 (Shadow Reader polling vs 3s) → covered by B17 above.

(The original critique numbered all of these as B11–B17 with "CONCERN/BLOCKING" severity tags; treating C1..C6 as the same items honors the Critic's intent without duplicating the response.)

**B18 (NIT — 1000-note p50 perf in CI):** ACKNOWLEDGED — `design.md` § "Semantic Search (Notes)" now states the perf assertion runs against deployed Postgres+pgvector, gated behind `--integration` + a new `RUN_PERF=1` env flag. Tester writes the locust script per the existing Test Plan; CI runs it only against the deployed dev resource group. Will track during US-2 implementation review.

**B19 (NIT — boost_weight CHECK constraint):** ACKNOWLEDGED — will track in US-7 implementation. Recommend adding `CHECK (boost_weight BETWEEN 0 AND 2)` to the `user_vocabulary` table in migration `002_add_user_vocabulary.py` (US-7 task 1.1). Pydantic already enforces `0..2`; the CHECK is defense-in-depth for raw SQL bulk imports.

**B20 (NIT — bulk import duplicate semantics):** ACKNOWLEDGED — will track in US-7. Recommend bulk endpoint silently skips duplicates and returns `{ inserted, skipped, total }`. Update will land in US-7 task 2.2 wording at implementation time; not a blocker.

---

End Round 2 responses. design.md and seven task files were revised (us-1, us-2, us-4, us-5, us-7, us-8, us-9 plus work-sequence.md). All BLOCKING items have an explicit REVISED response with the change location named; all CONCERN items resolved inline; NIT items acknowledged with tracking note.

---

## Round 2 Evaluation — 2026-04-30 00:07 UTC

Each item below has been verified against the revised artifacts. File paths and line numbers cited refer to the canonical design and task files.

**B1 (OQ-1 AOAI not in westus2):** RESOLVED — verified at design.md:1018–1022 (`param openaiLocation string = 'westus'`), design.md:1083–1089 (`openai` resource uses `location: openaiLocation`), design.md:1233 (output `openaiRegion`), design.md:1330 (OQ-1 status table), and us-5-deployment.tasks.md:35 + 47 (task 1.1 + 1.4 reference the canonical template + parameterize `openaiLocation`).

**B2 (OQ-2 + OQ-4 python-jose CVE + passlib/bcrypt):** RESOLVED — verified at design.md:917–949 (canonical `requirements.txt` table-formatted spec deviation: `python-jose[cryptography]>=3.5,<4`, `passlib[bcrypt]>=1.7,<2`, `bcrypt>=4.0,<4.1`, plus `slowapi==0.1.*` and `apscheduler==3.10.*`), design.md:1331+1333 (OQ-2/OQ-4 status table), us-1-foundation.tasks.md:49 (task 2.1 references the canonical pin set), and us-1-foundation.tasks.md:97 (task 4.1 rewritten — "No `# SECURITY: pending` comment needed; this is the resolved version", no Coder-picks language remains).

**B3 (OQ-9 CREATE EXTENSION pgvector):** RESOLVED — verified at design.md:301–313 (new "Required PostgreSQL extensions (canonical, Azure-compatible — resolves OQ-9)" subsection with verbatim `CREATE EXTENSION IF NOT EXISTS vector;` + `CREATE EXTENSION IF NOT EXISTS "uuid-ossp";` and the in-DB-vs-allowlist clarification), design.md:1338 (OQ-9 status table), and us-1-foundation.tasks.md:71 (task 3.1 cites OQ-9 and the correct lowercase `vector` token).

**B4 (OQ-5/OQ-6/OQ-7 missing Bicep blocks):** RESOLVED — verified at design.md:1060–1067 (OQ-5: Postgres `firewallRules` `AllowAllAzureServicesAndResourcesWithinAzureIps`), design.md:1125–1211 (OQ-7: full `Microsoft.App/containerApps` with system identity, ingress.transport='auto', allowInsecure=false, secrets, env, CPU scale rule with minReplicas=1/maxReplicas=3, liveness + readiness probes), design.md:1214–1227 (OQ-6: `Microsoft.Web/staticSites` Free SKU), design.md:1101–1107 (Vision account explicit), design.md:1077–1080 (blob container resource), design.md:1334–1336 (OQ-5/6/7 status table), and us-5-deployment.tasks.md:35 (task 1.1 enumerates all canonical resources).

**B5 (services/vision.py contradiction):** RESOLVED — verified at design.md:173 (Reusability section explicitly states "Image OCR lives in `pipeline/ocr.py` (per spec § 4.1 — there is no `services/vision.py`)"), design.md:866 (Project tree `services/{blob_storage.py, speech.py, openai_client.py}` — no vision.py), design.md:813–815 (Project Structure header notes B5 deletion explicitly), and us-2-ai-pipeline.tasks.md:113 (task 6.1 rewritten with B5 reference to inline `ImageAnalysisClient` in `pipeline/ocr.py`; task 6.2 was merged/now wires OCR scheduling).

**B6 (upload + tags routes in `__init__.py`):** RESOLVED — verified at design.md:862–863 (Project tree lists `upload.py`, `tags.py` as dedicated modules in `backend/app/api/`), design.md:813–814 (Project Structure header notes B6 deltas explicitly), us-2-ai-pipeline.tasks.md:53 (task 2.1 creates `api/upload.py` with router `prefix='/api'` and wires it in `main.py`), and us-2-ai-pipeline.tasks.md:141 (task 8.1 creates `api/tags.py` with router `prefix='/api/tags'` and wires it).

**B7 (search SQL missing tags filter):** RESOLVED — verified at design.md:670–705 (canonical hybrid SQL with `EXISTS` subquery against `note_tags ⨝ tags`, `t.user_id = :user_id AND t.name = ANY(:tags)`, indexes-present note), and us-2-ai-pipeline.tasks.md:127 (task 7.2 explicitly says "use the canonical hybrid SQL ... do NOT use the spec § 2.8 SQL verbatim because it omits the tags filter").

**B8 (NoteUpdate schema + manual override UI):** RESOLVED — verified at design.md:216–231 (explicit `NoteUpdate` Pydantic shape with `content`, `category` Literal, `tags`, `mood`, `music_metadata`, `image_url`, `audio_url`; `model_dump(exclude_unset=True)` semantics; mutation rules — manual category/tags/mood/music_metadata do NOT re-trigger pipeline), design.md:185 (UX Changes — first-class mitigation #6 manual-override section with `NoteEditor` requirements, AI-suggested badge, ≤2-tap acceptance), us-1-foundation.tasks.md:115 (task 5.1 enumerates all `NoteUpdate` fields with mutation semantics), and us-4-voice-ux-offline.tasks.md:18+59 (acceptance criteria adds manual-override UI line; task 2.3 enumerates category dropdown + tags chips + mood + music_metadata controls + AI-suggested pill + no-pipeline-rerun rule).

**B9 (NFR-1 < 2s unmeetable on file mode):** RESOLVED — verified at design.md:25 (Goals P0 row rewritten: "raw note appears in feed within 2s of 'stop recording' via offline-first IndexedDB write... transcribed/cleaned content arrives later (~3–5s file mode; <2s streaming via US-9 WebSocket)"), us-4-voice-ux-offline.tasks.md:11 (acceptance criterion explicitly states the 2s claim refers to IndexedDB feed update, not transcript; transcript-visible <2s claim moved to US-9), and us-9-realtime-stt.tasks.md:15 (US-9 owns the "final cleaned note within 2 seconds of stop (NFR-1)" claim).

**B10 (Stage 1.5 ↔ Stage 2 race):** RESOLVED — verified at design.md:499–553 (new "Pipeline state machine (B10 — Reflect-aware ordering)" subsection with state-transition diagram and five invariants: (1) Stage 2 BEFORE Stage 1.5, (2) gate `processing_status == 'enriched' AND shadow_reader_status == 'pending'`, (3) `merge_answer_into_note` SERIALIZABLE + `SELECT ... FOR UPDATE` + delete + relink, (4) no concurrent organize/answer, (5) idempotent re-trigger), design.md:476–484 (AI Pipeline diagram shows Stage 1.5 AFTER Stage 2), design.md:1276 (Shadow Reader section explicitly says "B10 — Stage 1.5 executes AFTER Stage 2 (Organize)"), us-2-ai-pipeline.tasks.md:67 (task 3.2 references B10 ordering and gate), us-8-shadow-reader.tasks.md:11+54+58 (acceptance + tasks 2.3 + 2.4 enforce B10).

**B11 (image offline sync missing):** RESOLVED — verified at design.md:581–612 ("Sync push flow (canonical, includes B11 image branch)" pseudocode contains the explicit `if (note.imageBlob)` upload branch ahead of audio upload), us-4-voice-ux-offline.tasks.md:13 (acceptance criterion adds "image notes captured while offline... sync via the same imageBlob upload branch"), and us-4-voice-ux-offline.tasks.md:103 (task 4.1 rewritten to follow the canonical pseudocode with both `imageBlob` and `audioBlob` branches).

**B12 (WebSocket `?token=` leaks JWT to logs):** RESOLVED — verified at design.md:721–725 (Security section now contains a "B12 — log-leak mitigation" subsection: scrub `token=` from access logs via `loggerOptions` regex / Application Insights TelemetryProcessor, never log request URL on WS handshake, document residual risk + future `Sec-WebSocket-Protocol` subprotocol mitigation), and us-5-deployment.tasks.md:51 (task 1.5 includes the log-scrubbing requirement explicitly).

**B13 (sync pull / conflict UX undesigned):** RESOLVED — verified at design.md:614–649 ("Sync pull flow (B13 — newly designed)" subsection with canonical pseudocode: Dexie `meta` table for `lastPull`, foreground polling cadence 60s + on-online + on-boot, conflict-flag rule, `conflictServerVersion` freeze), design.md:651–657 ("Conflict UI (B13)" subsection: `<SyncIndicator />` red badge with conflict count, Conflicts page with Local-vs-Server cards, Keep-Local / Keep-Server / Merge actions), us-4-voice-ux-offline.tasks.md:115 (task 4.4 rewritten to follow canonical pseudocode), and us-4-voice-ux-offline.tasks.md:119 (NEW task 4.5 creates `ConflictsPage.tsx`).

**B14 (Distill scheduler vs scale-to-zero):** RESOLVED — verified at design.md:101–105 (Key Decisions: `minReplicas: 1` chosen, rationale documented, alternatives + caveat noted), design.md:485–490 (Pipeline DISTILL stage explicitly notes APScheduler in-process + minReplicas=1 requirement), design.md:1196–1208 (canonical Bicep `scale.minReplicas: 1` with cpu-rule and maxReplicas=3), design.md:1244–1258 (Cost Budget table updated to $87–$160 band with Container Apps row at $25–40 and remediation note), and us-5-deployment.tasks.md:35+51 (task 1.1 + 1.5 require `minReplicas: 1` per B14).

**B15 (respx vs Speech SDK mocking):** RESOLVED — verified at design.md:753–763 (Test Plan now contains a per-service mocking-strategy table: respx for OpenAI / Vision / Blob HTTP-based SDKs; `unittest.mock.patch` for Speech file mode and WebSocket streaming because both are gRPC/native, with concrete patch targets and event-firing patterns), us-2-ai-pipeline.tasks.md:28 (TDD Hook references B15 strategy explicitly), us-7-personal-dictionary.tasks.md:30 (TDD Hook references "mocked Speech SDK"), and us-9-realtime-stt.tasks.md:29 (TDD Hook references "mocked Speech recognizer").

**B16 (us-7/us-9 shared-file convention not in tasks):** RESOLVED — verified at us-7-personal-dictionary.tasks.md:77 (task 3.4 turned into explicit "**(NO-OP — moved to US-9 per work-sequence merge-order convention, B16):**" with documentation), us-9-realtime-stt.tasks.md:44–55 (task 1.3 implements `try / except ImportError` guard with WARN log soft-fail; the import-guard pseudocode is included verbatim), us-9-realtime-stt.tasks.md:63 (task 1.5 also soft-fails `increment_term_usage`), and tasks/work-sequence.md:38–66 (Phase 5 commentary rewritten to make the convention canonical, including source-exclusivity caveat, what each story ships, and the soft-fail safety net + merge-order rule).

**B17 (Shadow Reader 5×1s polls miss the 3s NFR):** RESOLVED — verified at design.md:1285–1291 (Shadow Reader frontend polling reconciled: 3s NFR is measured "from Stage 2 (Organize) complete", not "from note creation"; canonical polling = 10×2s + 5×5s = 45s window with terminal-status early-stop; SSE noted as future ticket), us-8-shadow-reader.tasks.md:15 (acceptance criterion mirrors the 10×2s + 5×5s window and the "Stage 2 complete" reframing), and us-8-shadow-reader.tasks.md:90 (task 4.3 implements the tiered schedule).

**B18 (NIT — 1000-note p50 perf in CI):** ACKNOWLEDGED — verified at design.md:705 (Semantic Search section: "the acceptance criterion 'p50 < 500ms over 1000 notes' is measured against the **deployed** Postgres+pgvector instance, not local sqlite ... gate the perf assertion behind `--integration` + `RUN_PERF=1`"). Tracked for US-2 implementation review.

**B19 (NIT — boost_weight CHECK constraint):** ACKNOWLEDGED — Architect confirmed it will land in US-7 task 1.1 implementation. Currently us-7-personal-dictionary.tasks.md:37 ("creates `user_vocabulary` table with all columns and CHECK constraint per design Data Model `user_vocabulary` block") references the design block but the design schema (design.md:418 `boost_weight FLOAT DEFAULT 1.0`) does not yet add the CHECK; tracking note in critique Round 2 response is sufficient at this severity.

**B20 (NIT — bulk import duplicate semantics):** ACKNOWLEDGED — Architect committed to silent-skip-with-skipped-count semantics tracked into US-7 task 2.2 wording at implementation time. Not blocking.

**C1..C6 (CONCERN items):** RESOLVED — these were folded into B11 (C1 image offline sync), B12 (C2 WS token leak), B13 (C3 sync pull/conflict UX), B14 (C4 distill scheduler), B15 (C5 respx vs Speech SDK), B17 (C6 shadow reader polling vs 3s) and verified above.

**N1..N3 (NIT items B18/B19/B20):** ACKNOWLEDGED — verified above; non-blocking, tracked for implementation phase.

---

## Summary — 2026-04-30 00:07 UTC

### Resolved

- **B1:** AOAI region OQ-1 — canonical Bicep template now has `param openaiLocation string = 'westus'` and `openai.location: openaiLocation`; verified in design.md and us-5 task 1.1.
- **B2:** python-jose CVE + passlib/bcrypt incompat — pinned canonical requirements at `python-jose[cryptography]>=3.5,<4`, `passlib[bcrypt]>=1.7,<2`, `bcrypt>=4.0,<4.1`; documented as table-formatted spec deviation; us-1 task 4.1 rewritten with no "Coder picks" language.
- **B3:** `CREATE EXTENSION` on Azure — canonical Data Model section opens with `CREATE EXTENSION IF NOT EXISTS vector;` (lowercase) + `"uuid-ossp"` + clarifying note that Bicep allowlist token `VECTOR` is distinct from in-DB extension name; us-1 task 3.1 references it.
- **B4:** OQ-5/OQ-6/OQ-7 missing Bicep — canonical Bicep block now includes Postgres firewall rule, full `Microsoft.App/containerApps` resource, `Microsoft.Web/staticSites` Free SKU; us-5 task 1.1 enumerates all required resources.
- **B5:** `services/vision.py` contradiction — chose spec § 4.1 location: OCR lives in `pipeline/ocr.py`, `services/vision.py` removed from project tree; us-2 task 6.1 rewritten with inline `ImageAnalysisClient` construction.
- **B6:** upload + tags routes — design project tree adds dedicated `api/upload.py` and `api/tags.py`; us-2 tasks 2.1 + 8.1 rewritten to create the modules and wire routers.
- **B7:** search SQL tags filter — canonical hybrid SQL added with `EXISTS` subquery against `note_tags ⨝ tags`; us-2 tasks 7.1 + 7.2 reference it.
- **B8:** NoteUpdate schema + manual override mitigation #6 — explicit Pydantic shape defined with mutation rules + first-class UX requirement in NoteEditor with AI-suggested badge; us-1 task 5.1 + us-4 task 2.3 enumerate fields.
- **B9:** NFR-1 < 2s — Goals P0 row + us-4 acceptance criteria reframed: 2s is feed-update, not transcript; transcript claim moved to US-9 streaming.
- **B10:** Stage 1.5 ↔ Stage 2 race — new "Pipeline state machine" subsection establishes Stage 1 → Stage 2 → Stage 1.5 ordering, SERIALIZABLE answer-merge with relinking, five invariants; us-2 task 3.2 + us-8 tasks 2.3 + 2.4 enforce it.
- **B11:** image offline sync — canonical sync-push pseudocode contains `imageBlob` branch; us-4 task 4.1 follows it.
- **B12:** WebSocket `?token=` log leak — Security section requires log scrubbing of `token=` query param + forbids logging WS handshake URL; us-5 task 1.5 includes the requirement.
- **B13:** sync pull / conflict UX — new "Sync pull flow" + "Conflict UI" subsections with canonical pseudocode and three-action UX (Keep Local / Keep Server / Merge); us-4 task 4.4 follows the pseudocode + new task 4.5 creates ConflictsPage.
- **B14:** distill scheduler vs scale-to-zero — chose `minReplicas: 1` for API container; documented in Key Decisions, canonical Bicep, Cost Budget ($87–$160 band with remediation note); us-5 task 1.5 enforces minReplicas=1.
- **B15:** respx vs Speech SDK — Test Plan adds per-service mocking-strategy table; relevant TDD Hooks updated.
- **B16:** us-7 / us-9 shared-file convention — us-7 task 3.4 made explicit no-op; us-9 task 1.3 + 1.5 use `try/except ImportError` soft-fail; work-sequence Phase 5 commentary rewritten to canonicalize convention.
- **B17:** Shadow Reader polling vs 3s NFR — 3s reframed as "from Stage 2 complete"; polling expanded to 10×2s + 5×5s (45s); us-8 acceptance + task 4.3 mirror it.
- **B18:** 1000-note p50 perf in CI — perf assertion now gated behind `--integration` + `RUN_PERF=1`, runs against deployed Postgres+pgvector; tracked for US-2 review.
- **B19:** boost_weight CHECK constraint — Architect committed to add `CHECK (boost_weight BETWEEN 0 AND 2)` in us-7 task 1.1 migration; tracked.
- **B20:** bulk import duplicate semantics — silent-skip with `{ inserted, skipped, total }` decided; tracked in us-7 task 2.2.
- **C1..C6:** folded into B11/B12/B13/B14/B15/B17 above.

### Unresolved (escalated to user)

None. All BLOCKING items are RESOLVED with verified design / task-file evidence. CONCERN items (C1..C6) were folded into the BLOCKING set and resolved alongside them. NIT items (B18/B19/B20) are acknowledged with tracking notes that are appropriate at their severity.

### Key Design Decisions Surfaced During Critique

- **Container App `minReplicas: 1` (B14):** APScheduler runs nightly distill in-process; scale-to-zero is incompatible with on-schedule cron. Cost delta ≈ +$10–15/mo; total budget band updated to $87–$160 with remediation paths if it trends toward $150 (move Distill to Container Apps Jobs and revert API to scale-to-zero, OR right-size Postgres with auto-pause).
- **Pipeline ordering Stage 1 → Stage 2 → Stage 1.5 (B10):** Deliberate departure from the spec/addendum's "Stage 1.5 between Capture and Organize". Reflect questions are best generated against a categorized + summarized note, AND the embedding generated by Stage 2 is the canonical "pre-reflection" embedding. `merge_answer_into_note` is a SERIALIZABLE transaction with `SELECT ... FOR UPDATE` + relink, eliminating the previously-implicit race.
- **Azure region split (B1):** Cognitive Services accounts go to `location` (resource-group region), but Azure OpenAI MUST go to `openaiLocation = 'westus'` because `gpt-4o-mini` and `text-embedding-3-small` are not GA in `westus2`. Output `openaiRegion` from Bicep so deploy.sh can verify.
- **Auth pin set deviation (B2):** Spec § 4.3 verbatim pins (`python-jose==3.3.*` / `passlib[bcrypt]==1.7.*`) are unsafe AND broken; canonical pin set is `python-jose>=3.5,<4` (CVE fix) + `passlib>=1.7,<2` + `bcrypt>=4.0,<4.1` (passlib compat).
- **`CREATE EXTENSION` token mismatch (B3):** Azure requires the in-DB extension name `vector` (lowercase), distinct from the Bicep `azure.extensions` allowlist token `VECTOR` (uppercase). Both forms are correct in their respective contexts and are documented in the design canonical block.
- **WebSocket auth trade-off (B12):** Query-param token is the prescribed pattern (browsers cannot send custom headers on `WebSocket(url)`), but the JWT can leak to access logs. Mitigation: explicit log-scrubbing in Container App ingress + Application Insights TelemetryProcessor; future migration to `Sec-WebSocket-Protocol` subprotocol auth at multi-user phase.
- **Source exclusivity in voice.py / speech.py (B16):** us-7 ships file-mode integration only; us-9 ships the WS handler only. Soft-fail `try/except ImportError` guard in us-9 keeps the WS handler mergeable even if us-7 has not yet landed (degrades to unboosted STT with WARN log). Merge-order rule: us-7 SHOULD land first.
- **Mitigation #6 (manual override) is first-class UX (B8):** AI-populated category/tags/mood/music_metadata show an "AI-suggested" badge until edited. Once edited, manual values are user-authoritative and the pipeline does NOT re-overwrite them on `PUT /api/notes/{id}`. Mutating `content` re-pipelines; mutating overrides does not.
- **Sync conflict UX (B13):** Conflicts UI gives Keep Local / Keep Server / Merge; conflict detection rule is `local.updatedAt > lastPull AND local.syncStatus !== 'synced'`. `lastPull` cursor lives in a Dexie `meta` table.

---

Critique complete: features/cortex-second-brain/designs/critique.md — ALL RESOLVED
