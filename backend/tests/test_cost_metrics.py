"""Tests for app.observability.cost_metrics (PR Round 20 / beta)."""
from __future__ import annotations

import logging
import sys
import types
from unittest.mock import MagicMock

import pytest

from app.observability import cost_metrics
from app.observability.cost_metrics import (
    PRICING_USD_PER_1M,
    _compute_cost,
    emit_llm_cost,
)


# ---------------------------------------------------------------------------
# _compute_cost
# ---------------------------------------------------------------------------


def test_compute_cost_gpt_4o_mini():
    # 1000 prompt tokens @ $0.15 / 1M = $0.00015
    # 500 completion tokens @ $0.60 / 1M = $0.00030
    # total = $0.00045
    cost = _compute_cost("gpt-4o-mini", 1000, 500)
    assert cost == pytest.approx(0.00045, rel=1e-9)


def test_compute_cost_text_embedding_3_small():
    # 5000 prompt tokens @ $0.02 / 1M = $0.0001
    cost = _compute_cost("text-embedding-3-small", 5000, 0)
    assert cost == pytest.approx(0.0001, rel=1e-9)


def test_compute_cost_unknown_model_returns_zero(caplog):
    with caplog.at_level(logging.WARNING, logger=cost_metrics.__name__):
        cost = _compute_cost("not-a-real-model", 1000, 500)
    assert cost == 0.0
    assert any(
        "unknown model" in rec.message and "not-a-real-model" in rec.message
        for rec in caplog.records
    )


def test_compute_cost_negative_token_counts_are_clamped():
    assert _compute_cost("gpt-4o-mini", -100, -50) == 0.0


def test_pricing_table_includes_required_models():
    # Document the contract — all three models the wire-up code uses.
    assert "gpt-4o-mini" in PRICING_USD_PER_1M
    assert "gpt-4o" in PRICING_USD_PER_1M
    assert "text-embedding-3-small" in PRICING_USD_PER_1M


# ---------------------------------------------------------------------------
# emit_llm_cost
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_llm_cost_no_op_without_otel(caplog, monkeypatch):
    """If `from opentelemetry import metrics` raises, the helper must
    swallow the exception and log only at DEBUG (never ERROR)."""

    # Force the import to fail by inserting a sentinel module that lacks
    # the `metrics` attribute.
    monkeypatch.setitem(sys.modules, "opentelemetry", types.ModuleType("opentelemetry"))
    monkeypatch.delitem(sys.modules, "opentelemetry.metrics", raising=False)

    with caplog.at_level(logging.DEBUG, logger=cost_metrics.__name__):
        await emit_llm_cost(
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=50,
            route="/api/ai/answer",
        )

    # No ERROR/WARNING records about the failure (warning about "unknown
    # model" is a separate codepath that this test doesn't trigger).
    assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)


@pytest.mark.asyncio
async def test_emit_llm_cost_emits_three_counters(monkeypatch):
    """Verify cost + prompt + completion counters all get an `add` call
    with the correct value and {model, route} attributes."""

    cost_counter = MagicMock(name="cost_counter")
    prompt_counter = MagicMock(name="prompt_counter")
    completion_counter = MagicMock(name="completion_counter")

    counters_by_name: dict[str, MagicMock] = {
        "cortex.rag.cost_usd_estimate": cost_counter,
        "cortex.rag.prompt_tokens": prompt_counter,
        "cortex.rag.completion_tokens": completion_counter,
    }

    def _create_counter(name, *args, **kwargs):
        return counters_by_name[name]

    fake_meter = MagicMock(name="meter")
    fake_meter.create_counter.side_effect = _create_counter

    fake_metrics_mod = types.ModuleType("opentelemetry.metrics")
    fake_metrics_mod.get_meter = MagicMock(return_value=fake_meter)
    fake_otel_mod = types.ModuleType("opentelemetry")
    fake_otel_mod.metrics = fake_metrics_mod

    monkeypatch.setitem(sys.modules, "opentelemetry", fake_otel_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.metrics", fake_metrics_mod)

    await emit_llm_cost(
        model="gpt-4o-mini",
        prompt_tokens=1000,
        completion_tokens=500,
        route="/api/ai/answer",
    )

    fake_metrics_mod.get_meter.assert_called_once_with("cortex.rag")

    expected_attrs = {"model": "gpt-4o-mini", "route": "/api/ai/answer"}
    cost_counter.add.assert_called_once()
    cost_args, cost_kwargs = cost_counter.add.call_args
    assert cost_args[0] == pytest.approx(0.00045, rel=1e-9)
    assert cost_kwargs.get("attributes") == expected_attrs

    prompt_counter.add.assert_called_once_with(1000, attributes=expected_attrs)
    completion_counter.add.assert_called_once_with(500, attributes=expected_attrs)


@pytest.mark.asyncio
async def test_emit_llm_cost_swallows_meter_failures(caplog, monkeypatch):
    """If the meter raises mid-emit, the helper must not propagate."""

    fake_meter = MagicMock()
    fake_meter.create_counter.side_effect = RuntimeError("otel boom")

    fake_metrics_mod = types.ModuleType("opentelemetry.metrics")
    fake_metrics_mod.get_meter = MagicMock(return_value=fake_meter)
    fake_otel_mod = types.ModuleType("opentelemetry")
    fake_otel_mod.metrics = fake_metrics_mod
    monkeypatch.setitem(sys.modules, "opentelemetry", fake_otel_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.metrics", fake_metrics_mod)

    with caplog.at_level(logging.DEBUG, logger=cost_metrics.__name__):
        await emit_llm_cost(
            model="gpt-4o-mini",
            prompt_tokens=10,
            completion_tokens=5,
            route="/api/ai/answer",
        )
    # No WARNING/ERROR — failure path is DEBUG-only.
    assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)
