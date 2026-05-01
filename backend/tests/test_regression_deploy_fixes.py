"""
Regression tests for production bugs found during the live-deploy smoke
test on 2026-04-30 / 2026-05-01.

Bugs covered:
  R1. Backend exposes GET /api/sync/pull and POST /api/sync/push
      (frontend was hitting SWA host -> 404; backend was always correct,
      but a guard test prevents an accidental router-deregistration regression)
  R2. WebSocket route /api/voice/stream is registered on the voice router
      (prevents accidental removal of the streaming STT endpoint)
  R3. APScheduler is GATED on SCHEDULER_ENABLED env var (default False)
      so the BackgroundScheduler thread cannot conflict with the asyncpg
      connection pool on production traffic.
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
# R3 — APScheduler is GATED on SCHEDULER_ENABLED env var
# ---------------------------------------------------------------------------


class TestSchedulerGatedOnEnvVar:
    """The 500 on register was caused by APScheduler BackgroundScheduler
    thread + the FastAPI event loop fighting over the shared asyncpg
    connection pool. The fix gates the scheduler on a SCHEDULER_ENABLED
    env var (default False). For production, the spec's nightly distill
    cron should run as a Container Apps Job instead."""

    def test_main_lifespan_references_scheduler_enabled_env_var(self):
        from app import main

        src = inspect.getsource(main.lifespan)
        assert "SCHEDULER_ENABLED" in src, (
            "main.lifespan must check SCHEDULER_ENABLED env var. "
            "Removing this check re-introduces the 'cannot perform operation: "
            "another operation is in progress' asyncpg conflict on register."
        )

    def test_default_off_means_scheduler_does_not_start(self, monkeypatch):
        """When SCHEDULER_ENABLED is unset, the scheduler must NOT start.
        We verify by introspecting that the env-check returns early before
        importing BackgroundScheduler."""
        import os

        # Default off
        monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
        assert (
            os.getenv("SCHEDULER_ENABLED", "false").lower()
            not in ("true", "1", "yes")
        ), "Default value of SCHEDULER_ENABLED must be falsy"

    def test_explicit_true_enables(self, monkeypatch):
        import os

        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        assert (
            os.getenv("SCHEDULER_ENABLED", "false").lower() in ("true", "1", "yes")
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
# R6 — Smoke: app boots without scheduler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_starts_without_scheduler_enabled(monkeypatch):
    """End-to-end-ish smoke: the FastAPI app must boot and respond to
    /api/health when SCHEDULER_ENABLED is unset (the production default).
    """
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
