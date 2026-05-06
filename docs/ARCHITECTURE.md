# Architecture

The canonical architecture for the cortex-second-brain feature is fully documented in the design document:

`features/cortex-second-brain/designs/design.md`

Sections of interest:
- **Summary** — high-level overview and goals
- **Architecture** — component diagram (PWA → Container Apps → Postgres/Blob/Speech/OpenAI)
- **Components** — technology and dependency table
- **Data Flow** — voice capture, offline capture, AI pipeline, distill, search
- **AI Pipeline (CODE + Reflect)** — stage-by-stage breakdown with state machine
- **Data Model** — PostgreSQL tables and IndexedDB schema
- **Security** — JWT, CORS, rate-limit, WebSocket auth, log-scrubbing
- **Bicep Template (canonical)** — the source of truth for all Azure resources

Do not duplicate content here — reference the design document directly to avoid drift.
