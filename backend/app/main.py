"""
FastAPI application entry point.
"""
import logging
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings

# ---------------------------------------------------------------------------
# Rate limiter (critique mitigation #8 — 100 req/min/user)
# Imported from app.limiter so API routers can use @limiter.limit() without
# a circular import through app.main.
# ---------------------------------------------------------------------------

from app.limiter import limiter  # noqa: E402

# ---------------------------------------------------------------------------
# Log-scrubbing filter (B12 — redact ?token= from logged URLs)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"([?&])token=[^&\s]+", re.IGNORECASE)


class _ScrubTokenFilter(logging.Filter):
    """Remove ?token=<jwt> / &token=<jwt> from any log record message or args."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.msg = _TOKEN_RE.sub(r"\1token=REDACTED", str(record.msg))
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    _TOKEN_RE.sub(r"\1token=REDACTED", str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: _TOKEN_RE.sub(r"\1token=REDACTED", str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
        return True


# Apply scrub filter to the root logger so every handler inherits it.
_scrub_filter = _ScrubTokenFilter()
logging.getLogger().addFilter(_scrub_filter)
# Also attach to uvicorn access logger explicitly.
logging.getLogger("uvicorn.access").addFilter(_scrub_filter)


# ---------------------------------------------------------------------------
# FastAPI app
#
# 2026-05-06: Daily/weekly distill cron removed entirely (user feature
# decision). Previously the app lifespan started a background job runner
# under an env-gated flag to fire daily/weekly summary tasks; both that
# scheduling block and the distill module are gone. minReplicas=1 in Bicep
# is now justified by cold-start avoidance only (no background-job
# dependency).
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Cortex Second Brain API",
    description="Voice-first personal second brain API",
    version="1.0.0",
)

# Attach slowapi limiter to the app state so the middleware can find it.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CSP (Round 20 / PR delta) ---
# Lock all backend responses to default-src 'none'; frame-ancestors 'none'.
# Backend serves only JSON — no scripts, no embeds, no frames. This closes
# the XSS surface flagged in DECISIONS § 22v (refresh token in localStorage).
from app.middleware.csp import StrictCspMiddleware  # noqa: E402
app.add_middleware(StrictCspMiddleware)


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
from app.api.notes import router as notes_router, ai_router
from app.api.upload import router as upload_router   # B6 — dedicated upload module
from app.api.voice import router as voice_router
from app.api.search import router as search_router
from app.api.tags import router as tags_router       # B6 — dedicated tags module
from app.api.sync import router as sync_router
from app.api.dictionary import router as dictionary_router  # US-7 — personal dictionary
from app.api.insights import ai_router as ai_generate_router, insights_router  # US-6 — insights (daily/weekly summaries removed 2026-05-06)
from app.api.ai_answer import router as ai_answer_router  # P4 PR 4.1 — RAG /api/ai/answer
from app.api.export import router as export_router               # US-6 — export
from app.api.shadow_reader import router as shadow_reader_router  # US-8 — shadow reader
from app.api.users import router as users_router                  # US-8 — user settings
from app.api.import_url import router as import_url_router        # P5 PR 5.2 — URL import
from app.api.clip_token import router as clip_token_router        # P5 PR 5.5 — extension clip token
from app.api.note_links import router as note_links_router        # P6 PR 6.1 — backlinks API

app.include_router(auth_router,           prefix="/api/auth",          tags=["auth"])
app.include_router(notes_router,          prefix="/api/notes",         tags=["notes"])
app.include_router(ai_router,             prefix="/api/ai",            tags=["ai"])
app.include_router(ai_generate_router,    prefix="/api/ai",            tags=["ai"])
app.include_router(ai_answer_router,      prefix="/api/ai",            tags=["ai"])
app.include_router(upload_router,         prefix="/api",               tags=["upload"])
app.include_router(voice_router,          prefix="/api/voice",         tags=["voice"])
app.include_router(search_router,         prefix="/api/search",        tags=["search"])
app.include_router(tags_router,           prefix="/api/tags",          tags=["tags"])
app.include_router(sync_router,           prefix="/api/sync",          tags=["sync"])
app.include_router(dictionary_router,     prefix="/api/dictionary",    tags=["dictionary"])
app.include_router(insights_router,       prefix="/api/insights",      tags=["insights"])
app.include_router(export_router,         prefix="/api",               tags=["export"])
app.include_router(shadow_reader_router,  prefix="/api/notes",         tags=["shadow_reader"])
app.include_router(users_router,          prefix="/api/users",         tags=["users"])
app.include_router(import_url_router,     prefix="/api/import",        tags=["import"])
app.include_router(clip_token_router,     prefix="/api/auth",          tags=["auth"])
app.include_router(note_links_router,     prefix="/api/notes",         tags=["note_links"])

# --- Observability (Round 20 / PR alpha) ---
# Initialize Azure Monitor / Application Insights tracing. No-ops silently if
# APPLICATIONINSIGHTS_CONNECTION_STRING is unset (local dev, tests).
from app.observability.tracing import init_tracing  # noqa: E402

init_tracing(app)
