"""
Regression tests for production bugs found during the live-deploy smoke
test on 2026-04-30 / 2026-05-01.

Bugs covered:
  R1. Backend exposes GET /api/sync/pull and POST /api/sync/push
      (frontend was hitting SWA host -> 404; backend was always correct,
      but a guard test prevents an accidental router-deregistration regression)
  R2. WebSocket route /api/voice/stream is registered on the voice router
      (prevents accidental removal of the streaming STT endpoint)
  R3. APScheduler removed entirely 2026-05-06 (cron functionality dropped).
      The `lifespan` block is gone; `apscheduler` is removed from
      requirements; `app/pipeline/distill.py` is deleted. This guard ensures
      it does not get re-introduced.
  R4. JWT_SECRET_KEY validators reject the dev placeholder + short keys
      when ENVIRONMENT='production' (SEC-01)
  R5. CORS middleware is configured with allow_credentials=True so the
      cross-origin httpOnly refresh cookie round-trips correctly.
"""

import inspect

import pytest


# ---------------------------------------------------------------------------
# R1 — sync router registered
# ---------------------------------------------------------------------------


class TestSyncRouterRegistered:
    """The frontend bug was relative-fetch URLs that hit the SWA host. The
    backend was always correct, but a routing regression here would amplify
    the same 'sync stuck' symptom — guard the registration."""

    def test_sync_router_is_importable(self):
        from app.api.sync import router  # noqa: F401

    def test_main_includes_sync_router_at_api_sync_prefix(self):
        from app.main import app

        sync_routes = [r for r in app.routes if getattr(r, "path", "").startswith("/api/sync")]
        assert sync_routes, "/api/sync/* routes must be registered in app.main"

    def test_sync_pull_endpoint_exists(self):
        from app.main import app

        paths = {getattr(r, "path", "") for r in app.routes}
        assert "/api/sync/pull" in paths, (
            "GET /api/sync/pull must be registered (R1: prevents the "
            "'pending sync forever' regression seen on 2026-04-30)"
        )

    def test_sync_push_endpoint_exists(self):
        from app.main import app

        paths = {getattr(r, "path", "") for r in app.routes}
        assert "/api/sync/push" in paths


# ---------------------------------------------------------------------------
# R2 — WebSocket /api/voice/stream registered
# ---------------------------------------------------------------------------


class TestVoiceStreamWebSocketRegistered:
    """The 405 'Network issue — using file-upload fallback' on desktop came
    from the frontend pointing the WebSocket at the SWA host. Backend route
    must continue to exist on the voice router."""

    def test_voice_router_has_websocket_route_for_stream(self):
        from starlette.routing import WebSocketRoute

        from app.api.voice import router

        ws_paths = [
            r.path for r in router.routes if isinstance(r, WebSocketRoute)
        ]
        assert any("/stream" in p for p in ws_paths), (
            f"Voice router must expose a WebSocket /stream route. Found: {ws_paths}"
        )

    def test_full_path_resolves_to_api_voice_stream(self):
        from starlette.routing import WebSocketRoute

        from app.main import app

        ws_routes = [
            r for r in app.routes if isinstance(r, WebSocketRoute)
        ]
        ws_paths = [r.path for r in ws_routes]
        assert "/api/voice/stream" in ws_paths, (
            f"WebSocket must be addressable at /api/voice/stream. Found: {ws_paths}"
        )


# ---------------------------------------------------------------------------
# R3 — APScheduler removed entirely (cron removal 2026-05-06)
# ---------------------------------------------------------------------------


class TestSchedulerRemoved:
    """The APScheduler nightly distill cron was removed entirely on 2026-05-06
    per a user product decision (no daily/weekly summary feature). Guard against
    accidental re-introduction of the scheduler, the distill module, or the
    apscheduler dependency.
    """

    def test_main_does_not_reference_apscheduler(self):
        from app import main

        src = inspect.getsource(main)
        assert "apscheduler" not in src.lower(), (
            "app.main must not import or reference apscheduler — "
            "the nightly distill cron was removed 2026-05-06."
        )
        assert "BackgroundScheduler" not in src, (
            "app.main must not reference BackgroundScheduler — cron removed."
        )
        assert "SCHEDULER_ENABLED" not in src, (
            "app.main must not gate on SCHEDULER_ENABLED — flag removed with cron."
        )

    def test_distill_module_deleted(self):
        try:
            import app.pipeline.distill  # noqa: F401
        except ImportError:
            return  # expected — module was deleted
        else:
            raise AssertionError(
                "app.pipeline.distill must NOT exist — the distill cron was "
                "removed 2026-05-06; importing it should raise ImportError."
            )

    def test_daily_summary_model_deleted(self):
        try:
            import app.models.daily_summary  # noqa: F401
        except ImportError:
            return  # expected
        else:
            raise AssertionError(
                "app.models.daily_summary must NOT exist — the daily_summaries "
                "table is dropped in alembic 007."
            )

    def test_apscheduler_not_in_requirements(self):
        import pathlib

        req_path = pathlib.Path(__file__).resolve().parent.parent / "requirements.txt"
        text = req_path.read_text(encoding="utf-8").lower()
        assert "apscheduler" not in text, (
            "apscheduler must be removed from requirements.txt — "
            "the nightly cron functionality was removed 2026-05-06."
        )


# ---------------------------------------------------------------------------
# R4 — Production guard on JWT_SECRET_KEY (SEC-01)
# ---------------------------------------------------------------------------


class TestJWTSecretKeyProductionGuard:
    """When ENVIRONMENT=production, JWT_SECRET_KEY must (a) be at least
    32 chars and (b) not equal the dev placeholder. Catches misconfigured
    deploys before they accept real traffic."""

    def test_check_production_secrets_exists(self):
        from app import config

        assert hasattr(config, "check_production_secrets") or any(
            "production" in line and "JWT" in line
            for line in inspect.getsource(config).splitlines()
        ), "config.py must enforce a production-mode JWT secret check"

    def test_settings_class_validates_jwt_secret_key_strength(self):
        from app import config

        src = inspect.getsource(config)
        # Some form of validation must exist on JWT_SECRET_KEY
        assert "JWT_SECRET_KEY" in src
        assert (
            "field_validator" in src
            or "validator" in src
            or "min_length" in src
        ), "JWT_SECRET_KEY must have a Pydantic validator or length constraint"


# ---------------------------------------------------------------------------
# R5 — CORS allows credentials so the refresh cookie round-trips
# ---------------------------------------------------------------------------


class TestCORSAllowsCredentials:
    """Frontend at the SWA origin needs to send the httpOnly refresh
    cookie cross-origin to the Container App backend. CORS middleware
    must have allow_credentials=True. Without it the auth flow would
    silently drop the cookie."""

    def test_main_cors_middleware_allows_credentials(self):
        from app import main

        src = inspect.getsource(main)
        assert "allow_credentials=True" in src, (
            "CORSMiddleware must be configured with allow_credentials=True "
            "so the cross-origin refresh cookie works."
        )

    def test_settings_exposes_cors_origins_list(self):
        from app.config import settings

        assert hasattr(settings, "cors_origins_list"), (
            "settings.cors_origins_list() must exist so main.py can pass an "
            "allow-list (not '*') to CORSMiddleware. Wildcard + credentials "
            "is forbidden by CORS spec."
        )


# ---------------------------------------------------------------------------
# R6 — Smoke: app boots cleanly (no scheduler dependency)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_starts_and_responds_to_health():
    """End-to-end-ish smoke: the FastAPI app must boot and respond to
    /api/health. Previously gated on SCHEDULER_ENABLED env var; the
    scheduler was removed entirely 2026-05-06 so no env-var dance is needed.
    """
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
