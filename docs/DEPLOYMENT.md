# Deployment Guide

## Local Development

1. Copy `backend/.env.example` to `backend/.env` and fill in your secrets.
2. Start a local PostgreSQL instance with pgvector:
   ```
   docker run -d --name cortex-postgres \
     -e POSTGRES_USER=cortexadmin \
     -e POSTGRES_PASSWORD=localpass \
     -e POSTGRES_DB=cortex \
     -p 5432:5432 \
     pgvector/pgvector:pg16
   ```
3. Run Alembic migrations:
   ```
   cd backend
   alembic upgrade head
   ```
4. Start the FastAPI dev server:
   ```
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## Docker Build

```bash
docker build -t cortex-api ./backend
docker run --env-file backend/.env -p 8000:8000 cortex-api
```

Health check: `curl http://localhost:8000/api/health` should return `{"status":"ok"}`.

## Azure Container Apps

Full deployment workflow is defined in `.github/workflows/deploy-backend.yml` (implemented in US-5).

> **Security note:** Real `.env` files must never be committed to source control.
> Use Azure Key Vault references for production secrets (injected via Container App secret references).
