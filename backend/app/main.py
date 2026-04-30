"""
FastAPI application entry point.
"""
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
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
# Application lifespan (APScheduler nightly distill — B14)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start APScheduler background scheduler at startup so the nightly distill
    cron job fires even with minReplicas=1 (no scale-to-zero).
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler()

        # Nightly distill at 23:59 local time (single-user MVP — UTC approximate)
        try:
            from app.pipeline.distill import run_daily_distill, run_weekly_distill
            scheduler.add_job(run_daily_distill, "cron", hour=23, minute=59, id="daily_distill")
            scheduler.add_job(
                run_weekly_distill, "cron", day_of_week="sun", hour=23, minute=59, id="weekly_distill"
            )
        except ImportError:
            # distill module not yet implemented — skip gracefully
            pass

        # QA-04 recovery sweep: retry notes stuck in 'answer_pending' for > 1 minute.
        try:
            from app.pipeline.shadow_reader import retry_stale_answer_pending
            scheduler.add_job(
                retry_stale_answer_pending,
                "interval",
                minutes=2,
                id="answer_pending_sweep",
            )
        except (ImportError, AttributeError):
            # Shadow reader not yet available — skip gracefully
            pass

        scheduler.start()
        app.state.scheduler = scheduler
        yield
        scheduler.shutdown(wait=False)
    except ImportError:
        # APScheduler not installed — skip gracefully (e.g. during unit-test runs)
        yield


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Cortex Second Brain API",
    description="Voice-first personal second brain API",
    version="1.0.0",
    lifespan=lifespan,
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
from app.api.insights import ai_summary_router, insights_router  # US-6 — insights
from app.api.export import router as export_router               # US-6 — export
from app.api.shadow_reader import router as shadow_reader_router  # US-8 — shadow reader
from app.api.users import router as users_router                  # US-8 — user settings

app.include_router(auth_router,           prefix="/api/auth",          tags=["auth"])
app.include_router(notes_router,          prefix="/api/notes",         tags=["notes"])
app.include_router(ai_router,             prefix="/api/ai",            tags=["ai"])
app.include_router(ai_summary_router,     prefix="/api/ai",            tags=["ai"])
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
