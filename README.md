# cortex-ai — Cortex Second Brain

A voice-first PWA "second brain" backed by FastAPI, PostgreSQL/pgvector, and Azure AI services.

## Status

✅ **Phase 1 MVP + Phase 2 (Personal Dictionary + Shadow Reader)** are built and deployed to Azure.

Live endpoints:
- **Frontend (PWA):** https://gentle-river-06c1e4e10.7.azurestaticapps.net
- **Backend API:** https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io
- **API docs (Swagger):** https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/docs

## Documentation

For incoming agents/contributors, read in this order:

1. **[HANDOFF.md](./HANDOFF.md)** — entry point, live URLs, where things are, how to resume
2. **[PLAN.md](./PLAN.md)** — vision, phase scope, status snapshot, smoke test plan, roadmap
3. **[PROGRESS.md](./PROGRESS.md)** — chronological log of what's been done
4. **[DECISIONS.md](./DECISIONS.md)** — architecture decisions, deviations from spec, OQ/B/SEC/PERF/QA tags
5. **[KNOWN_ISSUES.md](./KNOWN_ISSUES.md)** — open work, test failures, prioritized backlog

Feature guides:
- **[docs/REMINDERS.md](./docs/REMINDERS.md)** — Round 35: write "submit by tomorrow #high #weekly" and Cortex extracts the deadline + priority + recurrence as you type. Push notifications (with email fallback) fire at the due time. Editable pill on every note. Full task model (`/tasks` page, mark done, recurring rollover) shipped on the existing notes table.
- **[docs/IMPORT.md](./docs/IMPORT.md)** — bulk import from Google Keep + Notion via `backend/scripts/import_notes.py`.
- **[docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)** — Azure setup runbook.

Build specs (canonical source of truth):
- [SECOND_BRAIN_BUILD_SPEC.md](./SECOND_BRAIN_BUILD_SPEC.md) — main spec
- [SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md](./SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md) — Personal Dictionary + Shadow Reader

Workforce artifacts (multi-agent build):
- [features/cortex-second-brain/](./features/cortex-second-brain/) — requirements, design, critique, 9 user-story task files, review-comments

## Project Structure

```
cortex/
├── frontend/     React 18 + Vite + Tailwind PWA (TypeScript, Zustand, Dexie)
├── backend/      FastAPI + async SQLAlchemy + asyncpg + pgvector (Python 3.11)
├── infra/        Bicep IaC (Container App, Postgres Flex, ACR, SWA, Cognitive Services)
├── docs/         Architecture, API reference, deployment runbook
├── .github/      CI/CD workflows for backend + frontend deploys
└── features/     Workforce design + tasks for cortex-second-brain
```

## Quick Start

See [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) for the full setup runbook, or `HANDOFF.md` § 3 for resume-from-here commands.

> **Security:** Never commit `.env` files. Use `.env.example` as a template and populate secrets from Azure Key Vault or your local secret manager. The live deploy uses Container App secrets (Azure-managed, not on disk).
