"""Application Insights tracing setup for the FastAPI app.

Round 20 / PR alpha. Uses ``azure-monitor-opentelemetry`` for autoinstrumentation
of FastAPI requests + httpx outgoing calls + asyncpg DB calls.

If the ``APPLICATIONINSIGHTS_CONNECTION_STRING`` env var is missing or empty,
this module silently no-ops so local development + tests don't depend on Azure.

Operational note
----------------
The connection string is sourced from the environment at startup. In production
the Bicep / Container Apps deployment is expected to mount it as
``APPLICATIONINSIGHTS_CONNECTION_STRING`` (already wired into the
``cortexks-ai`` App Insights component bootstrapped in Round 13). If you don't
see traces in App Insights, check that the Container App has this env var /
secret set — it is intentionally absent from ``app.config.Settings`` because
the Azure Monitor SDK reads it directly from ``os.environ``.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_initialized = False


def init_tracing(app) -> bool:
    """Initialize OpenTelemetry + Azure Monitor exporter against the FastAPI app.

    Returns
    -------
    bool
        ``True`` if tracing was successfully initialized (or was already
        initialized on a prior call); ``False`` if skipped because no
        connection string was configured, or because the optional Azure
        Monitor / OpenTelemetry packages are not installed.
    """
    global _initialized
    if _initialized:
        return True

    conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if not conn_str:
        logger.info(
            "App Insights connection string not set — tracing disabled"
        )
        return False

    try:
        # Local imports so the package becomes a true optional dependency:
        # if azure-monitor-opentelemetry isn't installed (e.g. in some test
        # environments) we degrade gracefully instead of crashing the app.
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        configure_azure_monitor(connection_string=conn_str)
        FastAPIInstrumentor.instrument_app(app)
        _initialized = True
        logger.info("App Insights tracing initialized")
        return True
    except Exception:  # noqa: BLE001 — telemetry must never crash the app
        logger.exception("Failed to initialize App Insights tracing")
        return False


def add_user_id_hash_to_span(user_id) -> None:
    """Enrich the current OpenTelemetry span with a hashed user id.

    The raw user id (a UUID) is never written to telemetry — we hash with
    SHA-256 and truncate to 16 hex chars so individual users can be correlated
    across spans without leaking identifiers.

    All exceptions are swallowed: telemetry must never break a request.
    """
    try:
        import hashlib

        from opentelemetry import trace

        span = trace.get_current_span()
        if span is None or not span.is_recording():
            return
        digest = hashlib.sha256(str(user_id).encode()).hexdigest()[:16]
        span.set_attribute("cortex.user_id_hash", digest)
    except Exception:  # noqa: BLE001 — never let telemetry break the request
        pass


def _reset_for_tests() -> None:
    """Test-only hook to reset the module-level init flag."""
    global _initialized
    _initialized = False
