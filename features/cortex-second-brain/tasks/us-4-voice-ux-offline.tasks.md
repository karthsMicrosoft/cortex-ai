# User Story: US-4 — Voice UX + Offline (FAB, Feed, Search, Sync, Nav)

> Feature: cortex-second-brain
> Requirements: `/features/cortex-second-brain/requirements/requirements.md`
> Design: `/features/cortex-second-brain/designs/design.md`
> Spec: `SECOND_BRAIN_BUILD_SPEC.md` Phase 1 items 15–19 (section 4.2), voice UX 2.6, offline 2.7

## Acceptance Criteria

- 1-tap floating action button on capture surface starts/stops `MediaRecorder` recording.
- After capture, raw transcript displays within 2 seconds (NFR-1) — for US-4 this uses `POST /api/voice/upload` (file mode); WS streaming arrives in US-9.
- Notes captured while offline persist in IndexedDB and sync when connection returns; conflicts surface visually.
- Library/Capture page renders chronological timeline of notes with category and date filters.
- Search page accepts natural-language query and renders results from `/api/search`.
- Bottom navigation has four tabs: Capture, Library, Insights, Create — visible on every authenticated page.
- Processing-status badge on each note shows current stage (`raw | transcribed | processed | enriched | failed`) per critique mitigation #5.

## Status
**Status**: Not Started
**Started**: TBD
**Completed**: TBD

## Relevant Documentation
- `/features/cortex-second-brain/designs/design.md` — Voice-First UX, Offline-First, UX Changes
- `SECOND_BRAIN_BUILD_SPEC.md` § 2.6 (VoiceCapture component), § 2.7 (SyncManager), § 4.1 (component layout)

## TDD Hook
Tester writes failing tests in `frontend/src/__tests__/` (VoiceCapture, syncManager, NoteCard, BottomNav, SearchBar) using Vitest with mocked MediaRecorder, fetch, and Dexie. Coder waits for failing-tests signal before each task.

---

## Tasks

- [ ] 1 Voice capture component
  - [ ] 1.1 Create `frontend/src/hooks/useVoiceRecorder.ts` exposing `{ isRecording, partialText, start, stop }` — uses `MediaRecorder({mimeType:'audio/webm'})`, accumulates chunks, returns `Blob` from `stop`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.2 Create `frontend/src/components/VoiceCapture.tsx` — floating action button styled per spec § 2.6 (`bg-indigo-600` idle / `bg-red-500 animate-pulse scale-110` recording, lucide MicIcon/MicOffIcon). On stop: write LocalNote to IndexedDB (`syncStatus='pending'`), enqueue create op in `syncQueue`, trigger `syncManager.pushChanges()` if online.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.3 In `VoiceCapture.tsx` — when online, after IndexedDB write, also POST audio blob to `/api/upload` then `/api/voice/upload` to get the cleaned-text response within 2s; update LocalNote with `serverId` + transcribed content
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 2 Note display components
  - [ ] 2.1 Create `frontend/src/components/NoteCard.tsx` — renders content snippet, category chip (color from formatters), date, processing badge; tap opens detail
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.2 Create `frontend/src/components/ProcessingBadge.tsx` showing the five states (`raw|transcribed|processed|enriched|failed`) with appropriate icon and color (mitigation #5)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.3 Create `frontend/src/components/NoteEditor.tsx` — inline editor for content + category dropdown (six fixed) + tag chips; `PUT /api/notes/{id}` on save
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.4 Create `frontend/src/components/SearchBar.tsx` — debounced text input, calls `api/search` and emits results upward
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.5 Create `frontend/src/components/SyncIndicator.tsx` — shows online/offline status and pending queue count (subscribes to Dexie `syncQueue` count)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 3 Pages and navigation
  - [ ] 3.1 Create `frontend/src/components/BottomNav.tsx` — fixed bottom bar with four tabs (Capture, Library, Insights, Create) using lucide icons; uses `react-router-dom` `<NavLink>`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.2 Create `frontend/src/pages/CapturePage.tsx` — hosts `<VoiceCapture />`, plus a text-input area for FR-1.4 manual capture, and image upload input for FR-1.5
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.3 Create `frontend/src/pages/LibraryPage.tsx` — chronological timeline; category filter chips (six fixed), date range selector; reads from `noteStore` + falls back to `api/notes`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.4 Create `frontend/src/pages/SearchPage.tsx` — uses `<SearchBar />`, renders ranked results
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.5 Create `frontend/src/pages/NoteDetailPage.tsx` — full note view with `<NoteEditor />`, processing badge, audio player placeholder (real player in US-6+US-9), tag chips, related notes (from `/api/search/similar/{id}`)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.6 Create stub pages `InsightsPage.tsx` and `CreatePage.tsx` with empty layout placeholders — actual content lands in US-6
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.7 Update `frontend/src/App.tsx` route table — protected routes for `/`, `/library`, `/search`, `/note/:id`, `/insights`, `/create`; render `<BottomNav />` inside the protected layout
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 4 Offline sync engine
  - [ ] 4.1 Create `frontend/src/sync/syncManager.ts` per design "Offline-First" / spec § 2.7 — singleton class that listens to `online` event, polls every 30s, drains `syncQueue` FIFO; for `create note` ops, uploads audioBlob via `/api/upload` then `POST /api/notes` with returned `audio_url`. On 2xx, update LocalNote `serverId` + `syncStatus='synced'`, delete queue item.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.2 Implement retry counter — bump `retryCount` on failure; after 5 failures, move item to a separate Dexie table `deadLetter` (critique mitigation #2) and delete from `syncQueue`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.3 Create `frontend/src/hooks/useSync.ts` exposing `pendingCount`, `isSyncing`, `pushNow()` for SyncIndicator and Settings
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.4 Create `frontend/src/hooks/useNotes.ts` — Dexie-backed hook combining IndexedDB local reads with server pulls via `/api/sync/pull?since=<lastPull>`; merges by `serverId`, prefers server version on conflict but flags `syncStatus='conflict'` if local was edited after pull
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
