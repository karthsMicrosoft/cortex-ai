# User Story: US-4 — Voice UX + Offline (FAB, Feed, Search, Sync, Nav)

> Feature: cortex-second-brain
> Requirements: `/features/cortex-second-brain/requirements/requirements.md`
> Design: `/features/cortex-second-brain/designs/design.md`
> Spec: `SECOND_BRAIN_BUILD_SPEC.md` Phase 1 items 15–19 (section 4.2), voice UX 2.6, offline 2.7

## Acceptance Criteria

- 1-tap floating action button on capture surface starts/stops `MediaRecorder` recording.
- After capture, the **raw note appears in the feed within 2 seconds (NFR-1, B9 resolution)** — this is the offline-first IndexedDB write, not the transcript. The transcribed/cleaned content arrives 3–5s later via `POST /api/voice/upload` (file mode). The < 2s "transcript visible" claim is moved to US-9 (WebSocket streaming).
- Notes captured while offline persist in IndexedDB and sync when connection returns; conflicts surface visually via `<SyncIndicator />` badge + Conflicts page (B13).
- **Image notes captured while offline (FR-1.5) sync via the same `imageBlob` upload branch in `syncManager.pushChanges()` (B11)** — design § "Offline-First / Sync push flow" pseudocode is canonical.
- Library/Capture page renders chronological timeline of notes with category and date filters.
- Search page accepts natural-language query and renders results from `/api/search`.
- Bottom navigation has four tabs: Capture, Library, Insights, Create — visible on every authenticated page.
- Processing-status badge on each note shows current stage (`raw | transcribed | processed | enriched | failed`) per critique mitigation #5.
- **Manual override UI (B8 — spec § 3.2 mitigation #6):** `<NoteEditor />` exposes editable controls for category (six-option dropdown), tags (chip add/remove), mood (text/dropdown), and music_metadata quick-edit chips when `category='Music'`. Each AI-populated value shows an "AI-suggested" badge until the user edits it.

## Status
**Status**: Completed
**Started**: 2026-04-29
**Completed**: 2026-04-29

## Relevant Documentation
- `/features/cortex-second-brain/designs/design.md` — Voice-First UX, Offline-First, UX Changes
- `SECOND_BRAIN_BUILD_SPEC.md` § 2.6 (VoiceCapture component), § 2.7 (SyncManager), § 4.1 (component layout)

## TDD Hook
Tester writes failing tests in `frontend/src/__tests__/` (VoiceCapture, syncManager, NoteCard, BottomNav, SearchBar) using Vitest with mocked MediaRecorder, fetch, and Dexie. Coder waits for failing-tests signal before each task.

---

## Tasks

- [x] 1 Voice capture component
  - [x] 1.1 Create `frontend/src/hooks/useVoiceRecorder.ts` exposing `{ isRecording, partialText, start, stop }` — uses `MediaRecorder({mimeType:'audio/webm'})`, accumulates chunks, returns `Blob` from `stop`
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~1h
  - [x] 1.2 Create `frontend/src/components/VoiceCapture.tsx` — floating action button styled per spec § 2.6 (`bg-indigo-600` idle / `bg-red-500 animate-pulse scale-110` recording, lucide MicIcon/MicOffIcon). On stop: write LocalNote to IndexedDB (`syncStatus='pending'`), enqueue create op in `syncQueue`, trigger `syncManager.pushChanges()` if online.
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~1h
  - [x] 1.3 In `VoiceCapture.tsx` — when online, after IndexedDB write, also POST audio blob to `/api/upload` then `/api/voice/upload` to get the cleaned-text response within 2s; update LocalNote with `serverId` + transcribed content
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~30m

- [x] 2 Note display components
  - [x] 2.1 Create `frontend/src/components/NoteCard.tsx` — renders content snippet, category chip (color from formatters), date, processing badge; tap opens detail
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~1h
  - [x] 2.2 Create `frontend/src/components/ProcessingBadge.tsx` showing the five states (`raw|transcribed|processed|enriched|failed`) with appropriate icon and color (mitigation #5)
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~30m
  - [x] 2.3 Create `frontend/src/components/NoteEditor.tsx` — inline editor for (a) `content`, (b) `category` dropdown (six fixed values from the Literal), (c) `tags` chips (add via input + Enter; remove via X), (d) `mood` field (free-text input, optional dropdown of common moods), and (e) when `category === 'Music'`, a `music_metadata` quick-edit row with editable chips for tempo/key/genre/instruments. Each AI-populated field shows an "AI-suggested" pill until edited. On save, send only the changed fields via `PUT /api/notes/{id}` using `NoteUpdate` shape (B8 — backend uses `model_dump(exclude_unset=True)`). Manual edits to category/tags/mood/music_metadata MUST NOT trigger pipeline re-run (mitigation #6).
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~2h
  - [x] 2.4 Create `frontend/src/components/SearchBar.tsx` — debounced text input, calls `api/search` and emits results upward
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~30m
  - [x] 2.5 Create `frontend/src/components/SyncIndicator.tsx` — shows online/offline status and pending queue count (subscribes to Dexie `syncQueue` count)
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~30m

- [x] 3 Pages and navigation
  - [x] 3.1 Create `frontend/src/components/BottomNav.tsx` — fixed bottom bar with four tabs (Capture, Library, Insights, Create) using lucide icons; uses `react-router-dom` `<NavLink>`
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~30m
  - [x] 3.2 Create `frontend/src/pages/CapturePage.tsx` — hosts `<VoiceCapture />`, plus a text-input area for FR-1.4 manual capture, and image upload input for FR-1.5
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~1h
  - [x] 3.3 Create `frontend/src/pages/LibraryPage.tsx` — chronological timeline; category filter chips (six fixed), date range selector; reads from `noteStore` + falls back to `api/notes`
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~1h
  - [x] 3.4 Create `frontend/src/pages/SearchPage.tsx` — uses `<SearchBar />`, renders ranked results
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~30m
  - [x] 3.5 Create `frontend/src/pages/NoteDetailPage.tsx` — full note view with `<NoteEditor />`, processing badge, audio player placeholder (real player in US-6+US-9), tag chips, related notes (from `/api/search/similar/{id}`)
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~1h
  - [x] 3.6 Create stub pages `InsightsPage.tsx` and `CreatePage.tsx` with empty layout placeholders — actual content lands in US-6
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~15m
  - [x] 3.7 Update `frontend/src/App.tsx` route table — protected routes for `/`, `/library`, `/search`, `/note/:id`, `/insights`, `/create`; render `<BottomNav />` inside the protected layout
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~30m

- [x] 4 Offline sync engine
  - [x] 4.1 Create `frontend/src/sync/syncManager.ts` per design § "Offline-First / Sync push flow" — singleton class that listens to `online` event, polls every 30s, drains `syncQueue` FIFO. For `create note` ops, follow the design pseudocode exactly (B11 includes the image branch): if `note.imageBlob` present, upload it via `/api/upload` to get `imageUrl`; if `note.audioBlob` present, upload via `/api/upload` to get `audioUrl`; then `POST /api/notes` with the returned URLs. On 2xx, update LocalNote `serverId` + `syncStatus='synced'`, delete queue item.
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~2h
  - [x] 4.2 Implement retry counter — bump `retryCount` on failure; after 5 failures, move item to a separate Dexie table `deadLetter` (critique mitigation #2) and delete from `syncQueue`
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~30m
  - [x] 4.3 Create `frontend/src/hooks/useSync.ts` exposing `pendingCount`, `isSyncing`, `pushNow()` for SyncIndicator and Settings
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~30m
  - [x] 4.4 Create `frontend/src/hooks/useNotes.ts` — Dexie-backed hook combining IndexedDB local reads with the pull flow per design § "Sync pull flow (B13)". Implementation MUST follow the canonical pseudocode: (a) persist `lastPull` cursor in a Dexie `meta` table (`stores: { meta: 'key' }`); (b) trigger pull on app boot, on `online` event, and every 60s while foreground; (c) merge by `serverId`; (d) flag `syncStatus='conflict'` when `local.updatedAt > lastPull AND local.syncStatus !== 'synced'`, freezing the server payload as `conflictServerVersion` for the Conflicts UI.
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~1h
  - [x] 4.5 Create `frontend/src/pages/ConflictsPage.tsx` (B13 — conflict resolution UI) — lists notes where `syncStatus='conflict'` with a Local vs Server side-by-side card and three actions: "Keep Local" (PUT /api/notes/{serverId} with local payload), "Keep Server" (overwrite local with `conflictServerVersion`), "Merge" (open `<NoteEditor />` prefilled with diff). After action, set `syncStatus='synced'`. `<SyncIndicator />` shows a red badge with the conflict count and links here.
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: ~1h
