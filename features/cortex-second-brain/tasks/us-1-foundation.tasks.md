# User Story: US-1 — Foundation (Repo, DB, Auth, Notes CRUD, Docker)

> Feature: cortex-second-brain
> Requirements: `/features/cortex-second-brain/requirements/requirements.md`
> Design: `/features/cortex-second-brain/designs/design.md`
> Spec: `SECOND_BRAIN_BUILD_SPEC.md` Phase 1 items 1–6 (section 4.2), structure 4.1, deps 4.3, env 4.4

## Acceptance Criteria

- Monorepo skeleton matches spec section 4.1 (top-level `frontend/`, `backend/`, `infra/`, `docs/`, `.github/workflows/`).
- FastAPI app boots with health-check endpoint `GET /api/health` returning `200 {status:"ok"}`.
- PostgreSQL extensions `uuid-ossp` and `pgvector` enabled; tables `users`, `notes`, `tags`, `note_tags`, `note_links`, `daily_summaries` created with all indexes including HNSW on `notes.embedding`.
- JWT auth: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/refresh`, `GET /api/auth/me` work end-to-end with bcrypt password hashing; access TTL 30 min, refresh TTL 30 days.
- Notes CRUD: `POST /api/notes`, `GET /api/notes` (paginated, filterable by `category`, `tag`, `date_from`, `date_to`), `GET /api/notes/{id}`, `PUT /api/notes/{id}`, `DELETE /api/notes/{id}` enforce ownership.
- Backend Dockerfile builds and `docker run` serves `/api/health` on port 8000.
- Alembic migration `001_initial_schema.py` runs cleanly forward and backward.

## Status
**Status**: Not Started
**Started**: TBD
**Completed**: TBD

## Relevant Documentation
- `/features/cortex-second-brain/designs/design.md` — Project Structure, Data Model, API/Interfaces (Auth + Notes CRUD), Security
- `SECOND_BRAIN_BUILD_SPEC.md` § 2.3 (data model SQL), § 2.4 (auth + notes endpoints), § 2.10 (JWT impl), § 4.1 (folder tree), § 4.3 (requirements.txt + Dockerfile), § 4.4 (env vars)

## TDD Hook
Per workforce protocol: the Tester writes failing tests in `backend/tests/` for each task below **before** the Coder begins. Coder waits for the failing-tests signal before implementing. Tests cover acceptance criteria including spec § 5.3 final checklist for Auth and Notes CRUD.

---

## Tasks

- [ ] 1 Repo and tooling skeleton
  - [ ] 1.1 Create top-level folders `frontend/`, `backend/`, `infra/`, `docs/`, `.github/workflows/` exactly per design "Project Structure" section
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.2 Add root `README.md` with project name and link to `SECOND_BRAIN_BUILD_SPEC.md`; add root `.gitignore` covering `__pycache__`, `node_modules`, `.env`, `*.pyc`, `dist/`, `.vite/`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.3 Create empty placeholder workflow files `.github/workflows/deploy-frontend.yml` and `.github/workflows/deploy-backend.yml` (content fleshed out in US-5)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 2 Backend project bootstrap
  - [ ] 2.1 Create `backend/requirements.txt` verbatim from design "Backend requirements.txt (pinned)" — do not substitute or add packages
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.2 Create `backend/Dockerfile` verbatim from design "Backend Dockerfile" (Python 3.11-slim, ffmpeg, uvicorn entrypoint)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.3 Create `backend/app/config.py` using `pydantic-settings` to load all env vars listed in design "Environment Variables" section (DATABASE_URL, AZURE_OPENAI_*, AZURE_SPEECH_*, AZURE_STORAGE_*, AZURE_VISION_*, JWT_SECRET_KEY, CORS_ORIGINS, ENVIRONMENT)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.4 Create `backend/app/database.py` exposing async SQLAlchemy `engine`, `SessionLocal`, `Base`, and `get_db()` FastAPI dependency using `asyncpg` driver
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.5 Create `backend/app/main.py` — instantiate FastAPI app, register CORS middleware from `settings.CORS_ORIGINS`, add `GET /api/health` route returning `{"status":"ok"}`, include router placeholders for auth and notes
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 3 Database schema and migrations
  - [ ] 3.1 Create `backend/alembic.ini` and `backend/alembic/env.py` configured for the async engine; ensure `uuid-ossp` and `vector` extensions are created in the migration's `upgrade()`. Note per design Open Question OQ-9: Azure's pgvector extension is named `vector` (not `pgvector`) in `CREATE EXTENSION` — use `CREATE EXTENSION IF NOT EXISTS vector` and `CREATE EXTENSION IF NOT EXISTS "uuid-ossp"`.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.2 Create `backend/app/models/user.py` with `User` SQLAlchemy model — fields per design Data Model `users` table (id UUID, email unique, password_hash, display_name, created_at, updated_at). Do not add Phase 2 columns yet — those come in US-7/US-8 migrations.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.3 Create `backend/app/models/note.py` with `Note` SQLAlchemy model — fields per design Data Model `notes` table including `embedding` Vector(1536) column from `pgvector.sqlalchemy`. Phase 2 columns excluded.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.4 Create `backend/app/models/tag.py` with `Tag` model and `note_tags` association table per design Data Model
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.5 Create `backend/app/models/daily_summary.py` (DailySummary) and a `note_links` association entity per design Data Model
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.6 Generate Alembic migration `backend/alembic/versions/001_initial_schema.py` that creates all tables and indexes from design "Tables (final schema)" — including HNSW index `idx_notes_embedding ... USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)`. Include working `downgrade()` that drops everything cleanly.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 4 JWT authentication
  - [ ] 4.1 Create `backend/app/auth/jwt.py` per design "Security" — `create_access_token(user_id)` (30 min HS256), `create_refresh_token(user_id)` (30 days HS256), `get_current_user()` dependency that decodes Bearer token and returns `UUID`. Use `passlib[bcrypt]` `CryptContext` for password hashing. Per design Open Questions OQ-2 and OQ-4, the Lead must escalate to the user before this task ships: (a) `python-jose==3.3.*` carries CVE-2024-33663/33664 — recommended bump to `>=3.5,<4`; (b) `passlib[bcrypt]==1.7.*` breaks on `bcrypt>=4.1` — pin `bcrypt<4.1` or replace with direct `bcrypt>=4.2`. Coder uses whichever the user approves; if no decision, default to spec pins and add a `# SECURITY: pending OQ-2/OQ-4 review` comment so the Reviewer-Security agent will catch it.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.2 Create `backend/app/schemas/auth.py` Pydantic schemas: `RegisterRequest`, `LoginRequest`, `TokenPair`, `UserOut`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.3 Create `backend/app/api/auth.py` with routes `POST /api/auth/register` (201, returns UserOut), `POST /api/auth/login` (returns TokenPair, sets refresh in httpOnly+secure+sameSite cookie), `POST /api/auth/refresh` (rotates refresh, returns new access), `GET /api/auth/me` (returns UserOut). Reject duplicates with HTTP 409.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.4 Wire auth router into `backend/app/main.py` and ensure all subsequent routers depend on `get_current_user`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 5 Notes CRUD
  - [ ] 5.1 Create `backend/app/schemas/note.py` Pydantic schemas: `NoteCreate` (content required, optional source_type/category/audio_url/image_url/client_id/tags), `NoteUpdate` (all optional), `NoteOut` (mirrors notes columns + computed tags list, excluding embedding bytes), `NoteListResponse` (`{items, total}`)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 5.2 Create `backend/app/api/notes.py` with `POST /api/notes` (201) — inserts row with `processing_status='raw'` for text input or `'transcribed'` if `audio_url` set; pipeline scheduling stub left for US-2
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 5.3 Implement `GET /api/notes` paginated list with query filters `category`, `tag`, `date_from`, `date_to`, `q` (no-op for now, real search in US-2), `limit=50`, `offset=0`. Always filter by current user.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 5.4 Implement `GET /api/notes/{id}` (404 if not user's), `PUT /api/notes/{id}` (partial update; if `content` changes, mark `processing_status='raw'` for re-pipeline in later stories), `DELETE /api/notes/{id}` (204)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 5.5 Add ownership-isolation safeguard: every notes query filters `Note.user_id == current_user`; cross-user access returns 404 (not 403) to avoid leaking existence
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 6 Local Docker run
  - [ ] 6.1 Confirm `docker build -t cortex-api ./backend` succeeds; document any base-image quirks in `docs/DEPLOYMENT.md` placeholder
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 6.2 Add `backend/.env.example` listing all env-var keys from design (no values) — flag in README that real `.env` must never be committed
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
