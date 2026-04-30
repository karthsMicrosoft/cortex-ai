# Cortex — Personal Second Brain

A voice-first PWA "second brain" backed by FastAPI, PostgreSQL/pgvector, and Azure AI services.

## Documentation

Full build specification: [SECOND_BRAIN_BUILD_SPEC.md](./SECOND_BRAIN_BUILD_SPEC.md)

Addendum (Phase 2 — Personal Dictionary, Shadow Reader): [SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md](./SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md)

Architecture & API reference: [docs/](./docs/)

## Project Structure

```
cortex/
├── frontend/     React 18 + Vite + Tailwind PWA
├── backend/      FastAPI + SQLAlchemy + asyncpg
├── infra/        Bicep infrastructure-as-code
├── docs/         Architecture, API reference, deployment guides
└── .github/      CI/CD workflow definitions
```

## Quick Start

See [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) for full setup instructions.

> **Security:** Never commit `.env` files. Use `.env.example` as a template and populate secrets from Azure Key Vault or your local secret manager.
