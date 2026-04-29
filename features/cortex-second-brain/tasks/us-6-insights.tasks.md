# User Story: US-6 — Insights (Distill, Brain View, Patterns, Music Player)

> Feature: cortex-second-brain
> Requirements: `/features/cortex-second-brain/requirements/requirements.md`
> Design: `/features/cortex-second-brain/designs/design.md`
> Spec: `SECOND_BRAIN_BUILD_SPEC.md` Phase 2 items 22–28 (section 4.2 + addendum)

## Acceptance Criteria

- Daily summary: scheduled task generates per-user summary from notes created on a date; persisted to `daily_summaries`. `GET /api/ai/summary/daily?date=` returns it.
- Weekly summary endpoint `GET /api/ai/summary/weekly?week=` aggregates a week's notes into a longer summary.
- `GET /api/insights/graph` returns `{ nodes, links }` for force-directed Brain View.
- `GET /api/insights/patterns` returns AI-detected themes/patterns across recent notes.
- Frontend `InsightsPage` renders the daily/weekly summaries.
- Frontend `BrainViewPage` renders the force-directed graph using `react-force-graph-2d`.
- `MusicPlayer` component plays audio with `wavesurfer.js` waveform and shows tempo/mood/genre chips on `NoteDetailPage` for `category='Music'`.
- Note cards display `<ProcessingBadge />` reflecting current pipeline state.

## Status
**Status**: Not Started
**Started**: TBD
**Completed**: TBD

## Relevant Documentation
- `/features/cortex-second-brain/designs/design.md` — AI Pipeline (Distill stage), Music Features
- `SECOND_BRAIN_BUILD_SPEC.md` § 2.5 (distill), § 2.9 (music note pipeline)

## TDD Hook
Tester writes failing tests in `backend/tests/test_distill.py`, `test_insights.py`, and `frontend/src/__tests__/InsightsPage.test.tsx`, `BrainViewPage.test.tsx`, `MusicPlayer.test.tsx`. Coder waits for failing-tests signal before each task.

---

## Tasks

- [ ] 1 Distill pipeline (daily + weekly)
  - [ ] 1.1 Create `backend/app/pipeline/distill.py::generate_daily_summary(user_id, target_date, openai_client, db)` per spec § 2.5 — fetch user notes for the date, build prompt with `[category] content` lines, call GPT-4o-mini (max_tokens=800, T=0.7), upsert into `daily_summaries`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.2 Add `generate_weekly_summary(user_id, iso_week, ...)` that aggregates seven daily summaries (or notes) into a higher-level weekly recap; persist to a new lightweight in-memory cache or extend `daily_summaries` with a `kind` column (preferred — keep schema clean: read 7 daily summaries on demand)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.3 Add a scheduler entry — simplest viable: an APScheduler hook attached at FastAPI startup that runs `generate_daily_summary` for the current user nightly at 23:59 local. (For single-user MVP this is sufficient; production scale would move to Container Apps Jobs.)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 2 Insights endpoints
  - [ ] 2.1 Create `backend/app/api/insights.py` with `GET /api/ai/summary/daily?date=` (returns `daily_summaries` row for date or 404), `GET /api/ai/summary/weekly?week=` (composes weekly view from 7 dailies)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.2 Add `GET /api/insights/graph` returning `{ nodes: [{id,label,category}], links: [{source,target,score}] }` from `notes` + `note_links` (capped at 200 nodes for performance)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.3 Add `GET /api/insights/patterns` — calls GPT-4o-mini with last 14 days of notes summarized by category, returns `{patterns:[{theme,evidence_note_ids}]}`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.4 Wire insights router into `backend/app/main.py`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 3 Express endpoint
  - [ ] 3.1 Add `POST /api/ai/generate` to `backend/app/api/insights.py` (or a new `express.py`) accepting `{kind: 'song'|'practice'|'reflection', source_note_ids[]}`. Builds a prompt per kind using spec § 2.5 / requirements FR-2.6/2.7/2.8, calls GPT-4o-mini, returns `{generated_text}`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 4 Export endpoint
  - [ ] 4.1 Create `backend/app/api/export.py` `GET /api/export` that returns a JSON dump of all user notes (with SAS-signed media URLs) + tags + summaries — streaming response if size large
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 5 Frontend insights UI
  - [ ] 5.1 Replace stub `frontend/src/pages/InsightsPage.tsx` with a layout showing daily summary card + weekly summary card + patterns list. Calls `/api/ai/summary/daily?date=today`, `/weekly?week=current`, `/insights/patterns`.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 5.2 Create `frontend/src/pages/BrainViewPage.tsx` using `react-force-graph-2d` to render `/api/insights/graph` data; node colors by category from formatters utility
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 5.3 Replace stub `frontend/src/pages/CreatePage.tsx` with form for selecting source notes + kind chooser (song / practice / reflection); renders generated text from `/api/ai/generate`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 6 Music player
  - [ ] 6.1 Create `frontend/src/components/MusicPlayer.tsx` using `wavesurfer.js` per spec § 2.9 — waveColor `#6366F1`, progressColor `#4F46E5`. Props: `audioUrl`, optional `metadata: {tempo, key, genre, mood}`.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 6.2 Update `frontend/src/pages/NoteDetailPage.tsx` to render `<MusicPlayer />` when `note.source_type === 'voice'` AND `note.category === 'Music'`; show `music_metadata` chips (tempo BPM, key, genre, mood)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 6.3 Add quick-label edit affordance on music notes — chip-style editor for tempo/mood/genre that PUTs the changes via `updateNote`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
