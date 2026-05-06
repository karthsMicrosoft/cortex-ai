# UX Issues — round 1

## Test failures (real app bugs)

### ISSUE-01: Notes stuck in "Pending sync…" — POST /api/notes appears to fail silently
- **Test**: `02-text-note-sync.spec.ts::library does not show "pending sync" forever for fresh text note`
- **Symptom**: After submitting a text note on `/`, the Library page shows the note card with badge `Pending sync…` even after 15 s. The note is never posted to the backend. Voice capture test's page snapshot also shows `1 pending sync items` badge in the header and `Pending sync…` on the voice note card, confirming the sync path is broken for all note types.
  ```
  Error: expect(received).not.toMatch(expected)
  Expected pattern: not /pending\s+sync/i
  Received string:  "Ideas\nMay 1, 2026 · less than a minute ago\n\nSync drain test …\n\nRaw\nPending sync…"
  ```
- **Root cause hypothesis**: The frontend's Zustand auth store is in-memory only. When a new browser context loads with a saved storageState (or when the access token expires), the store's `accessToken` field is null. Every `POST /api/notes` goes out without an `Authorization` header and receives a 401. The sync queue retries but never clears, so the note stays in "Pending sync". This is a regression in the session-restoration code path — the app does not re-hydrate the Zustand store from localStorage on startup.
- **Suggested fix**: In the frontend's auth store initializer (likely `src/store/authStore.ts` or similar), on app mount read `accessToken` from `localStorage` into the Zustand state. If the stored token is expired, immediately call `/api/auth/refresh` to get a fresh one before mounting the rest of the app.

---

### ISSUE-02: Session restore broken — hard reload and fresh page load redirect to /login; /api/auth/refresh returns 401 or is blocked by CORS
- **Test**: `01-auth-and-session.spec.ts::hard reload preserves session via /api/auth/refresh`
- **Symptom**: After a successful registration and auto-login, reloading the page bounces the user to `/login`. The `refresh_token` HttpOnly cookie is set by the backend but the cross-origin `fetch` to `/api/auth/refresh` either:
  - Is silently blocked (no `Access-Control-Allow-Origin` header from the backend for preflight), or
  - Is sent but the cookie is not included because it was set with `SameSite=Lax/Strict` (must be `SameSite=None; Secure` for cross-origin use).

  Evidence: the session-restore test consistently sees the page URL stay at `/login` for 15 s (23 retry checks).

  Evidence from the "login silently fails" scenario: when `useSharedUser` falls back to explicit `loginExisting`, the login form POSTs credentials but the page stays at `/login` with no error alert — this suggests the `fetch` to `/api/auth/login` either gets no CORS headers back and the response is opaque (network error), or the backend returns a non-redirect and the frontend's response handler silently fails.

  ```
  Expected pattern: /\/(\?|$)/
  Received string:  "https://gentle-river-06c1e4e10.7.azurestaticapps.net/login"
  Timeout: 15000ms  (23 × unexpected value)
  ```
- **Root cause hypothesis**: Two-part issue:
  1. The `refresh_token` cookie is missing `SameSite=None; Secure` — the browser will not send it in cross-origin requests from `azurestaticapps.net` to `azurecontainerapps.io`.
  2. The backend's CORS `Access-Control-Allow-Origin` configuration does not include `https://gentle-river-06c1e4e10.7.azurestaticapps.net` with `credentials: true`, causing preflight failures for `/api/auth/login` and `/api/auth/refresh`.
- **Suggested fix**:
  - **Backend** (`app/main.py` or CORS middleware): Add `https://gentle-river-06c1e4e10.7.azurestaticapps.net` to `allow_origins` with `allow_credentials=True`.
  - **Backend** (cookie set in `/api/auth/login` and `/api/auth/register`): Set the refresh token cookie with `SameSite=None; Secure; HttpOnly`.
  - **Frontend**: Ensure all `fetch` calls to the backend include `credentials: 'include'` so the refresh cookie is sent.

---

### ISSUE-03: CORS error on POST /api/upload — voice upload completely blocked
- **Test**: `04-voice-capture.spec.ts::FAB tap → recording starts → stop → /api/voice/upload not 422`
- **Symptom**: After stopping a voice recording, the app POSTs audio to `/api/upload` (NOT `/api/voice/upload`). The backend responds with no `Access-Control-Allow-Origin` header, blocking the upload.
  ```
  Console errors (2 copies):
  "Access to fetch at 'https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/api/upload'
   from origin 'https://gentle-river-06c1e4e10.7.azurestaticapps.net' has been blocked by CORS policy:
   No 'Access-Control-Allow-Origin' header is present on the requested resource."
  ```
  The Library page confirms the upload never completes: note card shows `Pending sync…` with no audio content.
- **Root cause hypothesis**: The `/api/upload` endpoint is missing from the backend's CORS `allow_origins` or the route-specific CORS config. The voice capture frontend code calls `/api/upload` (not `/api/voice/upload` as the test originally expected), and this endpoint has no CORS headers. This may be a recently renamed endpoint where the CORS config was not updated.
- **Suggested fix**:
  - **Backend** CORS middleware: ensure `/api/upload` is covered by the same `allow_origins` list as all other `/api/*` endpoints. If using FastAPI's `CORSMiddleware`, a single middleware registration should cover all routes — verify the middleware is not being added AFTER route registration.
  - Alternatively, if `/api/upload` is served by Azure Blob Storage directly, configure a CORS rule on the storage account to allow `https://gentle-river-06c1e4e10.7.azurestaticapps.net`.

---

### ISSUE-04: GET /api/ai/summary/weekly returns 500 ProgrammingError
- **Test**: `05-navigation-no-500s.spec.ts::/insights loads without 5xx + no console errors`
- **Symptom**: Navigating to `/insights` triggers a GET to `/api/ai/summary/weekly?week=2026-W18` which returns HTTP 500 with body:
  ```json
  {"detail":"Could not generate weekly summary: ProgrammingError"}
  ```
  This fails consistently on every run (including retries).
- **Root cause hypothesis**: A SQLAlchemy `ProgrammingError` indicates a database query issue — likely a missing column, wrong table name after a schema migration, or an invalid SQL query for the weekly summary feature. This appears to be a backend regression in the weekly AI summary endpoint, possibly introduced by a recent schema change that was not applied to the production database.
- **Suggested fix**:
  - **Backend** (`app/routes/ai.py` or similar): Check the `get_weekly_summary` function for any SQL queries referencing columns/tables that may not exist in the production DB schema.
  - Run `alembic upgrade head` (or equivalent) against the production database to apply any pending migrations.
  - Add a try/except around the weekly summary query that returns a 200 with an empty/placeholder summary instead of a 500, to avoid crashing the Insights page.

---

## Test infra issues fixed in this round

- **Shared auth fixture**: Created `tests/auth.setup.ts` (registers/logs in once per run) and `tests/constants.ts` (fixed shared credentials `e2e-shared-cortex@example.com`). Updated `playwright.config.ts` to add an `auth-setup` project that runs before `chromium-desktop` tests and saves storage state to `.auth/user.json`. All tests now load this storage state instead of each registering a fresh user — eliminates the 10/min `/register` rate-limit problem.

- **Replaced `registerAndLogin` with `useSharedUser`** in all tests except the dedicated registration test (`01-auth-and-session.spec.ts::register → auto-login`). Reduced `/register` calls from ~14 per run to 1.

- **Fixed `localStorage.clear()` SecurityError** in `01-auth-and-session.spec.ts::register → auto-login`: the test was calling `page.evaluate(() => localStorage.clear())` before navigating to any page (page was at `about:blank`). Fixed by navigating to `/` first.

- **Added `await expect(textArea).toBeVisible()` guard** in `02-text-note-sync.spec.ts::library does not show "pending sync"` and `03-note-detail.spec.ts` to avoid `fill()` hanging when the capture page hasn't loaded yet.

- **Added `constants.ts`** to separate shared credentials from the Playwright test file (`auth.setup.ts`), avoiding Playwright's "test file should not import test file" error.

## Tests that pass

13 of 17 tests pass (not counting auth-setup as 1 additional passing test).

Remaining failures are all genuine app bugs:
- ISSUE-01 (pending sync): `02-text-note-sync.spec.ts::library does not show "pending sync" forever`
- ISSUE-02 (session restore): intermittently affects `01-auth-and-session.spec.ts::hard reload preserves session`, `02-text-note-sync.spec.ts::library does not show "pending sync"`, `05-navigation-no-500s.spec.ts::/search loads without 5xx`
- ISSUE-03 (CORS on /api/upload): `04-voice-capture.spec.ts::FAB tap → recording starts → stop → /api/voice/upload not 422`
- ISSUE-04 (/insights 500): `05-navigation-no-500s.spec.ts::/insights loads without 5xx + no console errors`
