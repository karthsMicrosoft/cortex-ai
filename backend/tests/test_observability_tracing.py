"""Tests for app.observability.tracing (Round 20 / PR alpha).

These tests exercise the no-op + idempotency + failure-handling paths of the
App Insights tracing helper. They deliberately avoid making any network calls
or requiring the optional ``azure-monitor-opentelemetry`` package to be
importable — the helper is designed to degrade gracefully in both cases.
"""

from __future__ import annotations

import builtins
import sys

import pytest

from app.observability import tracing


@pytest.fixture(autouse=True)
def _reset_tracing_state(monkeypatch):
    """Reset the module-level ``_initialized`` flag before each test and
    ensure the connection-string env var starts unset."""
    tracing._reset_for_tests()
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    yield
    tracing._reset_for_tests()


def test_init_tracing_no_op_without_connection_string():
    """With no connection string set, init_tracing must return False and
    must not raise — local dev and tests must not depend on Azure."""
    app = object()  # never touched on the no-op path
    assert tracing.init_tracing(app) is False


def test_init_tracing_no_op_with_empty_connection_string(monkeypatch):
    """A connection string of only whitespace must also be treated as unset."""
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "   ")
    app = object()
    assert tracing.init_tracing(app) is False


def test_init_tracing_idempotent(monkeypatch):
    """Once initialized, a second call must short-circuit to True without
    re-running the (potentially expensive) Azure Monitor configuration."""
    # Force the success path by flipping the module-level flag directly —
    # that exercises the idempotent fast-path without needing the real
    # azure-monitor-opentelemetry package installed in the test env.
    tracing._initialized = True
    app = object()
    assert tracing.init_tracing(app) is True
    assert tracing.init_tracing(app) is True


def test_init_tracing_handles_missing_package_gracefully(monkeypatch):
    """If the azure-monitor-opentelemetry package isn't installed (or any
    import inside the try-block raises), init_tracing must log + return
    False rather than propagate the exception."""
    monkeypatch.setenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "InstrumentationKey=00000000-0000-0000-0000-000000000000",
    )

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name.startswith("azure.monitor") or name.startswith(
            "opentelemetry.instrumentation.fastapi"
        ):
            raise ImportError(f"simulated missing package: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    # Make sure any already-cached modules don't satisfy the import.
    for mod_name in list(sys.modules):
        if mod_name.startswith("azure.monitor") or mod_name.startswith(
            "opentelemetry.instrumentation.fastapi"
        ):
            monkeypatch.delitem(sys.modules, mod_name, raising=False)

    app = object()
    assert tracing.init_tracing(app) is False


def test_init_tracing_handles_runtime_exception_gracefully(monkeypatch):
    """Any exception from configure_azure_monitor must be swallowed."""
    monkeypatch.setenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "InstrumentationKey=00000000-0000-0000-0000-000000000000",
    )

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "azure.monitor.opentelemetry":
            class _FakeMod:
                @staticmethod
                def configure_azure_monitor(**_kwargs):
                    raise RuntimeError("simulated Azure Monitor failure")

            return _FakeMod
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    app = object()
    assert tracing.init_tracing(app) is False


def test_add_user_id_hash_truncated_to_16_chars(monkeypatch):
    """The helper must set a 16-char SHA-256 hex prefix as a span attribute,
    not the raw user id."""
    captured: dict[str, str] = {}

    class _FakeSpan:
        def is_recording(self) -> bool:
            return True

        def set_attribute(self, key: str, value: str) -> None:
            captured[key] = value

    class _FakeTraceModule:
        @staticmethod
        def get_current_span() -> _FakeSpan:
            return _FakeSpan()

    # Inject a fake `opentelemetry.trace` module so the helper's local import
    # picks it up.
    monkeypatch.setitem(sys.modules, "opentelemetry", type(sys)("opentelemetry"))
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", _FakeTraceModule)

    tracing.add_user_id_hash_to_span("11111111-2222-3333-4444-555555555555")

    assert "cortex.user_id_hash" in captured
    digest = captured["cortex.user_id_hash"]
    assert len(digest) == 16
    # Hex chars only.
    int(digest, 16)


def test_add_user_id_hash_is_silent_when_no_recording_span(monkeypatch):
    """When there is no recording span, the helper must do nothing and not
    raise — telemetry must never break a request."""

    class _FakeSpan:
        def is_recording(self) -> bool:
            return False

        def set_attribute(self, key: str, value: str) -> None:  # pragma: no cover
            raise AssertionError("must not be called when not recording")

    class _FakeTraceModule:
        @staticmethod
        def get_current_span() -> _FakeSpan:
            return _FakeSpan()

    monkeypatch.setitem(sys.modules, "opentelemetry", type(sys)("opentelemetry"))
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", _FakeTraceModule)

    # Should not raise.
    tracing.add_user_id_hash_to_span("any-user")


def test_add_user_id_hash_swallows_exceptions(monkeypatch):
    """Exceptions inside the helper must be swallowed silently."""

    class _BoomTraceModule:
        @staticmethod
        def get_current_span():
            raise RuntimeError("boom")

    monkeypatch.setitem(sys.modules, "opentelemetry", type(sys)("opentelemetry"))
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", _BoomTraceModule)

    tracing.add_user_id_hash_to_span("any-user")  # must not raise
