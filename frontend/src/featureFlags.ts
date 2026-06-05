/**
 * featureFlags.ts — runtime feature flags driven by Vite env vars.
 *
 * Most flags default OFF. Flip a default-off flag by setting the corresponding
 * env var to `"true"` in `.env.production` (or any `.env.*` file Vite picks up)
 * and rebuilding the frontend. Default-on flags document their disable values.
 *
 * Why a function (not a const): so tests can `vi.stubEnv('VITE_FEATURE_…', 'true')`
 * before render and have the flag respect the override without module-reload
 * gymnastics.
 */

/**
 * Canvas (Heptabase-style visual-thinking canvas) — Phase 7, Round 24.
 *
 * Disabled by default as of Round 28 (2026-05-29): the user opted out of
 * the feature. All backend endpoints + frontend implementation remain in
 * the repo so the flag can be flipped back on by setting
 * `VITE_FEATURE_CANVAS=true` in `frontend/.env.production`.
 *
 * What this flag gates (frontend only):
 *   - `/canvases` and `/canvas/:id` routes in `App.tsx`
 *   - "Canvas" tab in `BottomNav`
 *   - "Open as Canvas" toolbar button + export status banner in `BrainViewPage`
 *   - "Add to Canvas" toolbar button + modal + toast in `NoteDetailPage`
 *
 * Backend `/api/canvases/*` routes are unaffected — they keep working for
 * any consumer that already knows the URLs.
 */
export function isCanvasEnabled(): boolean {
  return import.meta.env.VITE_FEATURE_CANVAS === 'true';
}

/**
 * Tasks (Round 35 reminders/tasks) — enabled by default.
 * Set `VITE_FEATURE_TASKS=false` or `VITE_FEATURE_TASKS=0` to hide the Tasks UI.
 */
export function isTasksEnabled(): boolean {
  const value = import.meta.env.VITE_FEATURE_TASKS;
  return value !== 'false' && value !== '0';
}
