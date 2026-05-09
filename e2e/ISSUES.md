# E2E Issues Tracker

**Last reviewed: 2026-05-08 (Round 15)** — historical issues triaged against
PROGRESS.md. All four originally-reported issues from the Round-1 audit are
now obsolete (see "Resolved" section below). This file should be re-populated
the next time the Playwright suite is run against the live deployment and
genuine failures are identified.

## How this file is used

- `e2e/tests/*.spec.ts` runs against the live SWA + Container Apps deployment.
- When a test fails for a reason that points at a real app bug (not flaky test
  infra), file an entry below with: failing test, symptom, suspected root
  cause, and suggested fix.
- Keep entries terse; link back to PROGRESS.md once the round that fixes the
  bug lands.
- Run the suite via the `E2E (Playwright)` workflow (`workflow_dispatch` or
  the nightly cron) — see `.github/workflows/e2e.yml`.

## Open issues

_None tracked at the time of this triage. Re-run `npm run e2e` (locally or via
GH Actions) and add entries here for any genuine app bugs the suite surfaces._

---

## Resolved (historical — kept for traceability)

The Round-1 audit (`e2e/ISSUES.md` history before 2026-05-08) filed four
issues. All have since been fixed in subsequent rounds; the entries below are
condensed from the original report so the audit trail survives.

### ISSUE-01 — Notes stuck in "Pending sync…" — RESOLVED (Round 1)
- **Test**: `02-text-note-sync.spec.ts::library does not show "pending sync"
  forever for fresh text note`
- **Original symptom**: `POST /api/notes` failed silently because the Zustand
  auth store was not rehydrated from `localStorage` on app mount, so requests
  were sent without an `Authorization` header.
- **Resolution**: Auth store rehydration + sync queue retry logic landed in
  Round 1. PROGRESS.md line 213 confirms "Notes stuck in Pending sync forever"
  was on the round-1 punch list.

### ISSUE-02 — Session restore broken / hard reload bounces to /login — RESOLVED (Rounds 5 → 7)
- **Test**: `01-auth-and-session.spec.ts::hard reload preserves session via
  /api/auth/refresh`
- **Original symptom**: Cross-origin `/api/auth/refresh` failed because the
  refresh-token cookie was missing `SameSite=None; Secure` and CORS
  preflights were rejected.
- **Resolution**: Round 5 added the recursive-refresh guard in
  `frontend/src/api/client.ts` and made `/register` plant the
  `samesite=none + secure + httponly` cookie (PROGRESS.md row 18). Round 6
  added `credentials: 'include'` to all raw `syncManager.ts` fetches
  (PROGRESS.md row 22). Round 7 worked around browser tracking-prevention
  dropping third-party cookies by **also** returning the refresh token in
  the JSON body of `/login`, `/register`, `/refresh` and storing it in
  `localStorage('cortex_refresh')` (PROGRESS.md "Round 7" section).

### ISSUE-03 — CORS error on POST /api/upload (voice upload blocked) — RESOLVED (Round 2)
- **Test**: `04-voice-capture.spec.ts::FAB tap → recording starts → stop →
  /api/voice/upload not 422`
- **Original symptom**: `/api/upload` responded with no
  `Access-Control-Allow-Origin` header, surfacing as a CORS failure in the
  browser.
- **Resolution**: PROGRESS.md row "ISSUE-03" — `services/blob_storage.py`
  was passing a `dict` as `content_settings=` to `BlobClient.upload_blob()`;
  Azure SDK 12.22 expects `ContentSettings(content_type=…)`. The unhandled
  `AttributeError` bypassed `CORSMiddleware`, so the browser saw the failure
  as CORS. Fixed by importing `ContentSettings` and wrapping the content
  type. Voice upload returns 200 with a SAS URL.

### ISSUE-04 — GET /api/ai/summary/weekly returns 500 ProgrammingError — RESOLVED (Round 2 fix → endpoint removed in Round 9)
- **Test**: `05-navigation-no-500s.spec.ts::/insights loads without 5xx + no
  console errors`
- **Original symptom**: `pipeline/distill.py:generate_weekly_summary` filtered
  `Note.created_at >= str(monday)` against a `timestamptz` column; Postgres
  rejected the implicit text→timestamptz coercion.
- **Resolution (Round 2)**: Replaced `str(date)` with
  `datetime.combine(date, time.min, tzinfo=UTC)` (PROGRESS.md row "ISSUE-04").
- **Follow-up (Round 9)**: The `GET /summary/daily` and `GET /summary/weekly`
  endpoints were removed entirely; `InsightsPage` now only renders the
  Recurring Patterns section (PROGRESS.md lines 554, 567). The
  `05-navigation-no-500s.spec.ts::/insights` route assertion still applies
  (the page must load without 5xx) — but the specific weekly-summary 500 path
  no longer exists.

---

## Test infra fixes (still in effect)

Documented here so future maintainers don't re-introduce the original problems.

- **Shared auth fixture** (`tests/auth.setup.ts` + `tests/constants.ts`):
  registers / logs in once per run and writes storage state to
  `e2e/.auth/user.json`. The `auth-setup` Playwright project runs before
  `chromium-desktop`. Eliminates the original 10/min `/register`
  rate-limit problem.

- **`useSharedUser` helper** (in `tests/helpers.ts`) loads the shared session
  in every test except the dedicated `register → auto-login` case. Reduces
  `/register` calls to 1 per run.

- **`localStorage.clear()` SecurityError fix**: the `register → auto-login`
  test navigates to `/` before calling `localStorage.clear()` (running
  `evaluate(() => localStorage.clear())` on `about:blank` throws).

- **`await expect(textArea).toBeVisible()` guards** in tests that immediately
  call `fill()` on the capture page, so they don't hang when the page
  hasn't finished hydrating.
