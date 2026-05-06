# Cortex — Second Brain Application — Requirements

**Feature:** cortex-second-brain
**Type:** New Feature (full application)
**Author:** Karthik Subramanian (translated by PM agent)
**Date:** 2026-04-29
**Status:** Draft

> Source documents (verbatim translation, not re-interviewed):
> - `C:\Users\karths\dev\Projects\cortex\SECOND_BRAIN_BUILD_SPEC.md` — Section 1 (Requirements)
> - `C:\Users\karths\dev\Projects\cortex\SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md` — Sections F1.1 (Personal Dictionary) and F2.1 (Shadow Reader)

---

## 1. Overview

Cortex is a personal AI-powered knowledge management system — a "second brain" — optimized for frictionless voice-first capture, multi-modal input (voice, text, images), AI-assisted thinking (auto-tagging, summarization, pattern detection, creative generation), semantic retrieval over personal knowledge, and dedicated support for music ideation (humming, melodies, whistling). Delivered as a mobile-first PWA backed by an Azure-hosted FastAPI service, Cortex is a personal RAG system over its single owner's life data, not a generic note-taking app. The MVP targets a single user (the author) and is designed to feel like an extension of memory rather than a database, with two Phase-2 enhancements — Personal Dictionary (custom vocabulary that boosts STT accuracy) and Shadow Reader (gentle AI follow-up questions that deepen captured thoughts) — folded into the same system.

## 2. Problem & Context

**User:** Karthik (single-user MVP). A musician/engineer who captures ideas across many domains (music, fitness, journaling, ideas, spiritual reflections, learning) and wants a single, fast, voice-first place that both stores those captures and helps him think about them later.

**Specific friction points:**
- Existing note apps are not voice-first; capturing a hummed melody or a fleeting idea takes too many taps.
- Generic STT mishears domain-specific vocabulary — names ("Karthik", "Daniel Anvar"), music terms ("Phrygian mode", "arpeggio"), and technical jargon ("pgvector", "Cosmos DB") — making voice notes unreliable.
- Captured notes sit inert: there is no automated organization (tags, categories, semantic links), no daily/weekly distillation, and no surfacing of patterns or related ideas.
- Search is keyword-only in most tools; the user wants natural-language semantic retrieval ("Find my melody ideas from last week").
- Captures are often shallow because the user is in flow and does not pause to elaborate — there is no gentle prompt to go one level deeper while the thought is fresh.

**Why now?** The author wants a personal RAG system that fits within a strict $150/month Azure budget and showcases the CODE framework (Capture, Organize, Distill, Express). Cortex consolidates the capture+organize+retrieve+create loop into one system shaped around how he actually thinks.

**Current state:** No existing codebase to integrate with — this is a greenfield monorepo (`/frontend`, `/backend`, `/infra`, `/docs`). All Azure resources will be newly provisioned in `westus2`.

**Stakeholders:** The single owner-user (Karthik). No external teams or downstream consumers in the MVP.

## 3. Goals

1. **G1 — Frictionless capture:** A voice note must go from "stop recording" to "clean, structured note visible on screen" in under 2 seconds (NFR-1).
2. **G2 — Useful retrieval:** Semantic search across all notes returns relevant results in under 500ms p50 (NFR-2).
3. **G3 — Stays within budget:** Total Azure spend remains at or under $150/month for expected single-user volume (NFR-4).
4. **G4 — Works offline:** Full capture + read flows work with no network connectivity, with background sync on reconnect (NFR-3, FR-6.1).
5. **G5 — STT accuracy on personal vocabulary:** With Personal Dictionary populated, STT correctly transcribes a measurable majority of user-supplied domain terms that previously failed (Phase-2 Acceptance: measurable improvement on 10 known-difficult terms).
6. **G6 — Deepening without disruption:** Shadow Reader surfaces 1–2 contextual follow-up questions for substantive notes within 3 seconds, dismissible with one tap, and never blocks capture flow.

## 4. User Stories

1. **Story 1 — Voice capture (P0):** As the user, I want to tap one button, speak, and stop, so that my words are transcribed, cleaned, categorized, and saved without any further action from me.
2. **Story 2 — Text capture (P0):** As the user, I want to type a note manually, so that I can journal or jot ideas when speaking aloud isn't appropriate.
3. **Story 3 — Image capture with OCR (P1):** As the user, I want to upload an image and have its text extracted via OCR, so that handwritten or printed material can join my searchable knowledge base.
4. **Story 4 — Auto-organize (P0):** As the user, I want every captured note to be auto-tagged, auto-categorized into one of six domains, and embedded for semantic search, so that my library organizes itself without manual filing.
5. **Story 5 — Semantic search (P0):** As the user, I want to type a natural-language query like "Find my melody ideas from last week" and get semantically relevant notes, so that I can recall thoughts without remembering exact words.
6. **Story 6 — Filter and browse (P0):** As the user, I want to filter notes by category, tag, and date range, so that I can scope my search when I know roughly where to look.
7. **Story 7 — Hybrid search (P1):** As the user, I want hybrid keyword + semantic search, so that exact terms (e.g. song titles) and concepts both rank well.
8. **Story 8 — Timeline feed (P0):** As the user, I want a chronological feed of my notes on the home screen, so that recent captures are immediately visible.
9. **Story 9 — Bottom navigation (P0):** As the user, I want a four-tab bottom navigation (Capture, Library, Insights, Create), so that core surfaces are reachable in one tap on mobile.
10. **Story 10 — Brain View (P1):** As the user, I want a Brain View that shows AI summaries plus a graph of connected ideas, so that I can see how my thinking links together.
11. **Story 11 — Dark mode by default (P0):** As the user, I want dark mode by default, so that the app is comfortable to use day and night.
12. **Story 12 — Music labeling (P1):** As the user, I want music notes to support quick labeling of tempo, mood, and genre, plus audio playback with a waveform, so that musical captures are reviewable.
13. **Story 13 — Daily / weekly distill (P1):** As the user, I want daily and weekly AI summaries with key ideas and patterns highlighted, so that I see the through-line of my thinking without re-reading every note.
14. **Story 14 — Express (P2):** As the user, I want the system to generate song ideas from voice notes, practice plans from fitness logs, and reflections from journal entries, so that captures fuel new creative output.
15. **Story 15 — Offline capture (P0):** As the user, I want to capture and read notes with no network, so that I never lose a fleeting thought because of connectivity.
16. **Story 16 — Export (P1):** As the user, I want to export all my data as JSON plus the original media files, so that I am never locked in.
17. **Story 17 — Authenticated access (P0):** As the user, I want JWT-based login with refresh tokens, so that my personal corpus is protected.
18. **Story 18 — Add personal dictionary term (P1, Phase 2):** As the user, I want to add custom vocabulary terms (names, music terms, technical jargon, places, acronyms) from a settings page, so that subsequent voice recordings transcribe those terms correctly.
19. **Story 19 — Manage personal dictionary (P1, Phase 2):** As the user, I want to view, edit, and delete my dictionary terms, and bulk-import from CSV/JSON, so that I can curate my vocabulary over time.
20. **Story 20 — Cross-device sync of dictionary (P1, Phase 2):** As the user, I want my dictionary to be per-user and synced across devices, so that the same vocabulary boost is available anywhere I record.
21. **Story 21 — Receive Shadow Reader prompts (P1, Phase 2):** As the user, after capturing a substantive note (>= 50 words), I want 1–2 gentle, category-appropriate follow-up questions, so that I can voluntarily go one level deeper while the thought is fresh.
22. **Story 22 — Answer or dismiss Shadow Reader (P0/P1, Phase 2):** As the user, I want to answer Shadow Reader questions by voice or text and have the answer appended to the note as a "Reflection" section (with the embedding regenerated), or dismiss the prompt with one tap, so that deepening is always optional and never blocks me.
23. **Story 23 — Configure Shadow Reader (P0, Phase 2):** As the user, I want a global on/off toggle and per-category opt-out for Shadow Reader in settings, so that I never see prompts in contexts where they would be intrusive (e.g. quick fitness logs).

## 5. Functional Requirements

Numbered at the capability level. IDs preserve the spec's original numbering for traceability.

### Phase 1 — Core Cortex

**Input modes (FR-1):**
- **FR-1.1 (P0):** The system must support voice capture with a 1-tap record button. *(supports Story 1)*
- **FR-1.2 (P0):** The system must auto-transcribe voice input via streaming speech-to-text. *(supports Story 1)*
- **FR-1.3 (P0):** The system must preserve the original audio file alongside the transcription. *(supports Story 1, Story 12)*
- **FR-1.4 (P0):** The system must support manual text input for notes and journaling. *(supports Story 2)*
- **FR-1.5 (P1):** The system must support image upload with OCR text extraction. *(supports Story 3)*

**AI processing pipeline — CODE framework (FR-2):**
- **FR-2.1 (P0) — Capture:** The system must clean raw transcription into a structured note. *(supports Story 1)*
- **FR-2.2 (P0) — Organize:** The system must auto-tag, auto-categorize, and generate embeddings for every note. *(supports Story 4)*
- **FR-2.3 (P1) — Organize:** The system must link semantically related notes. *(supports Story 10)*
- **FR-2.4 (P1) — Distill:** The system must produce daily and weekly summaries. *(supports Story 13)*
- **FR-2.5 (P1) — Distill:** The system must extract key ideas and highlight patterns. *(supports Story 13)*
- **FR-2.6 (P2) — Express:** The system must be able to generate song ideas from voice notes. *(supports Story 14)*
- **FR-2.7 (P2) — Express:** The system must be able to generate practice plans from fitness logs. *(supports Story 14)*
- **FR-2.8 (P2) — Express:** The system must be able to generate reflections from journal entries. *(supports Story 14)*

**Search system (FR-3):**
- **FR-3.1 (P0):** The system must support semantic search via vector embeddings. *(supports Story 5)*
- **FR-3.2 (P0):** The system must support natural-language queries (e.g. "Find my melody ideas from last week"). *(supports Story 5)*
- **FR-3.3 (P0):** The system must allow filtering by category, tag, and date range. *(supports Story 6)*
- **FR-3.4 (P1):** The system must support hybrid (keyword + semantic) search. *(supports Story 7)*

**User interface (FR-4):**
- **FR-4.1 (P0):** The system must be a mobile-first PWA installable on iOS and Android. *(supports all UI stories)*
- **FR-4.2 (P0):** The capture surface must include a floating 1-tap voice action button. *(supports Story 1)*
- **FR-4.3 (P0):** The home screen must present a chronological timeline-based note feed. *(supports Story 8)*
- **FR-4.4 (P0):** The system must provide bottom navigation with four tabs: Capture, Library, Insights, Create. *(supports Story 9)*
- **FR-4.5 (P1):** The system must provide a Brain View page showing AI summaries plus a graph of connected ideas. *(supports Story 10)*
- **FR-4.6 (P0):** The system must default to dark mode. *(supports Story 11)*

**Music-specific features (FR-5):**
- **FR-5.1 (P0):** The system must allow audio notes to be tagged with the "Music" category. *(supports Story 12)*
- **FR-5.2 (P1):** The system must support audio playback with waveform visualization. *(supports Story 12)*
- **FR-5.3 (P1):** The system must support quick labeling of tempo, mood, and genre on music notes. *(supports Story 12)*
- **FR-5.4 (P2):** The system must include a placeholder for MIDI/DAW export. *(supports Story 14)*

**Data management (FR-6):**
- **FR-6.1 (P0):** The system must support offline capture with background sync on reconnect. *(supports Story 15)*
- **FR-6.2 (P1):** The system must export all user data as JSON plus original media files. *(supports Story 16)*
- **FR-6.3 (P1):** The system must use standard formats so the user is not locked in. *(supports Story 16)*

### Phase 2 — Personal Dictionary (FR-7)

- **FR-7.1 (P1):** The system must allow the user to add custom terms to a personal vocabulary. *(supports Story 18)*
- **FR-7.2 (P1):** Each term must have a type from the set {name, music_term, technical, place, acronym, general}. *(supports Story 18)*
- **FR-7.3 (P2):** Each term may carry an optional pronunciation hint (e.g. "Karthik = car-thick"). *(supports Story 18)*
- **FR-7.4 (P1):** The user's dictionary must be loaded into the streaming STT engine before each voice session, so subsequent recordings benefit from the boost. *(supports Story 18, Story 20)*
- **FR-7.5 (P1):** The user must be able to view, edit, and delete dictionary terms. *(supports Story 19)*
- **FR-7.6 (P1):** The dictionary must be per-user and synced across devices. *(supports Story 20)*
- **FR-7.7 (P2):** The system must support bulk import of terms from CSV/JSON. *(supports Story 19)*
- **FR-7.8 (derived):** The system must enforce a hard upper bound on dictionary size per user (2,000 terms total).
- **FR-7.9 (derived):** The system must track usage of dictionary terms (incrementing a usage counter when the term appears in a transcription) so that the highest-value terms remain prioritized when the per-session phrase budget is exceeded.

### Phase 2 — Shadow Reader (FR-8)

- **FR-8.1 (P1):** After capture, the system must generate 1–2 follow-up questions tailored to the note. *(supports Story 21)*
- **FR-8.2 (P0):** Questions must be dismissible without penalty. *(supports Story 22)*
- **FR-8.3 (P1):** Question style must vary by category (e.g. Music vs Journal vs Ideas). *(supports Story 21)*
- **FR-8.4 (P1):** The user must be able to answer via voice or text. *(supports Story 22)*
- **FR-8.5 (P1):** The user's answer must be appended to the note as a "Reflection" section. *(supports Story 22)*
- **FR-8.6 (P1):** The note's embedding must be regenerated after a Reflection is added. *(supports Story 22)*
- **FR-8.7 (P0):** The system must provide a global settings toggle to enable/disable Shadow Reader. *(supports Story 23)*
- **FR-8.8 (P1):** Shadow Reader must only trigger on substantive notes (>= 50 words). *(supports Story 21)*
- **FR-8.9 (P2):** The user must be able to mark individual categories as "never ask" (e.g. quick fitness logs). *(supports Story 23)*
- **FR-8.10 (derived):** The system must cap output at 2 questions, each <= 15 words.
- **FR-8.11 (derived):** A given note's Shadow Reader prompt is single-shot — dismissing or answering once does not retrigger for the same note, and dismissing one note's prompt must not affect future notes.

## 6. Non-Functional Requirements

- **Performance:**
  - **NFR-1:** Voice feedback latency from "stop recording" to "clean note visible" must be < 2 seconds.
  - **NFR-2:** Semantic search response time must be < 500ms.
  - **NFR-6:** API CRUD response time at p95 must be < 300ms.
  - **Phase 2 perf:** Shadow Reader questions must appear within 3 seconds of note creation; embedding regeneration after a Reflection answer must run asynchronously and not block the UI return.
- **Scalability:** Single-user MVP. Expected volume: ~1,000 notes/month. The architecture must remain within Azure budget at this volume; design must not preclude future single-user growth to ~10× without re-platforming.
- **Security:**
  - **NFR-7:** Data must be encrypted at rest (Azure default) and in transit (TLS 1.2+).
  - **NFR-8:** Authentication must be JWT-based with refresh tokens.
  - Personal Dictionary entries (which may contain personal names) must be protected with the same encryption posture as notes and must never be written to logs.
- **Reliability:** Offline capture and read must work fully without connectivity (NFR-3); on reconnect, background sync must reconcile pending notes. Shadow Reader prompts must be single-shot per note and dismissible at any time without losing the underlying note.
- **Observability:** The system must log enough information to diagnose pipeline-stage failures (capture, organize, distill, reflect) without logging note contents or dictionary contents. Speech sessions should record how many phrase-list entries were loaded for verification. (Detailed logging schema is for the Architect.)
- **Cost:**
  - **NFR-4:** Total monthly Azure cost must be ≤ $150.
  - The Phase-2 additions must add no more than ~$0.20/month at expected volume (Personal Dictionary adds $0; Shadow Reader adds ~$0.11/month at 1,000 notes).
- **Quality bar:**
  - **NFR-5:** PWA Lighthouse score must be ≥ 90 on Performance, Accessibility, and Best Practices.

## 7. API / Interface Requirements

The system exposes a backend HTTP/WebSocket surface to the PWA frontend. Detailed contracts are for the Architect; the following capabilities must exist:

- **Authentication:** JWT login, refresh, current-user endpoints.
- **Notes CRUD:** create, list (with filters: category, tag, date range), get, update, delete.
- **Capture:** voice ingestion (streaming WebSocket for STT), image upload (OCR), and text submission.
- **Search:** semantic search endpoint accepting natural-language queries; hybrid search variant.
- **AI pipeline:** server-side processing of capture → organize → (Phase 2) reflect → organize completion; processing-status visible per note.
- **Distill:** daily and weekly summary endpoints (read), plus a scheduled task to generate them.
- **Brain View / links:** endpoint returning graph data (notes + semantic links) and pattern-detection output.
- **Personal Dictionary (Phase 2):** list (filterable by type), add, update, delete, bulk-import, export. Dictionary must be loaded into the STT recognizer at the start of each voice session.
- **Shadow Reader (Phase 2):** poll for questions per note, submit answer, dismiss; user-level settings endpoint to toggle the feature globally and per-category.
- **Export:** full data export as JSON plus media files.
- **Error handling:** standard error envelope with machine-readable codes; integrity violations (e.g. duplicate dictionary term) must return a distinct conflict response so the UI can show a clear message.
- **Versioning:** single-owner MVP — no formal API versioning is required for MVP; the Architect should leave a clear path to add `/v1/` prefixes later.
- **Consumers:** the Cortex PWA only.

## 8. Scope

### In Scope (MVP — Phase 1)

- Voice, text, and image capture with streaming STT and OCR.
- The CODE pipeline: Capture (clean), Organize (tag/categorize/embed/link), Distill (daily/weekly summaries, key ideas, patterns), and the P2 Express generators (song ideas, practice plans, reflections).
- Six fixed categories: Music, Fitness, Journal, Ideas, Spiritual, Learning.
- Mobile-first PWA with timeline feed, four-tab bottom nav, dark mode, audio playback + waveform, music quick-labels (tempo/mood/genre), Brain View, Insights.
- Semantic and hybrid search with category/tag/date filters.
- Offline capture + read, background sync, full data export.
- JWT auth with refresh tokens.
- Single-user MVP (the author).

### In Scope (Phase 2 — included in this requirements doc)

- Personal Dictionary CRUD, bulk import, per-user storage, per-session loading into the STT engine, usage tracking.
- Shadow Reader pipeline stage, per-note question generation, answer/dismiss flows, Reflection appended to note + embedding regeneration, global toggle and per-category opt-out.

### Out of Scope

- Multi-user / team / collaboration features (single-owner MVP).
- A native iOS or Android binary — PWA only.
- DAW / MIDI export beyond a UI placeholder (FR-5.4 ships as a stub only).
- Federated identity, SSO, or SCIM provisioning.
- Payment, billing, subscription tiers.
- A formal API versioning scheme beyond a single un-versioned surface.
- Server-side processing of media beyond audio format conversion and OCR — no music transcription, pitch detection, or BPM detection in MVP.
- Real-time collaborative editing of notes.
- A non-fixed taxonomy: the six categories are fixed in MVP; users cannot add new top-level categories.
- Any external API integrations (calendar, email, Slack, etc.) in MVP.
- Automatic web crawling, RSS ingestion, or browser-extension capture.
- Any feature requiring exceeding the $150/month budget.

## 9. Constraints & Dependencies

### Technical Constraints (as stated in the source spec)

- **Budget:** Total Azure spend ≤ $150/month (NFR-4). Phase-2 additions must add ≤ ~$0.20/month at 1,000 notes/month.
- **Region:** All Azure resources in `westus2` unless specified otherwise.
- **Repository structure:** Monorepo with `/frontend`, `/backend`, `/infra`, `/docs`.
- **Deployment surface:** Azure Container Apps (backend) + Azure Static Web Apps (frontend).
- **Framework:** CODE (Capture → Organize → Distill → Express). Shadow Reader inserts a new stage 1.5 (Reflect) between Capture and Organize.
- **Design philosophy:** "Frictionless capture > everything. AI augments thinking, does not replace it. System feels like an extension of memory, not a database."
- **Six fixed categories:** Music, Fitness, Journal, Ideas, Spiritual, Learning.
- **STT phrase-list cap:** Azure Speech PhraseListGrammar caps at ~500 phrases per session — the system must handle dictionaries larger than that by selecting top-N by usage.
- **Source spec sections:** This requirements document is a translation of `SECOND_BRAIN_BUILD_SPEC.md` Section 1 and `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md` Sections F1.1 and F2.1 — those documents remain authoritative for richer context the Architect should consult.

### Timeline Constraints

- Phase 1 (core MVP) and Phase 2 (Personal Dictionary + Shadow Reader) are both in scope for this workforce run.
- The source spec estimates Personal Dictionary at ~1 day and Shadow Reader at ~2–3 days of effort once Phase 1 is in place. No external hard deadline.

### Dependencies

- **Dependent on (external services that must be available):**
  - Azure Container Apps (backend hosting)
  - Azure Static Web Apps (frontend hosting)
  - Azure PostgreSQL Flexible Server (with pgvector)
  - Azure Blob Storage (audio + image)
  - Azure Speech Service (streaming STT, including PhraseListGrammar for FR-7.4)
  - Azure OpenAI (text generation + embeddings; GPT-4o-mini class + text-embedding-3-small class)
  - Azure AI Vision (OCR for FR-1.5)
- **Dependents:** The Cortex PWA only. No downstream consumers.

## 10. Design Considerations *(optional, from the source spec)*

UI/UX cues drawn from the source spec — these are notes from the author, not new design decisions:

- **Mobile-first PWA**, dark mode by default.
- **Four-tab bottom navigation:** Capture, Library, Insights, Create.
- **Floating 1-tap voice action button** is the primary capture affordance.
- **Timeline feed** on the home screen.
- **Brain View page:** AI summaries combined with a force-directed graph of semantic links.
- **Personal Dictionary settings UI:** an inline add field with a type selector and a chip-style list of existing terms (each removable). Type-color coded (name/music/technical/place/acronym/general).
- **Shadow Reader prompt UI:** a soft slide-up from the bottom of the screen (never modal-blocking), dismissible with one X tap, with both text and voice answer affordances.
- **Shadow Reader settings UI:** a single global on/off toggle with a chip list of categories that can be marked "never ask".
- **Tone of Shadow Reader prompts:** category-aware and warm — Music asks about emotion/instrumentation, Journal asks compassionately about feelings beneath the surface, Ideas asks sharply about smallest next step, Fitness asks one short body-feel question, Spiritual asks contemplatively, Learning asks about connection/application.
- **Design philosophy preserved across all UX:** AI augments thinking, does not replace it. Frictionless capture comes before all other concerns.

## 11. Success Metrics

### Acceptance Criteria — Phase 1

- Voice note "stop recording → clean note visible" elapsed time is < 2s.
- Semantic search returns results in < 500ms p50 across at least 1,000 stored notes.
- Capture, read, and timeline browsing work fully offline; pending notes sync correctly when network returns.
- Lighthouse score on the PWA ≥ 90 for Performance, Accessibility, and Best Practices.
- Total measured Azure spend over a representative month ≤ $150.
- Auth: JWT login + refresh works; an unauthenticated user cannot access any note or media URL.
- Six categories work end-to-end (capture → categorize → list/filter → search).
- Brain View renders a graph of semantically linked notes.
- Daily and weekly summaries are generated on schedule.
- Full data export produces JSON + media files that round-trip on visual inspection.

### Acceptance Criteria — Phase 2: Personal Dictionary

- A user can add a term in < 10 seconds from the settings page.
- The next voice recording uses the updated dictionary (verifiable via server log showing the phrase-list size on each WebSocket connection).
- STT accuracy on dictionary terms is measurably higher than baseline on a manual test of 10 known-difficult terms (at least a majority correctly transcribed where they previously failed).
- Dictionary entries persist across app restarts.
- Hard limit of 2,000 terms per user is enforced (POST returns a clear error when the limit would be exceeded).
- Bulk import of up to 500 terms in one request succeeds; oversized requests are rejected with a clear error.
- DELETE removes a term and the UI updates.
- The Settings page renders the dictionary correctly on mobile and desktop.

### Acceptance Criteria — Phase 2: Shadow Reader

- For notes ≥ 50 words with the feature enabled and category not opted out, 1–2 questions appear within 3 seconds.
- For notes < 50 words, no questions are generated.
- The global off-toggle prevents all questions immediately; the per-category opt-out works (e.g. disabling Fitness still yields questions for Music).
- The dismiss button hides the prompt and sets the note's status to `dismissed`.
- Submitting an answer appends a `--- Reflection ---` section to the note's content and regenerates the embedding (verifiable by re-running a similar-search that should now match the reflection).
- Voice input works for the answer on mobile.
- All six categories produce contextually appropriate prompts on a manual review.
- The prompt component never blocks the rest of the UI and is dismissible at any time.
- Per-note dismissal does not affect future notes.

### Post-launch Metrics (single-user)

- Capture frequency: ≥ 5 captures per active day on average across the first month.
- Dictionary usage: ≥ 20 terms added within the first week of Phase 2 release.
- Shadow Reader engagement: of substantive notes that trigger a prompt, ≥ 30% are answered (rather than dismissed) — a soft target indicating prompts feel useful, not annoying.
- Azure cost stays at or below $150/month for ≥ 3 consecutive months.

## 12. Open Questions

None. All previously open questions were resolved against the source spec:

- **Multi-user vs single-user?** Resolved: single-user MVP (the author).
- **Native app vs PWA?** Resolved: PWA only.
- **Category taxonomy mutable?** Resolved: six fixed categories in MVP.
- **STT phrase-list size > 500?** Resolved: order by `usage_count` descending and load top-500 (FR-7.9 derived).
- **Dictionary upper bound?** Resolved: 2,000 terms per user (FR-7.8 derived).
- **Shadow Reader trigger threshold?** Resolved: ≥ 50 words.
- **Shadow Reader question cap?** Resolved: max 2 questions, ≤ 15 words each.
- **Embedding regeneration latency?** Resolved: runs async after the answer is saved; UI returns immediately.
- **Where in pipeline does Shadow Reader sit?** Resolved: new Stage 1.5 between Capture and Organize.
- **Versioning?** Resolved: no formal API versioning in MVP; leave room for a future `/v1/` prefix.
