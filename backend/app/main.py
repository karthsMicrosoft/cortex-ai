"""
FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

app = FastAPI(
    title="Cortex Second Brain API",
    description="Voice-first personal second brain API",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check() -> dict:
    """Public health-check endpoint — no auth required."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Routers — imported after models are defined to avoid circular imports.
# Auth and Notes routers are wired here; others added in their respective stories.
# ---------------------------------------------------------------------------

from app.api.auth import router as auth_router
from app.api.notes import router as notes_router

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(notes_router, prefix="/api/notes", tags=["notes"])
