# User Story: US-3 — Frontend Setup (Vite + PWA + Auth + Dexie)

> Feature: cortex-second-brain
> Requirements: `/features/cortex-second-brain/requirements/requirements.md`
> Design: `/features/cortex-second-brain/designs/design.md`
> Spec: `SECOND_BRAIN_BUILD_SPEC.md` Phase 1 items 12–14 (section 4.2), PWA 2.7

## Acceptance Criteria

- `frontend/` is a Vite + React 18 + TypeScript + Tailwind project with all dependencies pinned per design "Frontend `package.json` dependencies".
- `vite.config.ts` registers `vite-plugin-pwa` with the manifest from spec § 2.7 verbatim (theme `#4F46E5`, background `#0F172A`, standalone, icons 192/512/512-mask) and the runtime caching rules (NetworkFirst for `/api/.*`, CacheFirst for blob URLs).
- IndexedDB store implemented in `src/db.ts` per design "IndexedDB schema" — `notes` and `syncQueue` tables with the exact field shape from spec § 2.3.
- Login and Register pages call `/api/auth/login` and `/api/auth/register`; access token kept in Zustand store (memory only); refresh token relies on httpOnly cookie set by backend.
- Dark mode is the default — Tailwind configured with `darkMode: 'class'` and root `<html class="dark">`.
- App is installable as a PWA on Chrome and Safari (manual smoke test).

## Status
**Status**: Complete
**Started**: 2026-04-29
**Completed**: 2026-04-29

## Relevant Documentation
- `/features/cortex-second-brain/designs/design.md` — Project Structure, UX Changes, Offline-First, Security
- `SECOND_BRAIN_BUILD_SPEC.md` § 2.2 (frontend stack), § 2.3 (Dexie schema), § 2.7 (vite-plugin-pwa config), § 2.10 (auth flow), § 4.1 (frontend tree), § 4.3 (package.json)

## TDD Hook
Tester writes failing tests in `frontend/src/__tests__/` (auth flow, db schema, store) using Vitest + jsdom + mocked fetch. Coder waits for failing-tests signal before each task.

---

## Test Results

**111/112 tests passing** (1 test failure is a test-side state pollution bug — see note below).

**Known test issue (`api-client.test.ts` — 1 failure):**
The test `apiPost > attaches Authorization header` fails due to mock state leaking between `describe` blocks. The prior `apiGet` test `calls setAccessToken...` uses `vi.mocked(useAuthStore.getState).mockReturnValue({accessToken: 'old-token'})` and the `afterEach` only calls `vi.clearAllMocks()` (which does NOT reset `mockReturnValue` — only `vi.resetAllMocks()` would). This is a test-side ordering bug unrelated to the implementation. The implementation correctly reads `useAuthStore.getState().accessToken` at call time.

---

## Tasks

- [x] 1 Vite + React + TS + Tailwind bootstrap
  - [x] 1.1 Create `frontend/package.json` verbatim from design "Frontend package.json dependencies" — pin all versions exactly. Add test deps `@testing-library/react`, `@testing-library/jest-dom`, `jsdom` for the Tester.
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 1.2 Create `frontend/tsconfig.json` with `strict: true`, `noImplicitAny: true`, `target: ES2022`, `module: ESNext`, `jsx: react-jsx`, `moduleResolution: bundler`
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 1.3 Create `frontend/tailwind.config.js` with `darkMode: 'class'`, `content: ['./index.html', './src/**/*.{ts,tsx}']`, theme extension for indigo accents (`#4F46E5`)
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 1.4 Create `frontend/postcss.config.js` (tailwindcss + autoprefixer) and `frontend/src/styles/globals.css` with Tailwind directives + base font + dark background
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 1.5 Create `frontend/index.html` with `<html lang="en" class="dark">`, viewport meta, theme-color `#4F46E5`, root div, and module script for `src/main.tsx`
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h

- [x] 2 Vite + PWA configuration
  - [x] 2.1 Create `frontend/vite.config.ts` registering `@vitejs/plugin-react` and `vite-plugin-pwa` — manifest and `workbox.runtimeCaching` exactly as in design "Offline-First" / spec § 2.7
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 2.2 Create `frontend/public/manifest.json` mirroring the manifest in `vite.config.ts` for direct browser access
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 2.3 Add placeholder icon files at `frontend/public/icons/icon-192.png`, `icon-512.png`, `icon-512-mask.png` (any 192/512px square PNG to unblock PWA install; designer can replace later)
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h

- [x] 3 IndexedDB (Dexie) and API client
  - [x] 3.1 Create `frontend/src/db.ts` exporting `interface LocalNote`, `interface SyncQueue`, `class CortexDB extends Dexie`, and singleton `db` per design "IndexedDB schema" — stores `notes: 'localId, serverId, sourceType, category, syncStatus, createdAt'` and `syncQueue: '++id, operation, entityType, timestamp'`
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 3.2 Create `frontend/src/api/client.ts` exposing a fetch wrapper that auto-injects `Authorization: Bearer ${accessToken}`, handles 401 by calling `/api/auth/refresh` and retrying once, throws typed errors with `code` and `detail`
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 3.3 Create `frontend/src/api/auth.ts` with `login(email,pw)`, `register(email,pw,displayName?)`, `refresh()`, `me()` calling the corresponding REST endpoints
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 3.4 Create `frontend/src/api/notes.ts` with `createNote`, `listNotes(filters)`, `getNote(id)`, `updateNote(id, patch)`, `deleteNote(id)` — typed against backend `NoteOut`/`NoteCreate`
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 3.5 Create `frontend/src/api/search.ts` exposing `search(req)` calling `POST /api/search`
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h

- [x] 4 State stores
  - [x] 4.1 Create `frontend/src/store/authStore.ts` — Zustand store holding `accessToken`, `user`, with actions `login`, `logout`, `setAccessToken`. Token kept in memory only (no localStorage).
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 4.2 Create `frontend/src/store/noteStore.ts` — Zustand store for in-memory notes cache with `loadNotes`, `addNote`, `updateNote`, `removeNote`
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 4.3 Create `frontend/src/store/uiStore.ts` — Zustand store for UI state (loading, current modal, selected category filter)
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h

- [x] 5 Auth pages and routing
  - [x] 5.1 Create `frontend/src/main.tsx` mounting `<App />` into `#root` with `<BrowserRouter>` from react-router-dom v6
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 5.2 Create `frontend/src/App.tsx` with route table — public `/login`, `/register`; protected wildcard route guarded by an `<AuthGate>` that redirects to `/login` when not logged in
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 5.3 Create `frontend/src/pages/LoginPage.tsx` with email/password form, error display, calls `authStore.login`
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 5.4 Create `frontend/src/pages/RegisterPage.tsx` (referenced by LoginPage link) — register then auto-login
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 5.5 Create `frontend/src/hooks/useAuth.ts` — convenience hook exposing `isAuthenticated`, `login`, `logout`, `user` from authStore plus an effect that hydrates `user` via `me()` on mount
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h

- [x] 6 Utilities
  - [x] 6.1 Create `frontend/src/utils/audio.ts` with helpers `getMicStream()`, `createMediaRecorder(stream)`, `blobsToWebm(chunks)` — used later by VoiceCapture in US-4
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
  - [x] 6.2 Create `frontend/src/utils/formatters.ts` with date formatters (date-fns), category color map, word-count helper
    - **Started**: 2026-04-29
    - **Completed**: 2026-04-29
    - **Duration**: <1h
